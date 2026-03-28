# Prompt Quality Audit Report: 9-Subject Prompt Files

> snapshot: 2026-03-28
> Scope: /home/ubuntu/biology-exam-analyzer/prompts/{biology,chemistry,chinese,math,english,physics,history,geography,politics}/
> Files per subject: feature_extractor.txt, big_question_extractor.txt, split_prompt.txt, analysis_prompt.txt, competency_prompt.txt, report_insights_prompt.txt
> Total files audited: 54

---

## Executive Summary

Overall quality is **HIGH**. All 9 subjects have well-differentiated, domain-appropriate prompt files with correct curriculum standard alignment. No critical schema-breaking issues were found. The main findings are:

- **3 MEDIUM**: Template variable inconsistencies that could cause runtime issues in production (Docker)
- **1 MEDIUM**: JSON brace escaping inconsistency across subjects
- **5 LOW**: Missing file headers, minor variable naming inconsistencies

---

## 1. JSON Schema Consistency

### feature_extractor.txt

All 9 subjects output the **EXACT same JSON field set**:
`working_memory`, `working_memory_reason`, `reasoning_steps`, `steps_detail`, `chain_coupling`, `coupling_reason`, `trap_density`, `trap_reason`, `novelty`, `novelty_reason`, `knowledge_breadth`, `breadth_reason`, `bloom`, `bloom_distribution`, `bloom_reason`, `info_density`, `density_reason`, `representation_complexity`, `representation_reason`, `quality_score`, `quality_scientific`, `quality_normative`, `quality_language`, `quality_context`, `quality_sensitivity`, `teacher_comment`

**Result: PASS** -- No field name typos or missing fields detected.

### big_question_extractor.txt

All 9 subjects output the same structure: `subquestions[]`, `dependencies[]`, `global_features{}` plus the quality/bloom fields.

**Result: PASS** -- Schema is consistent across all subjects.

### competency_prompt.txt

Each subject correctly uses its own competency dimensions (see Section 3). All use the same output structure: competency dimensions with `{涉及, 具体维度, 权重, 分析说明}`, plus `primary_competency` and `competency_level`.

**Result: PASS**

---

## 2. Domain Terminology Accuracy

### Per-Subject Assessment

| Subject | Role | working_memory examples | chain_coupling examples | trap_density examples | novelty examples | knowledge_breadth examples | Result |
|---------|------|------------------------|------------------------|---------------------|-----------------|---------------------------|--------|
| biology | 生物命题审查专家 | 基因/系谱/细胞膜 | 基因工程全链 | 基因频率vs基因型频率 | 教材/变式/新情境 | 单知识点/跨考点/跨模块 | PASS |
| chemistry | 化学命题审查专家 | Na2O2/电离平衡 | 工艺流程全链 | 浓硫酸vs稀硫酸 | 教材/工业流程/前沿 | 单点/氧化还原+离子/有机+无机+实验 | PASS |
| chinese | 语文命题审查专家 | 字音字形/文言虚词 | 文言文断句-翻译-理解 | 古诗多解/虚词多义 | 经典/课外/非典型文体 | 单手法/阅读+写作/古今综合 | PASS |
| math | 数学命题审查专家 | 简单运算/公式代入/导数综合 | 解析几何全链推导 | 正负号/定义域/充要条件 | 教材/变式/竞赛背景 | 单点/函数+不等式/解析+向量+三角 | PASS |
| english | 英语命题审查专家 | 单词辨析/完形填空多条件 | 读后续写全链 | 近义词/熟词生义 | 常见话题/新话题/学术英语 | 单点/词汇+语法/听说读写综合 | PASS |
| physics | 物理命题审查专家 | 牛顿定律/多过程分析 | 多过程运动全链 | 方向/正负号/临界条件 | 教材/实际情境/前沿科技 | 单点/力学+运动学/电磁+力学+能量 | PASS |
| history | 历史命题审查专家 | 单一史实/多维度分析 | 论述题全链 | 时间混淆/因果倒置 | 教材/新史料/新学术观点 | 单事件/同时代跨领域/通史+专题+中外 | PASS |
| geography | 地理命题审查专家 | 气候类型/区域综合/全球尺度 | 自然-人文-可持续全链 | 南北半球/季风混淆 | 教材/新区域/热点事件 | 单点/气候+地形/自然+人文+区域 | PASS |
| politics | 思想政治命题审查专家 | 基本概念/多角度分析/开放论证 | 是什么-为什么-怎么办全链 | 易混概念/哲学原理多解 | 教材/时政改编/全新政策 | 单点/经济+政治/四模块综合 | PASS |

**Result: ALL PASS** -- No cross-subject contamination detected. All examples are domain-appropriate.

---

## 3. Curriculum Standard Alignment (competency_prompt.txt)

| Subject | Standard | Expected Competencies | Actual in Prompt | Result |
|---------|----------|----------------------|------------------|--------|
| biology | 2017/2020 | 生命观念 / 科学思维 / 科学探究 / 社会责任 | Correct (4 dimensions) | PASS |
| chemistry | 2017/2020 | 宏观辨识与微观探析 / 变化观念与平衡思想 / 证据推理与模型认知 / 科学探究与创新意识 / 科学态度与社会责任 | Correct (5 dimensions) | PASS |
| chinese | 2017/2020 | 语言建构与运用 / 思维发展与提升 / 审美鉴赏与创造 / 文化传承与理解 | Correct (4 dimensions) | PASS |
| math | 2017/2020 | 数学抽象 / 逻辑推理 / 数学建模 / 直观想象 / 数学运算 / 数据分析 | Correct (6 dimensions) | PASS |
| english | 2017/2020 | 语言能力 / 文化意识 / 思维品质 / 学习能力 | Correct (4 dimensions) | PASS |
| physics | 2017/2020 | 物理观念 / 科学思维 / 科学探究 / 科学态度与责任 | Correct (4 dimensions) | PASS |
| history | 2017/2020 | 唯物史观 / 时空观念 / 史料实证 / 历史解释 / 家国情怀 | Correct (5 dimensions) | PASS |
| geography | 2017/2020 | 人地协调观 / 综合思维 / 区域认知 / 地理实践力 | Correct (4 dimensions) | PASS |
| politics | 2017/2020 | 政治认同 / 科学精神 / 法治意识 / 公共参与 | Correct (4 dimensions) | PASS |

**Result: ALL PASS** -- Every subject lists the correct competencies per the 2017/2020 curriculum standard.

---

## 4. Template Variable Consistency

### 4.1 feature_extractor.txt and big_question_extractor.txt

All 9 subjects use `{question_block}` and `{qtype_hint}`. **PASS.**

### 4.2 competency_prompt.txt

All 9 subjects use `{question_text}` and `{knowledge_points}`. **PASS.**

### 4.3 split_prompt.txt

No template variables (image content is provided as separate message parts). **PASS.**

### 4.4 analysis_prompt.txt -- FINDING M01

| Subject | Has {question_type} | Has {section_header} | Result |
|---------|---------------------|---------------------|--------|
| biology | Yes | Yes | PASS |
| chemistry | **No** | Yes | **MEDIUM** |
| chinese | **No** | Yes | **MEDIUM** |
| math | **No** | Yes | **MEDIUM** |
| english | Yes | Yes | PASS |
| physics | **No** | Yes | **MEDIUM** |
| history | **No** | Yes | **MEDIUM** |
| geography | Yes | Yes | PASS |
| politics | Yes | Yes | PASS |

**Finding M01 (MEDIUM)**: 5 subjects (chemistry, chinese, math, physics, history) are missing `{question_type}` in analysis_prompt.txt. The backend (`gemini_analyzer.py:191`) always calls `.replace("{question_type}", question_type)` -- when the placeholder is absent, the replacement is a no-op and the question type information is silently lost. This means the LLM will not know the question type (single_choice, multiple_choice, fill_blank, short_answer) for these 5 subjects during analysis, which affects `total_score` inference and `option_difficulty_breakdown` generation.

### 4.5 report_insights_prompt.txt -- FINDING M02

| Subject | 6-dim variable name | Result |
|---------|-------------------|--------|
| biology | `{avg_per_dimension}` | baseline |
| chemistry | **`{feature_avg}`** | **MISMATCH** |
| chinese | `{avg_per_dimension}` | match |
| math | **`{feature_avg}`** | **MISMATCH** |
| english | `{avg_per_dimension}` | match |
| physics | **`{feature_avg}`** | **MISMATCH** |
| history | `{avg_per_dimension}` | match |
| geography | `{avg_per_dimension}` | match |
| politics | `{avg_per_dimension}` | match |

**Finding M02 (MEDIUM)**: Chemistry, math, and physics use `{feature_avg}` instead of `{avg_per_dimension}`. The backend `report_insights.py` currently uses a **hardcoded f-string prompt** and does NOT load from these template files. However, this is a real risk: when the backend migrates to use PromptLoader for report_insights (as it already does for feature_extractor and analysis_prompt), these 3 subjects will have an unsubstituted `{feature_avg}` placeholder while the backend passes `avg_per_dimension`.

---

## 5. JSON Brace Escaping Inconsistency -- FINDING M03

**Finding M03 (MEDIUM)**: The PromptLoader uses `str.replace()` (not `str.format()`), so `{{` is NOT interpreted as an escape -- it passes through as literal `{{` to the LLM.

| Subject | Brace style in all prompt files | JSON sent to LLM |
|---------|-------------------------------|-------------------|
| biology | `{{` double | `{{ "working_memory": ... }}` |
| chemistry | `{` single | `{ "working_memory": ... }` |
| chinese | `{{` double | `{{ "working_memory": ... }}` |
| math | `{` single | `{ "working_memory": ... }` |
| english | `{{` double | `{{ "working_memory": ... }}` |
| physics | `{` single | `{ "working_memory": ... }` |
| history | `{{` double | `{{ "working_memory": ... }}` |
| geography | `{{` double | `{{ "working_memory": ... }}` |
| politics | `{{` double | `{{ "working_memory": ... }}` |

Pattern: chemistry, math, physics use correct single braces `{}`; all others use double braces `{{}}`.

Each subject is internally consistent (a subject either uses all double or all single braces across all its files). LLMs are tolerant of `{{}}`, but it is technically incorrect JSON syntax in the prompt example. The correct style is single `{}` since PromptLoader uses str.replace.

---

## 6. Sensitivity Coverage

| Subject | Expected Sensitivity Level | Actual in quality_sensitivity | Result |
|---------|--------------------------|-------------------------------|--------|
| politics | Enhanced: political stance, ideology | "政治立场正确性、意识形态导向...民族宗教...外交立场" | PASS |
| history | Enhanced: political, ethnic, territorial | "政治立场偏向、民族关系...宗教争议、领土主权争议..." | PASS |
| chinese | Enhanced: value orientation, emotional | "政治敏感话题、价值观争议、不当情感表达...民族宗教争议" | PASS |
| biology | Standard + ethics | "政治敏感话题、民族宗教争议、不当伦理情境（如人体实验、基因编辑）" | PASS |
| chemistry | Standard + safety | "危险品制备/毒品合成/环境污染争议...安全隐患" | PASS |
| physics | Standard + safety | "核辐射/武器等敏感表述、安全隐患" | PASS |
| english | Standard + cultural | "政治敏感...文化偏见、性别歧视、宗教争议、种族问题" | PASS |
| geography | Standard + territorial | "领土主权争议（如边界标注）、民族宗教...环境政策争议" | PASS |
| math | Standard (minimal) | "争议性表述、可能引发误解的情境描述" | PASS |

### report_insights_prompt.txt Sensitivity

Politics has a dedicated "意识形态导向分析" section with explicit warning label. History has time-space coverage and source analysis sections. Both are appropriate.

**Result: ALL PASS**

---

## 7. Cross-Subject Contamination Check

Verified: no biology-specific terms (基因, 细胞, 光合作用) appear in non-biology prompts. No subject name mismatches detected across any files.

**Result: PASS** -- No cross-contamination detected.

---

## 8. File Header Consistency -- FINDING L01

**Finding L01 (LOW)**: Comment headers (# Subject: / # Purpose: / # Source: / # Variables:) are present in all 6 files for: biology, english, geography, politics.

Missing from ALL 6 files for: chemistry, chinese, math, physics, history (30 files total).

---

## 9. Detailed Finding Summary

| ID | Severity | Category | File(s) | Description | Impact | Recommended Action |
|----|----------|----------|---------|-------------|--------|-------------------|
| M01 | MEDIUM | template-var | chemistry, chinese, math, physics, history: analysis_prompt.txt | Missing `{question_type}` placeholder | LLM loses question type info for 5 subjects during analysis, affecting score inference and option breakdown | Add `{question_type}` placeholder to these 5 files |
| M02 | MEDIUM | template-var | chemistry, math, physics: report_insights_prompt.txt | Uses `{feature_avg}` instead of `{avg_per_dimension}` | No current runtime impact (hardcoded prompt), but will break on migration to PromptLoader | Rename `{feature_avg}` to `{avg_per_dimension}` in 3 files |
| M03 | MEDIUM | json-format | biology, chinese, english, history, geography, politics: feature_extractor, big_question_extractor, competency_prompt, report_insights_prompt | Double-brace `{{}}` instead of single `{}` for JSON delimiters | LLM receives `{{ }}` instead of `{ }` as JSON example; functional but incorrect | Standardize to single braces `{}` across all files |
| L01 | LOW | documentation | chemistry, chinese, math, physics, history: all 6 files each (30 files) | Missing comment headers | Reduced maintainability | Add headers matching biology/english/geography/politics pattern |
| L02 | LOW | template-var | chemistry, chinese, math, physics, history: analysis_prompt.txt | Missing labeled `**分节信息**：{section_header}` first line | Minor: section_header substituted but unlabeled in prompt | Standardize presentation line |

---

## 10. Per-Subject Summary

| Subject | feature_extractor | big_question_extractor | split_prompt | analysis_prompt | competency_prompt | report_insights_prompt | Overall |
|---------|------------------|----------------------|-------------|----------------|------------------|----------------------|---------|
| biology | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| chemistry | PASS* | PASS* | PASS | M01 | PASS* | M02 | **ISSUES (M01+M02)** |
| chinese | PASS | PASS | PASS | M01 | PASS | PASS | **ISSUES (M01)** |
| math | PASS* | PASS* | PASS | M01 | PASS* | M02 | **ISSUES (M01+M02)** |
| english | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| physics | PASS* | PASS* | PASS | M01 | PASS* | M02 | **ISSUES (M01+M02)** |
| history | PASS | PASS | PASS | M01 | PASS | PASS | **ISSUES (M01)** |
| geography | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| politics | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |

*PASS* = functionally correct but uses single braces (different style from majority)

### Clean subjects (4): biology, english, geography, politics
### Subjects with issues (5): chemistry (M01+M02), chinese (M01), math (M01+M02), physics (M01+M02), history (M01)

---

## 11. Recommendations

### Priority 1 (MEDIUM -- fix before next deployment)

1. **M01**: Add `{question_type}` to analysis_prompt.txt for chemistry, chinese, math, physics, history. The backend always passes this variable; without the placeholder, question type information is lost for these subjects. Suggested insertion: add a line like `**题型**：{question_type}` near the `{section_header}` line.

2. **M02**: Rename `{feature_avg}` to `{avg_per_dimension}` in report_insights_prompt.txt for chemistry, math, physics. Prevents future breakage when migrating to PromptLoader.

3. **M03**: Standardize JSON brace style. Since PromptLoader uses str.replace (not str.format), single braces `{}` are correct. Convert biology, chinese, english, history, geography, politics from `{{}}` to `{}` for JSON delimiters. Alternatively, convert the minority (chemistry, math, physics) to `{{}}` -- but single braces are technically more correct.

### Priority 2 (LOW -- maintainability)

4. **L01**: Add comment headers to all files in chemistry, chinese, math, physics, history directories (30 files). Copy the 4-line pattern from biology/english/geography/politics.

5. **L02**: Standardize the `{section_header}` presentation line across all analysis_prompt.txt files.
