# 🤖 AI Mock Interview System

> 基于 RAG + LLM 的智能模拟面试系统 — 上传简历，AI 深度解析，自动生成个性化面试题。

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)](https://redis.io/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-4B32C3)](https://deepseek.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 目录

- [核心亮点](#-核心亮点)
- [系统架构](#-系统架构)
- [功能流程](#-功能流程)
- [技术栈](#-技术栈)
- [快速开始](#-快速开始)
- [题库概览](#-题库概览)
- [API 概览](#-api-概览)
- [项目结构](#-项目结构)
- [设计决策](#-设计决策)

---

## ✨ 核心亮点

| 亮点 | 说明 |
|------|------|
| 🧠 **AI 深度简历分析** | 提取核心技能（含熟练度 + 年限）、优势领域、风险区域、面试策略建议 |
| 🔍 **混合 RAG 检索** | 向量语义检索 + BM25 关键词检索 + RRF 融合排序，确保题目相关且多样 |
| 📚 **391 道手选题库** | 5 大领域、3 种题型（知识深度 / 工程实践 / 软技能），全口头回答型 |
| 🎯 **题库优先 + LLM 兜底** | 相关题目优先从题库出（答案精确可控），不匹配时 LLM 原创生成 |
| ⚡ **Mock 模式零门槛启动** | 无需 PostgreSQL/Redis，内存字典 + 关键词匹配即可体验完整流程 |
| 🐳 **Docker 容器化部署** | 4 个服务（PostgreSQL + Redis + API + Celery）一键编排启动 |
| 🔧 **工程化实践** | 全量类型注解、依赖注入、统一异常处理、结构化日志 |

---

## 🏗 系统架构

```
┌──────────────────────────────────────────────────┐
│                 Frontend (SPA)                    │
│          Drag & Drop PDF Upload                   │
└────────────────────┬─────────────────────────────┘
                     │ HTTP
┌────────────────────▼─────────────────────────────┐
│               FastAPI Gateway                     │
│  ┌────────────┬──────────────┬────────────────┐  │
│  │   Resume   │  Interview   │   Questions    │  │
│  │   Upload   │   Session    │   Search       │  │
│  └─────┬──────┴──────┬───────┴───────┬────────┘  │
└────────┼─────────────┼───────────────┼───────────┘
         │             │               │
┌────────▼─────────────▼───────────────▼───────────┐
│                Service Layer                      │
│  ┌──────────────┬──────────────┬───────────────┐ │
│  │ ResumeParser │   Profile    │ QuestionGen   │ │
│  │ (PDF→Text)   │  Extractor   │ (RAG+LLM)     │ │
│  └──────────────┴──────────────┴───────────────┘ │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│                  Data Layer                        │
│  ┌──────────┬──────────┬──────────────────────┐  │
│  │PostgreSQL│  Redis   │       Celery         │  │
│  │+pgvector │  Cache   │   Async Workers      │  │
│  └──────────┴──────────┴──────────────────────┘  │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│                External APIs                      │
│  ┌─────────────────┬──────────────────────────┐  │
│  │   DeepSeek API   │  DashScope Embedding API │  │
│  │ (LLM 分析/出题)   │ (Qwen3.7 1024维向量)     │  │
│  └─────────────────┴──────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 🔄 功能流程

```
  📄 上传简历 PDF
        │
        ▼
  🔬 AI 深度分析
  ├─ 核心技能 + 熟练度 + 实战年限
  ├─ 候选人优势领域
  ├─ 风险区域（需面试验证）
  ├─ 教育背景总结
  └─ 面试策略建议
        │
        ▼
  🎯 设置面试参数
  ├─ 岗位名称 + JD
  ├─ 题目数量（1-30）
  ├─ 难度（easy / medium / hard）
  └─ 题型（knowledge / practice / soft_skill）
        │
        ▼
  🔍 混合 RAG 检索
  ├─ 向量语义检索（DashScope Embedding）
  ├─ BM25 关键词检索
  └─ RRF 融合排序
        │
        ▼
  📝 智能出题（题库优先 + LLM 兜底）
  ├─ 相似度 ≥ 0.018 → 题库选取
  ├─ 0.014 ~ 0.018 → 题库 + LLM 混合
  └─ 相似度 < 0.014 → 全部 LLM 原创
        │
        ▼
  📋 查看题目 + 参考答案
  ├─ 逐题展示（含 reference_answer）
  ├─ 关键考查点（key_points）
  └─ 题目来源标记（bank / llm）
```

> 💡 评分与报告模块为规划中的功能，暂未实现。当前专注于简历分析 → 出题的完整链路。

---

## 🛠 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI + Uvicorn | async 高性能 API |
| **数据库** | PostgreSQL 15 + pgvector | 向量存储 + 余弦相似度检索 |
| **缓存/队列** | Redis 7 | Celery broker + 业务缓存 |
| **异步任务** | Celery 5 | 简历解析等耗时任务后台执行 |
| **LLM** | DeepSeek (deepseek-chat) | 简历分析、深度画像、题目生成 |
| **Embedding** | DashScope Qwen3.7 | 文本向量化，1024 维 |
| **ORM** | SQLAlchemy 2.0 (async) | 全异步数据库操作 |
| **数据校验** | Pydantic v2 | 请求/响应模型 + 配置管理 |
| **部署** | Docker Compose | 4 容器一键编排 |
| **日志** | structlog | 结构化 JSON 日志 |

---

## 🚀 快速开始

### 方式一：Mock 模式（推荐，无需数据库）

```bash
# 1. 克隆项目
git clone https://github.com/Jerry1693464132/AI-Interview-RAG-Agent-.git
cd AI-Interview-RAG-Agent-

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 .env（填写你的 API Key）
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY
# 确保 USE_MOCK_DB=true

# 4. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. 打开浏览器
# 前端界面: http://localhost:8000/
# API 文档:  http://localhost:8000/docs
```

> 💡 Mock 模式使用内存字典模拟数据库，无需安装 PostgreSQL/Redis。启动时自动从 `seed_questions.json` 加载 391 道题库，重启后数据清空。

### 方式二：Docker Compose（完整生产环境）

```bash
# 1. 配置 .env
cp .env.example .env
# 编辑 .env：USE_MOCK_DB=false，填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY

# 2. 一键启动
docker compose up -d

# 3. 初始化数据库表
docker compose exec api python -c "import asyncio;from app.core.database import engine;from app.models import Base;asyncio.run((lambda: (lambda conn: conn.run_sync(Base.metadata.create_all)))((lambda e: e.begin())(engine)))"

# 4. 导入种子题库
docker compose exec api python -c "import asyncio,json;from app.core.database import async_session_factory;from app.rag.embeddings import EmbeddingClient;from app.rag.vector_store import VectorStore;from app.rag.indexer import QuestionBankIndexer;async def seed(): questions=json.load(open('app/data/seed_questions.json','r',encoding='utf-8')); async with async_session_factory() as s: await QuestionBankIndexer(EmbeddingClient(),VectorStore(s)).index_questions(questions); print('Done:',len(questions)); asyncio.run(seed())"

# 5. 访问 http://localhost:8000/
```

### 方式三：本地开发

```bash
# 前提：已安装 PostgreSQL 15（pgvector 扩展）+ Redis 7

# 1. 配置 .env
USE_MOCK_DB=false
POSTGRES_HOST=localhost
REDIS_HOST=localhost

# 2. 创建表 + 导入题库（同 Docker 方式步骤 3-4）

# 3. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📚 题库概览

共 **391 道** 手工精选题目，全部为口头回答型（禁止生成代码编写题）。

| 领域 | 数量 | 覆盖范围 |
|------|------|---------|
| 🔧 后端开发 | 130 | Python、Java、Go、API 设计、微服务 |
| 🎨 前端 | 100 | React、Vue、TypeScript、性能优化 |
| 🏛️ 架构设计 | 93 | 系统设计、分布式、高可用、数据库选型 |
| 🤖 AI / Agent | 45 | LLM 原理、RAG、Agent 架构、Prompt Engineering |
| 💬 软技能 | 23 | 沟通协作、Code Review、向上管理、职业发展 |

| 题型 | 数量 | 考查方向 |
|------|------|---------|
| 📖 知识深度 (knowledge) | 322 | 原理、机制、底层实现 |
| 🔨 工程实践 (practice) | 46 | 系统设计、故障排查、架构决策 |
| 🗣️ 软技能 (soft_skill) | 23 | 沟通、协作、学习能力 |

---

## 📡 API 概览

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/resumes/upload-sync` | 上传简历 PDF，同步解析并返回画像 |
| `POST` | `/api/v1/interviews/` | 创建面试会话 |
| `GET` | `/api/v1/interviews/` | 列出历史面试记录 |
| `POST` | `/api/v1/interviews/{id}/generate-questions` | 触发 RAG 增强出题 |
| `GET` | `/api/v1/interviews/{id}/questions` | 查看已生成的题目列表 |
| `POST` | `/api/v1/questions/search` | 混合语义检索（向量 + 关键词） |
| `GET` | `/health` | 健康检查 |
| `GET` | `/docs` | Swagger API 文档 |

---

## 📁 项目结构

```
.
├── app/
│   ├── main.py                    ← FastAPI 入口，lifespan 管理启动/销毁
│   ├── core/                      ← 基础设施
│   │   ├── config.py              ← 配置中心（pydantic-settings）
│   │   ├── database.py            ← async engine + ORM 基类
│   │   ├── deps.py                ← 依赖注入（DB 会话/Redis）
│   │   ├── llm_client.py          ← DeepSeek API 封装（重试+日志）
│   │   └── exceptions.py          ← 统一异常体系
│   ├── api/v1/                    ← 路由层
│   │   ├── resume.py              ← 简历上传/同步解析
│   │   ├── interview.py           ← 面试会话 + RAG 出题
│   │   └── questions.py           ← 题库混合检索
│   ├── services/                  ← 业务逻辑
│   │   ├── resume_parser.py       ← PDF 解析 + LLM 结构化提取
│   │   ├── profile_extractor.py   ← AI 深度画像分析
│   │   └── question_generator.py  ← 出题引擎（题库优先+LLM兜底）
│   ├── rag/                       ← RAG 检索链路
│   │   ├── embeddings.py          ← DashScope 文本向量化
│   │   ├── vector_store.py        ← pgvector 向量 CRUD
│   │   ├── retriever.py           ← 混合检索 + RRF 融合
│   │   └── indexer.py             ← 题库批量索引
│   ├── models/                    ← ORM 数据库表（5 张表）
│   ├── schemas/                   ← Pydantic 请求/响应模型
│   ├── tasks/                     ← Celery 异步任务
│   ├── prompts/                   ← Prompt 工具
│   ├── data/                      ← 种子题库（391 题 JSON）
│   └── static/                    ← 前端 SPA
├── tests/                         ← pytest 测试
├── Dockerfile                     ← 应用镜像
├── docker-compose.yml             ← 服务编排
├── requirements.txt               ← Python 依赖
├── pyproject.toml                 ← 项目元数据 + ruff/mypy/pytest 配置
├── .env.example                   ← 环境变量模板
└── CLAUDE.md                      ← Claude Code 项目规范
```

---

## 🎯 设计决策

| 决策点 | 选型 | 理由 |
|--------|------|------|
| **出题策略** | 题库优先 + LLM 兜底 | 题库答案精确可控，LLM 填补缺口 |
| **双阈值过滤** | SIM=0.014 / HARD=0.018 | 相似度过低 → 题库不匹配 → 全走 LLM 原创 |
| **检索融合** | 向量 + BM25 + RRF | 语义匹配 + 精确关键词，互补提高召回率 |
| **评分设计** | reference_answer + key_points 注入 | 标准答案做锚点，评分稳定一致 |
| **Mock 模式** | 内存 dict 模拟 DB | 零基础设施门槛，一键体验完整流程 |
| **API 响应格式** | `{code, message, data}` | 前端消费一致性 |
| **Prompt 管理** | Python 函数返回 | 版本控制友好，无外部依赖 |

---

## 🤝 待完善

- [ ] WebSocket 实时面试对话
- [ ] AI 智能评分引擎
- [ ] 面试报告生成（逐题反馈 + 整体评价）
- [ ] 多轮追问对话
- [ ] 语音输入支持
- [ ] 题库扩充（安全、DevOps、数据工程等）

---

## 📄 License

MIT © [Jerry](https://github.com/Jerry1693464132)

---

<p align="center">
  <b>⭐ 如果这个项目对你有帮助，欢迎 Star</b><br/>
  <sub>Built with ❤️ for better interviews</sub>
</p>
