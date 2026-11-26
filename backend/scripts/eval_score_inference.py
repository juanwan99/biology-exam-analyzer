"""去掉拆题文本中的卷面分值，测量现有分析链的分值推断偏差。"""

import argparse
import asyncio
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deps
from analysis_options import set_analysis_options
from analysis_scheduling import gather_longest_first
from score_rules import _HEAD_SCORE, _PER_QUESTION, _SECTION_TOTAL, paper_score
from visual_word_splitter import split_word_with_visual


_SCORE_TEXT = re.compile(r"\d+(?:\.\d+)?\s*分")
_CHOICE_TYPES = {"single_choice", "multiple_choice"}


def strip_scores(question: dict) -> int:
    """就地去分，返回题干和分节标题里剩下的分值字样数。"""
    remaining = 0
    for field in ("content", "_section_header"):
        value = question.get(field)
        if value is None:
            continue
        for pattern in (_HEAD_SCORE, _PER_QUESTION, _SECTION_TOTAL):
            value = pattern.sub("", value)
        question[field] = value
        remaining += len(_SCORE_TEXT.findall(value))
    return remaining


async def split_paper(path: Path) -> tuple[list[dict], list[bytes]]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        result = await asyncio.to_thread(split_word_with_visual, str(path), subject="biology")
        processor = deps.get_doc_processor()
        images = await asyncio.to_thread(processor.process_docx, str(path))
        image_bytes = await asyncio.to_thread(processor.images_to_bytes, images) if images else []
    elif suffix == ".pdf":
        result = await asyncio.to_thread(deps.get_pdf_splitter().split, str(path))
        image_bytes = []  # PDF 页图已在题目的 _media_for_ai 中。
    else:
        raise ValueError(f"仅支持 .docx 和 .pdf 格式：{path}")
    return result["questions"], image_bytes


async def evaluate_paper(path: Path, runs: int) -> list[list[dict]]:
    questions, image_bytes = await split_paper(path)
    expected_scores = [paper_score(q)[0] for q in questions]
    remaining = sum(strip_scores(q) for q in questions)
    print(f"{path.name} 残留分值字样 {remaining} 处", flush=True)

    service = deps.get_analysis_service()
    sem = asyncio.Semaphore(deps.MAX_WORKERS)

    async def analyze_one(question):
        async with sem:
            result = await service.analyze_question(question, image_bytes, "deep", subject="biology")
        # 服务可能把异常转换成失败结果，此时终止本次测量。
        if result.get("analysis_failed"):
            raise RuntimeError(f"{path.name} 题目 {result['id']} 分析失败：{result['analysis_failure_reason']}")
        return result

    paper_runs = []
    for run in range(1, runs + 1):
        # 分析服务会就地写回 total_score。每次从同一份去分后的拆题结果开始。
        analyzed = await gather_longest_first(deepcopy(questions), analyze_one)
        rows = []
        for result, expected in zip(analyzed, expected_scores):
            question_type = result["question_type"]
            score = result["total_score"]
            rows.append({
                "paper": path.name,
                "run": run,
                "question_id": result["id"],
                "question_type": question_type,
                "paper_score": expected,
                "total_score": score,
                "difference": score - expected if expected is not None else None,
                "score_source": result["score_source"],
                "score_status": result["score_status"],
            })
        paper_runs.append(rows)
        print_run(path.name, run, rows)
    return paper_runs


def print_run(paper: str, run: int, rows: list[dict]) -> None:
    expected_total = inferred_total = 0.0
    for row in rows:
        expected = row["paper_score"]
        inferred = row["total_score"]
        expected_text = f"{expected:.1f}" if expected is not None else "—"
        difference = row["difference"]
        difference_text = f"{difference:+.1f}" if difference is not None else "—"
        print(f"{paper} 第 {run} 次 第 {row['question_id']} 题 {row['question_type']} "
              f"真值 {expected_text} 推断 {inferred:.1f} 差 {difference_text} {row['score_source']}")
        if expected is not None:
            expected_total += expected
            inferred_total += inferred
    print(f"{paper} 第 {run} 次 整卷总分 真值 {expected_total:.1f} 推断 {inferred_total:.1f}", flush=True)


def summarize(papers: list[list[list[dict]]]) -> tuple[dict, float | None]:
    differences = {"选择题": [], "非选择题": []}
    spreads = []
    for paper_runs in papers:
        # 调度结果仍按拆题顺序，用卷内位置对齐同题的各次结果。
        for attempts in zip(*paper_runs):
            if attempts[0]["paper_score"] is None:
                continue
            category = "选择题" if attempts[0]["question_type"] in _CHOICE_TYPES else "非选择题"
            differences[category].extend(row["difference"] for row in attempts)
            if len(attempts) > 1:
                scores = [row["total_score"] for row in attempts]
                spreads.append(max(scores) - min(scores))

    metrics = {
        category: (mean(map(abs, values)), mean(values)) if values else (None, None)
        for category, values in differences.items()
    }
    return metrics, max(spreads, default=None)


async def evaluate(paths: list[Path], runs: int, json_path: Path | None) -> None:
    set_analysis_options()
    papers = [await evaluate_paper(path, runs) for path in paths]
    metrics, max_spread = summarize(papers)
    for category, (mae, bias) in metrics.items():
        mae_text = f"{mae:.1f}" if mae is not None else "—"
        bias_text = f"{bias:+.1f}" if bias is not None else "—"
        print(f"{category} MAE {mae_text} 平均偏差 {bias_text}")
    spread_text = f"{max_spread:.1f}" if max_spread is not None else "—"
    print(f"同题多次推断的最大差 {spread_text}")

    if json_path is not None:
        rows = [row for paper in papers for run in paper for row in run]
        for row in rows:
            for key in ("paper_score", "total_score", "difference"):
                if row[key] is not None:
                    row[key] = round(float(row[key]), 1)
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("papers", nargs="+", type=Path, help="试卷路径（.docx / .pdf）")
    parser.add_argument("--runs", type=int, default=2, help="每份卷的分析次数（默认 2）")
    parser.add_argument("--json", type=Path, help="逐题结果的 JSON 输出路径")
    args = parser.parse_args()
    asyncio.run(evaluate(args.papers, args.runs, args.json))


if __name__ == "__main__":
    main()
