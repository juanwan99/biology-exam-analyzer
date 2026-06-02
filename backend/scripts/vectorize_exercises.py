#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题库向量化脚本
为exercise_bank表中的题目生成向量embedding
"""
import os
import sys
import time
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# 设置HuggingFace镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biology:biology123@localhost:5432/biology_edu")
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 50  # 每批处理的题目数

# 全局模型
_model = None


def get_model():
    """加载embedding模型"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print(f"加载模型: {EMBEDDING_MODEL}...")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"模型加载完成, 维度: {_model.get_sentence_embedding_dimension()}")
    return _model


def get_exercise_text(row) -> str:
    """
    组合题目内容生成用于embedding的文本
    包含: 题目内容 + 选项 + 答案 + 解析
    """
    parts = []

    # 题目内容
    if row.content:
        parts.append(row.content)

    # 选项（如果是选择题）
    if row.options:
        if isinstance(row.options, dict):
            for key, value in row.options.items():
                parts.append(f"{key}. {value}")

    # 答案
    if row.answer:
        parts.append(f"答案: {row.answer}")

    # 解析
    if row.explanation:
        parts.append(f"解析: {row.explanation}")

    return "\n".join(parts)


def vectorize_exercises(batch_size: int = BATCH_SIZE):
    """向量化所有未处理的题目"""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    model = get_model()

    try:
        # 获取总数和未向量化数
        result = session.execute(text("SELECT COUNT(*) FROM exercise_bank"))
        total = result.scalar()

        result = session.execute(text("SELECT COUNT(*) FROM exercise_bank WHERE content_embedding IS NULL"))
        pending = result.scalar()

        print(f"\n题库统计: 总计 {total} 题, 待向量化 {pending} 题")

        if pending == 0:
            print("所有题目已完成向量化!")
            return

        processed = 0
        start_time = time.time()

        while True:
            # 获取一批未向量化的题目
            result = session.execute(text("""
                SELECT id, content, options, answer, explanation
                FROM exercise_bank
                WHERE content_embedding IS NULL
                LIMIT :limit
            """), {"limit": batch_size})

            rows = result.fetchall()
            if not rows:
                break

            # 准备文本
            ids = []
            texts = []
            for row in rows:
                ids.append(row.id)
                texts.append(get_exercise_text(row))

            # 批量生成embedding
            embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

            # 更新数据库
            for i, (ex_id, embedding) in enumerate(zip(ids, embeddings)):
                embedding_str = "[" + ",".join(map(str, embedding.tolist())) + "]"
                session.execute(
                    text("""
                        UPDATE exercise_bank
                        SET content_embedding = CAST(:embedding AS vector)
                        WHERE id = :id
                    """),
                    {"id": ex_id, "embedding": embedding_str}
                )

            session.commit()
            processed += len(rows)

            # 进度显示
            elapsed = time.time() - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            remaining = (pending - processed) / speed if speed > 0 else 0

            print(f"进度: {processed}/{pending} ({processed*100/pending:.1f}%) "
                  f"| 速度: {speed:.1f}题/秒 | 剩余: {remaining:.0f}秒")

        print(f"\n完成! 共处理 {processed} 道题目, 耗时 {time.time()-start_time:.1f}秒")

    except Exception as e:
        session.rollback()
        print(f"错误: {e}")
        raise
    finally:
        session.close()


def verify_vectors():
    """验证向量化结果"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # 统计
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(content_embedding) as vectorized
            FROM exercise_bank
        """))
        row = result.fetchone()
        print(f"\n向量化统计:")
        print(f"  总题目数: {row.total}")
        print(f"  已向量化: {row.vectorized}")
        print(f"  完成率: {row.vectorized*100/row.total:.1f}%")

        # 测试向量搜索
        if row.vectorized > 0:
            print("\n测试向量搜索...")
            model = get_model()

            # 测试查询
            test_query = "DNA复制"
            query_embedding = model.encode(test_query, convert_to_numpy=True)
            embedding_str = "[" + ",".join(map(str, query_embedding.tolist())) + "]"

            result = conn.execute(text("""
                SELECT id, question_type, LEFT(content, 100) as content_preview,
                       1 - (content_embedding <=> CAST(:embedding AS vector)) as similarity
                FROM exercise_bank
                WHERE content_embedding IS NOT NULL
                ORDER BY content_embedding <=> CAST(:embedding AS vector)
                LIMIT 5
            """), {"embedding": embedding_str})

            print(f"\n搜索 '{test_query}' 的结果:")
            for i, r in enumerate(result.fetchall(), 1):
                print(f"  {i}. [ID:{r.id}] {r.question_type} (相似度:{r.similarity:.4f})")
                print(f"     {r.content_preview}...")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_vectors()
    else:
        vectorize_exercises()
        print("\n" + "="*60)
        verify_vectors()
