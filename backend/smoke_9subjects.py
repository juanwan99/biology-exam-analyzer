"""九学科贯通验证：对每科真题跑 analyze_competency，验证学科 prompt 路由 + 动态素养维度全对。
复用 test_9subjects.py 的九科真题内容。
运行：docker exec biology_backend python /app/smoke_9subjects.py
"""
import asyncio
from deps import get_competency_analyzer
from subject_config import get_competency_dims, get_subject_name
from test_9subjects import QUESTIONS

ORDER = ["chinese", "math", "english", "physics", "chemistry",
         "biology", "politics", "history", "geography"]


async def check(ca, subject):
    q = QUESTIONS[f"{subject}_choice"]
    question = {"id": 1, "content": q["content"],
                "knowledge_points": q.get("knowledge_points", [q.get("question_type", "")])}
    r = await ca.analyze_competency(question, subject=subject)
    expected = set(get_competency_dims(subject))
    present = expected & set(r.keys())
    calls = r.get("_llm_calls", [])
    pid = calls[0].get("prompt_id") if calls else "?"
    ok = present == expected and subject in str(pid)
    print(f"{'PASS' if ok else 'FAIL'} {subject:10s}({get_subject_name(subject)}) "
          f"dims={len(present)}/{len(expected)} pid={pid} primary={r.get('primary_competency','?')}")
    return ok


async def main():
    ca = get_competency_analyzer()
    results = []
    for s in ORDER:
        try:
            results.append(await check(ca, s))
        except Exception as e:
            print(f"FAIL {s:10s} EXCEPTION {type(e).__name__}: {str(e)[:80]}")
            results.append(False)
    passed = sum(results)
    print(f"==== 9学科 competency 验证 {passed}/9 {'ALL PASS' if passed == 9 else 'SOME FAIL'} ====")


asyncio.run(main())
