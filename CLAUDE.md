# AI Mock Interview System

## 技术栈
- 后端框架：FastAPI + Uvicorn (async)
- 数据库：PostgreSQL 15 + pgvector 扩展
- 缓存/消息队列：Redis 7（Celery broker + 业务缓存）
- 异步任务：Celery 5 + celery[redis]
- LLM：DeepSeek API（chat/deepseek-chat 模型）
- Embedding：DashScope text-embedding-v3
- Agent：LangChain Tool Calling Agent
- ORM：SQLAlchemy 2.0 (async) + Alembic 迁移
- 部署：Docker Compose

## 目录结构
app/
├── main.py                 # FastAPI入口
├── core/                   # 配置、安全、依赖注入
│   ├── config.py           # pydantic-settings
│   ├── database.py         # async engine + session
│   └── deps.py
├── api/                    # 路由层
│   ├── v1/
│   │   ├── resume.py
│   │   ├── interview.py
│   │   ├── questions.py
│   │   ├── scoring.py
│   │   └── report.py
├── services/               # 业务逻辑层
│   ├── resume_parser.py
│   ├── profile_extractor.py
│   ├── question_generator.py
│   ├── scoring_engine.py
│   ├── report_builder.py
│   └── job_matching_agent.py
├── rag/                    # RAG链路
│   ├── embeddings.py       # DashScope封装
│   ├── vector_store.py     # pgvector CRUD
│   ├── retriever.py        # 混合检索
│   └── indexer.py          # 题库入库
├── agent/                  # LangChain Agent
│   ├── tools.py
│   ├── prompts.py
│   └── matching_agent.py
├── tasks/                  # Celery异步任务
│   ├── celery_app.py
│   ├── resume_tasks.py
│   ├── scoring_tasks.py
│   └── report_tasks.py
├── models/                 # SQLAlchemy ORM
├── schemas/                # Pydantic DTO
├── prompts/                # Prompt模板（带版本号）
└── tests/

## 编码规范
- 全量类型注解，Pydantic v2 定义所有请求/响应模型
- LLM调用统一走 app/core/llm_client.py（DeepSeek封装）
- Embedding调用统一走 app/rag/embeddings.py（DashScope封装）
- 所有异步任务通过Celery执行，API层不阻塞
- 每个Celery task必须有：重试策略、超时、失败回调、结构化日志
- Prompt模板集中管理在 app/prompts/，禁止硬编码在业务代码中
- 评分必须注入 reference_answer + key_points
- 数据库操作全部async，禁止同步阻塞调用

## 工作方式
- 每个模块实现前先输出设计方案，等我确认
- 每个模块必须附带pytest测试
- 遇到技术选型给出2-3个方案对比