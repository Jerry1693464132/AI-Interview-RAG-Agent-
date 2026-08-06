"""
候选人画像提取服务 — 使用 DeepSeek 深度分析简历，输出面试指导报告。

输出结构:
    - 核心技能评估（含熟练度和实战年限）
    - 候选人优势领域
    - 潜在风险/短板（需要面试验证的点）
    - 建议考查方向与策略
"""

import json
import re
from typing import Optional

import structlog

from app.core.llm_client import LLMClient

logger = structlog.get_logger(__name__)


class ProfileExtractError(Exception):
    """画像提取失败。"""


class ProfileExtractor:
    """候选人画像提取器 — LLM 深度分析模式。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def extract(self, structured_data: dict) -> dict:
        """
        提取候选人画像。

        Args:
            structured_data: 简历解析结果（来自 ResumeParser）

        Returns:
            深度画像数据，可直接用于前端展示和出题 Prompt
        """
        personal = structured_data.get("personal_info", {})

        # 调用 DeepSeek 做深度分析
        try:
            analysis = await self._deep_analyze(structured_data)
        except Exception as exc:
            logger.warning("profile_deep_analysis_failed", error=str(exc))
            analysis = {}

        return {
            "name": personal.get("name"),
            "email": personal.get("email"),
            "phone": personal.get("phone"),
            # 核心技能评估
            "core_skills": analysis.get("core_skills", []),
            # 优势
            "strengths": analysis.get("strengths", []),
            # 风险点
            "risk_areas": analysis.get("risk_areas", []),
            # LLM 生成的结构化分析
            "analysis_summary": analysis.get("analysis_summary", ""),
            "interview_strategy": analysis.get("interview_strategy", ""),
            # 兼容旧字段
            "skills": analysis.get("skills", structured_data.get("skills", [])),
            "target_role": analysis.get("target_role", ""),
            "target_level": analysis.get("target_level", ""),
            "education_summary": self._summarize_education(structured_data.get("education", [])),
            "work_summary": self._summarize_work(structured_data.get("experience", [])),
        }

    async def _deep_analyze(self, data: dict) -> dict:
        """使用 DeepSeek 对简历做深度面试分析。"""
        prompt = self._build_analysis_prompt(data)

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("analysis_json_parse_failed")
            return {}

    def _build_analysis_prompt(self, data: dict) -> str:
        skills = data.get("skills", [])
        experience = data.get("experience", [])
        education = data.get("education", [])
        projects = data.get("projects", [])

        exp_lines = []
        for e in experience:
            company = e.get("company", e.get("公司", ""))
            title = e.get("title", e.get("职位", ""))
            desc = e.get("description", e.get("工作描述", e.get("描述", "")))
            skills_used = e.get("skills_used", e.get("使用技能", []))
            exp_lines.append(
                f"- {title} @ {company}\n  {desc[:300]}"
                + (f"\n  使用技能: {', '.join(skills_used)}" if skills_used else "")
            )

        edu_lines = []
        for ed in education:
            school = ed.get("school", ed.get("学校", ""))
            degree = ed.get("degree", ed.get("学位", ""))
            major = ed.get("major", ed.get("专业", ""))
            edu_lines.append(f"- {school}, {degree}, {major}")

        return (
            f"## 候选人技能\n{', '.join(skills) if skills else '未提取到'}\n\n"
            f"## 工作经历\n" + "\n".join(exp_lines) + "\n\n"
            + (f"## 项目经验\n" + "\n".join(
                f"- {p.get('name', p.get('项目名', ''))}: {p.get('description', p.get('描述', ''))}"[:200]
                for p in projects
            ) + "\n\n" if projects else "")
            + (f"## 教育背景\n" + "\n".join(edu_lines) + "\n\n" if edu_lines else "")
            + "请基于以上信息进行深度分析。"
        )

    @staticmethod
    def _summarize_education(education: list[dict]) -> dict:
        schools = []
        degrees = []
        for e in education:
            s = e.get("school", e.get("学校", ""))
            d = e.get("degree", e.get("学位", ""))
            if s: schools.append(s)
            if d: degrees.append(d)
        degree_rank = {"博士": 4, "硕士": 3, "本科": 2, "大专": 1, "PhD": 4, "Master": 3, "Bachelor": 2}
        highest = max(degrees, key=lambda x: degree_rank.get(x, 0)) if degrees else None
        return {
            "highest_degree": highest,
            "schools": schools,
            "total_entries": len(education),
        }

    @staticmethod
    def _summarize_work(experience: list[dict]) -> dict:
        titles = [e.get("title", e.get("职位", "")) for e in experience if e.get("title", e.get("职位", ""))]
        companies = [e.get("company", e.get("公司", "")) for e in experience if e.get("company", e.get("公司", ""))]
        return {
            "total_companies": len(companies),
            "latest_title": titles[0] if titles else "",
            "recent_companies": companies[:3],
        }


_ANALYSIS_SYSTEM_PROMPT = """你是一位资深技术面试官和招聘顾问，拥有 10 年以上技术面试经验。
请基于候选人简历，从面试官视角进行深度分析，输出结构化 JSON。

## 输出格式（严格遵循）
{
  "skills": ["技能列表"],
  "core_skills": [
    {"skill": "Python", "level": "expert", "years": 6, "evidence": "6年Python后端开发，主导过高并发系统设计"},
    {"skill": "Go", "level": "advanced", "years": 3, "evidence": "参与过性能优化项目"}
  ],
  "strengths": [
    "高并发系统架构设计经验丰富",
    "有微服务从 0 到 1 经验"
  ],
  "risk_areas": [
    "声称精通 K8s 但经历中只有容器化部署，编排能力需验证",
    "缺少消息队列相关经验，分布式事务可能有盲区"
  ],
  "analysis_summary": "2-4 句话的综合评估，概括候选人整体水平、核心优势和主要疑问点。",
  "interview_strategy": "针对该候选人的面试策略建议，包括应该重点考察什么、可以略过什么。",
  "target_role": "最适合的目标岗位（如「高级后端工程师」）",
  "target_level": "junior/mid/senior/staff"
}

## 技能等级标准
- expert: 能主导架构设计，有深度优化经验，是该领域的 go-to person
- advanced: 深入理解原理，能独立技术选型和方案设计
- intermediate: 能独立完成日常开发任务
- novice: 了解基础概念，需要指导

## 分析要求
- 每个评估必须有证据支撑（引用简历中的具体内容）
- risk_areas 要具体到可以设计面试题验证的程度
- 不要编造信息，不确定的地方要标注
- 用中文输出（技术术语可用英文）"""
