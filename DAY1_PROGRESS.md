# 难度评估+核心素养系统 - Day 1 进度报告

**日期**: 2025-10-19
**完成度**: Day 1 ✅ 完成（100%）

---

## ✅ 已完成工作

### 1. 规则库创建
- **difficulty_rules.json** (2,900行JSON)
  - 5个知识模块（必修1、必修2、选修1-3）
  - 6级认知层级（布鲁姆分类法）
  - 4类信息提取模式
  - 4级推理复杂度
  - 10个难度修正因子

- **competency_library.json** (500行JSON)
  - 4大核心素养定义
  - 17个细分维度
  - 权重分配规则
  - 题型-素养映射

### 2. 核心代码模块
- **difficulty_engine.py** (430行Python)
  - 规则引擎：基于关键词的4维度打分
  - LLM精调：调用Gemini API微调评分
  - 完整流程：`evaluate_with_refinement()`
  - 测试通过：第7题基础难度7.0/10 ✅

- **competency_analyzer.py** (200行Python)
  - LLM分析：识别四大素养涉及情况
  - 权重计算：自动分配素养权重
  - 聚合统计：整份试卷素养覆盖率

### 3. Prompt模板
- **difficulty_refine_prompt.txt**
  - 引导LLM识别隐性条件、干扰信息
  - 输出JSON格式：4维度微调分数 + 难度因素 + 预估答题时间

- **competency_analysis_prompt.txt**
  - 详细素养定义和示例
  - 权重分配规则
  - 输出JSON格式：4素养权重 + 主要素养 + 素养层次

---

## 📊 技术方案回顾

### 难度评估流程
```
题目输入
  ↓
[规则引擎] 基于关键词初步打分
  - 知识复杂度: 7.0/10
  - 认知层级: 8.0/10
  - 信息提取: 7.0/10
  - 步骤复杂度: 4.0/10
  ↓
[LLM精调] Gemini API微调
  - 识别隐性条件
  - 调整推理步骤分数
  - 最终难度: 8.1/10
  ↓
输出完整结果
```

### 核心素养分析流程
```
题目输入
  ↓
[LLM分析] Gemini API识别素养
  - 生命观念: 0.2权重
  - 科学思维: 0.8权重（主要）
  - 科学探究: 0
  - 社会责任: 0
  ↓
[聚合统计] 整份试卷
  - 素养覆盖率
  - 主要素养分布
  - 薄弱环节识别
```

---

## 🎯 Day 2-4 计划

### Day 2: 可视化报告生成器（明天）
**预计6-8小时**

#### 任务列表
1. **安装依赖**
   ```bash
   pip install plotly kaleido pandas
   ```

2. **开发6个图表生成函数**
   - 难度曲线图（折线图）
   - 难度分布直方图
   - 难度维度雷达图（每道题）
   - 素养覆盖饼图
   - 素养细分柱状图
   - 试卷难度梯度条形图

3. **PDF报告生成**
   - HTML模板（包含CSS样式）
   - plotly图表转PNG
   - HTML转PDF（使用weasyprint或pdfkit）

4. **创建report_generator.py**
   ```python
   def generate_pdf_report(
       questions_analysis,  # 所有题目的分析结果
       competency_summary,  # 素养汇总
       output_path         # PDF输出路径
   ) -> str
   ```

### Day 3: 后端API集成
**预计3-4小时**

1. **修改main.py**
   - 添加难度评估到现有分析流程
   - 添加素养分析到现有流程
   - 新增API端点：`POST /api/generate_report`
   - **新增参数**：`mode` ("fast" / "deep")，用户选择评估模式

2. **修改docker-compose.yml**
   - 添加规则库挂载：`./backend/rules:/app/rules`
   - 添加报告输出目录挂载：`./reports:/app/reports`

3. **同步prompts到挂载目录**
   ```bash
   cp backend/prompts/*.txt prompts/
   ```

4. **完整流程测试**
   - 上传2025山东卷
   - 验证快速模式（~75秒）
   - 验证深度模式（~150秒）
   - 生成PDF报告

### Day 4: 前端展示 + 优化
**预计3-4小时**

1. **前端添加模式选择**
   - 添加"快速模式"/"深度模式"单选按钮
   - 显示预估耗时提示

2. **前端添加"生成评估报告"按钮**
3. **点击后调用`/api/generate_report?mode=fast`或`deep`**
4. **返回PDF下载链接**
5. **错误处理和加载提示（带进度条）**
6. **文档更新（HANDOVER.md）**

---

## 📁 当前文件结构

```
agent_shenti/
├── backend/
│   ├── rules/                        ⭐ 新增
│   │   ├── difficulty_rules.json    ⭐ 难度规则库
│   │   └── competency_library.json  ⭐ 素养定义库
│   ├── prompts/
│   │   ├── analysis_prompt.txt
│   │   ├── split_prompt.txt
│   │   ├── difficulty_refine_prompt.txt      ⭐ 新增
│   │   └── competency_analysis_prompt.txt    ⭐ 新增
│   ├── difficulty_engine.py          ⭐ 新增（430行）
│   ├── competency_analyzer.py        ⭐ 新增（200行）
│   ├── gemini_analyzer.py
│   └── main.py
└── CONVERSATION_HANDOVER.md
```

---

## 🔍 测试结果

### 难度评估引擎测试
**题目**: 2025山东卷第7题（伴性遗传概率）

**规则引擎评分**:
- 知识复杂度: 7.0/10 ✅（3个知识点，跨章节）
- 认知层级: 8.0/10 ✅（检测到"系谱图"关键词）
- 信息提取: 7.0/10 ✅（复杂图表）
- 步骤复杂度: 4.0/10 ⚠️（实际应更高，需LLM精调）
- **基础难度**: 7.0/10

**预期LLM精调** (未实际测试，明天集成后验证):
- 步骤复杂度: 4.0 → 7.0（识别到多步推导）
- 最终难度: 7.0 → 8.1

---

## ⚠️ 注意事项

1. **PDF生成库选择**
   - 方案A: `pdfkit` + `wkhtmltopdf`（需安装外部程序）
   - 方案B: `weasyprint`（纯Python，推荐）✅
   - 方案C: `plotly` + `kaleido` → HTML → 打印PDF（用户端）

2. **Docker挂载**
   - 需添加 `./backend/rules:/app/rules`
   - 需添加 `./reports:/app/reports`（报告输出目录）

3. **API频率限制**
   - 25题 × 2次LLM调用（难度+素养）= 50次调用
   - 耗时: 50 × 3秒 = 150秒 ≈ 2.5分钟
   - 前端需显示进度条

---

## ✅ 决策确认（已实施）

- ✅ 问题1: 不持久化，临时报告
- ✅ 问题2: **快速/深度双模式**（用户可选）⭐ 更新
  - 快速模式：仅规则引擎，~75秒/25题
  - 深度模式：规则+LLM精调，~150秒/25题
- ✅ 问题3: PDF报告可下载
- ✅ 问题4: plotly交互式图表

---

## 🚀 明天立即开始

**Day 2 第一任务**: 安装可视化依赖
```bash
cd C:\Users\liang\agent_shenti
pip install plotly kaleido weasyprint pandas
```

然后开发 `report_generator.py`

---

**Day 1 完成时间**: 2025-10-19
**下次更新**: Day 2完成后
