"""B1a 批量重算脚本 — 逐题处理，每 10 题 commit 一次。

用法: docker exec biology_backend python scripts/recalculate_difficulty.py [--limit N]
"""
import asyncio
import json
import sys
import os
import math
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from database import async_session
from feature_extractor import extract_features
from rule_scorer import compute_difficulty, score_to_label

COMMIT_EVERY = 10


async def main():
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])
        print(f"限制处理 {limit} 题")

    print("=" * 50)
    print("B1a 批量重算 — 非线性 Pipeline v2")
    print("=" * 50)

    async with async_session() as db:
        query = "SELECT id, content, answer, options, difficulty_level FROM exercise_bank ORDER BY id"
        if limit:
            query += f" LIMIT {limit}"
        result = await db.execute(text(query))
        rows = [dict(r._mapping) for r in result]
        total = len(rows)
        print(f"共 {total} 题待处理\n")

        scores = []
        errors = 0

        for i, row in enumerate(rows):
            q_id = row["id"]
            content = row["content"] or ""
            answer = row["answer"] or ""
            options_str = ""
            if row["options"]:
                try:
                    opts = row["options"] if isinstance(row["options"], dict) else json.loads(str(row["options"]))
                    if isinstance(opts, dict):
                        options_str = " ".join(f"{k}.{v}" for k, v in sorted(opts.items()))
                except Exception:
                    pass

            full_text = f"{content}\n{options_str}" if options_str else content

            try:
                features = await extract_features(full_text, options_str, answer)
                score = compute_difficulty(features)
                label = score_to_label(score)

                await db.execute(text("""
                    UPDATE exercise_bank
                    SET difficulty_score_v2 = :score,
                        difficulty_label_v2 = :label,
                        difficulty_features_v2 = cast(:features as jsonb)
                    WHERE id = :id
                """), {
                    "id": q_id,
                    "score": score,
                    "label": label,
                    "features": json.dumps(features, ensure_ascii=False),
                })
                scores.append(score)

            except Exception as e:
                print(f"  ❌ 题目 {q_id} 失败: {e}")
                errors += 1

            # 每 COMMIT_EVERY 题 commit 一次
            if (i + 1) % COMMIT_EVERY == 0:
                await db.commit()
                print(f"  [{i+1}/{total}] committed ({(i+1)*100//total}%)")

        # 最后 commit
        await db.commit()
        print(f"\n完成: {len(scores)} 成功, {errors} 失败")

        # 统计
        if scores:
            label_counts = Counter(score_to_label(s) for s in scores)
            print(f"\n分布:")
            for lbl in ["简单", "中等偏易", "中等偏难", "困难"]:
                cnt = label_counts.get(lbl, 0)
                print(f"  {lbl}: {cnt} ({cnt*100/len(scores):.1f}%)")
            
            print(f"\n数值: min={min(scores):.1f}, max={max(scores):.1f}, mean={sum(scores)/len(scores):.2f}")
            
            bins = Counter(round(s * 2) / 2 for s in scores)
            n = len(scores)
            entropy = -sum((c/n) * math.log2(c/n) for c in bins.values() if c > 0)
            print(f"Shannon 熵: {entropy:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
