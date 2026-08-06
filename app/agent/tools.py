"""
Agent 工具定义 — LangChain Tool Calling Agent 可调用的工具。

工具列表:
    - search_question_bank: RAG 检索题库
    - get_candidate_profile: 获取候选人画像
    - match_job_template: 岗位模板匹配
    - analyze_skill_gap: 技能差距分析
"""

import json
from typing import Any, Optional

import structlog
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.retriever import HybridRetriever

logger = structlog.get_logger(__name__)


# 岗位模板库（简化版，生产环境应存储在数据库）
_JOB_TEMPLATES = {
    "backend": {
        "type": "backend",
        "name": "后端开发工程师",
        "required_skills": ["Python", "Java", "Go", "数据库", "API设计", "Linux"],
        "nice_to_have": ["Kubernetes", "Docker", "消息队列", "微服务"],
        "common_questions": ["系统设计", "数据库优化", "并发处理", "API安全"],
        "levels": {
            "junior": {"years": "0-2", "expectations": ["能独立完成CRUD", "了解基本框架"]},
            "mid": {"years": "2-5", "expectations": ["独立设计模块", "性能调优", "团队协作"]},
            "senior": {"years": "5-8", "expectations": ["系统架构设计", "技术选型", "指导他人"]},
            "staff": {"years": "8+", "expectations": ["跨团队架构", "技术规划", "影响力"]},
        },
    },
    "frontend": {
        "type": "frontend",
        "name": "前端开发工程师",
        "required_skills": ["JavaScript", "TypeScript", "React/Vue", "HTML/CSS", "浏览器原理"],
        "nice_to_have": ["Node.js", "Webpack/Vite", "微前端", "Canvas/WebGL"],
        "common_questions": ["组件设计", "性能优化", "状态管理", "跨端开发"],
        "levels": {
            "junior": {"years": "0-2", "expectations": ["能独立开发页面", "了解主流框架"]},
            "mid": {"years": "2-5", "expectations": ["组件库设计", "性能优化", "工程化"]},
            "senior": {"years": "5-8", "expectations": ["架构设计", "搭建脚手架", "指导团队"]},
            "staff": {"years": "8+", "expectations": ["多端架构", "技术规划", "开源贡献"]},
        },
    },
    "data": {
        "type": "data",
        "name": "数据工程师",
        "required_skills": ["SQL", "Python", "Spark", "ETL", "数据仓库"],
        "nice_to_have": ["Flink", "Kafka", "数据湖", "Airflow"],
        "common_questions": ["数据建模", "Pipeline设计", "数据质量", "实时计算"],
        "levels": {
            "junior": {"years": "0-2", "expectations": ["SQL熟练", "基本ETL", "数据报表"]},
            "mid": {"years": "2-5", "expectations": ["数据建模", "Pipeline开发", "Spark优化"]},
            "senior": {"years": "5-8", "expectations": ["架构设计", "数据治理", "团队管理"]},
            "staff": {"years": "8+", "expectations": ["公司级数据战略", "平台建设"]},
        },
    },
    "devops": {
        "type": "devops",
        "name": "DevOps/SRE工程师",
        "required_skills": ["Linux", "Docker", "Kubernetes", "CI/CD", "监控"],
        "nice_to_have": ["Terraform", "Ansible", "Prometheus", "服务网格"],
        "common_questions": ["故障排查", "容量规划", "自动化", "安全加固"],
        "levels": {
            "junior": {"years": "0-2", "expectations": ["基本运维", "Docker", "脚本编写"]},
            "mid": {"years": "2-5", "expectations": ["K8s管理", "CI/CD搭建", "监控体系"]},
            "senior": {"years": "5-8", "expectations": ["混合云架构", "SRE体系", "灾备"]},
            "staff": {"years": "8+", "expectations": ["基础设施战略", "FinOps"]},
        },
    },
    "ai_ml": {
        "type": "ai_ml",
        "name": "AI/ML工程师",
        "required_skills": ["Python", "PyTorch/TensorFlow", "机器学习", "深度学习"],
        "nice_to_have": ["MLOps", "CUDA", "模型部署", "LLM应用"],
        "common_questions": ["模型选型", "特征工程", "模型部署", "评估指标"],
        "levels": {
            "junior": {"years": "0-2", "expectations": ["模型训练", "数据处理", "基本调参"]},
            "mid": {"years": "2-5", "expectations": ["模型优化", "Pipeline设计", "AB实验"]},
            "senior": {"years": "5-8", "expectations": ["架构设计", "ML平台", "研究方向"]},
            "staff": {"years": "8+", "expectations": ["AI战略", "前沿研究", "技术品牌"]},
        },
    },
}

# ---- Tool 1: 检索题库 ----

@tool
async def search_question_bank(
    query: str,
    question_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """
    从题库中检索面试题目。

    使用场景:
        - 查找与目标岗位相关的技术题目
        - 获取特定难度和类型的参考题目
        - 为出题提供 RAG 上下文

    Args:
        query: 查询关键词，如 "Python 装饰器" 或 "系统设计"
        question_type: 题型过滤 (technical/coding/system_design/behavioral/scenario)
        difficulty: 难度过滤 (easy/medium/hard)
        top_k: 返回结果数

    Returns:
        JSON 格式的检索结果
    """
    logger.info(
        "agent_tool_search_question_bank",
        query=query,
        question_type=question_type,
        difficulty=difficulty,
    )

    # 此函数需要被 AgentExecutor 注入 retriever
    # 如果 retriever 不可用，返回占位结果
    return json.dumps({
        "tool": "search_question_bank",
        "query": query,
        "message": "题库检索工具（需要在 Agent 初始化时注入 retriever）",
        "results": [],
    }, ensure_ascii=False)


# ---- Tool 2: 获取候选人画像 ----

@tool
async def get_candidate_profile(profile_data: str = "") -> str:
    """
    获取候选人画像信息。

    使用场景:
        - 分析候选人的技能、经验和目标岗位
        - 评估候选人与岗位的匹配度
        - 确定面试难度和题型分布

    Args:
        profile_data: JSON 格式的候选人画像数据
            {"skills": [...], "years_of_experience": 3.5, "target_role": "...", ...}

    Returns:
        候选人画像摘要
    """
    if not profile_data:
        return json.dumps({"error": "未提供画像数据"}, ensure_ascii=False)

    try:
        profile = json.loads(profile_data) if isinstance(profile_data, str) else profile_data
    except json.JSONDecodeError:
        return json.dumps({"error": "画像数据 JSON 解析失败"}, ensure_ascii=False)

    skills = profile.get("skills", [])
    years = profile.get("years_of_experience", 0)
    target_role = profile.get("target_role", "未知")
    target_level = profile.get("target_level", "mid")

    return json.dumps({
        "skills": skills,
        "skills_count": len(skills),
        "years_of_experience": years,
        "target_role": target_role,
        "target_level": target_level,
        "education": profile.get("education_summary", {}),
        "work_summary": profile.get("work_summary", {}),
    }, ensure_ascii=False)


# ---- Tool 3: 岗位模板匹配 ----

@tool
async def match_job_template(
    target_role: str,
    candidate_skills: str = "[]",
    years_of_experience: float = 0.0,
) -> str:
    """
    匹配岗位模板，分析候选人与标准岗位要求的差距。

    使用场景:
        - 确定面试考查重点
        - 识别技能差距
        - 选择适合的面试难度和题型

    Args:
        target_role: 目标岗位，如 "后端开发工程师" / "前端开发工程师"
        candidate_skills: JSON 数组，候选人技能列表
        years_of_experience: 工作年限

    Returns:
        JSON 格式的岗位匹配分析结果
    """
    logger.info(
        "agent_tool_match_job_template",
        target_role=target_role,
        years=years_of_experience,
    )

    # 解析技能列表
    try:
        skills = json.loads(candidate_skills) if isinstance(candidate_skills, str) else candidate_skills
        skills_lower = [s.lower() for s in skills]
    except (json.JSONDecodeError, TypeError):
        skills = []
        skills_lower = []

    # 岗位关键词匹配
    role_lower = target_role.lower()
    matched_template = None

    for key, template in _JOB_TEMPLATES.items():
        if key in role_lower or template["name"] in target_role:
            matched_template = template
            break

    if not matched_template:
        # 默认使用后端模板
        matched_template = _JOB_TEMPLATES["backend"]

    # 技能匹配分析
    required = matched_template["required_skills"]
    nice = matched_template["nice_to_have"]
    matched_required = [s for s in required if any(s.lower() in sk for sk in skills_lower)]
    missing_required = [s for s in required if not any(s.lower() in sk for sk in skills_lower)]
    matched_nice = [s for s in nice if any(s.lower() in sk for sk in skills_lower)]

    # 级别推断
    level = "mid"
    if years_of_experience < 2:
        level = "junior"
    elif years_of_experience < 5:
        level = "mid"
    elif years_of_experience < 8:
        level = "senior"
    else:
        level = "staff"

    level_info = matched_template["levels"].get(level, matched_template["levels"]["mid"])

    return json.dumps({
        "matched_template": matched_template["name"],
        "template_type": matched_template["type"],
        "inferred_level": level,
        "level_expectations": level_info.get("expectations", []),
        "matched_required_skills": matched_required,
        "missing_required_skills": missing_required,
        "matched_nice_skills": matched_nice,
        "skill_match_rate": round(
            len(matched_required) / max(len(required), 1), 2
        ),
        "recommended_question_types": matched_template["common_questions"],
        "suggested_difficulty": "hard" if level in ("senior", "staff") else "medium",
    }, ensure_ascii=False)


# ---- Tool 4: 技能差距分析 ----

@tool
async def analyze_skill_gap(
    required_skills: str = "[]",
    candidate_skills: str = "[]",
) -> str:
    """
    分析候选人与岗位需求的技能差距。

    使用场景:
        - 为面试出题提供重点考查方向
        - 识别最需要验证的技能领域
        - 生成个性化的面试策略

    Args:
        required_skills: JSON 数组，岗位要求的技能
        candidate_skills: JSON 数组，候选人声称的技能

    Returns:
        JSON 格式的技能差距分析
    """
    logger.info("agent_tool_analyze_skill_gap")

    try:
        required = set(json.loads(required_skills) if isinstance(required_skills, str) else required_skills)
    except (json.JSONDecodeError, TypeError):
        required = set()

    try:
        candidate = set(json.loads(candidate_skills) if isinstance(candidate_skills, str) else candidate_skills)
    except (json.JSONDecodeError, TypeError):
        candidate = set()

    # 分类
    matched = sorted(required & candidate)
    missing = sorted(required - candidate)
    extra = sorted(candidate - required)

    # 面试考查优先级
    priority_skills = missing[:5] if missing else list(matched)[:5]
    verify_skills = list(matched)[:5]  # 自称会的技能需在面试中验证

    return json.dumps({
        "matched_skills": matched,
        "missing_skills": missing,
        "extra_skills": extra,
        "match_rate": round(len(matched) / max(len(required), 1), 2),
        "priority_check": {
            "skills_to_verify": verify_skills,
            "skills_to_probe": priority_skills,
            "strategy": (
                f"面试应重点考查这 {len(priority_skills)} 个缺失技能是否确实不了解，"
                f"同时验证 {len(verify_skills)} 个声称技能的真实掌握程度。"
            ),
        },
    }, ensure_ascii=False)


# ---- 工具列表汇总 ----

AGENT_TOOLS = [
    search_question_bank,
    get_candidate_profile,
    match_job_template,
    analyze_skill_gap,
]
