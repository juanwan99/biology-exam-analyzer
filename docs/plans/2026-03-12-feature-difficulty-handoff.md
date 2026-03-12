---
type: handoff
created: 2026-03-12 15:01:05
design: docs/plans/2026-03-12-feature-difficulty-design.md
plan: docs/plans/2026-03-12-feature-difficulty-plan.md
---

## 约束与偏好

**T3 流程**。单 Chunk，6 Tasks，单批次执行。

- 项目路径: `/home/ubuntu/biology-exam-analyzer/`（jdcloud，SSH 别名 `jdcloud`，用户 `ubuntu`）
- DB: `biology_edu`，用户 `biology`，密码 `biology123`，表 `exercise_bank`（701 题，697 有答案）
- API: Claude Sonnet via `claude_client.py`，AIProxy Kiro 分组 0.2x。API key 在 `.env` 的 `CLAUDE_API_KEY`
- `options` 字段格式: 执行前先查 `SELECT options FROM exercise_bank LIMIT 3` 确认是字符串还是 JSON array，据此处理拼接（plan review F-03）
- Python 版本: 服务器用 `python3`，测试用 `python -m pytest`（先确认 pytest 是否已安装，否则 `pip3 install pytest`）
- pm2 进程名: `biology-analyzer`
- 用户偏好: 最小化验证，10 道题足够，别搞复杂

## 启动 Prompt

```
[biology-exam-analyzer] Executor | 2026-03-12
项目: /home/ubuntu/biology-exam-analyzer/（SSH: jdcloud）
读取 docs/plans/2026-03-12-feature-difficulty-handoff.md，按 docs/plans/2026-03-12-feature-difficulty-plan.md Task 1-6 执行。使用 executing-plans skill。完成后输出审查交接单。使用 codex-review skill 进行 GPT 代码审查。
```
