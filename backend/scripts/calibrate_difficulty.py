"""难度 → 得分率整体映射校准（#7）。

用真实考试的按题得分率，拟合「规则难度分(0-10) → 预估得分率」的单调递减映射
（sklearn IsotonicRegression），写进 backend/calibration_data/difficulty_rate_curve.json，
分数预估（difficulty_mapper）用它替代占位的线性默认值。只拟合整体映射，不逐题改。

输入（都不进仓）：
  --pred   分析结果：JSON 列表，每个元素是一次整卷分析的 score_prediction.per_question_data
           （每题含 question_number / difficulty / predicted_rate / question_score）；同一份卷可给多次，
           拟合时全用上，把模型波动也算进去。
  --actual 真实得分率：{"questions": [{"number": 1, "full": 2, "rate": 0.77}, ...]}，只要按题汇总的
           得分率，不带学生信息。

用法（ECS 一次性容器里跑）：
  python scripts/calibrate_difficulty.py --pred pred.json --actual rates.json            # 只出报告
  python scripts/calibrate_difficulty.py --pred pred.json --actual rates.json --write    # 报告 + 写曲线

报告：每题实际得分率 / 难度 / 校准前后预估；校准前后 MAE（校准后给留一交叉验证，即每题都用
不含它的其余题拟合出的曲线来预估）；整卷均分预估 vs 实际。
PASS 条件：留一 MAE < 校准前 MAE，且整卷均分误差变小。
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date

import numpy as np
from sklearn.isotonic import IsotonicRegression

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, BACKEND)

from rule_scorer import score_to_label  # noqa: E402

# difficulty_mapper.CURVE_PATH 读的就是这个文件
CURVE_PATH = os.path.join(BACKEND, "calibration_data", "difficulty_rate_curve.json")


def load_pairs(pred_runs, actual):
    rates = {int(q["number"]): (float(q["rate"]), float(q["full"])) for q in actual["questions"]}
    rows = []  # (题号, 满分, 实际得分率, 难度, 校准前预估得分率, 第几次分析)
    for k, run in enumerate(pred_runs):
        got = {int(p["question_number"]): p for p in run}
        if sorted(got) != sorted(rates):
            raise SystemExit(f"第 {k + 1} 次分析题号 {sorted(got)} 和真实成绩 {sorted(rates)} 对不上，先修拆题")
        for num, p in got.items():
            rate, full = rates[num]
            rows.append((num, full, rate, float(p["difficulty"]), float(p["predicted_rate"]), k))
    return rows


def fit(rows):
    ir = IsotonicRegression(increasing=False, y_min=0.0, y_max=1.0, out_of_bounds="clip")
    ir.fit([r[3] for r in rows], [r[2] for r in rows])
    return ir


def paper_mean(rows, rate_of, runs):
    """每次分析各算一个整卷均分预估，再取平均。"""
    return statistics.mean(sum(rate_of(r) * r[1] for r in rows if r[5] == k) for k in range(runs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--actual", required=True)
    ap.add_argument("--write", action="store_true", help="把拟合曲线写进 calibration_data")
    ap.add_argument("--source", default="真实联考按题得分率", help="写进曲线文件的来源说明（不写校名、人名）")
    args = ap.parse_args()

    pred_runs = json.load(open(args.pred, encoding="utf-8"))
    actual = json.load(open(args.actual, encoding="utf-8"))
    rows = load_pairs(pred_runs, actual)
    runs = len(pred_runs)
    numbers = sorted({r[0] for r in rows})

    ir_all = fit(rows)
    loo = {}
    for num in numbers:
        ir = fit([r for r in rows if r[0] != num])
        loo[num] = ir
    after_loo = {id(r): float(loo[r[0]].predict([r[3]])[0]) for r in rows}
    after_in = {id(r): float(ir_all.predict([r[3]])[0]) for r in rows}

    def mae(f):
        return statistics.mean(abs(f(r) - r[2]) for r in rows)

    mae_before = mae(lambda r: r[4])
    mae_loo = mae(lambda r: after_loo[id(r)])
    mae_in = mae(lambda r: after_in[id(r)])

    actual_mean = sum(q["rate"] * q["full"] for q in actual["questions"])
    mean_before = paper_mean(rows, lambda r: r[4], runs)
    mean_loo = paper_mean(rows, lambda r: after_loo[id(r)], runs)

    print(f"样本：{len(numbers)} 题 × {runs} 次分析 = {len(rows)} 对")
    print("题号 满分 实际得分率 难度(均) 标签 校准前预估 校准后预估(留一)")
    for num in numbers:
        rs = [r for r in rows if r[0] == num]
        d = statistics.mean(r[3] for r in rs)
        print(f"{num:>3} {rs[0][1]:>4g} {rs[0][2]:>9.3f} {d:>8.2f} {score_to_label(d):<5} "
              f"{statistics.mean(r[4] for r in rs):>9.3f} {statistics.mean(after_loo[id(r)] for r in rs):>9.3f}")
    print(f"每题得分率 MAE：校准前 {mae_before:.3f} → 校准后 留一 {mae_loo:.3f}（同样本拟合 {mae_in:.3f}）")
    print(f"整卷均分：实际 {actual_mean:.2f}；预估 校准前 {mean_before:.2f}（差 {mean_before - actual_mean:+.2f}）"
          f" → 校准后 留一 {mean_loo:.2f}（差 {mean_loo - actual_mean:+.2f}）")

    ok = mae_loo < mae_before and abs(mean_loo - actual_mean) < abs(mean_before - actual_mean)
    print("PASS" if ok else "FAIL", "：留一 MAE 小于校准前，且整卷均分误差变小")

    if args.write:
        residual = statistics.pstdev([after_loo[id(r)] - r[2] for r in rows])
        curve = {
            "method": "sklearn IsotonicRegression(increasing=False)",
            "x": [round(float(v), 3) for v in ir_all.X_thresholds_],
            "y": [round(float(v), 4) for v in ir_all.y_thresholds_],
            "residual_std": round(residual, 4),
            "n_questions": len(numbers),
            "n_runs": runs,
            "n_exams": 1,
            "source": args.source,
            "fitted": date.today().isoformat(),
            "loo_mae": round(mae_loo, 4),
            "before_mae": round(mae_before, 4),
        }
        os.makedirs(os.path.dirname(CURVE_PATH), exist_ok=True)
        with open(CURVE_PATH, "w", encoding="utf-8") as f:
            json.dump(curve, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"已写 {CURVE_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
