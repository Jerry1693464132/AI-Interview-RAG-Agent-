# 🤖 AI Mock Interview System

> 基于 RAG + LLM 的智能模拟面试系统 — 上传简历，AI 深度解析，自动生成个性化面试题，智能评分。

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://www.python.org/)
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
| 🧠 **AI 深度简历分析** | 不只是提取技能关键词，而是分析候选人优势、风险区域，生成面试策略 |
| 🔍 **混合 RAG 检索** | 向量语义检索 + BM25 关键词检索 + RRF 融合，确保题目相关且多样 |
| 📚 **391 道手选题库** | 8 大领域、5 级难度、3 种题型（知识深度 / 工程实践 / 软技能） |
| 🎯 **题库优先 + LLM 兜底** | 相关题目优先从题库出（答案更精确），不匹配时 LLM 原创生成 |
| ⚡ **Mock 模式一键启动** | 无需 PostgreSQL/Redis，内存数据库即可体验完整流程 |
| 🐳 **Docker 一键部署** | `docker compose up` 直接上生产环境 |
| 🔧 **工程化实践** | 全量类型注解、统一异常处理、Celery 异步任务、结构化日志 |

---

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                     Frontend (SPA)                        │
│              Drag & Drop PDF Upload                       │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼───────────────────────────────────┐
│                   FastAPI Gateway                         │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐ │
│  │ Resume   │ Interview│ Questions│ Scoring  │ Report │ │
│  │ Upload   │ Session  │ Generate │ & Review │ Export │ │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬───┘ │
└───────┼──────────┼──────────┼──────────┼──────────┼─────┘
        │          │          │          │          │
┌───────▼──────────▼──────────▼──────────▼──────────▼─────┐
│                    Service Layer                          │
│  ┌──────────────┬──────────────┬───────────────────────┐ │
│  │ ResumeParser │   Profile    │   QuestionGenerator   │ │
│  │ (PDF→Text)   │  Extractor   │ (RAG + LLM Pipeline)  │ │
│  └──────────────┴──────────────┴───────────────────────┘ │
│  ┌──────────────┬──────────────┬───────────────────────┐ │
│  │ ScoringEngine│ ReportBuilder│   JobMatchingAgent    │ │
│  └──────────────┴──────────────┴───────────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                      Data Layer                           │
│  ┌──────────┬──────────┬──────────┬────────────────────┐ │
│  │PostgreSQL│ pgvector │  Redis   │       Celery       │ │
│  │  ORM DB  │Embedding │  Cache   │   Async Workers    │ │
│  └──────────┴──────────┴──────────┴────────────────────┘ │
└──────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                    External APIs                          │
│  ┌─────────────────────┬──────────────────────────────┐  │
│  │    DeepSeek API      │   DashScope Embedding API    │  │
│  │  (LLM 对话 / 生成)    │  (Qwen3.7 Text Embedding)    │  │
│  └─────────────────────┴──────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 🔄 功能流程

```
  📄 上传简历 PDF
        │
        ▼
  🔬 AI 深度解析
  ├─ 核心技能 + 熟练度 + 年限
  ├─ 候选人优势
  ├─ 风险区域（需验证的点）
  ├─ 教育背景总结
  └─ 面试策略建议
        │
        ▼
  🎯 设置面试岗位
  ├─ 岗位名称 + JD
  ├─ 题目数量（1-30）
  ├─ 难度（easy/medium/hard）
  └─ 题型（knowledge/practice/soft_skill）
        │
        ▼
  🔍 混合 RAG 检索
  ├─ 向量语义检索 (DashScope Embedding)
  ├─ BM25 关键词检索
  └─ RRF 融合排序
        │
        ▼
  📝 智能出题（题库优先）
  ├─ 相似度 ≥ 0.018 → 从题库选取
  ├─ 0.014 ≤ 相似度 < 0.018 → 题库 + LLM 混合
  └─ 相似度 < 0.014 → 全部 LLM 原创
        │
        ▼
  💬 模拟面试（待完善）
  ├─ 逐题展示
  └─ 候选人口头回答
        │
        ▼
  📊 AI 智能评分
  ├─ 参考答案比对
  ├─ 关键点覆盖度分析
  └─ 维度评分（content/expression/logic/depth）
        │
        ▼
  📋 面试报告
  ├─ 总分 + 各维度得分
  ├─ 逐题详细反馈
  └─ 整体评价 + 改进建议
```

---

## 🛠 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI + Uvicorn | async 高性能 API |
| **数据库** | PostgreSQL 15 + pgvector | 向量存储 + 混合检索 |
| **缓存** | Redis 7 | Celery broker + 业务缓存 |
| **异步任务** | Celery 5 | 简历解析、评分、报告生成 |
| **LLM** | DeepSeek (deepseek-chat) | 简历分析、出题、评分 |
| **Embedding** | DashScope Qwen3.7 | 文本向量化，1024 维 |
| **Agent** | LangChain Tool Calling | 岗位匹配 Agent |
| **ORM** | SQLAlchemy 2.0 (async) | 全异步数据库操作 |
| **部署** | Docker Compose | 一键启动全栈服务 |
| **监控** | structlog | 结构化 JSON 日志 |

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
# API 文档: http://localhost:8000/docs
# 前端界面: http://localhost:8000/
```

> 💡 Mock 模式使用内存数据库，无需安装 PostgreSQL/Redis，391 道题库自动加载。重启后数据清空。

### 方式二：Docker Compose（完整生产环境）

```bash
# 1. 配置 .env
cp .env.example .env
# 编辑 .env，设置 USE_MOCK_DB=false，填入 API Key

# 2. 启动全部服务
docker compose up -d

# 3. 初始化数据库
docker compose exec api alembic upgrade head

# 4. 导入种子题库
docker compose exec api python -m app.rag.indexer

# 5. 访问
# http://localhost:8000/docs
```

### 方式三：本地开发（需要 PostgreSQL + Redis）

```bash
# 1. 启动 PostgreSQL 15（需安装 pgvector 扩展）+ Redis 7

# 2. 配置 .env
USE_MOCK_DB=false
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=interview
POSTGRES_PASSWORD=interview_secret
POSTGRES_DB=interview_db

# 3. 初始化
python -m alembic upgrade head
python -m app.rag.indexer   # 导入种子题库

# 4. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📚 题库概览

共 **391 道** 手工精选题目，全部为口头回答型（无代码编写题）。

### 按领域分布

| 领域 | 数量 | 说明 |
|------|------|------|
| 🔧 后端开发 | 130 | Python、Java、Go、API 设计、微服务 |
| 🎨 前端 | 100 | React、Vue、TypeScript、性能优化 |
| 🏛️ 架构设计 | 93 | 系统设计、分布式、高可用、数据库选型 |
| 🤖 AI / Agent | 45 | LLM 原理、RAG、Agent 架构、Prompt Engineering |
| 💬 通用软技能 | 23 | 沟通协作、项目管理、学习方法 |

### 按题型分布

| 题型 | 数量 | 考查重点 |
|------|------|---------|
| 📖 knowledge | 322 | 原理、机制、底层实现（口头讲述） |
| 🔨 practice | 46 | 系统设计、故障排查、架构决策 |
| 🗣️ soft_skill | 23 | 沟通、协作、学习能力 |

### 按难度分布

| 难度 | 数量 |
|------|------|
| 🟢 Easy | 65 |
| 🟡 Medium | 226 |
| 🔴 Hard | 100 |

---

## 📡 API 概览

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/resumes/upload` | 上传简历 PDF，返回解析结果 |
| `POST` | `/api/v1/resumes/{id}/profile` | 生成候选人深度画像 |
| `POST` | `/api/v1/interviews/` | 创建面试会话 + 生成题目 |
| `GET` | `/api/v1/interviews/{id}` | 查询面试会话详情 |
| `POST` | `/api/v1/questions/search` | 题库检索（向量 + 关键词混合） |
| `GET` | `/api/v1/questions/` | 分页查询面试题目 |
| `POST` | `/api/v1/scoring/batch` | 批量评分（全部题目） |
| `GET` | `/api/v1/reports/{id}` | 获取面试报告 |
| `GET` | `/api/v1/reports/` | 报告列表 |
| `GET` | `/health` | 健康检查 |
| `GET` | `/docs` | Swagger API 文档 |

---

## 📁 项目结构

```
.
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── core/                      # 基础设施
│   │   ├── config.py              # 配置中心 (pydantic-settings)
│   │   ├── database.py            # async engine + session
│   │   ├── llm_client.py          # DeepSeek API 封装
│   │   ├── deps.py                # 依赖注入
│   │   └── exceptions.py          # 统一异常
│   ├── api/v1/                    # 路由层
│   │   ├── resume.py              # 简历上传/解析
│   │   ├── interview.py           # 面试流程
│   │   ├── questions.py           # 题库检索/管理
│   │   ├── scoring.py             # 评分
│   │   └── report.py              # 报告
│   ├── services/                  # 业务逻辑
│   │   ├── resume_parser.py       # PDF 解析 + LLM 提取
│   │   ├── profile_extractor.py   # AI 深度画像分析
│   │   ├── question_generator.py  # RAG + LLM 出题引擎
│   │   ├── scoring_engine.py      # 评分引擎
│   │   └── report_builder.py      # 报告生成
│   ├── rag/                       # RAG 检索链
│   │   ├── embeddings.py          # DashScope Embedding
│   │   ├── vector_store.py        # pgvector CRUD
│   │   ├── retriever.py           # 混合检索 (向量+BM25+RRF)
│   │   └── indexer.py             # 题库入库
│   ├── tasks/                     # Celery 异步任务
│   ├── models/                    # SQLAlchemy ORM
│   ├── schemas/                   # Pydantic DTO
│   ├── prompts/                   # Prompt 模板
│   ├── data/                      # 种子数据
│   │   └── seed_questions.json    # 391 道题库
│   └── static/                    # 前端静态文件
│       └── index.html
├── tests/                         # 测试
├── .env.example                   # 环境变量模板
├── Dockerfile                     # 应用镜像
├── docker-compose.yml             # 服务编排
├── requirements.txt               # Python 依赖
└── CLAUDE.md                      # Claude Code 项目规范
```

---

## 🎯 设计决策

| 决策点 | 选型 | 理由 |
|--------|------|------|
| **出题策略** | 题库优先 + LLM 兜底 | 题库题目答案更精确可控，LLM 用于填补缺口 |
| **双阈值过滤** | SIM=0.014 / HARD=0.018 | 相似度太低说明题库不匹配，全走 LLM 原创 |
| **检索融合** | 向量 + BM25 + RRF | 语义匹配 + 精确关键词，互补提高召回率 |
| **评分设计** | reference_answer + key_points 注入 | 标准答案做锚点，评分更稳定一致 |
| **Mock 模式** | 内存 dict 模拟 DB | 无基础设施门槛，一键体验完整流程 |
| **Prompt 管理** | Python 函数返回 | 简单直接，版本控制友好 |
| **API 格式** | 统一 `{code, message, data}` | 前端消费一致性 |

---

## 🤝 待完善

- [ ] WebSocket 实时面试对话
- [ ] 语音输入 + 语音评分
- [ ] 多轮追问对话
- [ ] 面试回放与逐题复盘
- [ ] 候选人多次面试趋势分析
- [ ] 更多领域的题库扩充（安全、DevOps、数据工程等）

---

## 📄 License

MIT © [Jerry](https://github.com/Jerry1693464132)

---

<p align="center">
  <b>⭐ 如果这个项目对你有帮助，欢迎 Star</b><br/>
  <sub>Built with ❤️ for better interviews</sub>
</p>
