"""
面试题生成服务 — RAG 增强的个性化出题。

流程:
    1. 根据岗位与画像，从题库中混合检索相关题目
    2. 将检索到的参考内容注入 Prompt
    3. 调用 DeepSeek 生成个性化面试题（含 reference_answer + key_points）
    4. 将题目持久化到 InterviewQuestion
"""

import json
import re
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_client import LLMClient
from app.models.question import InterviewQuestion
from app.prompts import PromptLoader, get_prompt_loader
from app.rag.retriever import HybridRetriever

logger = structlog.get_logger(__name__)


class QuestionGenerateError(Exception):
    """题目生成失败。"""


class QuestionGenerator:
    """
    面试题生成器 — RAG + LLM 生成个性化面试题目。

    关键设计:
        - 每道题必须包含 reference_answer 和 key_points
        - 这两个字段是后续评分稳定性的核心保证
    """

    # 默认题型分布
    DEFAULT_TYPE_DISTRIBUTION = {
        "technical": 0.4,
        "coding": 0.15,
        "system_design": 0.15,
        "behavioral": 0.2,
        "scenario": 0.1,
    }

    def __init__(
        self,
        llm_client: LLMClient,
        retriever: HybridRetriever,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        self.llm = llm_client
        self.retriever = retriever
        self.prompts = prompt_loader or get_prompt_loader()

    async def generate(
        self,
        session: AsyncSession,
        *,
        interview_id: str,
        job_title: str,
        job_description: str,
        profile: dict,
        question_count: int = 5,
        difficulty: str = "medium",
        question_types: Optional[list[str]] = None,
    ) -> list[InterviewQuestion]:
        """
        生成整场面试的题目列表。

        Args:
            session:           数据库会话
            interview_id:      面试会话 ID
            job_title:         目标岗位
            job_description:   岗位描述
            profile:           候选人画像
            question_count:    题目数量
            difficulty:        难度
            question_types:    题型列表（默认按分布生成）

        Returns:
            InterviewQuestion 列表（已 flush 到 DB）
        """
        # 1. 计算各类型题目数量
        if question_types is None:
            question_types = list(self.DEFAULT_TYPE_DISTRIBUTION.keys())
        type_counts = self._distribute_question_types(question_count, question_types)

        # 2. RAG 检索：从题库中获取相关参考内容
        all_rag_context: list[dict] = []
        for qtype in type_counts:
            if type_counts[qtype] > 0:
                results = await self.retriever.retrieve(
                    query=f"{job_title} {job_description} {qtype}",
                    top_k=max(3, type_counts[qtype] * 2),
                    question_type=qtype,
                    difficulty=difficulty,
                )
                all_rag_context.extend([
                    {"content": r.content, "metadata": r.metadata} for r in results
                ])

        # 3. 调用 DeepSeek 生成题目
        try:
            generated = await self._generate_with_llm(
                job_title=job_title,
                job_description=job_description,
                profile=profile,
                question_count=question_count,
                difficulty=difficulty,
                type_counts=type_counts,
                rag_context=all_rag_context,
            )
        except Exception as exc:
            logger.error("question_generation_failed", error=str(exc))
            raise QuestionGenerateError(f"题目生成失败: {exc}") from exc

        # 4. 持久化
        questions: list[InterviewQuestion] = []
        for i, q in enumerate(generated):
            question = InterviewQuestion(
                session_id=interview_id,
                content=q["content"],
                question_type=q.get("question_type", "technical"),
                difficulty=difficulty,
                order_index=i + 1,
                reference_answer=q.get("reference_answer", ""),
                key_points=q.get("key_points", []),
                source_chunks=q.get("source_chunks", []),
            )
            session.add(question)
            questions.append(question)

        await session.flush()
        logger.info(
            "questions_generated",
            interview_id=interview_id,
            count=len(questions),
            types=list(type_counts.keys()),
        )

        return questions

    async def _generate_with_llm(
        self,
        job_title: str,
        job_description: str,
        profile: dict,
        question_count: int,
        difficulty: str,
        type_counts: dict,
        rag_context: list[dict],
    ) -> list[dict]:
        """使用 DeepSeek 生成题目 — RAG 内容注入 Prompt。"""
        # 构建 RAG 上下文文本（截断）
        rag_texts: list[str] = []
        total_chars = 0
        for ctx in rag_context[:20]:  # 最多 20 条参考
            chunk = f"- {ctx['content'][:300]}"
            total_chars += len(chunk)
            if total_chars > 4000:
                break
            rag_texts.append(chunk)

        profile_summary = self._format_profile(profile)

        prompt = (
            f"## 岗位信息\n"
            f"- 岗位: {job_title}\n"
            f"- 描述: {job_description}\n"
            f"- 难度: {difficulty}\n"
            f"- 题目数量: {question_count}\n\n"
            f"## 题型分布\n"
            + "\n".join(f"- {t}: {c} 题" for t, c in type_counts.items() if c > 0)
            + f"\n\n## 候选人画像\n{profile_summary}\n\n"
            f"## 参考题库 (RAG 检索结果)\n"
            + "\n".join(rag_texts) if rag_texts else "(无参考资料)"
            + "\n\n请生成题目。"
        )

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self._generation_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,  # 较高温度保证题目多样性
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())

        result = json.loads(content)
        return result.get("questions", [])

    def _generation_system_prompt(self) -> str:
        return (
            "你是一位资深技术面试官。请根据岗位需求、候选人画像和参考题库，"
            "生成个性化的面试题目。\n\n"
            "## 要求\n"
            '- 以 JSON 格式输出: {"questions": [...]}\n'
            "每道题目包含:\n"
            "  - content: 题目内容\n"
            "  - question_type: 题型 (technical/coding/system_design/behavioral/scenario)\n"
            "  - reference_answer: 参考答案（详细、准确，用于后续评分基准）\n"
            "  - key_points: 关键得分点列表（评分时逐一检查）\n"
            "  - source_chunks: 引用的 RAG 内容片段索引\n\n"
            "## 出题原则\n"
            "1. 题目要有区分度，能测试候选人的真实水平\n"
            "2. reference_answer 必须专业准确，因为它是评分的黄金标准\n"
            "3. key_points 要具体可量化，每条代表一个可明确判断的得分点\n"
            "4. 避免过于偏门或仅限于特定公司的知识点\n"
            "5. 针对候选人技能弱点适当增加考查深度"
        )

    def _format_profile(self, profile: dict) -> str:
        """格式化候选画像为 Prompt 可读文本（新格式）。"""
        # 新格式：core_skills 带评估
        core_skills = profile.get("core_skills", [])
        if core_skills:
            skill_lines = []
            for s in core_skills[:15]:
                skill_lines.append(f"- {s['skill']}: {s['level']}, ~{s.get('years','?')}年 ({s.get('evidence','')})")
            skill_str = "\n".join(skill_lines)
        else:
            skills = profile.get("skills", [])
            skill_str = ", ".join(skills[:15])

        target_role = profile.get("target_role", "未知")

        lines = [
            f"目标岗位: {target_role}",
            f"候选级别: {profile.get('target_level', 'mid')}",
            f"核心技能:\n{skill_str}",
        ]

        # 加入优势和风险
        strengths = profile.get("strengths", [])
        risks = profile.get("risk_areas", [])
        if strengths:
            lines.append(f"优势: {'; '.join(strengths[:5])}")
        if risks:
            lines.append(f"需验证: {'; '.join(risks[:5])}")

        edu = profile.get('education_summary', {})
        if edu:
            schools = edu.get('schools', edu.get('top_schools', []))
            if schools:
                lines.append(f"教育: {', '.join(schools[:3])}")

        return "\n".join(lines)

    def _distribute_question_types(
        self, count: int, types: list[str]
    ) -> dict[str, int]:
        """
        按默认分布分配各题型数量。

        Returns:
            {"technical": 2, "behavioral": 1, "system_design": 1, ...}
        """
        result: dict[str, int] = {t: 0 for t in types}
        remaining = count

        # 按默认比例分配
        type_list = list(types)
        for i in range(count):
            # 选择当前占比最低的类型
            min_type = min(type_list, key=lambda t: result[t])
            result[min_type] += 1

        return result
