"""
修复题库中缺失题干的大题

问题：部分填空题/简答题只保存了小问，缺失了背景描述的题干
解决：从原始Word文档中查找完整题干，更新数据库
"""
import json
import re
import asyncio
from pathlib import Path
from docx import Document
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# 数据库连接
engine = create_engine('postgresql://biology:biology123@localhost:5432/biology_edu')
Session = sessionmaker(bind=engine)

# Word文件目录
DOCX_DIR = Path("uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类")


def find_questions_with_missing_stems():
    """找出所有以序号开头的题目（可能缺失题干）"""
    with engine.connect() as conn:
        result = conn.execute(text('''
            SELECT id, question_type, content,
                   competency_scores->>'exam_source' as exam_source,
                   competency_scores->>'year' as year,
                   competency_scores->>'question_number' as question_number
            FROM exercise_bank
            WHERE content ~ '^\s*[\(（][0-9一二三四五六七八九十]'
            ORDER BY id
        '''))
        return result.fetchall()


def extract_docx_text(docx_path):
    """提取Word文档的所有段落文本"""
    doc = Document(docx_path)
    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if text:
            paragraphs.append((i, text))
    return paragraphs


def find_complete_stem(paragraphs, year, exam_source, question_number, first_subquestion):
    """在段落中查找完整题干"""
    # 搜索匹配的题目
    # 先找到小问开始的位置
    subq_start = None
    for i, (idx, text) in enumerate(paragraphs):
        if first_subquestion in text:
            subq_start = i
            break

    if subq_start is None:
        return None

    # 向前搜索题干开始位置（通常包含年份和来源信息，或者以题号开头）
    stem_start = subq_start
    for i in range(subq_start - 1, max(0, subq_start - 10), -1):
        idx, text = paragraphs[i]
        # 检查是否是题目开头（包含年份和卷名，或题号）
        if re.match(r'^\d+\.', text):  # 以数字和点开头，如 "23."
            stem_start = i
            break
        if year and str(year) in text and exam_source and exam_source in text:
            stem_start = i
            break
        # 检查是否是前一题的答案或解析（停止搜索）
        if re.match(r'^\d+\.[A-D]', text) or '[解析]' in text:
            break

    # 收集完整题干
    complete_stem = []
    for i in range(stem_start, subq_start + 1):
        idx, text = paragraphs[i]
        # 移除题号前缀（如 "23.E8[2021·海南卷]"）
        cleaned = re.sub(r'^\d+\.[A-Z0-9]*\[\d+[·.]\w+卷?\]\s*', '', text)
        if cleaned:
            complete_stem.append(cleaned)

    return '\n'.join(complete_stem)


def main():
    print("=" * 60)
    print("修复缺失题干的大题")
    print("=" * 60)

    # 1. 找出问题题目
    problems = find_questions_with_missing_stems()
    print(f"\n找到 {len(problems)} 道可能缺失题干的题目")

    if not problems:
        print("没有需要修复的题目")
        return

    # 2. 加载所有Word文档
    print("\n加载Word文档...")
    docx_data = {}
    for docx_file in DOCX_DIR.glob("*.docx"):
        try:
            paragraphs = extract_docx_text(docx_file)
            docx_data[docx_file.stem] = paragraphs
            print(f"  - {docx_file.name}: {len(paragraphs)} 段落")
        except Exception as e:
            print(f"  - {docx_file.name}: 加载失败 - {e}")

    # 3. 查找并修复每个问题题目
    fixes = []
    for row in problems:
        ex_id, q_type, content, exam_source, year, q_num = row
        print(f"\n处理 ID:{ex_id} ({year}年 {exam_source} 第{q_num}题)")
        print(f"  当前内容: {content[:80]}...")

        # 提取第一个小问用于匹配
        first_line = content.split('\n')[0].strip()

        # 在所有文档中搜索
        found_stem = None
        for doc_name, paragraphs in docx_data.items():
            stem = find_complete_stem(paragraphs, year, exam_source, q_num, first_line)
            if stem and stem != content and len(stem) > len(content):
                found_stem = stem
                print(f"  找到完整题干 (来自 {doc_name})")
                print(f"  新题干: {stem[:100]}...")
                break

        if found_stem:
            fixes.append((ex_id, found_stem))
        else:
            print(f"  未找到完整题干")

    # 4. 确认并执行更新
    if fixes:
        print(f"\n\n找到 {len(fixes)} 个可修复的题目")
        confirm = input("是否执行更新? (y/n): ")

        if confirm.lower() == 'y':
            session = Session()
            try:
                for ex_id, new_content in fixes:
                    session.execute(
                        text("UPDATE exercise_bank SET content = :content WHERE id = :id"),
                        {"content": new_content, "id": ex_id}
                    )
                session.commit()
                print(f"成功更新 {len(fixes)} 条记录")
            except Exception as e:
                session.rollback()
                print(f"更新失败: {e}")
            finally:
                session.close()
    else:
        print("\n没有可自动修复的题目，可能需要手动检查")


if __name__ == "__main__":
    main()
