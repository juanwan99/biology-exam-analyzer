# biology-exam-analyzer（试卷智能分析器）

## 项目概述
试卷智能分析系统。上传 PDF/DOCX 试卷 → AI 拆题 + 分析 + 难度评估 + 分数预估。

## 技术栈
- 后端: FastAPI + PostgreSQL(pgvector) + DeepSeek V4(首选) + DeepSeek/Qwen-VL(fallback)
- 前端: React 18 + Vite + Tailwind CSS + Lucide React
- LLM: DeepSeek 直连(首选) + AIProxy(fallback)，`llm_config.py` 一键切换 Claude/GPT
- 部署: Docker Compose

## 核心模块
- 文档处理: PDF/DOCX → 图片 → 题目提取（rule_splitter + document_processor）
- AI 分析: Claude Sonnet 多模态（知识点、认知层级、素养）— question_analyzer.py（类名历史遗留）
- 难度量化: 7 维特征提取(feature_extractor) + 非线性规则评分(rule_scorer) → 2-10 分制
- 报告生成: 数据聚合(report_data) + LLM 分析(report_insights) + PDF 渲染(report_generator)
- 分数预估: 难度-得分率映射 → 班级成绩预测
- 题库: 701 题，向量检索（pgvector）
- 教材管理: 教材解析 + 知识点映射
- 组卷: 按难度/知识点/题型自动组卷
- 积分: 对接 momowan.xyz 主站积分系统（credits_service.py）

## 端口（宿主机）
- 前端: 127.0.0.1:3001（容器内 nginx:80）
- 后端: 127.0.0.1:8001（容器内 uvicorn:8000）
- PostgreSQL: 5432

## 当前状态（2026-05-12）
- 核心功能完整可用（3 容器运行中）
- AI 已从 AI 全面切换为 Claude Sonnet 4.5（AIProxy 中转）
- 难度 Pipeline v2 已实现（7 维特征 + 非线性评分）
- 前端精简为单页应用 + momowan 设计系统
- 安全加固已完成（路径穿越/认证/限流）
- 单元测试 101 个（6 个测试文件）

## 测试数据

### PostgreSQL (biology_edu)
- **15 张表**: TextbookVersion/Chapter/Content/Page/Chunk, KnowledgePoint, ExerciseSource/Bank, AdminUser, OperationLog, Resource, ExamHistory, QuestionPerformance, DifficultyMapping, ScorePrediction
- **exercise_bank**: 701 题（697 有答案），2021-2024 高考真题
  - 题型: 单选 529, 填空 94, 简答 49, 多选 29
  - 来源: 33 套卷（`exercise_sources` 表）
  - 查询: `SELECT * FROM exercise_bank WHERE answer != '' ORDER BY source_id`

### 试卷原件
- 查询命令: `ls ~/biology-exam-analyzer/uploads/`
