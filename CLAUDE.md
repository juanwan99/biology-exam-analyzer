# Claude Code 项目规范

## 重要警告

### API 使用限制

**严禁在 Python 代码中调用 Claude Code API！**

- Claude Code API 是专用 API，仅限于 Claude Code CLI 工具内部使用
- 在 Python、JavaScript 或任何其他代码中直接调用此 API 会导致账号被封禁
- 如需在代码中使用 AI 能力，请使用其他已配置的 API（如本项目中的 Gemini API）

### 当前项目 AI 配置

本项目使用两个 AI API：

**Gemini API（题目分析）：**
- API 端点: `GEMINI_API_BASE` (环境变量配置)
- API 密钥: `GEMINI_API_KEY` (环境变量配置)
- 分析模型: gemini-2.5-pro
- 快速评估模型: gemini-2.5-flash

**Claude API（难度评估特征提取）：**
- API 端点: `CLAUDE_API_BASE` (环境变量配置，AIProxy)
- API 密钥: `CLAUDE_API_KEY` (环境变量配置)
- 模型: claude-sonnet-4-20250514
- 用途: 6 维特征提取（feature_extractor.py）

---

## 项目结构

```
biology-exam-analyzer/
├── backend/           # FastAPI 后端
│   ├── main.py       # 主入口 + API 路由
│   ├── config.py     # 路径配置
│   ├── database.py   # 数据库连接
│   ├── models.py     # SQLAlchemy 模型
│   ├── gemini_analyzer.py    # Gemini AI 分析
│   ├── difficulty_pipeline.py # 难度评估主控（v2 特征分析+规则评分）
│   ├── feature_extractor.py  # LLM 特征提取（6 维度）
│   ├── rule_scorer.py        # 规则评分引擎（加权公式）
│   ├── difficulty_engine.py  # 难度评估引擎（旧，pipeline 调用）
│   ├── competency_analyzer.py # 素养分析
│   ├── knowledge_mapper.py   # 知识点映射
│   ├── document_processor.py # 文档处理（PDF/DOCX→图片）
│   ├── report_generator.py   # PDF 报告生成
│   ├── textbook_router.py    # 教材管理 API
│   ├── textbook_service.py   # 教材服务层
│   ├── exercise_router.py    # 题库 API
│   ├── knowledge_router.py   # 知识库 API
│   ├── quiz_router.py        # 组卷 API
│   ├── auth_router.py        # 认证 API
│   ├── logger.py             # 日志配置
│   └── exceptions.py         # 自定义异常
│   ├── archived/      # 归档代码（simulated_student, irt_estimator）
│   ├── scripts/       # 一次性脚本（批量导入/处理）
├── frontend/          # React + Vite 前端
│   ├── src/
│   │   ├── pages/     # 页面组件
│   │   ├── components/ # 通用组件
│   │   └── api/       # API 客户端
│   └── ...
├── database/          # 数据库初始化脚本
├── uploads/           # 上传文件存储
├── logs/              # 日志文件
├── prompts/           # AI 提示词模板
├── reports/           # 生成的报告
├── docker-compose.yml # Docker 配置
├── CLAUDE.md          # 项目规范（本文件）
└── TODO_OPTIMIZATION.md # 优化待办清单
```

## 开发环境

- 后端: Python 3.x + FastAPI + uvicorn
- 前端: React 18 + Vite + Tailwind CSS
- 数据库: PostgreSQL 16 + pgvector (Docker)
- 部署: Docker Compose
- 端口:
  - 前端: 3000
  - 后端: 8000
  - PostgreSQL: 5432

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

---

## 开发规范

### 1. 后端代码规范

#### 文件组织
- **单一职责**: 每个文件只负责一个明确的功能领域
- **新增 API**: 创建独立的 `xxx_router.py`，在 `main.py` 中通过 `app.include_router()` 注册
- **业务逻辑**: 不要写在路由函数里，抽到独立的 service 层或工具模块
- **避免 main.py 膨胀**: main.py 只负责应用初始化和路由注册，业务逻辑放到对应模块

#### 接口设计
- 统一使用 `/api/` 前缀
- RESTful 风格: GET 查询、POST 创建、PUT 更新、DELETE 删除
- 请求参数用 Pydantic 模型校验，不要直接 `json.loads()` 未验证的输入
- 统一响应格式:
  ```json
  {"success": true, "data": {...}}
  {"success": false, "error": "错误描述", "detail": "..."}
  ```

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

### 5. 已知技术债（参见 TODO_OPTIMIZATION.md）

开发新功能时如果涉及以下区域，顺手优化：
- `main.py` 过于臃肿（~1400 行）→ 新功能用独立 router 文件
- Session 存内存（active_tokens，已加 24h TTL）→ 新功能如需持久化状态用数据库
- ThreadPoolExecutor → 新的并发场景用 asyncio
- 无输入校验 → 新接口必须用 Pydantic 模型
- Word/PDF 处理器重复（word_parser_v2/word_splitter, pdf_parser/pdf_splitter/rule_splitter）→ 确认使用链路后统一
