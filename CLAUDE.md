# Claude Code 项目规范

## 重要警告

### API 使用限制

**严禁在 Python 代码中调用 Claude Code API！**

- Claude Code API 是专用 API，仅限于 Claude Code CLI 工具内部使用
- 在 Python、JavaScript 或任何其他代码中直接调用此 API 会导致账号被封禁
- 如需在代码中使用 AI 能力，请使用已配置的 API（AIProxy 中转）

### 当前项目 AI 配置

本项目通过 `llm_client.py` 统一管理 LLM 调用，内置双 provider fallback 链：

| 优先级 | Provider | 模型 | API 格式 | 认证 | 备注 |
|--------|----------|------|----------|------|------|
| 2（兜底） | deepseek | `deepseek-v4-pro` | OpenAI Chat | API Key | no_proxy=True 绕过 HTTPS_PROXY |

**统一入口**: `llm_client.llm_call(messages, max_tokens, temperature)`
**配置中枢**: `llm_config.py` 定义 Provider 列表 + `get_providers()` 过滤已配置 key
**并发控制**: 每 provider semaphore_limit=10，题目级并发由 `ANALYSIS_CONCURRENCY` 环境变量控制（默认 5）

> 400 Bad Request 不 fallback（prompt 问题），401/403 会 fallback。

---

## 项目结构

```
biology-exam-analyzer/
├── backend/
│   ├── main.py              # 入口（208 行）— 初始化 + 路由注册 + 全局异常处理
│   ├── config.py            # 路径配置（UPLOAD_DIR, LOG_DIR 等）
│   ├── database.py          # AsyncEngine + 连接池（pool_size=10）
│   ├── models.py            # 15 张表的 ORM 定义
│   ├── deps.py              # 惰性单例工厂（9 个服务对象）
│   ├── middleware.py         # RequestId 中间件
│   ├── exceptions.py        # 自定义异常
│   ├── logger.py            # 日志配置
│   ├── llm_config.py        # LLM 配置中枢（MODEL_PROVIDER 切换 Claude/GPT）
│   │
│   │   # === 路由模块（8 个） ===
│   ├── admin_router.py      # 管理后台（prompt/日志/报告/静态资源）
│   ├── analysis_router.py   # 核心分析（上传→拆分→AI分析→统计）— 1172 行
│   ├── auth_router.py       # 认证（bcrypt + 限流 + token）
│   ├── exercise_router.py   # 题库 CRUD + 搜索 — 778 行
│   ├── knowledge_router.py  # 知识库查询
│   ├── prediction_router.py # 成绩预测
│   ├── quiz_router.py       # 组卷
│   ├── textbook_router.py   # 教材管理（最大，1672 行，含向量处理）
│   │
│   │   # === AI/ML 服务 ===
│   ├── claude_client.py     # 兼容垫片（重导出 llm_client）
│   ├── feature_extractor.py # 特征提取（v3 扁平 + v3.1 大题结构化）
│   ├── rule_scorer.py       # 规则评分 v3 + v3.1 大题聚合（关键路径模型）
│   ├── difficulty_pipeline.py # 难度评估编排（v3.1 大题分流）
│   ├── difficulty_mapper.py # 难度映射（573 行）
│   ├── calibration.py       # Isotonic Regression 校准（未集成）
│   ├── competency_analyzer.py # 素养分析
│   ├── knowledge_mapper.py  # 知识点映射（501 行）
│   │
│   │   # === 文档处理 ===
│   ├── document_processor.py # PDF/DOCX→图片（602 行）
│   ├── rule_splitter.py     # 规则拆题（963 行）
│   ├── pdf_splitter.py      # PDF 拆分
│   ├── pdf_parser.py        # PDF 解析
│   ├── word_splitter.py     # DOCX 拆分
│   ├── word_parser_v2.py    # Word 精确解析器 v2（图文关联）
│   │
│   │   # === 报告生成 ===
│   ├── report_generator.py  # PDF 报告渲染（967 行）
│   ├── report_data.py       # 报告数据聚合层（纯数据转换，无 LLM）
│   ├── report_insights.py   # 报告 LLM 分析层（GPT 5.4 生成综合分析文本）
│   │
│   │   # === 业务服务 ===
│   ├── session_manager.py   # 内存 Session（30min TTL）
│   ├── credits_service.py   # 积分服务（对接 momowan.xyz 主站 zhixue-server）
│   ├── chapter_locator.py   # 章节定位服务（页码→章节）
│   ├── task_registry.py     # 异步任务状态（未集成）
│   ├── textbook_service.py  # 教材服务层（801 行）
│   ├── textbook_parser_v2.py # 教材解析器 v2
│   ├── prediction_service.py # 预测服务层（530 行）
│   ├── quiz_service.py      # 组卷服务层
│   ├── vector_service.py    # pgvector 向量搜索（450 行）
│   ├── gaokao_extractor.py  # 高考真题提取器 v1
│   ├── gaokao_extractor_v2.py # 高考真题提取器 v2
│   ├── utils.py             # 题型推断
│   │
│   ├── archived/            # 归档（simulated_student, irt_estimator）
│   ├── scripts/             # 一次性脚本（14 个：批量导入/处理/诊断/向量化）
│   ├── test_core_modules.py      # 单元测试（37 个：utils/session/calibration/feature/scorer）
│   ├── test_feature_difficulty.py # 单元测试（28 个：特征提取+难度评分）
│   ├── test_llm_client.py         # 单元测试（14 个：fallback 链 + 格式转换）
│   ├── test_report_data.py       # 单元测试（5 个：报告数据聚合）
│   ├── test_report_insights.py   # 单元测试（3 个：报告 LLM 分析）
│   ├── test_report_render.py     # 单元测试（14 个：报告渲染）
│   └── test_weighted_statistics.py # 单元测试（14 个：加权统计）
│
├── frontend/src/
│   ├── App.jsx              # 路由 + 导航 + ErrorBoundary
│   ├── main.jsx             # 入口
│   ├── api/axios.js         # HTTP 客户端（token 注入 + 错误拦截）
│   ├── pages/               # 7 个页面组件
│   │   ├── AnalyzerPage.jsx       # 主页：试卷上传+分析
│   │   ├── ExercisePage.jsx       # 题库浏览
│   │   ├── QuizGeneratorPage.jsx  # 组卷
│   │   ├── TextbookPage.jsx       # 教材管理
│   │   ├── HistoryDataPage.jsx    # 历史数据
│   │   ├── CorrectionPage.jsx     # 纠错
│   │   └── AdminPage.jsx          # 管理后台（含 5 个 Tab 子组件）
│   │       └── admin/ (PromptsTab, UsersTab, ExercisesTab, LogsTab, TextbookTab)
│   └── components/          # 5 个复用组件
│       ├── ErrorBoundary.jsx
│       ├── ResultDisplay.jsx
│       ├── ExamStatistics.jsx
│       ├── ExamStatisticsEnhanced.jsx
│       └── ScorePrediction.jsx
├── database/init/           # PostgreSQL 初始化脚本
├── prompts/                 # AI 提示词模板
├── docker-compose.yml
├── CLAUDE.md
└── WHAT_IS_THIS.md
```

## 开发环境

- 后端: Python 3.x + FastAPI + uvicorn
- 前端: React 18 + Vite + Tailwind CSS + Lucide React
- 数据库: PostgreSQL 16 + pgvector (Docker)
- 部署: Docker Compose
- 端口（宿主机映射）:
  - 前端: 127.0.0.1:**3001** → 容器 80 (nginx)
  - 后端: 127.0.0.1:**8001** → 容器 8000 (uvicorn)
  - PostgreSQL: **5432** (直接暴露)

## 常用命令

```bash
# Docker 方式启动全部服务
cd /home/ubuntu/biology-exam-analyzer && docker-compose up -d

# 仅启动数据库
docker-compose up -d postgres

# 查看日志
docker logs -f biology_backend
docker logs -f biology_frontend

# 重启后端（代码修改后）
docker-compose restart backend

# 重建镜像（依赖变更后）
docker-compose up -d --build backend
```

## 数据库

- 用户: biology
- 密码: biology123
- 数据库: biology_edu
- 连接串: postgresql://biology:biology123@localhost:5432/biology_edu

### 表清单（15 张）

TextbookVersion, TextbookChapter, TextbookContent, KnowledgePoint,
ExerciseSource, ExerciseBank, AdminUser, OperationLog, Resource,
TextbookPage, TextbookChunk, ExamHistory, QuestionPerformance,
DifficultyMapping, ScorePrediction

---

## 开发规范

### 1. 后端代码规范

#### 文件组织
- **单一职责**: 每个文件只负责一个明确的功能领域
- **新增 API**: 创建独立的 `xxx_router.py`，在 `main.py` 中通过 `app.include_router()` 注册
- **业务逻辑**: 不要写在路由函数里，抽到独立的 service 层或工具模块
- **避免 main.py 膨胀**: main.py 只负责应用初始化和路由注册，业务逻辑放到对应模块
- **LLM 调用**: 统一通过 `llm_client.llm_call()` 调用，fallback 链自动处理；`claude_client` 为兼容垫片

#### 接口设计
- 统一使用 `/api/` 前缀
- RESTful 风格: GET 查询、POST 创建、PUT 更新、DELETE 删除
- 请求参数用 Pydantic 模型校验，不要直接 `json.loads()` 未验证的输入
- 统一响应格式:
  ```json
  {"success": true, "data": {...}}
  {"success": false, "error": "错误描述", "detail": "..."}
  ```

#### 路由前缀

| Router | 前缀 |
|--------|------|
| analysis_router | `/api/` (手动) |
| admin_router | `/api/` (手动) |
| auth_router | `/api/auth` |
| exercise_router | `/api/exercises` |
| knowledge_router | `/api/knowledge` |
| prediction_router | `/api/prediction` |
| quiz_router | `/api/quiz` |
| textbook_router | `/api/textbook` |

#### 错误处理
- 区分业务异常和系统异常，不要用裸 `except Exception` 吞掉所有错误
- API 限流(429)等可重试错误应实现重试逻辑
- 保留异常堆栈: `logger.exception("...")` 而非 `logger.error(str(e))`

#### 安全要求
- **路径操作**: 使用 `Path.resolve()` + 基目录校验，防止路径穿越
- **用户输入**: 所有外部输入必须校验（类型、长度、范围）
- **敏感信息**: API 密钥等通过环境变量传入，禁止硬编码，日志中不打印完整密钥
- **文件上传**: 校验文件类型和大小，仅允许白名单后缀（.pdf, .docx）

#### 日志规范
- `DEBUG`: 开发调试信息（变量值、中间状态）
- `INFO`: 关键业务节点（请求开始/完成、分析进度）
- `WARNING`: 异常但可恢复的情况（重试、降级）
- `ERROR`: 需要关注的错误（API 调用失败、数据异常）
- 生产环境日志级别设为 INFO，不要用 INFO 级别打印调试内容

### 2. 前端代码规范

#### 文件组织
- `pages/`: 页面级组件，对应路由
- `components/`: 可复用的 UI 组件
- `api/`: API 调用封装，统一在此处处理错误和 loading 状态
- 组件文件名使用 PascalCase: `AnalyzerPage.jsx`

#### 状态管理
- 简单状态用 `useState`，跨组件共享用 `useContext`
- API 请求统一通过 `api/axios.js` 发出
- loading/error 状态必须处理，给用户明确反馈

#### 样式
- 优先使用 Tailwind CSS 类名
- 避免内联样式对象，除非是动态计算值

### 3. 数据库规范

- 新增表必须在 `models.py` 中定义 SQLAlchemy 模型
- 表名使用 snake_case 复数形式: `exam_papers`, `analysis_results`
- 必须定义主键、创建时间(`created_at`)、更新时间(`updated_at`)
- 向量列如需语义搜索，建立 HNSW 索引
- 数据库初始化脚本放在 `database/init/` 目录

### 4. 提交与变更

- 功能变更前先说明改动范围，确认后再动手
- 改动涉及多个文件时，分步骤进行，每步可验证
- 新增功能应考虑对现有 API 的兼容性
- Docker 相关变更后需测试 `docker-compose up -d --build` 是否正常

### 5. 已知技术债

- ~~main.py 臃肿~~ → **已完成**（208 行，8 router 拆分）
- ~~P0 安全~~ → **已完成**（路径穿越/认证/限流/输入校验/异常脱敏）
- **文档处理器重复** — word_parser_v2/word_splitter/pdf_parser/pdf_splitter/rule_splitter 需统一
