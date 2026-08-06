"""
LangChain Agent 模块 — 岗位匹配 Agent。

组件:
    - tools.py             Agent 工具（题库检索、画像获取、岗位匹配、技能分析）
    - prompts.py           Agent 系统 Prompt
    - matching_agent.py    岗位匹配 Agent（Tool Calling）
"""

from app.agent.matching_agent import JobMatchingAgent, create_matching_agent
from app.agent.tools import AGENT_TOOLS

__all__ = [
    "JobMatchingAgent",
    "create_matching_agent",
    "AGENT_TOOLS",
]
