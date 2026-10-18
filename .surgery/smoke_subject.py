"""九学科贯通冒烟：验证 subject 路由到正确 prompt + 动态素养维度。
运行：docker exec biology_backend python /app/smoke_subject.py
"""
import asyncio
import json
from deps import get_competency_analyzer
from subject_config import get_competency_dims

BIO_Q = {"id": 1, "content": "下列关于细胞膜的叙述，错误的是\nA. 细胞膜主要由脂质和蛋白质组成\nB. 不同功能细胞膜上蛋白质种类数量相同\nC. 细胞膜具有流动性\nD. 细胞膜具有选择透过性",
         "knowledge_points": ["细胞膜", "流动镶嵌模型"]}
CHEM_Q = {"id": 2, "content": "下列离子方程式正确的是\nA. 铁与稀硫酸：2Fe+6H+=2Fe3++3H2↑\nB. 碳酸钙与盐酸：CO3 2-+2H+=H2O+CO2↑\nC. 氢氧化钡与稀硫酸：Ba2++2OH-+2H++SO4 2-=BaSO4↓+2H2O\nD. 铜与硝酸银：Cu+Ag+=Cu2++Ag",
          "knowledge_points": ["离子方程式", "化学反应"]}


async def check(ca, q, subject):
    r = await ca.analyze_competency(q, subject=subject)
    expected = set(get_competency_dims(subject))
    present = expected & set(r.keys())
    calls = r.get("_llm_calls", [])
    pid = calls[0].get("prompt_id") if calls else "?"
    print(f"--- subject={subject} ---")
    print("expected_dims", sorted(expected))
    print("present_dims ", sorted(present))
    print("prompt_id    ", pid)
    print("primary      ", r.get("primary_competency"))
    ok = present == expected and subject in str(pid)
    print("RESULT", "PASS" if ok else "FAIL")
    return ok


async def main():
    ca = get_competency_analyzer()
    bio_ok = await check(ca, BIO_Q, "biology")
    chem_ok = await check(ca, CHEM_Q, "chemistry")
    print("==== SMOKE", "PASS" if (bio_ok and chem_ok) else "FAIL", "====")


asyncio.run(main())
