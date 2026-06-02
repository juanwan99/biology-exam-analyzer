"""
导入2024年高考题到数据库
"""
import os
import json
import asyncio
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 数据库连接
DATABASE_URL = "postgresql+asyncpg://biology:biology123@localhost:5432/biology_edu"

# JSON文件到来源映射
FILE_TO_SOURCE = {
    "必修1_v2.json": {"name": "2024年高考真题-必修1", "type": "全国", "textbook": "必修1"},
    "必修2_v2.json": {"name": "2024年高考真题-必修2", "type": "全国", "textbook": "必修2"},
    "选择性必修1_v2.json": {"name": "2024年高考真题-选择性必修1", "type": "全国", "textbook": "选择性必修1"},
    "选择性必修2_v2.json": {"name": "2024年高考真题-选择性必修2", "type": "全国", "textbook": "选择性必修2"},
    "选择性必修3_v2.json": {"name": "2024年高考真题-选择性必修3", "type": "全国", "textbook": "选择性必修3"},
}

# 题目类型映射
QUESTION_TYPE_MAP = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "fill_blank": "填空题",
    "short_answer": "简答题",
}


async def create_source(session: AsyncSession, name: str, year: int, q_type: str, textbook: str) -> int:
    """创建来源记录并返回ID"""
    # 检查是否已存在
    result = await session.execute(
        text("SELECT id FROM exercise_sources WHERE name = :name"),
        {"name": name}
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  来源已存在: {name} (ID: {existing})")
        return existing

    # 创建新来源 (使用正确的列名 source_type 和 description)
    result = await session.execute(
        text("""
            INSERT INTO exercise_sources (name, year, source_type, description)
            VALUES (:name, :year, :source_type, :description)
            RETURNING id
        """),
        {"name": name, "year": year, "source_type": q_type, "description": f"2024年高考真题-{textbook}"}
    )
    source_id = result.scalar_one()
    await session.commit()
    print(f"  创建来源: {name} (ID: {source_id})")
    return source_id


async def import_questions(session: AsyncSession, source_id: int, questions: list) -> int:
    """导入题目并返回导入数量"""
    count = 0
    for q in questions:
        # 提取数据
        q_type = QUESTION_TYPE_MAP.get(q.get("question_type", ""), "其他")
        # 题干在JSON中是 stem 字段，不是 content
        content = q.get("stem", "") or q.get("content", "")
        options = q.get("options")  # 可能是 None 或 dict
        answer = q.get("answer", "")
        explanation = q.get("explanation", "")
        # difficulty在JSON中是1-5的整数，需要转换为0.0-1.0
        raw_difficulty = q.get("difficulty", 3)
        difficulty = raw_difficulty / 5.0 if isinstance(raw_difficulty, (int, float)) else 0.5
        source_info = q.get("exam_source", "") or q.get("source", "")

        # 选择题的选项转JSON
        options_json = json.dumps(options, ensure_ascii=False) if options else None

        # 插入题目 (使用正确的列名 difficulty_level)
        await session.execute(
            text("""
                INSERT INTO exercise_bank (
                    source_id, question_type, content, options,
                    answer, explanation, difficulty_level
                ) VALUES (
                    :source_id, :question_type, :content, :options,
                    :answer, :explanation, :difficulty_level
                )
            """),
            {
                "source_id": source_id,
                "question_type": q_type,
                "content": content,
                "options": options_json,
                "answer": str(answer) if answer else "",
                "explanation": explanation or "",
                "difficulty_level": difficulty
            }
        )
        count += 1

    await session.commit()
    return count


async def delete_old_2024_data(session: AsyncSession):
    """删除旧的2024年数据"""
    # 获取2024年来源ID
    result = await session.execute(
        text("SELECT id, name FROM exercise_sources WHERE year = 2024")
    )
    sources = result.fetchall()

    if not sources:
        print("  没有找到2024年的旧数据")
        return

    for source_id, source_name in sources:
        # 删除题目
        result = await session.execute(
            text("DELETE FROM exercise_bank WHERE source_id = :source_id"),
            {"source_id": source_id}
        )
        deleted_count = result.rowcount
        print(f"  删除来源 '{source_name}' 的 {deleted_count} 道题目")

        # 删除来源
        await session.execute(
            text("DELETE FROM exercise_sources WHERE id = :id"),
            {"id": source_id}
        )

    await session.commit()
    print(f"  共清理 {len(sources)} 个来源")


async def main():
    """主函数"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    extracted_dir = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted")

    total_imported = 0

    print("=" * 60)
    print("导入2024年高考题目")
    print("=" * 60)

    async with async_session() as session:
        # 先删除旧数据
        print("\n[清理] 删除旧的2024年数据...")
        await delete_old_2024_data(session)

        for filename, source_info in FILE_TO_SOURCE.items():
            file_path = extracted_dir / filename

            if not file_path.exists():
                print(f"\n[跳过] {filename}: 文件不存在")
                continue

            print(f"\n[处理] {filename}")

            # 读取JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                questions = json.load(f)

            if not questions:
                print(f"  无题目")
                continue

            print(f"  题目数量: {len(questions)}")

            # 创建来源
            source_id = await create_source(
                session,
                source_info["name"],
                2024,
                source_info["type"],
                source_info["textbook"]
            )

            # 导入题目
            imported = await import_questions(session, source_id, questions)
            print(f"  导入成功: {imported} 道")
            total_imported += imported

    await engine.dispose()

    print("\n" + "=" * 60)
    print(f"导入完成，共导入 {total_imported} 道题目")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
