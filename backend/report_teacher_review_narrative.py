"""Teacher-facing narrative helpers for the report product model."""
from __future__ import annotations


def _range_text(ids: list[int]) -> str:
    if not ids:
        return "暂无明确高风险题"
    ordered = sorted(set(int(item) for item in ids))
    if len(ordered) >= 3 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"第 {ordered[0]}-{ordered[-1]} 题"
    return "、".join(f"第 {item} 题" for item in ordered)


def classify_overall_verdict(
    *,
    high_risk_count: int,
    language_risk_count: int,
    scientific_risk_count: int,
    student_fit_level: str,
    review_candidate_count: int = 0,
) -> dict:
    if scientific_risk_count > 0 or language_risk_count >= 2:
        return {
            "label": "建议修改后使用",
            "stance": "watch",
            "teacher_takeaway": "本卷整体结构可用，但存在需要先复核的科学性或表述风险，建议完成题目修订后再正式使用。",
        }
    if high_risk_count >= 3 or student_fit_level in {"low", "需拆解使用"}:
        return {
            "label": "谨慎使用",
            "stance": "risk",
            "teacher_takeaway": "本卷压力集中或学情适配不足，建议拆分为专题训练或调整难度后使用。",
        }
    if review_candidate_count > 0:
        return {
            "label": "建议复核后使用",
            "stance": "watch",
            "teacher_takeaway": f"本卷整体可作为阶段诊断卷基础，但有 {review_candidate_count} 道题需先做人工复核，完成修订后再正式使用。",
        }
    return {
        "label": "可作为诊断卷使用",
        "stance": "positive",
        "teacher_takeaway": "本卷整体质量稳定，可用于阶段诊断；讲评时重点解释高压力题的思维路径。",
    }


def summarize_teacher_priorities(*, risk_question_ids: list[int], weak_dimensions: list[str], use_case: str, attention_question_ids: list[int] | None = None) -> list[dict]:
    weak_text = "、".join(weak_dimensions[:3]) if weak_dimensions else "知识迁移和题干信息处理"
    if risk_question_ids:
        review_summary = f"建议先复核{_range_text(risk_question_ids)}的设问边界、评分标准和干扰项合理性。"
    else:
        review_summary = "暂未标出必须优先复核的高风险题；建议抽样复核高分值题、材料复杂题和表述较长题。"
    items = [
        {
            "title": "优先复核题",
            "summary": review_summary,
        },
    ]
    if attention_question_ids:
        items.append({
            "title": "建议关注题",
            "summary": f"{_range_text(attention_question_ids)}为中等风险或待优化，建议抽样关注表述与区分度，不强制先复核。",
        })
    items.extend([
        {
            "title": "优先讲评点",
            "summary": f"讲评重点应放在{weak_text}，避免只讲答案不讲审题路径。",
        },
        {
            "title": "使用建议",
            "summary": f"本卷更适合作为{use_case}；若用于基础较弱班级，建议拆题讲评后再整卷训练。",
        },
    ])
    return items


def summarize_student_fit(*, avg_difficulty: float, high_pressure_count: int, target_group: str = "高三学生") -> dict:
    if avg_difficulty >= 7 or high_pressure_count >= 5:
        level = "需拆解使用"
        note = f"对{target_group}压力偏高，建议先拆解材料阅读、设问边界和推理链条。"
    elif avg_difficulty >= 5.5 or high_pressure_count >= 2:
        level = "基本适配"
        note = f"整体适配{target_group}，但高压力题需要配套讲评和变式训练。"
    else:
        level = "适配"
        note = f"难度对{target_group}较友好，可作为基础诊断或巩固训练使用。"
    return {"fit_level": level, "teacher_note": note}
