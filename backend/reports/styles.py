"""报告 CSS 样式。"""

def _get_report_css() -> str:
    """A4 排版 CSS 样式"""
    return """<style>
@page { size: A4; margin: 2cm; }
body { font-family: 'SimSun', 'Microsoft YaHei', sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; }
h1 { text-align: center; color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 10px; margin-bottom: 30px; }
h2 { color: #1e40af; border-left: 4px solid #3b82f6; padding-left: 10px; margin-top: 30px; page-break-after: avoid; }
.cover { text-align: center; padding: 60px 0 40px; }
.cover h1 { font-size: 28px; margin-bottom: 20px; }
.cover .subtitle { font-size: 20px; color: #475569; margin: 10px 0; }
.cover p { color: #64748b; margin: 5px 0; }
.metrics-grid { display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }
.metric-card { flex: 1; min-width: 140px; background: #f0f9ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 15px; text-align: center; }
.metric-value { font-size: 28px; font-weight: bold; color: #1e40af; }
.metric-label { font-size: 12px; color: #64748b; margin-top: 5px; }
.insight-box { background: #fefce8; border-left: 4px solid #eab308; padding: 12px 16px; margin: 15px 0; border-radius: 0 8px 8px 0; }
.chart { margin: 20px 0; text-align: center; page-break-inside: avoid; }
.chart img { max-width: 100%; height: auto; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; page-break-inside: auto; }
th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; font-size: 13px; }
th { background: #eff6ff; font-weight: bold; color: #1e40af; }
tr:nth-child(even) { background: #f8fafc; }
tr { page-break-inside: avoid; }
.question-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 15px 0; page-break-inside: avoid; }
.question-card h4 { color: #1e40af; margin: 0 0 10px; }
.question-card .meta { color: #64748b; font-size: 12px; margin-bottom: 8px; }
.question-card .comment { background: #f0fdf4; border-left: 3px solid #22c55e; padding: 8px 12px; margin-top: 10px; font-style: italic; }
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

