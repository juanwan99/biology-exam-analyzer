# 项目总览 - 生物试卷智能分析系统 v2.0

**最后更新**: 2025-10-19
**版本**: 2.0 (难度评估 + 核心素养分析)
**状态**: ✅ 已完成，可用于生产环境

---

## 🎯 项目简介

本系统是一个基于AI的生物试卷智能分析平台，能够自动完成：
1. **文档解析**：支持PDF和DOCX格式
2. **题目拆分**：利用Gemini AI自动识别题目边界
3. **深度分析**：知识点、详细解析、答案、易错点
4. **难度评估**：4维度量化评分（快速/深度双模式）
5. **素养分析**：基于课程标准的4素养识别
6. **PDF报告**：6张可视化图表的质量评估报告

---

## 📊 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (React + Vite)                      │
│  - 文件上传                                                   │
│  - 模式选择（快速/深度）                                      │
│  - 报告生成选项                                               │
│  - 结果可视化展示                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP REST API
┌──────────────────────────┴──────────────────────────────────┐
│                   后端 (FastAPI + Python)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. DocumentProcessor (PDF/DOCX → 图片)              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 2. GeminiAnalyzer (题目拆分 + 逐题分析)              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 3. DifficultyEngine (难度评估 双模式)                │   │
│  │    - 规则引擎：关键词匹配                             │   │
│  │    - LLM精调：识别隐性条件（仅深度模式）             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 4. CompetencyAnalyzer (素养分析)                     │   │
│  │    - 基于课程标准（2017版2020修订）                  │   │
│  │    - 4大素养：生命观念、科学思维、科学探究、社会责任  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 5. ReportGenerator (PDF报告生成)                     │   │
│  │    - plotly可视化：6张图表                            │   │
│  │    - weasyprint: HTML → PDF                          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                   外部服务 (Gemini API)                      │
│  - 题目拆分                                                   │
│  - 知识点分析                                                 │
│  - 素养识别                                                   │
│  - 难度精调（深度模式）                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗓️ 开发进度

### Day 1-2: 核心引擎开发 ✅

**文件**: 3个核心Python模块

1. **difficulty_rules.json** (2,900行)
   - 必修1、必修2、选修1、选修2、选修3知识库
   - 6层认知层级（布鲁姆分类法）
   - 难度调节器（系谱图、实验设计等）

2. **competency_library.json** (500行)
   - 4大核心素养定义
   - 每个素养的子维度
   - 关键词和示例

3. **difficulty_engine.py** (450行)
   - `evaluate_difficulty()`: 规则引擎评估
   - `refine_with_llm()`: LLM精调
   - `evaluate_with_refinement()`: 双模式入口

4. **competency_analyzer.py** (200行)
   - `analyze_competency()`: 单题素养分析
   - `aggregate_exam_competencies()`: 全卷聚合

5. **report_generator.py** (682行)
   - 6个图表生成函数
   - `generate_pdf_report()`: PDF导出

**成果**:
- ✅ 规则库完整覆盖高中生物知识点
- ✅ 双模式架构（快速/深度）
- ✅ PDF报告生成框架

---

### Day 3: 后端API集成 ✅

**文件**: 1个修改，2个新增配置

1. **main.py** (backend/main.py:85-395)
   - 扩展 `/api/analyze` 接口（+2参数）
     - `mode: str = "fast"`
     - `generate_report: bool = False`
   - 新增 `/api/reports/{filename}` 下载接口
   - 8步完整流程集成

2. **docker-compose.yml**
   - 新增 `./backend/rules:/app/rules` 挂载
   - 新增 `./reports:/app/reports` 挂载

3. **prompts/** 目录
   - 同步 `difficulty_refine_prompt.txt`
   - 同步 `competency_analysis_prompt.txt`

**成果**:
- ✅ 后端功能完全打通
- ✅ Docker容器重新构建并运行
- ✅ API接口可用

---

### Day 4: 前端集成 ✅

**文件**: 2个React组件修改

1. **AnalyzerPage.jsx** (+110行)
   - 新增模式选择器（快速/深度）
   - 新增报告生成复选框
   - 优化加载提示（显示预估时间）
   - API调用添加2个参数

2. **ResultDisplay.jsx** (+215行)
   - 统计卡片：3列→4列（新增"评估模式"）
   - 新增报告下载区域
   - 新增素养分布汇总区域
   - 题目卡片头部：新增难度评分和素养标签
   - 新增难度详情展示（4维度）
   - 新增素养详情展示（权重分布）

**成果**:
- ✅ 前端UI完整实现
- ✅ Docker前端容器重新构建
- ✅ 系统完整可用

---

## 🎨 功能特性

### 1. 双模式难度评估

| 特性 | 快速模式 🚄 | 深度模式 🔬 |
|------|-----------|-----------|
| **评估方式** | 仅规则引擎 | 规则引擎 + AI精调 |
| **LLM调用** | 25次（仅素养） | 50次（素养25 + 难度25） |
| **预估耗时** | ~75秒 | ~150秒 |
| **准确度** | 中等 | 高 |
| **识别能力** | 显性特征 | 显性+隐性条件、干扰信息 |

### 2. 4维度难度量化

- **知识复杂度** (40%)：知识点数量、跨章节程度
- **认知层级** (30%)：布鲁姆6层分类（记忆→评价）
- **信息提取** (20%)：图表、系谱图、实验数据
- **推理步骤** (10%)：多步推导、综合分析

### 3. 4素养权重分析

基于《普通高中生物学课程标准（2017年版2020修订）》:
- **生命观念**: 结构与功能观、进化与适应观、稳态与平衡观、物质与能量观
- **科学思维**: 归纳与概括、演绎与推理、模型与建模、批判性思维
- **科学探究**: 问题、证据、解释、交流
- **社会责任**: 生态意识、健康生活、科学决策

### 4. PDF质量评估报告

6张可视化图表：
1. **难度变化曲线**: 折线图，横轴题号，纵轴难度
2. **难度分布统计**: 柱状图，简单/中等/困难占比
3. **维度雷达图**: 单题4维度分析
4. **素养覆盖饼图**: 4素养占比
5. **素养细分柱状图**: 素养权重分布
6. **难度梯度条形图**: 前/中/后段难度对比

---

## 📂 项目结构

```
agent_shenti/
├── backend/                           # 后端（Python）
│   ├── rules/                         # 规则库（JSON）
│   │   ├── difficulty_rules.json      # 难度评估规则（2,900行）
│   │   └── competency_library.json    # 素养库（500行）
│   ├── prompts/                       # Prompt模板
│   │   ├── difficulty_refine_prompt.txt
│   │   └── competency_analysis_prompt.txt
│   ├── main.py                        # FastAPI主文件 ⭐
│   ├── difficulty_engine.py           # 难度评估引擎 ⭐
│   ├── competency_analyzer.py         # 素养分析器 ⭐
│   ├── report_generator.py            # PDF报告生成器 ⭐
│   ├── gemini_analyzer.py             # Gemini API封装
│   ├── document_processor.py          # 文档处理器
│   ├── logger.py                      # 日志系统
│   ├── requirements.txt               # Python依赖
│   └── Dockerfile                     # Docker配置
│
├── frontend/                          # 前端（React）
│   ├── src/
│   │   ├── pages/
│   │   │   ├── AnalyzerPage.jsx       # 分析页面 ⭐
│   │   │   └── AdminPage.jsx          # 管理后台
│   │   ├── components/
│   │   │   └── ResultDisplay.jsx      # 结果展示 ⭐
│   │   ├── main.jsx                   # React入口
│   │   └── App.jsx                    # 路由配置
│   ├── package.json                   # Node依赖
│   ├── vite.config.js                 # Vite配置
│   └── Dockerfile                     # Docker配置
│
├── prompts/                           # Prompt挂载目录（Docker）
├── reports/                           # PDF报告输出目录（Docker）
├── logs/                              # 日志目录（Docker）
├── uploads/                           # 临时上传目录（Docker）
│
├── docker-compose.yml                 # 容器编排配置
├── .env                               # 环境变量（GEMINI_API_KEY）
│
├── DAY1_PROGRESS.md                   # Day 1 进度文档
├── DAY3_COMPLETED.md                  # Day 3 完成报告
├── DAY4_COMPLETED.md                  # Day 4 完成报告
├── DUAL_MODE_GUIDE.md                 # 双模式使用指南
└── PROJECT_OVERVIEW.md                # 本文档
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone <repo-url>
cd agent_shenti

# 配置环境变量
cp .env.example .env
# 编辑.env，填入GEMINI_API_KEY
```

### 2. 启动服务

```bash
# 启动Docker容器
docker-compose up -d

# 查看容器状态
docker-compose ps

# 查看后端日志
docker-compose logs -f backend
```

### 3. 访问系统

- **前端**: http://localhost:3000
- **后端**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

### 4. 使用流程

1. 打开前端页面
2. 上传PDF或DOCX试卷文件
3. 选择评估模式（快速/深度）
4. 可选：勾选"生成PDF报告"
5. 点击"开始分析"
6. 等待处理（快速~75秒，深度~150秒）
7. 查看结果（难度、素养、分析）
8. 下载PDF报告（如果生成）

---

## 📡 API接口

### 1. 分析接口

**请求**: `POST /api/analyze`

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@exam.pdf" \
  -F "mode=fast" \
  -F "generate_report=false"
```

**参数**:
- `file`: PDF或DOCX文件（必需）
- `mode`: 评估模式，"fast"或"deep"（默认"fast"）
- `generate_report`: 是否生成PDF，true或false（默认false）

**响应**: JSON
```json
{
  "questions": [...],
  "total_count": 25,
  "processing_time": 85.3,
  "competency_summary": {...},
  "report_url": "/api/reports/xxx.pdf",
  "mode": "fast"
}
```

### 2. 报告下载接口

**请求**: `GET /api/reports/{filename}`

```bash
curl -O http://localhost:8000/api/reports/20251019_143022.pdf
```

**响应**: PDF文件流

---

## 🧪 测试用例

### 测试文件
- **2025年山东生物高考卷**: 25道题，综合难度中等
- **预期耗时**: 快速模式75秒，深度模式150秒

### 快速模式测试
```bash
# 1. 上传文件，选择快速模式，不生成报告
# 预期：返回难度评分，基于规则引擎

# 2. 验证返回结果
# - questions[0].difficulty.final_difficulty 存在
# - questions[0].difficulty.knowledge_complexity 存在
# - questions[0].competency.primary_competency 存在
# - report_url 为 null
```

### 深度模式测试
```bash
# 1. 上传文件，选择深度模式，生成报告
# 预期：返回AI精调后的难度评分 + PDF下载链接

# 2. 验证返回结果
# - questions[0].difficulty.difficulty_factors 存在（如 ["隐性条件识别"]）
# - report_url 不为 null
# - 访问 report_url 可下载PDF

# 3. 验证PDF报告
# - 包含6张图表
# - 文字清晰可读
# - 图表正确渲染
```

---

## ⚙️ 配置说明

### 环境变量 (.env)

```bash
# Gemini API配置
GEMINI_API_KEY=your_api_key_here
GEMINI_API_BASE=https://generativelanguage.googleapis.com  # 可选

# 管理后台密码
ADMIN_PASSWORD=admin123

# 日志级别
LOG_LEVEL=INFO
```

### Docker资源限制

```yaml
# docker-compose.yml
backend:
  deploy:
    resources:
      limits:
        cpus: '0.7'
        memory: 1400M

frontend:
  deploy:
    resources:
      limits:
        cpus: '0.3'
        memory: 600M
```

---

## 🔧 故障排查

### 问题1: 容器启动失败

**症状**: `docker-compose up -d` 后容器状态为Exited

**排查**:
```bash
# 查看容器日志
docker-compose logs backend

# 常见原因：
# 1. GEMINI_API_KEY未配置
# 2. 端口被占用（8000, 3000）
# 3. Docker内存不足
```

**解决方案**:
```bash
# 检查.env文件
cat .env

# 检查端口占用
netstat -an | grep 8000
netstat -an | grep 3000

# 释放Docker内存
docker system prune -a
```

### 问题2: Gemini API调用失败

**症状**: 分析时报错"Gemini API调用失败"

**排查**:
```bash
# 检查API Key是否有效
curl https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-exp:generateContent \
  -H "Content-Type: application/json" \
  -H "x-goog-api-key: YOUR_KEY" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}'
```

**解决方案**:
1. 验证API Key是否正确
2. 检查网络连接
3. 查看后端日志确认错误详情

### 问题3: PDF报告生成失败

**症状**: generate_report=true但report_url显示error

**排查**:
```bash
# 检查后端日志
docker-compose logs backend | grep "报告生成"

# 常见原因：
# 1. plotly图表渲染失败
# 2. weasyprint字体缺失
# 3. 磁盘空间不足
```

**解决方案**:
```bash
# 检查磁盘空间
df -h

# 清理旧报告
rm -rf reports/*.pdf

# 重新构建后端容器
docker-compose build --no-cache backend
```

---

## 📈 性能优化建议

### 当前性能
- 25题试卷：快速模式75秒，深度模式150秒
- LLM调用：快速25次，深度50次
- 内存占用：后端~800MB，前端~100MB

### 优化方向

**1. 并发化LLM调用**
- 现状：逐题串行调用
- 优化：批量并发调用（5题/批）
- 预期提升：耗时减少60%

**2. 结果缓存**
- 现状：每次都重新分析
- 优化：相同文件MD5哈希缓存
- 预期提升：重复分析秒级返回

**3. 流式响应**
- 现状：全部完成后返回
- 优化：WebSocket实时推送进度
- 用户体验：实时看到每道题分析结果

---

## 🔐 安全说明

### API安全
- ✅ 路径穿越防护（`/api/reports/{filename}`）
- ✅ 文件类型校验（仅PDF/DOCX）
- ✅ 文件大小限制（默认16MB）
- ✅ 管理后台密码保护

### 数据隐私
- ✅ 上传文件分析后自动删除
- ✅ 报告文件定期清理（可配置）
- ✅ 日志不记录文件内容
- ⚠️ Gemini API会接收题目文本（注意敏感信息）

---

## 📚 相关文档

- **Day 1-2 规则库开发**: `DAY1_PROGRESS.md`
- **Day 3 后端集成**: `DAY3_COMPLETED.md`
- **Day 4 前端集成**: `DAY4_COMPLETED.md`
- **双模式使用指南**: `DUAL_MODE_GUIDE.md`
- **API文档**: http://localhost:8000/docs

---

## 🤝 贡献指南

### 目录规范
- 后端代码：`backend/`
- 前端代码：`frontend/src/`
- 规则库：`backend/rules/`
- 文档：项目根目录

### 代码规范
- Python: PEP 8
- JavaScript: ESLint + Prettier
- 注释：中文，简洁明了
- 日志：使用统一logger

### 提交规范
```bash
# 格式
[类型] 简短描述

# 类型：
# feat: 新功能
# fix: Bug修复
# docs: 文档更新
# refactor: 重构
# perf: 性能优化

# 示例
[feat] 添加素养分析可视化展示
[fix] 修复PDF报告下载路径错误
[docs] 更新Day 4完成报告
```

---

## 📄 许可证

本项目仅供学习和研究使用。

---

## 📞 联系方式

- 项目地址: [GitHub Repository]
- Issue反馈: [Issues Page]
- 邮箱: [Contact Email]

---

**本文档最后更新**: 2025-10-19
**系统版本**: 2.0
**状态**: ✅ 生产可用
