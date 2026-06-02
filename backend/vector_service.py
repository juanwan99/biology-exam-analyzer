# -*- coding: utf-8 -*-
"""
向量索引服务
负责将教材内容存入数据库并生成向量Embedding
使用本地 sentence-transformers 模型生成中文向量
"""
import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from textbook_parser_v2 import TextbookParserV2, Section, Chunk
from logger import get_logger

logger = get_logger()

# 数据库配置
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biology:biology123@postgres:5432/biology_edu")

# 向量模型配置
# 使用 paraphrase-multilingual-MiniLM-L12-v2，支持中文，768维
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # MiniLM模型输出384维

# 全局模型实例（懒加载）
_model = None


def get_embedding_model():
    """获取或加载embedding模型"""
    global _model
    if _model is None:
        try:
            # 设置HuggingFace镜像
            import os
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

            from sentence_transformers import SentenceTransformer
            logger.info(f"[VectorService] 加载embedding模型: {EMBEDDING_MODEL} (使用镜像: hf-mirror.com)")
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"[VectorService] 模型加载完成，向量维度: {_model.get_sentence_embedding_dimension()}")
        except ImportError:
            logger.error("[VectorService] sentence-transformers未安装，请运行: pip install sentence-transformers")
            raise
    return _model


class VectorService:
    """向量索引服务"""

    def __init__(self):
        # 数据库连接
        self.engine = create_engine(DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        self._model = None

    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            self._model = get_embedding_model()
        return self._model

    async def process_textbook(
        self,
        pdf_path: str,
        book_name: str,
        version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理教材：解析PDF -> 存储章节 -> 生成切片 -> 创建向量

        Args:
            pdf_path: PDF文件路径
            book_name: 教材名称
            version_id: 教材版本ID（可选）

        Returns:
            处理结果统计
        """
        logger.info(f"[VectorService] 开始处理教材: {book_name}")

        # 1. 解析PDF
        parser = TextbookParserV2(pdf_path)
        try:
            sections = parser.parse()
        finally:
            parser.close()

        logger.info(f"[VectorService] 解析完成，共 {len(sections)} 个章节")

        # 2. 存储章节并生成切片
        stats = {
            "book_name": book_name,
            "total_sections": len(sections),
            "total_chunks": 0,
            "sections_processed": 0,
            "chunks_with_embeddings": 0,
            "errors": []
        }

        session = self.Session()
        try:
            for section in sections:
                try:
                    # 存储section
                    section_id = self._save_section(session, section, book_name, version_id)

                    # 生成chunks
                    chunks = parser.generate_chunks(section, section_id)
                    stats["total_chunks"] += len(chunks)

                    # 批量生成embedding（更高效）
                    chunk_texts = [c.content for c in chunks]
                    if chunk_texts:
                        embeddings = self._generate_embeddings_batch(chunk_texts)

                        # 存储chunks和embedding
                        for i, chunk in enumerate(chunks):
                            chunk_id = self._save_chunk(session, chunk, section_id)
                            if i < len(embeddings) and embeddings[i] is not None:
                                self._update_chunk_embedding(session, chunk_id, embeddings[i])
                                stats["chunks_with_embeddings"] += 1

                    stats["sections_processed"] += 1
                    session.commit()
                    logger.info(f"[VectorService] 已处理: {section.full_title} ({len(chunks)}个切片)")

                except Exception as e:
                    session.rollback()
                    logger.error(f"[VectorService] 处理章节失败: {e}")
                    stats["errors"].append(f"Section {section.full_title}: {str(e)}")

        finally:
            session.close()

        logger.info(f"[VectorService] 处理完成: 共{stats['sections_processed']}个章节, {stats['chunks_with_embeddings']}个向量")
        return stats

    def _save_section(
        self,
        session,
        section: Section,
        book_name: str,
        version_id: Optional[int]
    ) -> int:
        """保存章节到数据库"""
        sql = text("""
            INSERT INTO textbook_sections
            (version_id, book_name, chapter_num, chapter_title, section_num, section_title,
             full_content, page_start, page_end, images, metadata)
            VALUES
            (:version_id, :book_name, :chapter_num, :chapter_title, :section_num, :section_title,
             :full_content, :page_start, :page_end, :images, :metadata)
            RETURNING id
        """)

        result = session.execute(sql, {
            "version_id": version_id,
            "book_name": book_name,
            "chapter_num": section.chapter_num,
            "chapter_title": section.chapter_title,
            "section_num": section.section_num,
            "section_title": section.section_title,
            "full_content": section.content,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "images": json.dumps(section.images),
            "metadata": json.dumps({})
        })

        return result.fetchone()[0]

    def _save_chunk(self, session, chunk: Chunk, section_id: int) -> int:
        """保存切片到数据库"""
        sql = text("""
            INSERT INTO textbook_chunks
            (section_id, chunk_index, chunk_content, page_num, metadata)
            VALUES
            (:section_id, :chunk_index, :chunk_content, :page_num, :metadata)
            RETURNING id
        """)

        result = session.execute(sql, {
            "section_id": section_id,
            "chunk_index": chunk.chunk_index,
            "chunk_content": chunk.content,
            "page_num": chunk.page_num,
            "metadata": json.dumps({})
        })

        return result.fetchone()[0]

    def _update_chunk_embedding(self, session, chunk_id: int, embedding: List[float]):
        """更新切片的向量"""
        # pgvector需要特殊的向量格式
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        sql = text("""
            UPDATE textbook_chunks
            SET embedding = CAST(:embedding AS vector)
            WHERE id = :chunk_id
        """)

        session.execute(sql, {
            "chunk_id": chunk_id,
            "embedding": embedding_str
        })

    def _generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """批量生成文本向量"""
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"[VectorService] 批量生成embedding失败: {e}")
            return [None] * len(texts)

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成单个文本向量"""
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"[VectorService] 生成embedding失败: {e}")
            return None

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        book_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        语义搜索：找到与查询最相似的内容

        Args:
            query: 查询文本
            top_k: 返回结果数量
            book_name: 限定教材名称（可选）

        Returns:
            相似内容列表，包含章节信息
        """
        # 生成查询向量
        query_embedding = self._generate_embedding(query)
        if not query_embedding:
            return []

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        session = self.Session()
        try:
            # 构建SQL - 使用余弦相似度
            if book_name:
                sql = text("""
                    SELECT
                        c.id,
                        c.chunk_content,
                        c.page_num,
                        c.chunk_index,
                        s.id as section_id,
                        s.chapter_num,
                        s.chapter_title,
                        s.section_num,
                        s.section_title,
                        s.book_name,
                        1 - (c.embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM textbook_chunks c
                    JOIN textbook_sections s ON c.section_id = s.id
                    WHERE c.embedding IS NOT NULL
                    AND s.book_name = :book_name
                    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :top_k
                """)
                params = {
                    "query_embedding": embedding_str,
                    "book_name": book_name,
                    "top_k": top_k
                }
            else:
                sql = text("""
                    SELECT
                        c.id,
                        c.chunk_content,
                        c.page_num,
                        c.chunk_index,
                        s.id as section_id,
                        s.chapter_num,
                        s.chapter_title,
                        s.section_num,
                        s.section_title,
                        s.book_name,
                        1 - (c.embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM textbook_chunks c
                    JOIN textbook_sections s ON c.section_id = s.id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :top_k
                """)
                params = {
                    "query_embedding": embedding_str,
                    "top_k": top_k
                }

            result = session.execute(sql, params)
            rows = result.fetchall()

            # 格式化结果
            results = []
            for row in rows:
                # 构建章节标题
                if row.section_title:
                    full_title = f"第{row.chapter_num}章 {row.chapter_title} - 第{row.section_num}节 {row.section_title}"
                else:
                    full_title = f"第{row.chapter_num}章 {row.chapter_title}"

                results.append({
                    "chunk_id": row.id,
                    "content": row.chunk_content,
                    "page_num": row.page_num,
                    "section_id": row.section_id,
                    "chapter_num": row.chapter_num,
                    "chapter_title": row.chapter_title,
                    "section_num": row.section_num,
                    "section_title": row.section_title,
                    "full_title": full_title,
                    "book_name": row.book_name,
                    "similarity": float(row.similarity) if row.similarity else 0.0
                })

            return results

        finally:
            session.close()

    async def get_section_context(self, section_id: int) -> Optional[Dict[str, Any]]:
        """
        获取完整的章节内容（用于LLM上下文）
        """
        session = self.Session()
        try:
            sql = text("""
                SELECT
                    id, book_name, chapter_num, chapter_title,
                    section_num, section_title, full_content,
                    page_start, page_end
                FROM textbook_sections
                WHERE id = :section_id
            """)

            result = session.execute(sql, {"section_id": section_id})
            row = result.fetchone()

            if not row:
                return None

            if row.section_title:
                full_title = f"第{row.chapter_num}章 {row.chapter_title} - 第{row.section_num}节 {row.section_title}"
            else:
                full_title = f"第{row.chapter_num}章 {row.chapter_title}"

            return {
                "id": row.id,
                "book_name": row.book_name,
                "chapter_num": row.chapter_num,
                "chapter_title": row.chapter_title,
                "section_num": row.section_num,
                "section_title": row.section_title,
                "full_title": full_title,
                "full_content": row.full_content,
                "page_start": row.page_start,
                "page_end": row.page_end
            }

        finally:
            session.close()

    def clear_book_data(self, book_name: str):
        """清除指定教材的所有数据"""
        session = self.Session()
        try:
            # 先删除chunks（外键关联）
            sql = text("""
                DELETE FROM textbook_chunks
                WHERE section_id IN (
                    SELECT id FROM textbook_sections WHERE book_name = :book_name
                )
            """)
            session.execute(sql, {"book_name": book_name})

            # 再删除sections
            sql = text("DELETE FROM textbook_sections WHERE book_name = :book_name")
            session.execute(sql, {"book_name": book_name})

            session.commit()
            logger.info(f"[VectorService] 已清除教材数据: {book_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"[VectorService] 清除数据失败: {e}")
            raise
        finally:
            session.close()


async def test_vector_service():
    """测试向量服务"""
    import sys

    service = VectorService()

    if len(sys.argv) >= 2:
        action = sys.argv[1]

        if action == "process" and len(sys.argv) >= 4:
            pdf_path = sys.argv[2]
            book_name = sys.argv[3]
            result = await service.process_textbook(pdf_path, book_name)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif action == "search" and len(sys.argv) >= 3:
            query = sys.argv[2]
            results = await service.search_similar(query, top_k=5)
            print(f"\n搜索: {query}\n")
            print("=" * 60)
            for i, r in enumerate(results, 1):
                print(f"\n{i}. [{r['full_title']}] (P{r['page_num']}, 相似度: {r['similarity']:.4f})")
                print(f"   {r['content'][:200]}...")

        elif action == "clear" and len(sys.argv) >= 3:
            book_name = sys.argv[2]
            service.clear_book_data(book_name)
            print(f"已清除教材数据: {book_name}")

        else:
            print("用法:")
            print("  python vector_service.py process <pdf_path> <book_name>")
            print("  python vector_service.py search <query>")
            print("  python vector_service.py clear <book_name>")
    else:
        print("用法:")
        print("  python vector_service.py process <pdf_path> <book_name>")
        print("  python vector_service.py search <query>")
        print("  python vector_service.py clear <book_name>")


if __name__ == "__main__":
    asyncio.run(test_vector_service())
