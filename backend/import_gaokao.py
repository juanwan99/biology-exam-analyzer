"""
将提取的高考真题导入数据库
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, async_session
from models import ExerciseSource, ExerciseBank, Resource
from logger import get_logger

logger = get_logger()


async def import_gaokao_questions():
    """导入高考真题到数据库"""

    extracted_dir = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted")
    json_files = list(extracted_dir.glob("*_v2.json"))

    print(f"\n{'='*60}")
    print("导入高考真题到数据库")
    print(f"{'='*60}")
    print(f"找到 {len(json_files)} 个 JSON 文件")

    async with async_session() as db:
        try:
            # 统计
            stats = {
                "sources_created": 0,
                "questions_imported": 0,
                "images_imported": 0,
                "errors": []
            }

            for json_file in json_files:
                category = json_file.stem.replace("_v2", "")
                print(f"\n处理: {category}")

                # 读取题目数据
                with open(json_file, 'r', encoding='utf-8') as f:
                    questions = json.load(f)

                if not questions:
                    print(f"  跳过: 无题目")
                    continue

                # 查找对应的图片目录
                images_dir = extracted_dir / f"{category}_images"
                images_available = images_dir.exists()

                # 按年份和来源分组创建 ExerciseSource
                source_cache = {}

                for q in questions:
                    year = q.get("year", 0)
                    exam_source = q.get("exam_source", "未知来源")
                    source_key = f"{year}_{exam_source}"

                    if source_key not in source_cache:
                        # 检查是否已存在
                        result = await db.execute(
                            select(ExerciseSource).filter(
                                ExerciseSource.year == year,
                                ExerciseSource.name == f"{year}年{exam_source}生物"
                            )
                        )
                        existing = result.scalar_one_or_none()

                        if existing:
                            source_cache[source_key] = existing.id
                        else:
                            # 创建新来源
                            new_source = ExerciseSource(
                                name=f"{year}年{exam_source}生物",
                                source_type="高考",
                                year=year,
                                region=exam_source.replace("卷", ""),
                                description=f"{year}年高考{exam_source}生物试题 - {category}"
                            )
                            db.add(new_source)
                            await db.flush()
                            source_cache[source_key] = new_source.id
                            stats["sources_created"] += 1

                    # 准备题目数据
                    question_type_map = {
                        "single_choice": "单选题",
                        "multiple_choice": "多选题",
                        "fill_blank": "填空题",
                        "short_answer": "简答题"
                    }

                    # 处理图片
                    image_refs = []
                    if q.get("image_ids") and images_available:
                        for img_id in q["image_ids"]:
                            # 检查图片文件
                            img_file = None
                            for ext in ["png", "jpg", "jpeg"]:
                                candidate = images_dir / f"{img_id}.{ext}"
                                if candidate.exists():
                                    img_file = candidate
                                    break

                            if img_file:
                                # 保存图片引用
                                image_refs.append({
                                    "id": img_id,
                                    "path": str(img_file.relative_to(Path("/home/ubuntu/biology-exam-analyzer")))
                                })
                                stats["images_imported"] += 1

                    # 构建题目内容
                    content = q.get("stem", "")

                    # 处理难度值
                    difficulty = q.get("difficulty")
                    if difficulty is None:
                        difficulty = 3
                    difficulty_level = difficulty / 5.0

                    # 创建题目记录
                    exercise = ExerciseBank(
                        source_id=source_cache[source_key],
                        question_type=question_type_map.get(q.get("question_type", "single_choice"), "单选题"),
                        content=content,
                        options=q.get("options"),
                        answer=q.get("answer", ""),
                        explanation=q.get("explanation", ""),
                        difficulty_level=difficulty_level,
                        tags=[category] + (q.get("knowledge_points") or []),
                        competency_scores={
                            "images": image_refs,
                            "table_index": q.get("table_index"),
                            "year": year,
                            "exam_source": exam_source,
                            "question_number": q.get("question_number")
                        }
                    )

                    db.add(exercise)
                    stats["questions_imported"] += 1

                await db.commit()
                print(f"  导入 {len(questions)} 道题")

            # 最终统计
            print(f"\n{'='*60}")
            print("导入完成")
            print(f"{'='*60}")
            print(f"创建来源: {stats['sources_created']} 个")
            print(f"导入题目: {stats['questions_imported']} 道")
            print(f"关联图片: {stats['images_imported']} 张")

            if stats["errors"]:
                print(f"\n错误:")
                for err in stats["errors"]:
                    print(f"  - {err}")

            return stats

        except Exception as e:
            await db.rollback()
            print(f"导入失败: {e}")
            raise


async def verify_import():
    """验证导入结果"""
    async with async_session() as db:
        # 统计题目
        result = await db.execute(select(func.count(ExerciseBank.id)))
        total_exercises = result.scalar()

        # 按类型统计
        result = await db.execute(
            select(
                ExerciseBank.question_type,
                func.count(ExerciseBank.id)
            ).group_by(ExerciseBank.question_type)
        )
        type_counts = result.all()

        # 来源统计
        result = await db.execute(
            select(
                ExerciseSource.name,
                func.count(ExerciseBank.id)
            ).join(ExerciseBank).group_by(ExerciseSource.name).limit(10)
        )
        source_counts = result.all()

        print(f"\n{'='*60}")
        print("数据库验证")
        print(f"{'='*60}")
        print(f"题库总数: {total_exercises}")
        print(f"\n题型分布:")
        for qt, count in type_counts:
            print(f"  {qt}: {count}")
        print(f"\n来源示例 (前10):")
        for name, count in source_counts:
            print(f"  {name}: {count}")


async def main():
    await import_gaokao_questions()
    await verify_import()


if __name__ == "__main__":
    asyncio.run(main())
