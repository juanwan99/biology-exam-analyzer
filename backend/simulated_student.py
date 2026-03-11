"""模拟学生定义、prompt 生成、作答与评判。

设计文档: docs/plans/2026-03-11-difficulty-pipeline-design.md §2
"""
import json
import re
import asyncio
from claude_client import send_message


# 12 个模拟学生（4 档 × 3 人）
STUDENTS = [
    # Level 1: 基础薄弱（后 25%），θ=-1.5
    {"name": "张明辉", "level": 1, "theta": -1.5,
     "percentile": "后 25%",
     "description": "你对生物基础概念掌握不牢，经常混淆相似概念。遗传、细胞代谢等抽象内容对你很难。你能记住一些简单事实，但应用和推理经常出错。"},
    {"name": "李小雨", "level": 1, "theta": -1.5,
     "percentile": "后 25%",
     "description": "你上课经常走神，笔记不完整。基础知识有很多漏洞，考试时主要靠记忆碎片和猜测。实验题和图表分析题对你特别难。"},
    {"name": "王浩然", "level": 1, "theta": -1.5,
     "percentile": "后 25%",
     "description": "你对生物不太感兴趣，花在学习上的时间不多。能认出一些专业术语但说不清含义。遇到需要多步推理的题基本放弃。"},

    # Level 2: 中等偏下（25-50%），θ=-0.5
    {"name": "刘思远", "level": 2, "theta": -0.5,
     "percentile": "25%-50%",
     "description": "你基础概念大部分掌握了，但容易在细节上出错。简单的判断和选择题能做对，但综合分析题经常理不清思路。遗传计算偶尔能做对简单类型。"},
    {"name": "陈雨桐", "level": 2, "theta": -0.5,
     "percentile": "25%-50%",
     "description": "你学习比较努力但方法不太对，喜欢死记硬背。对于需要理解和灵活运用的题感到吃力。实验设计题知道基本步骤但变量控制经常遗漏。"},
    {"name": "赵晓峰", "level": 2, "theta": -0.5,
     "percentile": "25%-50%",
     "description": "你能跟上课堂进度，作业基本完成。中等难度的选择题有把握，但简答题组织语言不好，要点经常不全。图表分析能读懂但容易漏看关键信息。"},

    # Level 3: 中等偏上（50-75%），θ=+0.5
    {"name": "吴子涵", "level": 3, "theta": 0.5,
     "percentile": "50%-75%",
     "description": "你生物成绩中上，概念理解较好。大多数题能做对，但遇到新情境题或需要深入分析的题会犯错。遗传计算能处理两对基因但三对以上容易算错。"},
    {"name": "林雅琪", "level": 3, "theta": 0.5,
     "percentile": "50%-75%",
     "description": "你善于记笔记和总结，基础扎实。实验题和图表题表现不错，但偶尔会忽略题目条件导致思路偏差。简答题能答到大部分要点。"},
    {"name": "黄博文", "level": 3, "theta": 0.5,
     "percentile": "50%-75%",
     "description": "你对生物有兴趣，课外会读科普文章。理解力强但有时过度思考简单问题。大多数题型都能应对，只在最难的综合题上失分。"},

    # Level 4: 优秀（前 25%），θ=+1.5
    {"name": "周逸晨", "level": 4, "theta": 1.5,
     "percentile": "前 25%",
     "description": "你是班级生物课代表，基础扎实、思维清晰。各种题型都很有把握，遗传计算从不出错。实验设计题能系统思考，简答题要点全面、逻辑清晰。只有极难的创新情境题可能需要仔细思考。"},
    {"name": "孙思琪", "level": 4, "theta": 1.5,
     "percentile": "前 25%",
     "description": "你喜欢钻研生物竞赛题，知识面广。审题仔细，很少因为粗心丢分。对教材上的所有知识点了然于胸，能在新情境中灵活运用。"},
    {"name": "杨子墨", "level": 4, "theta": 1.5,
     "percentile": "前 25%",
     "description": "你的生物成绩稳定在年级前列。善于从题目中提取关键信息，推理步骤清晰。图表分析、实验设计、遗传计算都是你的强项。"},
]


def _answer_format(question_type: str) -> str:
    """根据题型返回答案格式说明。"""
    qt = question_type.lower() if question_type else ""
    if "选择" in qt or "choice" in qt:
        return "写一个选项字母，如 A"
    elif "填空" in qt or "fill" in qt:
        return "写出填空内容，多个空用 | 分隔"
    else:
        return "写出答案要点，50字以内"


def build_student_prompt(student: dict, question_text: str, question_type: str) -> str:
    """为一个模拟学生构建做题 prompt。"""
    fmt = _answer_format(question_type)
    name = student["name"]
    percentile = student["percentile"]
    desc = student["description"]
    return f"""你是{name}，一名高中生，生物成绩在年级{percentile}。

你的知识水平：
{desc}

请以你的真实水平做下面这道题。
- 如果你觉得会做，给出答案
- 如果不确定，写出你的猜测和犹豫点
- 如果完全不会，诚实说不会

不要表现得比你的水平更强或更弱。

题目：
{question_text}

请按以下 JSON 格式回答（不要输出其他内容）：
{{"answer": "{fmt}", "correct_confidence": 0.0-1.0, "reasoning": "一句话（30字以内）"}}"""


def parse_student_response(raw: str) -> dict:
    """从模拟学生的原始回复中提取 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown code block 中提取
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取第一个 JSON object
    m = re.search(r'\{[^{}]*\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # 解析失败，返回默认
    return {"answer": raw.strip()[:50], "correct_confidence": 0.5, "reasoning": "解析失败"}


def judge_choice(answer: str, correct_answer: str) -> float:
    """选择题纯代码评判。返回 0 或 1。"""
    # 提取首个 A-D 字母
    m = re.search(r'[A-Da-d]', answer)
    if not m:
        return 0.0
    student_choice = m.group().upper()
    # correct_answer 也提取（可能是 "A" 或 "AB" 多选）
    correct_set = set(re.findall(r'[A-Da-d]', correct_answer.upper()))
    if not correct_set:
        return 0.0
    if len(correct_set) == 1:
        return 1.0 if student_choice in correct_set else 0.0
    # 多选题：完全匹配才算对
    student_set = set(re.findall(r'[A-Da-d]', answer.upper()))
    return 1.0 if student_set == correct_set else 0.0


async def judge_subjective(answer: str, correct_answer: str, total_score: float) -> float:
    """主观题/填空题 Haiku 评判。返回 0/0.5/1。"""
    prompt = f"""你是一名阅卷老师。请判断学生答案的得分率。

标准答案：{correct_answer}
学生答案：{answer}
满分：{total_score}分

只回复一个数字：0（完全错误）、0.5（部分正确）、1（完全正确）。不要解释。"""

    raw = await send_message(
        prompt,
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        temperature=0,
    )
    # 提取 0/0.5/1
    raw = raw.strip()
    if "0.5" in raw:
        return 0.5
    elif raw.startswith("1"):
        return 1.0
    else:
        return 0.0


async def simulate_one_student(
    student: dict,
    question_text: str,
    question_type: str,
    correct_answer: str,
    total_score: float,
    image_base64: str = None,
) -> dict:
    """一个学生做一道题，返回作答结果。"""
    prompt = build_student_prompt(student, question_text, question_type)

    if image_base64:
        from claude_client import send_message_with_image
        raw = await send_message_with_image(prompt, image_base64)
    else:
        raw = await send_message(prompt)

    parsed = parse_student_response(raw)
    answer = str(parsed.get("answer", ""))
    confidence = float(parsed.get("correct_confidence", 0.5))

    # 评判
    qt = (question_type or "").lower()
    if "选择" in qt or "choice" in qt:
        score = judge_choice(answer, correct_answer)
    else:
        score = await judge_subjective(answer, correct_answer, total_score)

    return {
        "student": student["name"],
        "level": student["level"],
        "answer": answer,
        "correct": score >= 1.0,
        "score": score,
        "confidence": confidence,
        "reasoning": parsed.get("reasoning", ""),
    }


async def simulate_all_students(
    question_text: str,
    question_type: str,
    correct_answer: str,
    total_score: float,
    image_base64: str = None,
) -> list:
    """12 个学生并发做同一道题。"""
    tasks = [
        simulate_one_student(s, question_text, question_type,
                            correct_answer, total_score, image_base64)
        for s in STUDENTS
    ]
    return await asyncio.gather(*tasks)
