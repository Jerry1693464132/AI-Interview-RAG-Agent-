"""
面试题生成服务 — RAG 增强的个性化出题。

流程:
    1. 根据岗位与画像，从题库中混合检索相关题目
    2. 将检索到的参考内容注入 Prompt
    3. 调用 DeepSeek 生成个性化面试题（含 reference_answer + key_points）
    4. 将题目持久化到 InterviewQuestion
"""

import json
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_client import LLMClient
from app.models.question import InterviewQuestion
from app.prompts import clean_json_response
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
        "knowledge": 0.5,   # 知识深度：原理、机制、底层实现
        "practice": 0.35,   # 工程实践：设计、排查、架构决策
        "soft_skill": 0.15, # 软技能：沟通、协作、学习
    }

    def __init__(self, llm_client: LLMClient, retriever: HybridRetriever) -> None:
        self.llm = llm_client
        self.retriever = retriever

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

        # 2. RAG 检索：优先从题库取，不够的 LLM 补
        SIM_THRESHOLD = 0.014  # 高于此值才是真正相关，低于则不如让LLM生成
        bank_questions: list[dict] = []
        all_rag_context: list[dict] = []
        for qtype, needed in type_counts.items():
            if needed <= 0:
                continue
            results = await self.retriever.retrieve(
                query=f"{job_title} {job_description} {qtype}",
                top_k=needed * 3, question_type=qtype, difficulty=difficulty,
                min_similarity=SIM_THRESHOLD,
            )
            taken = 0
            seen_contents = {q["content"] for q in bank_questions}
            for r in results:
                if r.content in seen_contents:
                    all_rag_context.append({"content": r.content, "metadata": r.metadata})
                    continue
                if r.score < SIM_THRESHOLD or taken >= needed:
                    all_rag_context.append({"content": r.content, "metadata": r.metadata})
                    continue
                bank_questions.append({
                    "content": r.content, "question_type": qtype,
                    "reference_answer": r.metadata.get("reference_answer", ""),
                    "key_points": r.metadata.get("key_points", []),
                    "source": "bank", "bank_score": r.score,
                })
                seen_contents.add(r.content)
                taken += 1
            # 剩余的该类型需要 LLM 生成
            type_counts[qtype] = needed - taken

        logger.info("question_source", from_bank=len(bank_questions), to_generate=sum(type_counts.values()))

        # 3. 不够的用 LLM 补
        questions: list[InterviewQuestion] = []
        idx = 0
        for q in bank_questions:
            idx += 1
            question = InterviewQuestion(
                session_id=interview_id, content=q["content"],
                question_type=q["question_type"], difficulty=difficulty,
                order_index=idx, reference_answer=q["reference_answer"],
                key_points=q["key_points"], source_chunks=[q["source"]],
            )
            session.add(question); questions.append(question)

        if sum(type_counts.values()) > 0:
            try:
                generated = await self._generate_with_llm(
                    job_title=job_title, job_description=job_description,
                    profile=profile, question_count=sum(type_counts.values()),
                    difficulty=difficulty, type_counts=type_counts,
                    rag_context=all_rag_context,
                )
            except Exception as exc:
                logger.error("llm_generation_failed", error=str(exc))
                generated = []
            for q in generated:
                idx += 1
                question = InterviewQuestion(
                    session_id=interview_id, content=q["content"],
                    question_type=q.get("question_type", "technical"),
                    difficulty=difficulty, order_index=idx,
                    reference_answer=q.get("reference_answer", ""),
                    key_points=q.get("key_points", []),
                    source_chunks=["llm"],
                )
                session.add(question); questions.append(question)

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
        """使用 DeepSeek 生成题目 — 智能处理 RAG 上下文。"""
        # 构建 RAG 上下文（仅保留高相关度结果）
        rag_texts: list[str] = []
        if rag_context:
            total_chars = 0
            for ctx in rag_context[:10]:
                chunk = f"- {ctx['content'][:300]}"
                total_chars += len(chunk)
                if total_chars > 3000:
                    break
                rag_texts.append(chunk)

        profile_summary = self._format_profile(profile)

        # 根据有无 RAG 结果选择不同的 Prompt 策略
        if rag_texts:
            rag_section = (
                "## 参考题库（仅供参考，可能不完全匹配当前岗位）\n"
                "以下是从题库检索到的题目。请严格判断：如果题目内容和当前岗位无关，\n"
                "务必忽略它们，完全基于岗位描述原创出题。如果有关联，可以借鉴深度和格式，\n"
                "但内容必须针对当前岗位重新设计，严禁照抄。\n\n"
                + "\n".join(rag_texts)
            )
        else:
            rag_section = (
                "## 重要提示\n题库中没有找到高度相关的参考题目。"
                "请完全基于岗位描述和候选人画像，原创生成题目。"
                "题目要切合岗位的实际工作场景和技术栈。"
            )

        prompt = (
            f"## 岗位信息\n- 岗位: {job_title}\n- 描述: {job_description}\n"
            f"- 难度: {difficulty}\n- 题目数量: {question_count}\n\n"
            f"## 题型分布\n"
            + "\n".join(f"- {t}: {c} 题" for t, c in type_counts.items() if c > 0)
            + f"\n\n## 候选人画像\n{profile_summary}\n\n{rag_section}\n\n请生成题目。"
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
        result = json.loads(clean_json_response(content))
        return result.get("questions", [])

    def _generation_system_prompt(self) -> str:
        return (
            "你是一位资深技术面试官。请根据岗位需求、候选人画像生成个性化面试题。\n\n"
            "## 要求\n"
            '- 以 JSON 格式输出: {"questions": [...]}\n'
            "每道题目包含:\n"
            "  - content: 题目内容\n"
            "  - question_type: 题型 (knowledge/practice/soft_skill)\n"
            "  - reference_answer: 参考答案（详细、准确）\n"
            "  - key_points: 关键考查点列表（3-7 个具体可量化的点）\n"
            "  - source_chunks: 引用的 RAG 内容片段索引（如无则为空数组）\n\n"
            "## 出题原则\n"
            "1. 如果题库内容与岗位不相关，忽略题库，基于岗位需求完全原创出题\n"
            "2. 题目要有区分度，能测试候选人的真实水平\n"
            "3. reference_answer 必须专业准确\n"
            "4. key_points 要具体可量化\n"
            "5. 避免偏门或仅限特定公司的知识点\n"
            "6. 如果 candidates 画像中有标注的弱点，优先考查那些领域"
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
