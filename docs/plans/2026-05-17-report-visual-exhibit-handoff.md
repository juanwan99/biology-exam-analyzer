# Report Visual Exhibit Handoff

Goal: 继续把 `/home/ubuntu/biology-exam-analyzer` 的试卷质量报告做成专业商业报告级呈现，当前交付 URL 为 `http://localhost:8001/api/reports/report_product_demo_20260516.html` 和 `.pdf`。
Current State: 已完成元数据恢复、67 SEU / 54 DU / 25 SU 真实样本报告生成、Bain 红白灰配色、细粒度图表、SEU/DU 证据卡片化、内部证据 ID 中文化。
Changed Files: `/home/ubuntu/biology-exam-analyzer/backend/report_data.py`, `report_product_model.py`, `report_product_html.py`, `report_product_charts.py`, `test_report_data.py`, `test_report_commercial_model.py`, `test_report_commercial_html.py`。
Artifacts: 远端 `/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.html|pdf`，本机镜像 `C:\Users\Administrator\Documents\New project\api\reports\report_product_demo_20260516.html|pdf`。
Last Verified Evidence: `python3 -m pytest test_report_data.py test_report_commercial_model.py test_report_product_model.py test_report_commercial_html.py test_report_product_html.py test_report_product_publish.py -q` => `35 passed in 1.48s`；HTML/PDF local 200；browser raw IDs/None/English Exhibit all 0。
Must Preserve: 单版本原位替换，不新增 report v2；保留 `report_product_*` 合约和 `write_report_artifacts` 链路；保留元数据治理字段、LLM 调用 63、SEU/DU/SU 聚合证据。
Must Preserve: 可见报告不得暴露 `seu:`, `question:Q`, `metadata:Q`, `fine_grained_exhibits`, `weighted score`, `purpose_counts`；不得恢复横向滚动和原始 SEU/DU 表格。
Must Preserve: 每次改完必须重新生成真实报告、同步本机 `api/reports`，并用浏览器验证当前 localhost URL。
Must Not Change: 不回滚远端 dirty/untracked 文件；不要清理无关 `.bak` 文件；不要修改服务器代理/JDCloud SSH 配置；不要把 demo 数据硬编码成静态 HTML。
Must Not Change: 不隐藏元数据问题来制造“好看”，综合诊断必须依赖细粒度证据表和可追溯字段。
Known Gap: 当前热力图和矩阵已可用，但仍有进一步美术精修空间，尤其是图表中文字层级、PDF 分页密度、首屏信息密度。
Next Best Step: 继续图表美术精修，优先 `report_product_charts.py` 的 heatmap/matrix/trap chart，再看 PDF 专用布局。
Suggested Prompt: “接手 `/home/ubuntu/biology-exam-analyzer` 报告视觉 exhibit 迭代，先读 `C:\Users\Administrator\Documents\New project\docs\plans\2026-05-17-report-visual-exhibit-handoff.md`，保留 Must Preserve/Must Not Change，继续自测并优化图表和 PDF。”
