---
type: handoff
created: 2026-05-22 16:37:30
project_dir: C:\Users\Administrator\Documents\New project
remote_project_dir: /home/ubuntu/biology-exam-analyzer
topic: hunan-2025-gaokao-scored12-e2e
---

# Hunan 2025 Gaokao Scored-12 E2E Handoff

=== 生成块开始 ===
**task_id**: hunan-2025-gaokao-scored12-e2e-20260522
**topic**: 2025 湖南高考生物真题 Word 补逐题 12 分后的端到端验证
**project_dir**: C:\Users\Administrator\Documents\New project
**effective_tier**: T3
**gate_status**: projectctl unavailable in local Codex environment; manual evidence block used
**last_verified_evidence**: 2026-05-22 16:30:56 local response JSON check: questions=21, score_total=100.0, blocked_questions=Q19/Q21 points_sum_mismatch, report_error=null
**subject_hash**: 98D313F9A98C735CA81DA2147991B8769E3679BE68EA4C8848E1C34E32B233FA
**raw_output_hashes**: html=A32236BF8B20E4A411FCDD52C136471AA5F0BDA72B7B2936983EBC4417EB710A; response=5A8E159E6B6B2429825450ED03A9E36B7815D1901D679F98483F0FA79C230948; log=AA1AE6A88A5AB1AA561A1EDB412E6E7F4C547814F6366133F38FFCD1F747A773
**timestamp**: 2026-05-22 16:37:30 UTC+8
=== 生成块结束 ===

=== 自由备注开始 ===

## 1. 当前任务背景

用户提供的新测试文档是：

- 原始 Word：`C:\Users\Administrator\Downloads\2025年高考生物真题（湖南自主命题）（原卷版）.docx`
- 当前打开报告：`http://127.0.0.1:8877/hunan_2025_gaokao_scored12_e2e_20260522.html#deep-dives`

此前直接跑原始 Word 生成：

- `C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_e2e_20260522.html`
- 该报告暴露出全卷总分为 `98.0`，不是 100。
- 根因是第三大题原文只写了“本题共5小题，共60分”，没有明确每题 12 分。
- 系统让 LLM 推断题目总分，Q17 被推成 10 分并被接受为 valid，导致 24 + 16 + 10 + 48 = 98。

用户随后要求：“每个题目分配12分，改一下 word，然后重新测试。”

## 2. 本轮实际做了什么

没有覆盖原始下载文件，而是创建了一个明确分值的 Word 副本：

- 本机：`C:\Users\Administrator\Documents\New project\artifacts\2025_hunan_gaokao_biology_scored_12.docx`
- 远端：`/home/ubuntu/biology-exam-analyzer/uploads/2025_hunan_gaokao_biology_scored_12.docx`
- 容器：`/app/uploads/2025_hunan_gaokao_biology_scored_12.docx`

修改段落：

```text
原：三、非选择题：本题共5小题，共60分。
新：三、非选择题：本题共5小题，每小题12分，共60分。
```

修改验证：

```text
Word paragraph 88:
三、非选择题：本题共5小题，每小题12分，共60分。
SHA256:
98D313F9A98C735CA81DA2147991B8769E3679BE68EA4C8848E1C34E32B233FA
```

新建 E2E 脚本：

- 本机：`C:\Users\Administrator\Documents\New project\artifacts\hunan_2025_scored12_e2e_20260522.py`
- 远端：`/home/ubuntu/biology-exam-analyzer/artifacts/hunan_2025_scored12_e2e_20260522.py`
- 容器：`/tmp/hunan_2025_scored12_e2e_20260522.py`

脚本使用：

- `exam_id = "hunan_2025_gaokao_scored12_e2e_20260522"`
- `file_path = "/app/uploads/2025_hunan_gaokao_biology_scored_12.docx"`
- `mode = "deep"`
- `subject = "biology"`
- `generate_report = True`
- `report_mode = "full"`
- `reports_dir = "/app/reports"`

## 3. 端到端运行方式

远端启动命令曾第一次失败一次，因为从 `/tmp` 运行脚本时没有 `/app` 在 `PYTHONPATH`，错误为：

```text
ModuleNotFoundError: No module named 'deps'
```

随后用正确命令重跑：

```bash
cd /home/ubuntu/biology-exam-analyzer
nohup docker exec biology_backend bash -lc 'cd /app && PYTHONPATH=/app python /tmp/hunan_2025_scored12_e2e_20260522.py' \
  > artifacts/e2e_logs/hunan_2025_scored12_e2e_20260522.log 2>&1 < /dev/null &
```

日志路径：

- 本机：`C:\Users\Administrator\Documents\New project\artifacts\hunan_2025_scored12_e2e_20260522.log`
- 远端：`/home/ubuntu/biology-exam-analyzer/artifacts/e2e_logs/hunan_2025_scored12_e2e_20260522.log`

关键日志证据：

```text
[16:13:12] [分节检测] 识别到分节标题: 三、非选择题：本题共5小题，每小题12分，共60分。
[16:28:41] [报告数据] 聚合完成，总分=100.0
```

最终脚本输出：

```json
{
  "questions": 21,
  "report_url": "/api/reports/hunan_2025_gaokao_scored12_e2e_20260522.pdf",
  "html_report_url": "/api/reports/hunan_2025_gaokao_scored12_e2e_20260522.html",
  "report_error": null,
  "blocked_questions": [
    {"id": 19, "reason": "points_sum_mismatch"},
    {"id": 21, "reason": "points_sum_mismatch"}
  ],
  "failure_events": [
    {"stage": "difficulty", "severity": "blocked", "question_id": 19, "reason": "points_sum_mismatch"},
    {"stage": "difficulty", "severity": "blocked", "question_id": 21, "reason": "points_sum_mismatch"}
  ],
  "score_issue_questions": []
}
```

## 4. 新报告产物

本机：

- HTML：`C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.html`
- PDF：`C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.pdf`
- JSON：`C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.response.json`
- 浏览器 URL：`http://127.0.0.1:8877/hunan_2025_gaokao_scored12_e2e_20260522.html`

远端：

- HTML：`/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.html`
- PDF：`/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.pdf`
- JSON：`/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.response.json`

文件大小：

```text
hunan_2025_gaokao_scored12_e2e_20260522.html           709449 bytes
hunan_2025_gaokao_scored12_e2e_20260522.pdf            357366 bytes
hunan_2025_gaokao_scored12_e2e_20260522.response.json  2603524 bytes
```

关键哈希：

```text
HTML     A32236BF8B20E4A411FCDD52C136471AA5F0BDA72B7B2936983EBC4417EB710A
Response 5A8E159E6B6B2429825450ED03A9E36B7815D1901D679F98483F0FA79C230948
Log      AA1AE6A88A5AB1AA561A1EDB412E6E7F4C547814F6366133F38FFCD1F747A773
```

视觉截图：

- `C:\Users\Administrator\Documents\New project\artifacts\hunan_2025_scored12_visual_20260522\top.png`
- `C:\Users\Administrator\Documents\New project\artifacts\hunan_2025_scored12_visual_20260522\summary.png`
- `C:\Users\Administrator\Documents\New project\artifacts\hunan_2025_scored12_visual_20260522\deep-dives.png`

浏览器验证摘要：

```json
{
  "h1": "AI 审题与审卷质量诊断报告",
  "metrics": ["题目数21", "总分100.0", "元数据状态blocked", "LLM 调用63"],
  "summary": "当前存在 2 道阻断题（Q19, Q21），不得用推断难度或默认结论掩盖",
  "badText": false
}
```

静态扫描：

```text
未发现 undefined
未发现 NaN
未发现 商业报告 v1
未发现 锟 或 � 常见乱码标记
```

## 5. 当前验证结论

已解决：

1. Word 输入中第三大题逐题分值缺失的问题已通过副本补明确。
2. 新 E2E 报告总分已从 98.0 回到 100.0。
3. Q17 已从错误的 10 分回到 12 分。
4. Q17、Q18、Q20 已进入正常大题难度评估。
5. 报告中没有把失败题伪装成正常难度题；Q19/Q21 被显式 block。
6. 报告前端首屏和摘要区能正常渲染；没有发现明显乱码、NaN、undefined。

仍未解决：

1. Q19 仍因 `points_sum_mismatch` 被阻断。
2. Q21 仍因 `points_sum_mismatch` 被阻断。
3. `metadata_status` 在 response JSON 中为 `null`，但 HTML 展示为 `blocked`；后续可检查数据模型是否应在 JSON 顶层也写入状态。
4. 知识点映射仍有 23/112 未映射，日志显示如“同位素标记法”“分解者的分解作用”“条件反射的建立”等返回原始内容。当前它不阻断报告，但属于教材映射库覆盖问题。
5. 报告摘要中“另有 19 道人工优先复核题”可能过宽，建议后续优化复核分层，避免所有非阻断题都被提示为优先复核。

## 6. Q17-Q21 关键题结果

本机 response JSON 结构化检查结果：

```text
questions = 21
score_total = 100.0
blocked = Q19, Q21
llm_call_counts = {
  question_analysis: 21,
  feature_extraction: 16,
  competency_analysis: 21,
  big_question_feature_extraction: 5
}
```

逐题摘要：

```text
Q17 score=12.0 raw_difficulty=8.7  failed=false confidence=0.79 flags=[media_representation_adjustment]
Q18 score=12.0 raw_difficulty=10.0 failed=false confidence=0.75 flags=[]
Q19 score=12.0 raw_difficulty=null failed=true  reason=points_sum_mismatch confidence=0.0 flags=[big_question_structure_failed, points_sum_mismatch]
Q20 score=12.0 raw_difficulty=10.0 failed=false confidence=0.71 flags=[media_representation_adjustment]
Q21 score=12.0 raw_difficulty=null failed=true  reason=points_sum_mismatch confidence=0.0 flags=[big_question_structure_failed, points_sum_mismatch]
```

重要判断：

- 补“每小题12分”解决的是“题目总分来源不稳定/总分不守恒”问题。
- 它不能根治 Q19/Q21 的“大题小问分值不闭合”问题。
- Q19/Q21 的失败不是前端渲染问题，也不是 Word 拆题失败，而是 `big_question_feature_extraction` 返回的子结构分值合计无法通过校验。

## 7. 根因判断

当前流水线中有两套分值概念：

1. 题目总分 `total_score`：现在 Q17-Q21 都已是 12 分。
2. 大题内部小问/采分点 `points`：由 `big_question_feature_extraction` LLM 输出，并要求合计等于题目总分。

这次 Word 补分只修复了第 1 层。

Q19/Q21 卡在第 2 层：模型尝试给小问或采分点分配绝对分值，但原卷没有参考答案和评分细则，模型只能猜。猜出来的 `points_sum` 与 12 不闭合，于是后端正确地 fail-close。

所以现在的核心设计问题是：

```text
没有评分细则时，不应要求 LLM 输出绝对 points 并用 points_sum == total_score 作为硬条件。
```

应该改为：

```text
没有明确评分细则时，要求 LLM 输出相对权重 score_share，系统只校验 score_share sum ≈ 1.0。
需要展示分值时，再用可信 total_score * score_share 派生，并标注 allocation_source=inferred。
```

## 8. 下一步建议修复方案

优先级 P0：

1. 修改 `prompts/biology/big_question_extractor.txt`：
   - 区分“有明确评分细则”和“无评分细则”。
   - 无评分细则时禁止输出伪精确小问分值。
   - 输出 `score_share`，并声明 `allocation_source="inferred"`。

2. 修改 `backend/feature_extractor.py`：
   - `parse_big_question_features` 当前硬校验 `points_sum`。
   - 增加相对权重模式：当输入没有评分细则或小问绝对分值来源不可靠时，校验 `score_share_sum`，不要用 `points_sum_mismatch` 阻断。
   - 仅当题面/答案/评分细则明确给出 points 时，才使用 `points_sum == total_score` 硬阻断。

3. 修改 `backend/difficulty_pipeline.py` 或相关调用：
   - 将 `allocation_source` 传入难度分析和报告模型。
   - 如果使用相对权重推断，报告要显示“采分点权重为系统推断，不是官方评分细则”。

4. 增加测试：
   - 无评分细则、只有总分 12 的大题，LLM 返回 `score_share` 能成功。
   - 有评分细则、points 合计不等于 total_score 时仍必须 block。
   - Q19/Q21 类题不能生成假难度；要么正常相对权重模式通过，要么清晰失败。

优先级 P1：

1. 增加章节总分守恒测试：
   - 第三大题“5小题，每小题12分，共60分”必须使 Q17-Q21 全部为 12。
   - 全卷总分必须为 100。

2. 优化报告文案：
   - “Q19 大题结构未闭合”目前可读，但还不够精准。
   - 更建议写成：“系统已确认题目总分为12，但缺少官方小问/采分点分值；当前模型给出的小问分值合计不闭合，因此难度暂不出数。”

3. 检查 `metadata_status`：
   - HTML 能显示 blocked。
   - response JSON 的 `metadata_quality.status` 当前为 null，建议统一写入 `blocked/warning/pass`。

优先级 P2：

1. 教材知识点映射库补充：
   - 同位素标记法
   - 分解者的分解作用
   - 条件反射的建立
   - ABO血型系统
   - 植物开花信号的传导
   - 实验设计与分析

2. “人工优先复核题”分层：
   - 阻断题：必须先处理。
   - 低置信题：建议复核。
   - 普通题：只进入讲评参考，不应全部标成优先复核。

## 9. 不要做的事

1. 不要把 Q19/Q21 定向改成通过。
2. 不要为了报告好看而给失败题填默认难度。
3. 不要用真实得分率拟合难度；之前用户明确说这里测的是绝对难度。
4. 不要把 `points_sum_mismatch` 降级成普通 warning，除非已经实现“无评分细则相对权重模式”并能在报告中说明权重来源。
5. 不要覆盖原始 Word；继续用副本做测试。

## 10. 常用命令

查看新报告：

```text
http://127.0.0.1:8877/hunan_2025_gaokao_scored12_e2e_20260522.html
```

远端查看日志：

```bash
ssh jdcloud "cd /home/ubuntu/biology-exam-analyzer && tail -n 120 artifacts/e2e_logs/hunan_2025_scored12_e2e_20260522.log"
```

远端重新跑同一副本：

```bash
ssh jdcloud "cd /home/ubuntu/biology-exam-analyzer && docker cp uploads/2025_hunan_gaokao_biology_scored_12.docx biology_backend:/app/uploads/2025_hunan_gaokao_biology_scored_12.docx && docker cp artifacts/hunan_2025_scored12_e2e_20260522.py biology_backend:/tmp/hunan_2025_scored12_e2e_20260522.py"

ssh jdcloud "cd /home/ubuntu/biology-exam-analyzer && docker exec biology_backend bash -lc 'cd /app && PYTHONPATH=/app python /tmp/hunan_2025_scored12_e2e_20260522.py'"
```

同步报告回本机：

```powershell
scp jdcloud:/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.html "C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.html"
scp jdcloud:/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.pdf "C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.pdf"
scp jdcloud:/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.response.json "C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.response.json"
```

本机检查总分和阻断题：

```powershell
@'
import json
from pathlib import Path
p=Path(r'C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.response.json')
data=json.loads(p.read_text(encoding='utf-8'))
qs=data.get('questions', [])
meta=data.get('metadata_quality', {})
print('questions=', len(qs))
print('score_total=', sum(float((q.get('total_score') or q.get('analysis',{}).get('total_score') or 0)) for q in qs))
print('blocked=', meta.get('blocked_questions'))
for qid in [17,18,19,20,21]:
    q=next(q for q in qs if (q.get('id') or q.get('question_id'))==qid)
    d=q.get('difficulty') or {}
    print(qid, q.get('total_score') or q.get('analysis',{}).get('total_score'), d.get('raw_score'), d.get('analysis_failed'), d.get('failure_reason'), d.get('flags'))
'@ | python -
```

## 11. 当前工作树状态提示

本机工作树和远端工作树都很脏，包含大量历史未提交/未跟踪文件。不要随意 revert。

本机相关新增文件包括：

- `artifacts/2025_hunan_gaokao_biology_scored_12.docx`
- `artifacts/hunan_2025_scored12_e2e_20260522.py`
- `artifacts/hunan_2025_scored12_e2e_20260522.log`
- `artifacts/hunan_2025_scored12_visual_20260522/`
- `api/reports/hunan_2025_gaokao_scored12_e2e_20260522.html`
- `api/reports/hunan_2025_gaokao_scored12_e2e_20260522.pdf`
- `api/reports/hunan_2025_gaokao_scored12_e2e_20260522.response.json`
- `docs/plans/2026-05-22-hunan-2025-scored12-e2e-handoff.md`

远端相关新增文件包括：

- `/home/ubuntu/biology-exam-analyzer/uploads/2025_hunan_gaokao_biology_scored_12.docx`
- `/home/ubuntu/biology-exam-analyzer/artifacts/hunan_2025_scored12_e2e_20260522.py`
- `/home/ubuntu/biology-exam-analyzer/artifacts/e2e_logs/hunan_2025_scored12_e2e_20260522.log`
- `/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.html`
- `/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.pdf`
- `/home/ubuntu/biology-exam-analyzer/reports/hunan_2025_gaokao_scored12_e2e_20260522.response.json`

## 12. Suggested Prompt

```text
接手 biology-exam-analyzer 项目。请先阅读交接文档：

C:\Users\Administrator\Documents\New project\docs\plans\2026-05-22-hunan-2025-scored12-e2e-handoff.md

远端同路径：

/home/ubuntu/biology-exam-analyzer/docs/plans/2026-05-22-hunan-2025-scored12-e2e-handoff.md

当前目标：
1. 不要覆盖原始 Word，继续使用 scored_12 副本测试。
2. 核实最新报告：
   C:\Users\Administrator\Documents\New project\api\reports\hunan_2025_gaokao_scored12_e2e_20260522.html
   http://127.0.0.1:8877/hunan_2025_gaokao_scored12_e2e_20260522.html
3. 当前已验证：总分=100，Q17/Q18/Q20 正常，Q19/Q21 因 points_sum_mismatch 被显式 block。
4. 继续系统修复：没有评分细则时，big_question_feature_extraction 不应强制输出绝对 points，而应输出 score_share；只有官方评分细则明确 points 时才做 points_sum == total_score 硬校验。
5. 修复后重新跑 2025 湖南卷 scored_12 E2E，确认：
   - 全卷总分仍为 100；
   - Q19/Q21 不再因为伪精确 points_sum_mismatch 失败；
   - 若仍失败，报告必须清楚说明是 LLM 调用失败、结构化解析失败、评分细则缺失，还是渲染失败；
   - 不允许静默失败，不允许用默认难度掩盖问题。
6. 使用 codex-review skill 或 Claude MCP 对后端逻辑和前端报告做一轮审查，再给出证据。
```

=== 自由备注结束 ===
