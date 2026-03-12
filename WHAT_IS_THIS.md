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
- 难度量化: 模拟学生(12人×4档) + 2PL IRT 拟合 → 0-10 分制
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
