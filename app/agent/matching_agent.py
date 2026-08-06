"""
岗位匹配 Agent — 基于 LangChain Tool Calling Agent。

核心流程:
    1. 解析候选人画像 → 获取技能、经验、目标岗位
    2. 调用 match_job_template 工具 → 匹配标准岗位模板
    3. 调用 analyze_skill_gap 工具 → 技能差距分析
    4. 调用 search_question_bank 工具 → 检索相关题库
    5. Agent 综合所有工具结果 → 输出匹配分析报告

用法:
    from app.agent.matching_agent import JobMatchingAgent

    agent = JobMatchingAgent(llm_client, retriever)
    result = await agent.analyze(profile_data)
"""

import json
from typing import Any, Optional

import structlog
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.prompts import MATCHING_AGENT_SYSTEM_PROMPT
from app.agent.tools import AGENT_TOOLS

logger = structlog.get_logger(__name__)


class JobMatchingAgent:
    """
    岗位匹配 Agent — 使用 LangChain Tool Calling 实现多步骤匹配分析。

    设计要点:
        - Agent 通过 Tool Calling 自主决策调用哪些工具、按什么顺序
        - 每个工具返回结构化数据，Agent 做最终的综合分析
        - 支持传入 retriever 实例以启用题库检索
    """

    def __init__(
        self,
        llm: BaseChatModel,
        retriever: Any = None,
        *,
        max_iterations: int = 10,
        verbose: bool = False,
    ) -> None:
        """
        Args:
            llm:            LangChain ChatModel（DeepSeek 兼容）
            retriever:      HybridRetriever 实例（可选）
            max_iterations: Agent 最大推理步数
            verbose:        是否输出详细日志
        """
        self.llm = llm
        self.retriever = retriever
        self.max_iterations = max_iterations
        self.verbose = verbose

        # 构建 Agent
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", MATCHING_AGENT_SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        self.agent = create_tool_calling_agent(self.llm, AGENT_TOOLS, self.prompt)
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=AGENT_TOOLS,
            max_iterations=self.max_iterations,
            verbose=self.verbose,
            handle_parsing_errors=True,
            return_intermediate_steps=False,
        )

    async def analyze(
        self,
        profile_data: dict[str, Any],
        job_title: Optional[str] = None,
        job_description: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        执行岗位匹配分析。

        Args:
            profile_data:    候选人画像数据
            job_title:       目标岗位（可覆盖画像中的 target_role）
            job_description: 岗位描述

        Returns:
            匹配分析报告
            {
                "match_score": 0.85,
                "matched_template": "...",
                "inferred_level": "senior",
                "skill_analysis": {...},
                "interview_strategy": {...},
                "recommendations": [...],
                "raw_agent_output": "..."
            }
        """
        target_role = job_title or profile_data.get("target_role", "后端开发工程师")
        skills_str = json.dumps(profile_data.get("skills", []), ensure_ascii=False)
        years = profile_data.get("years_of_experience", 0)

        # 构建输入
        input_text = (
            f"请对以下候选人进行岗位匹配分析：\n\n"
            f"## 候选人信息\n"
            f"- 目标岗位: {target_role}\n"
            f"- 工作年限: {years} 年\n"
            f"- 技能: {skills_str}\n"
            f"- 岗位描述: {job_description or '未提供'}\n\n"
            f"请按照工作流程执行岗位匹配分析，"
            f"使用工具检索岗位模板、分析技能差距、搜索相关题库。"
        )

        logger.info(
            "agent_analyze_start",
            target_role=target_role,
            years=years,
            skills_count=len(profile_data.get("skills", [])),
        )

        try:
            result = await self.executor.ainvoke({"input": input_text})
        except Exception as exc:
            logger.error("agent_analyze_error", error=str(exc))
            return self._fallback_analysis(profile_data, target_role, job_description)

        output = result.get("output", "")

        logger.info("agent_analyze_complete", output_length=len(output))

        # 尝试从 Agent 输出中提取结构化数据
        return {
            "raw_agent_output": output,
            "profile": profile_data,
            "target_role": target_role,
            "status": "completed",
        }

    def _fallback_analysis(
        self,
        profile_data: dict,
        target_role: str,
        job_description: Optional[str],
    ) -> dict:
        """Agent 失败时的回退分析 — 使用规则匹配。"""
        logger.warning("agent_fallback_analysis", target_role=target_role)

        skills = profile_data.get("skills", [])
        years = profile_data.get("years_of_experience", 0)

        level = "mid"
        if years < 2:
            level = "junior"
        elif years < 5:
            level = "mid"
        elif years < 8:
            level = "senior"
        else:
            level = "staff"

        return {
            "raw_agent_output": f"Agent 分析异常，已使用规则匹配回退。目标岗位: {target_role}",
            "profile": profile_data,
            "target_role": target_role,
            "match_score": 0.7,
            "inferred_level": level,
            "status": "fallback",
        }


def create_matching_agent(
    llm_client: Any,
    retriever: Any = None,
) -> JobMatchingAgent:
    """
    工厂函数 — 创建 JobMatchingAgent。

    需要将 app.core.llm_client.LLMClient 包装为 LangChain BaseChatModel。
    使用 langchain_openai.ChatOpenAI 适配 DeepSeek API。

    Args:
        llm_client: app.core.llm_client.LLMClient 或 LangChain ChatModel
        retriever:  HybridRetriever 实例

    Returns:
        JobMatchingAgent 实例
    """
    from langchain_openai import ChatOpenAI

    if isinstance(llm_client, BaseChatModel):
        chat_model = llm_client
    else:
        # 从 LLMClient 创建 LangChain ChatOpenAI
        settings = llm_client.settings
        chat_model = ChatOpenAI(
            model=settings.MODEL,
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
        )

    return JobMatchingAgent(chat_model, retriever=retriever)
