"""
修复题库中缺失的表格内容

问题：只存储了 table_index（表格索引），没有存储实际表格内容
解决：从原始 Word 文档中提取表格内容，更新数据库
"""
import os
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from word_parser_v2 import WordParserV2

# 数据库连接
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biology:biology123@localhost:5432/biology_edu")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# Word 文件目录
DOCX_DIR = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类")


def table_to_markdown(table_data):
    """将表格数据转换为 Markdown 格式"""
    if not table_data or len(table_data) == 0:
        return ""

    lines = []

    # 第一行作为表头
    header = table_data[0]
    lines.append("| " + " | ".join(cell or "" for cell in header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")

    # 其余行
    for row in table_data[1:]:
        # 确保列数一致
        while len(row) < len(header):
            row.append("")
        lines.append("| " + " | ".join(cell or "" for cell in row[:len(header)]) + " |")

    return "\n".join(lines)


def table_to_html(table_data):
    """将表格数据转换为 HTML 格式"""
    if not table_data or len(table_data) == 0:
        return ""

    html = ['<table class="border-collapse border border-gray-300 w-full">']

    # 第一行作为表头
    html.append('<thead class="bg-gray-100">')
    html.append('<tr>')
    for cell in table_data[0]:
        html.append(f'<th class="border border-gray-300 px-2 py-1 text-left">{cell or ""}</th>')
    html.append('</tr>')
    html.append('</thead>')

    # 其余行
    html.append('<tbody>')
    for row in table_data[1:]:
        html.append('<tr>')
        for i, cell in enumerate(row):
            if i < len(table_data[0]):  # 确保列数一致
                html.append(f'<td class="border border-gray-300 px-2 py-1">{cell or ""}</td>')
        html.append('</tr>')
    html.append('</tbody>')
    html.append('</table>')

    return "\n".join(html)


def find_questions_with_table_index():
    """查找所有有 table_index 但没有 table_content 的题目"""
    with engine.connect() as conn:
        result = conn.execute(text('''
            SELECT id, question_type, content,
                   competency_scores->>'table_index' as table_index,
                   competency_scores->>'exam_source' as exam_source,
                   competency_scores->>'year' as year,
                   tags
            FROM exercise_bank
            WHERE competency_scores->>'table_index' IS NOT NULL
              AND (competency_scores->>'table_content' IS NULL OR competency_scores->>'table_content' = 'null')
            ORDER BY id
        '''))
        return result.fetchall()


def parse_all_documents():
    """解析所有 Word 文档，构建表格映射"""
    parser = WordParserV2()
    doc_tables = {}  # category -> {index: table_data}

    print("解析 Word 文档...")

    for docx_file in DOCX_DIR.glob("*.docx"):
        try:
            category = docx_file.stem
            parsed = parser.parse(str(docx_file))

            # 提取所有表格
            tables = {}
            for elem in parsed.elements:
                if elem.type == 'table' and elem.table_data:
                    tables[elem.index] = elem.table_data

            if tables:
                doc_tables[category] = tables
                print(f"  {category}: {len(tables)} 个表格")
        except Exception as e:
            print(f"  {docx_file.name}: 解析失败 - {e}")

    return doc_tables


def main():
    print("=" * 60)
    print("修复缺失的表格内容")
    print("=" * 60)

    # 1. 查找需要修复的题目
    questions = find_questions_with_table_index()
    print(f"\n找到 {len(questions)} 道有 table_index 的题目")

    if not questions:
        print("没有需要修复的题目")
        return

    # 2. 解析所有文档获取表格
    doc_tables = parse_all_documents()

    # 3. 匹配并更新
    session = Session()
    updated = 0

    try:
        for row in questions:
            ex_id, q_type, content, table_index, exam_source, year, tags = row

            if table_index is None:
                continue

            table_index = int(table_index)

            # 从 tags 中获取分类
            category = None
            if tags:
                for tag in tags:
                    if tag in doc_tables:
                        category = tag
                        break

            if not category:
                print(f"  ID:{ex_id} - 无法找到对应分类")
                continue

            # 获取表格数据
            if category in doc_tables and table_index in doc_tables[category]:
                table_data = doc_tables[category][table_index]
                table_markdown = table_to_markdown(table_data)
                table_html = table_to_html(table_data)

                # 更新数据库
                session.execute(
                    text("""
                        UPDATE exercise_bank
                        SET competency_scores = competency_scores || :updates
                        WHERE id = :id
                    """),
                    {
                        "id": ex_id,
                        "updates": json.dumps({
                            "table_content": table_data,
                            "table_markdown": table_markdown,
                            "table_html": table_html
                        })
                    }
                )

                print(f"  ID:{ex_id} [{year}年{exam_source}] - 更新表格 T{table_index} ({len(table_data)} 行)")
                updated += 1
            else:
                print(f"  ID:{ex_id} - 表格 T{table_index} 不存在于 {category}")

        session.commit()
        print(f"\n成功更新 {updated} 道题目的表格内容")

    except Exception as e:
        session.rollback()
        print(f"更新失败: {e}")
        raise
    finally:
        session.close()


def verify_tables():
    """验证表格内容"""
    with engine.connect() as conn:
        result = conn.execute(text('''
            SELECT id,
                   competency_scores->>'table_index' as table_index,
                   competency_scores->'table_content' as table_content,
                   LEFT(content, 80) as content_preview
            FROM exercise_bank
            WHERE competency_scores->>'table_index' IS NOT NULL
            LIMIT 10
        '''))

        print("\n表格内容验证:")
        for row in result:
            has_content = row.table_content is not None and row.table_content != 'null'
            status = "✓" if has_content else "✗"
            print(f"\nID:{row.id} T{row.table_index} [{status}]")
            print(f"  题目: {row.content_preview}...")
            if has_content:
                # 显示表格预览
                try:
                    data = json.loads(row.table_content) if isinstance(row.table_content, str) else row.table_content
                    if data and len(data) > 0:
                        print(f"  表格: {len(data)} 行, 首行: {data[0]}")
                except:
                    pass


if __name__ == "__main__":
    main()
    print("\n" + "=" * 60)
    verify_tables()
