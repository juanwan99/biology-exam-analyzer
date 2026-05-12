# -*- coding: utf-8 -*-
"""
知识库API路由 - 基于Vision处理的新数据结构
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

from logger import get_logger
from chapter_locator import locate_chapter

logger = get_logger()

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])

# 数据库配置
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biology:biology123@postgres:5432/biology_edu")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# 教材信息映射
BOOK_INFO = {
    "bx1": {"name": "生物学必修1·分子与细胞", "short": "必修1"},
    "bx2": {"name": "生物学必修2·遗传与进化", "short": "必修2"},
    "xxbx1": {"name": "生物学选择性必修1·稳态与调节", "short": "选必1"},
    "xxbx2": {"name": "生物学选择性必修2·生物与环境", "short": "选必2"},
    "xxbx3": {"name": "生物学选择性必修3·生物技术与工程", "short": "选必3"},
}


# ============ Pydantic Models ============

class SearchRequest(BaseModel):
    """搜索请求"""
    query: str
    top_k: int = 10
    book_id: Optional[str] = None


# ============ API Endpoints ============

@router.get("/stats")
async def get_knowledge_stats():
    """获取知识库统计信息"""
    session = Session()
    try:
        # 获取各教材的统计
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

        books = []
        total_pages = 0
        total_chunks = 0
        total_embeddings = 0

        for row in rows:
            books.append({
                "book_id": row.book_id,
                "book_name": row.book_name,
                "short_name": BOOK_INFO.get(row.book_id, {}).get("short", row.book_id),
                "page_count": row.page_count,
                "chunk_count": row.chunk_count,
                "embedding_count": row.embedding_count
            })
            total_pages += row.page_count
            total_chunks += row.chunk_count
            total_embeddings += row.embedding_count

        return {
            "success": True,
            "data": {
                "books": books,
                "total_books": len(books),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "total_embeddings": total_embeddings
            }
        }
    finally:
        session.close()


@router.get("/books")
async def get_books():
    """获取所有已处理的教材列表"""
    session = Session()
    try:
        sql = text("""
            SELECT DISTINCT book_id, book_name, COUNT(*) as page_count
            FROM textbook_pages
            GROUP BY book_id, book_name
            ORDER BY book_id
        """)
        result = session.execute(sql)
        rows = result.fetchall()

        books = []
        for row in rows:
            books.append({
                "book_id": row.book_id,
                "book_name": row.book_name,
                "short_name": BOOK_INFO.get(row.book_id, {}).get("short", row.book_id),
                "page_count": row.page_count
            })

        return {"success": True, "data": books}
    finally:
        session.close()


@router.get("/books/{book_id}/pages")
async def get_book_pages(book_id: str, page: int = 1, limit: int = 20):
    """获取指定教材的页面列表"""
    session = Session()
    try:
        offset = (page - 1) * limit

        # 获取总数
        count_sql = text("SELECT COUNT(*) FROM textbook_pages WHERE book_id = :book_id")
        total = session.execute(count_sql, {"book_id": book_id}).scalar()

        # 获取页面列表
        sql = text("""
            SELECT id, book_id, book_name, page_num,
                   SUBSTRING(markdown_content, 1, 300) as preview,
                   LENGTH(markdown_content) as content_length,
                   created_at
            FROM textbook_pages
            WHERE book_id = :book_id
            ORDER BY page_num
            LIMIT :limit OFFSET :offset
        """)
        result = session.execute(sql, {"book_id": book_id, "limit": limit, "offset": offset})
        rows = result.fetchall()

        pages = []
        for row in rows:
            pages.append({
                "id": row.id,
                "page_num": row.page_num,
                "preview": row.preview,
                "content_length": row.content_length,
                "created_at": str(row.created_at) if row.created_at else None
            })

        return {
            "success": True,
            "data": {
                "pages": pages,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit
            }
        }
    finally:
        session.close()


@router.get("/pages/{page_id}")
async def get_page_content(page_id: int):
    """获取单个页面的完整内容"""
    session = Session()
    try:
        sql = text("""
            SELECT id, book_id, book_name, page_num, markdown_content, created_at
            FROM textbook_pages
            WHERE id = :page_id
        """)
        result = session.execute(sql, {"page_id": page_id})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="页面不存在")

        # 获取该页面的切片
        chunks_sql = text("""
            SELECT id, chunk_index, chunk_content,
                   CASE WHEN embedding IS NOT NULL THEN true ELSE false END as has_embedding
            FROM textbook_chunks
            WHERE page_id = :page_id
            ORDER BY chunk_index
        """)
        chunks_result = session.execute(chunks_sql, {"page_id": page_id})
        chunks = [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.chunk_content,
                "has_embedding": c.has_embedding
            }
            for c in chunks_result.fetchall()
        ]

        return {
            "success": True,
            "data": {
                "id": row.id,
                "book_id": row.book_id,
                "book_name": row.book_name,
                "page_num": row.page_num,
                "markdown_content": row.markdown_content,
                "created_at": str(row.created_at) if row.created_at else None,
                "chunks": chunks
            }
        }
    finally:
        session.close()


@router.post("/search")
async def search_knowledge(request: SearchRequest):
    """语义搜索知识库"""
    try:
        # 动态导入以避免启动时加载模型
        from vision_processor import VisionProcessor

        processor = VisionProcessor()
        results = await processor.search_similar(
            query=request.query,
            top_k=request.top_k,
            book_id=request.book_id
        )

        # 格式化结果，添加章节定位
        formatted_results = []
        for r in results:
            # 获取章节信息
            chapter_info = locate_chapter(r["book_id"], r["page_num"], r["content"])

            formatted_results.append({
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "page_num": r["page_num"],
                "book_id": r["book_id"],
                "book_name": r["book_name"],
                "short_name": BOOK_INFO.get(r["book_id"], {}).get("short", r["book_id"]),
                "similarity": round(r["similarity"], 4),
                # 章节定位信息
                "chapter": chapter_info.get("chapter", ""),
                "chapter_title": chapter_info.get("chapter_title", ""),
                "section": chapter_info.get("section", ""),
                "section_title": chapter_info.get("section_title", ""),
                "location": chapter_info.get("location", "")
            })

        return {
            "success": True,
            "data": {
                "query": request.query,
                "results": formatted_results,
                "count": len(formatted_results)
            }
        }
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/search/simple")
async def simple_search(q: str, limit: int = 10, book_id: Optional[str] = None):
    """简单关键词搜索（不使用向量）"""
    session = Session()
    try:
        if book_id:
            sql = text("""
                SELECT c.id, c.chunk_content, c.page_num, c.book_id, p.book_name
                FROM textbook_chunks c
                JOIN textbook_pages p ON c.page_id = p.id
                WHERE c.book_id = :book_id AND c.chunk_content ILIKE :query
                LIMIT :limit
            """)
            params = {"book_id": book_id, "query": f"%{q}%", "limit": limit}
        else:
            sql = text("""
                SELECT c.id, c.chunk_content, c.page_num, c.book_id, p.book_name
                FROM textbook_chunks c
                JOIN textbook_pages p ON c.page_id = p.id
                WHERE c.chunk_content ILIKE :query
                LIMIT :limit
            """)
            params = {"query": f"%{q}%", "limit": limit}

        result = session.execute(sql, params)
        rows = result.fetchall()

        results = []
        for row in rows:
            # 获取章节信息
            chapter_info = locate_chapter(row.book_id, row.page_num, row.chunk_content)

            results.append({
                "chunk_id": row.id,
                "content": row.chunk_content,
                "page_num": row.page_num,
                "book_id": row.book_id,
                "book_name": row.book_name,
                "short_name": BOOK_INFO.get(row.book_id, {}).get("short", row.book_id),
                # 章节定位信息
                "chapter": chapter_info.get("chapter", ""),
                "chapter_title": chapter_info.get("chapter_title", ""),
                "section": chapter_info.get("section", ""),
                "section_title": chapter_info.get("section_title", ""),
                "location": chapter_info.get("location", "")
            })

        return {
            "success": True,
            "data": {
                "query": q,
                "results": results,
                "count": len(results)
            }
        }
    finally:
        session.close()
