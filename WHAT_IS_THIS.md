# biology-exam-analyzer（生物试卷分析器）

## 项目概述
高中生物试卷智能分析系统。上传 PDF/DOCX 试卷 → AI 拆题 + 分析 + 难度评估 + 分数预估。

## 技术栈
- 后端: FastAPI + PostgreSQL(pgvector) + Gemini API(分析) + Claude API(难度模拟)
- 前端: React 18 + Vite + Tailwind CSS
- 部署: Docker Compose

## 核心模块
- 文档处理: PDF/DOCX → 图片 → 题目提取
- AI 分析: Gemini 多模态（知识点、认知层级、素养）
- 难度量化: 题目特征提取(6维) + 加权规则评分 → 0-10 分制
- 分数预估: 难度-得分率映射 → 班级成绩预测
- 题库: 701 题，向量检索
- 教材管理: 教材解析 + 知识点映射
- 组卷: 按难度/知识点/题型自动组卷

## 端口
- 前端: 3000
- 后端: 8000
- PostgreSQL: 5432

## 当前状态（2026-03-12）
- 核心功能完整可用
- 难度 Pipeline 有已知 floor_hit 问题（中等题区分度不足）
- 安全加固已完成（路径穿越/认证/限流）

## 测试数据

### PostgreSQL (biology_edu)
- **exercise_bank**: 701 题（697 有答案），2021-2024 高考真题
  - 题型: 单选 529, 填空 94, 简答 49, 多选 29
  - 来源: 33 套卷（`exercise_sources` 表），含 2024 必修1/2、选必3 等
  - 字段: content, options, answer, explanation, difficulty_level, competency_scores, knowledge_point_ids
  - 旧难度分布: 77% 聚集在 0.60（区分度差，正是新 Pipeline 要解决的）
  - 查询: `SELECT * FROM exercise_bank WHERE answer != '' ORDER BY source_id`

### 试卷原件
- 查询命令: `ls ~/biology-exam-analyzer/uploads/` 或 `find ~/biology-exam-analyzer/ -name '*.zip' -o -name '*.pdf'`
