# -*- coding: utf-8 -*-
"""
Vision Processor 服务
使用 Qwen-VL 视觉模型从 PDF 页面提取 Markdown 文本
"""
import os
import base64
import asyncio
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

import httpx
import fitz  # PyMuPDF
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logger import get_logger

logger = get_logger()

# 数据库配置
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biology:biology123@postgres:5432/biology_edu")

# 视觉模型 API 配置
API_KEY = os.environ.get("QWEN_API_KEY_2", os.environ.get("QWEN_API_KEY", ""))
API_BASE = os.environ.get("QWEN_API_BASE", "")
VISION_MODEL = "qwen-vl-max"

# 提示词
EXTRACTION_PROMPT = """你是一个专业的教材数字化专家。请阅读这张图片，将其内容转换为标准的 Markdown 格式。

**要求：**
1. **排版识别：** 严格区分主栏正文和侧栏（如"相关信息"、"小贴士"等）。侧栏内容请使用引用格式 `>` 包裹，并在合适位置插入。
2. **章节标题：** 如果有章节标题（如"第X章"、"第X节"），请使用 ## 或 ### 标记。
3. **过滤噪音：** 自动去除页眉、页脚和页码。
4. **图片描述：** 如果遇到图表或插图，请插入 `[图片: 对图片的简短描述]`。
5. **表格还原：** 如果有表格，输出为 Markdown Table 格式。
6. **公式：** 如果遇到生物/化学公式，使用行内格式表示。
7. **纯净输出：** 不要输出任何解释或闲聊，只输出 Markdown 内容。"""

# 教材ID映射
BOOK_ID_MAP = {
    "必修1": "bx1",
    "必修2": "bx2",
    "选择性必修1": "xxbx1",
    "选择性必修2": "xxbx2",
    "选择性必修3": "xxbx3",
}

# 向量模型配置
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80

# 全局模型实例
_embedding_model = None


def get_embedding_model():
    """获取或加载embedding模型"""
    global _embedding_model
    if _embedding_model is None:
        try:
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            from sentence_transformers import SentenceTransformer
            logger.info(f"[VisionProcessor] 加载embedding模型: {EMBEDDING_MODEL}")
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"[VisionProcessor] 模型加载完成")
        except ImportError:
            logger.error("[VisionProcessor] sentence-transformers未安装")
            raise
    return _embedding_model


def detect_book_info(filename: str) -> Dict[str, str]:
    """从文件名检测教材信息"""
    # 默认值
    book_id = "unknown"
    book_name = filename

    # 注意：必须先检测"选择性必修X"，再检测"必修X"
    # 因为"选择性必修1"中也包含"必修1"字符串
    if "选择性必修1" in filename or "稳态与调节" in filename:
        book_id = "xxbx1"
        book_name = "生物学选择性必修1·稳态与调节"
    elif "选择性必修2" in filename or "生物与环境" in filename:
        book_id = "xxbx2"
        book_name = "生物学选择性必修2·生物与环境"
    elif "选择性必修3" in filename or "生物技术与工程" in filename:
        book_id = "xxbx3"
        book_name = "生物学选择性必修3·生物技术与工程"
    elif "必修1" in filename or "分子与细胞" in filename:
        book_id = "bx1"
        book_name = "生物学必修1·分子与细胞"
    elif "必修2" in filename or "遗传与进化" in filename:
        book_id = "bx2"
        book_name = "生物学必修2·遗传与进化"

    return {"book_id": book_id, "book_name": book_name}


class VisionProcessor:
    """视觉处理器"""

    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        self._embedding_model = None

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model()
        return self._embedding_model

    async def extract_page_markdown(
        self,
        image_base64: str,
        page_num: int,
        timeout: float = 120.0
    ) -> Optional[str]:
        """
        使用 Qwen-VL 从图片提取 Markdown
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{API_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": VISION_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_base64}"
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": EXTRACTION_PROMPT
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 4000,
                        "temperature": 0.1
                    }
                )

                if response.status_code != 200:
                    logger.error(f"[VisionProcessor] API错误 (P{page_num}): {response.status_code}")
                    return None

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                logger.info(f"[VisionProcessor] P{page_num} 提取成功, tokens={usage.get('completion_tokens', 'N/A')}")
                return content

            except Exception as e:
                logger.error(f"[VisionProcessor] 提取失败 (P{page_num}): {e}")
                return None

    def pdf_page_to_image(self, doc: fitz.Document, page_num: int, dpi: float = 2.0) -> str:
        """将PDF页面转换为base64图片"""
        page = doc[page_num - 1]  # 0-based
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi, dpi))
        img_bytes = pix.tobytes("png")
        return base64.b64encode(img_bytes).decode("utf-8")

    def generate_chunks(self, markdown_content: str, page_num: int) -> List[Dict[str, Any]]:
        """从Markdown生成切片"""
        content = markdown_content.strip()
        if not content:
            return []

        chunks = []

        if len(content) <= CHUNK_SIZE:
            chunks.append({
                "chunk_index": 0,
                "content": content,
                "page_num": page_num
            })
            return chunks

        # 滑动窗口切分
        start = 0
        chunk_index = 0

        while start < len(content):
            end = start + CHUNK_SIZE

            # 尽量在句号处断开
            if end < len(content):
                for sep in ['。', '！', '？', '\n\n', '\n']:
                    punct_pos = content.find(sep, end - 50, end + 50)
                    if punct_pos > 0:
                        end = punct_pos + len(sep)
                        break

            chunk_text = content[start:end].strip()
            if chunk_text:
                chunks.append({
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                    "page_num": page_num
                })
                chunk_index += 1

            start = end - CHUNK_OVERLAP
            if start >= len(content) - CHUNK_OVERLAP:
                break

        return chunks

    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """批量生成向量"""
        try:
            embeddings = self.embedding_model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"[VisionProcessor] 生成embedding失败: {e}")
            return [None] * len(texts)

    async def process_pdf(
        self,
        pdf_path: str,
        start_page: int = 1,
        end_page: Optional[int] = None,
        skip_existing: bool = True,
        delay: float = 1.0
    ) -> Dict[str, Any]:
        """
        处理整本PDF教材

        Args:
            pdf_path: PDF文件路径
            start_page: 起始页码
            end_page: 结束页码（None表示到末尾）
            skip_existing: 是否跳过已处理的页面
            delay: API调用间隔（秒）

        Returns:
            处理统计信息
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return {"error": f"文件不存在: {pdf_path}"}

        # 检测教材信息
        book_info = detect_book_info(pdf_path.name)
        book_id = book_info["book_id"]
        book_name = book_info["book_name"]

        logger.info(f"[VisionProcessor] 开始处理: {book_name} ({book_id})")

        # 打开PDF
        doc = fitz.open(str(pdf_path))
        total_pages = doc.page_count

        if end_page is None or end_page > total_pages:
            end_page = total_pages

        logger.info(f"[VisionProcessor] 总页数: {total_pages}, 处理范围: P{start_page}-{end_page}")

        stats = {
            "book_id": book_id,
            "book_name": book_name,
            "total_pages": end_page - start_page + 1,
            "pages_processed": 0,
            "pages_skipped": 0,
            "total_chunks": 0,
            "chunks_with_embeddings": 0,
            "errors": []
        }

        session = self.Session()

        try:
            for page_num in range(start_page, end_page + 1):
                # 检查是否已处理
                if skip_existing:
                    existing = session.execute(
                        text("SELECT id FROM textbook_pages WHERE book_id = :book_id AND page_num = :page_num"),
                        {"book_id": book_id, "page_num": page_num}
                    ).fetchone()

                    if existing:
                        logger.info(f"[VisionProcessor] P{page_num} 已存在，跳过")
                        stats["pages_skipped"] += 1
                        continue

                logger.info(f"[VisionProcessor] 处理 P{page_num}/{end_page}...")

                # 转换为图片
                img_base64 = self.pdf_page_to_image(doc, page_num)

                # 调用AI提取Markdown
                markdown = await self.extract_page_markdown(img_base64, page_num)

                if not markdown:
                    stats["errors"].append(f"P{page_num}: 提取失败")
                    continue

                # 存储页面
                result = session.execute(
                    text("""
                        INSERT INTO textbook_pages (book_id, book_name, page_num, markdown_content)
                        VALUES (:book_id, :book_name, :page_num, :markdown_content)
                        ON CONFLICT (book_id, page_num) DO UPDATE SET markdown_content = :markdown_content
                        RETURNING id
                    """),
                    {
                        "book_id": book_id,
                        "book_name": book_name,
                        "page_num": page_num,
                        "markdown_content": markdown
                    }
                )
                page_id = result.fetchone()[0]

                # 生成切片
                chunks = self.generate_chunks(markdown, page_num)
                stats["total_chunks"] += len(chunks)

                if chunks:
                    # 批量生成向量
                    chunk_texts = [c["content"] for c in chunks]
                    embeddings = self.generate_embeddings_batch(chunk_texts)

                    # 存储切片
                    for i, chunk in enumerate(chunks):
                        embedding_str = None
                        if i < len(embeddings) and embeddings[i]:
                            embedding_str = "[" + ",".join(map(str, embeddings[i])) + "]"
                            stats["chunks_with_embeddings"] += 1

                        session.execute(
                            text("""
                                INSERT INTO textbook_chunks
                                (page_id, book_id, chunk_index, chunk_content, page_num, embedding)
                                VALUES (:page_id, :book_id, :chunk_index, :chunk_content, :page_num,
                                        CAST(:embedding AS vector))
                            """),
                            {
                                "page_id": page_id,
                                "book_id": book_id,
                                "chunk_index": chunk["chunk_index"],
                                "chunk_content": chunk["content"],
                                "page_num": page_num,
                                "embedding": embedding_str
                            }
                        )

                session.commit()
                stats["pages_processed"] += 1
                logger.info(f"[VisionProcessor] P{page_num} 完成, {len(chunks)}个切片")

                # API限流
                await asyncio.sleep(delay)

        except Exception as e:
            session.rollback()
            logger.error(f"[VisionProcessor] 处理失败: {e}")
            stats["errors"].append(str(e))

        finally:
            session.close()
            doc.close()

        logger.info(f"[VisionProcessor] 处理完成: {stats['pages_processed']}页, {stats['chunks_with_embeddings']}个向量")
        return stats

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        book_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        语义搜索
        """
        # 生成查询向量
        try:
            query_embedding = self.embedding_model.encode(query, convert_to_numpy=True).tolist()
        except Exception as e:
            logger.error(f"[VisionProcessor] 查询向量生成失败: {e}")
            return []

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        session = self.Session()
        try:
            if book_id:
                sql = text("""
                    SELECT
                        c.id, c.chunk_content, c.page_num, c.book_id,
                        p.book_name,
                        1 - (c.embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM textbook_chunks c
                    JOIN textbook_pages p ON c.page_id = p.id
                    WHERE c.embedding IS NOT NULL AND c.book_id = :book_id
                    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :top_k
                """)
                params = {"query_embedding": embedding_str, "book_id": book_id, "top_k": top_k}
            else:
                sql = text("""
                    SELECT
                        c.id, c.chunk_content, c.page_num, c.book_id,
                        p.book_name,
                        1 - (c.embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM textbook_chunks c
                    JOIN textbook_pages p ON c.page_id = p.id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :top_k
                """)
                params = {"query_embedding": embedding_str, "top_k": top_k}

            result = session.execute(sql, params)
            rows = result.fetchall()

            results = []
            for row in rows:
                results.append({
                    "chunk_id": row.id,
                    "content": row.chunk_content,
                    "page_num": row.page_num,
                    "book_id": row.book_id,
                    "book_name": row.book_name,
                    "similarity": float(row.similarity) if row.similarity else 0.0
                })

            return results

        finally:
            session.close()

    def clear_book_data(self, book_id: str):
        """清除指定教材的所有数据"""
        session = self.Session()
        try:
            session.execute(
                text("DELETE FROM textbook_chunks WHERE book_id = :book_id"),
                {"book_id": book_id}
            )
            session.execute(
                text("DELETE FROM textbook_pages WHERE book_id = :book_id"),
                {"book_id": book_id}
            )
            session.commit()
            logger.info(f"[VisionProcessor] 已清除教材数据: {book_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"[VisionProcessor] 清除数据失败: {e}")
            raise
        finally:
            session.close()

    def get_book_stats(self) -> List[Dict[str, Any]]:
        """获取各教材的处理统计"""
        session = self.Session()
        try:
            sql = text("""
                SELECT
                    p.book_id,
                    p.book_name,
                    COUNT(DISTINCT p.id) as page_count,
                    COUNT(c.id) as chunk_count,
                    COUNT(CASE WHEN c.embedding IS NOT NULL THEN 1 END) as embedding_count
                FROM textbook_pages p
                LEFT JOIN textbook_chunks c ON c.page_id = p.id
                GROUP BY p.book_id, p.book_name
                ORDER BY p.book_id
            """)
            result = session.execute(sql)
            rows = result.fetchall()

            return [
                {
                    "book_id": row.book_id,
                    "book_name": row.book_name,
                    "page_count": row.page_count,
                    "chunk_count": row.chunk_count,
                    "embedding_count": row.embedding_count
                }
                for row in rows
            ]
        finally:
            session.close()


async def main():
    """命令行入口"""
    import sys

    processor = VisionProcessor()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python vision_processor.py process <pdf_path> [start_page] [end_page]")
        print("  python vision_processor.py search <query> [book_id]")
        print("  python vision_processor.py stats")
        print("  python vision_processor.py clear <book_id>")
        return

    action = sys.argv[1]

    if action == "process" and len(sys.argv) >= 3:
        pdf_path = sys.argv[2]
        start_page = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        end_page = int(sys.argv[4]) if len(sys.argv) > 4 else None

        result = await processor.process_pdf(pdf_path, start_page, end_page)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == "search" and len(sys.argv) >= 3:
        query = sys.argv[2]
        book_id = sys.argv[3] if len(sys.argv) > 3 else None

        results = await processor.search_similar(query, top_k=5, book_id=book_id)
        print(f"\n搜索: {query}\n")
        print("=" * 60)
        for i, r in enumerate(results, 1):
            print(f"\n{i}. [{r['book_name']}] P{r['page_num']} (相似度: {r['similarity']:.4f})")
            print(f"   {r['content'][:200]}...")

    elif action == "stats":
        stats = processor.get_book_stats()
        print("\n教材处理统计:")
        print("=" * 60)
        for s in stats:
            print(f"{s['book_id']}: {s['book_name']}")
            print(f"  页数: {s['page_count']}, 切片: {s['chunk_count']}, 向量: {s['embedding_count']}")

    elif action == "clear" and len(sys.argv) >= 3:
        book_id = sys.argv[2]
        processor.clear_book_data(book_id)
        print(f"已清除教材数据: {book_id}")

    else:
        print("无效命令")


if __name__ == "__main__":
    asyncio.run(main())
