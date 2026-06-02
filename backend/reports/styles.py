"""报告 CSS 样式。"""

def _get_report_css() -> str:
    """A4 排版 CSS 样式"""
    return """<style>
@page { size: A4; margin: 2cm 1.5cm; @top-center { content: "试卷分析报告"; font-size: 9pt; color: #94a3b8; } @bottom-center { content: "第 " counter(page) " 页"; font-size: 9pt; color: #94a3b8; } }
body { font-family: "SimSun", "SimHei", "Microsoft YaHei", serif; font-size: 11pt; line-height: 1.6; color: #1e293b; }
.cover { page-break-after: always; text-align: center; padding-top: 120px; }
.cover h1 { font-size: 28pt; color: #1e40af; margin-bottom: 20px; font-family: "SimHei"; }
.cover .subtitle { font-size: 14pt; color: #64748b; margin-top: 10px; }
.cover .meta { margin-top: 60px; font-size: 12pt; color: #475569; }
h2 { font-size: 16pt; color: #1e40af; border-bottom: 2px solid #3b82f6; padding-bottom: 6px; margin-top: 30px; font-family: "SimHei"; page-break-after: avoid; }
h3 { font-size: 13pt; color: #334155; margin-top: 20px; font-family: "SimHei"; }
.section { margin-bottom: 25px; }
.chart-container { text-align: center; margin: 15px 0; page-break-inside: avoid; }
.chart-container img { max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; }
.chart { margin: 20px 0; text-align: center; page-break-inside: avoid; }
.chart img { max-width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
.metrics-grid { display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }
.metric-card { flex: 1; min-width: 140px; background: #f0f9ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 15px; text-align: center; }
.metric-value { font-size: 28px; font-weight: bold; color: #1e40af; }
.metric-label { font-size: 12px; color: #64748b; margin-top: 5px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 10pt; page-break-inside: avoid; }
th { background: #f1f5f9; color: #334155; padding: 8px 10px; text-align: left; border: 1px solid #cbd5e1; font-weight: bold; }
td { padding: 6px 10px; border: 1px solid #e2e8f0; }
tr:nth-child(even) { background: #f8fafc; }
.rating-excellent { color: #059669; font-weight: bold; }
.rating-good { color: #2563eb; }
.rating-fair { color: #d97706; }
.rating-poor { color: #dc2626; font-weight: bold; }
.diagnosis-card { background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 12px 16px; margin: 10px 0; border-radius: 0 8px 8px 0; }
.diagnosis-card h4 { margin: 0 0 6px 0; color: #1e40af; }
.insight-box { background: #fffbeb; border: 1px solid #fbbf24; border-radius: 8px; padding: 12px 16px; margin: 15px 0; }
.insight-box h4 { color: #92400e; margin: 0 0 6px 0; }
.question-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin: 12px 0; page-break-inside: avoid; }
.question-card h4 { color: #1e40af; margin: 0 0 10px; }
.question-card .meta { color: #64748b; font-size: 12px; margin-bottom: 8px; }
.question-card .comment { background: #f0fdf4; border-left: 3px solid #22c55e; padding: 8px 12px; margin-top: 10px; font-style: italic; }
.question-card .q-header { font-weight: bold; color: #1e40af; margin-bottom: 8px; }
.question-card .q-difficulty { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.diff-easy { background: #dcfce7; color: #166534; }
.diff-medium { background: #fef3c7; color: #92400e; }
.diff-hard { background: #fee2e2; color: #991b1b; }
.tag { display: inline-block; background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 12px; font-size: 9pt; margin: 2px; }
.rec-item { border-left: 3px solid #3b82f6; padding: 8px 12px; margin: 10px 0; }
.rec-item.high { border-left-color: #ef4444; }
.rec-item.medium { border-left-color: #f59e0b; }
.rec-item.low { border-left-color: #22c55e; }
.rec-category { font-weight: bold; color: #1e40af; font-size: 13px; }
.difficulty-high { color: #dc2626; font-weight: bold; }
.difficulty-medium { color: #ea580c; }
.difficulty-low { color: #16a34a; }
.footer { margin-top: 40px; text-align: center; color: #64748b; font-size: 11px; border-top: 1px solid #e2e8f0; padding-top: 20px; }
</style>"""
