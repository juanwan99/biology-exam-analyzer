# 多学科扩展设计文档 — 从生物到化学/历史/语文

> snapshot: 2026-03-28
> 状态: 设计确认（用户逐段审批通过 §1-§4）

## §0 覆盖声明

本设计扩展 biology-exam-analyzer 为通用考试分析平台。选择题/大题评分引擎（v3/v3.1）完全不变，通过 Subject 抽象层实现多学科支持。

## §1 核心架构：Subject 抽象层

在数据库和 API 之间插入 Subject 概念，贯穿全链路：

```
请求(subject="chemistry")
  → API 路由(透传 subject)
  → Pipeline(按 subject 加载 prompt + calibration)
  → LLM(学科专用 prompt)
  → 评分(共享引擎, 学科权重可选覆盖)
  → 报告(学科术语)
```

### 数据库变更

新增 `subjects` 表：
```sql
CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,      -- "biology", "chemistry", "history", "chinese"
    display_name VARCHAR(100) NOT NULL,     -- "生物", "化学", "历史", "语文"
    config_json JSONB DEFAULT '{}',         -- 学科专属配置（素养维度、权重覆盖等）
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO subjects (name, display_name, config_json) VALUES
('biology', '生物', '{"competencies": ["生命观念", "科学思维", "科学探究", "社会责任"]}'),
('chemistry', '化学', '{"competencies": ["宏观辨识与微观探析", "变化观念与平衡思想", "证据推理与模型认知", "科学探究与创新意识", "科学态度与社会责任"]}'),
('history', '历史', '{"competencies": ["唯物史观", "时空观念", "史料实证", "历史解释", "家国情怀"]}'),
('chinese', '语文', '{"competencies": ["语言建构与运用", "思维发展与提升", "审美鉴赏与创造", "文化传承与理解"]}');
```

现有表加 `subject_id` 外键：
- textbook_chapters: `ADD COLUMN subject_id INTEGER REFERENCES subjects(id) DEFAULT 1`
- exercise_bank: `ADD COLUMN subject_id INTEGER REFERENCES subjects(id) DEFAULT 1`
- knowledge_points: `ADD COLUMN subject_id INTEGER REFERENCES subjects(id) DEFAULT 1`
- exam_history: `ADD COLUMN subject_id INTEGER REFERENCES subjects(id) DEFAULT 1`

DEFAULT 1 = 生物（向后兼容，现有数据自动归入生物）。

### 不变的部分

- compute_difficulty() 公式完全不动
- find_critical_path / aggregate_big_question 完全不动
- calibration.py 逻辑不动（只是按学科加载不同 model 文件）
- prediction_service.py 完全不动
- report_data.py / report_generator.py 完全不动

## §2 Prompt 外置化

当前 13+ 个 prompt 全部硬编码在 Python 源码里。改为文件加载：

```
prompts/
├── biology/
│   ├── feature_extractor.txt
│   ├── big_question_extractor.txt
│   ├── split_prompt.txt
│   ├── analysis_prompt.txt
│   ├── competency_prompt.txt
│   └── report_insights_prompt.txt
├── chemistry/
│   └── (同结构，化学专用措辞)
├── history/
│   └── (同结构，历史专用措辞)
├── chinese/
│   └── (同结构，语文专用措辞)
└── _base/
    └── (共享模板骨架，学科 prompt 可继承覆盖)
```

### PromptLoader 设计

```python
class PromptLoader:
    def __init__(self, subject: str, prompts_dir: str = "prompts"):
        self.subject = subject
        self.prompts_dir = Path(prompts_dir)

    def load(self, prompt_name: str, **kwargs) -> str:
        # 优先加载学科专用，fallback 到 _base
        subject_path = self.prompts_dir / self.subject / f"{prompt_name}.txt"
        base_path = self.prompts_dir / "_base" / f"{prompt_name}.txt"
        path = subject_path if subject_path.exists() else base_path
        template = path.read_text(encoding="utf-8")
        return template.format(**kwargs)
```

- prompt 文件不入数据库（纯文本，方便 git diff 和人工审阅）
- 每个 prompt 文件头部注释声明所需变量
- 找不到学科专用文件时 fallback 到 _base/

## §3 学科适配的具体改动

### 评分模型策略

统一 6 维度（working_memory / reasoning_steps / chain_coupling / trap_density / novelty / knowledge_breadth），靠 LLM prompt 引导在不同学科语境下打分。评分引擎零改动。

如果校准验证发现某学科系统性偏差，再升级为学科定制维度（rule_scorer.py 预留 weights_override 参数）。

### HARD-COUPLED 文件改动

| 文件 | 改法 |
|------|------|
| feature_extractor.py | build_feature_prompt() / build_big_question_prompt() 改为从 PromptLoader 加载；extract_features() 增加 subject 参数透传 |
| competency_analyzer.py | 4 个生物素养硬编码 → 从 subjects.config_json 读取学科素养维度列表；prompt 从文件加载 |
| knowledge_mapper.py | 删除 TEXTBOOK_STRUCTURE / KEYWORD_MAPPING 两个硬编码 dict → 改为查 textbook_chapters 表 |
| report_insights.py | prompt 从文件加载，{subject_name} 替换 |

### SOFT-COUPLED 文件改动

| 文件 | 改法 |
|------|------|
| difficulty_pipeline.py | _evaluate_single() 从 question dict 读 subject，透传给 extractor |
| gemini_analyzer.py | split/analysis prompt 从 PromptLoader 加载 |
| quiz_service.py | 教师角色 prompt 从文件加载 |
| rule_scorer.py | 权重不动；预留 weights_override 参数供未来学科定制 |

### API 层

- analysis_router.py 的上传/分析接口增加 subject 参数（默认 "biology" 向后兼容）
- 前端学科选择器（下拉框），选中后所有 API 请求带上 subject

## §4 化学试点验证策略

用 2026届高三3月4-5日考试-化学.pptx 做端到端验证。

### 验收标准（不需要校准数据）

- 拆题准确：化学选择题/大题正确分割
- 特征合理：选择题 working_memory 1-3，大题 3-5
- 评分区分度：简单识记题 < 5 分，复杂推断/工艺流程题 > 7 分
- 不崩溃：所有题都能出分，无 fallback 到默认值

### 后续学科扩展

化学验证通过后，历史和语文仅需：
1. 写学科专用 prompt 文件（6 个文件/学科）
2. 在 subjects 表插入一行
3. 用真实试卷验证

代码层面零改动（架构已通用化）。

## §5 不做的部分

- 不改评分公式（compute_difficulty 共享）
- 不做学科定制维度（先用统一 6 维 + prompt 引导）
- 不做学科独立校准（先用生物权重裸跑）
- 不做前端多学科 UI 重设计（仅加下拉选择器）
- 不做知识图谱跨学科建设（各学科独立）

## §6 实施顺序

Phase 1: 基础设施（Subject 表 + PromptLoader + API subject 参数）
Phase 2: Prompt 外置化（生物 prompt 提取到文件，验证现有功能不变）
Phase 3: 化学适配（化学 prompt + 端到端验证）
Phase 4: 历史适配（历史 prompt + 端到端验证）
Phase 5: 语文适配（语文 prompt + 端到端验证）
