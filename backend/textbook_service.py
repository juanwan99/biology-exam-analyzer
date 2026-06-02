"""
教材资料服务
处理教材上传、解析、存储和检索
"""
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import TextbookVersion, TextbookChapter, TextbookContent, KnowledgePoint
from logger import get_logger

logger = get_logger()


class TextbookService:
    """教材服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 教材版本管理 ====================

    async def get_versions(self) -> List[Dict]:
        """获取所有教材版本"""
        result = await self.db.execute(
            select(TextbookVersion).order_by(TextbookVersion.id)
        )
        versions = result.scalars().all()
        return [{"id": v.id, "name": v.name, "description": v.description} for v in versions]

    async def create_version(self, name: str, publisher: str = None, year: int = None, description: str = None) -> Dict:
        """创建教材版本"""
        version = TextbookVersion(name=name, description=description)
        self.db.add(version)
        await self.db.flush()
        logger.info(f"[教材服务] 创建版本: {name}")
        return {"id": version.id, "name": version.name}

    # ==================== 章节管理 ====================

    async def get_chapters(self, version_id: int = None, module_name: str = None) -> List[Dict]:
        """获取章节列表"""
        query = select(TextbookChapter).order_by(TextbookChapter.sort_order)

        if version_id:
            query = query.where(TextbookChapter.version_id == version_id)
        if module_name:
            query = query.where(TextbookChapter.module_name == module_name)

        result = await self.db.execute(query)
        chapters = result.scalars().all()

        return [{
            "id": c.id,
            "version_id": c.version_id,
            "grade": c.grade,
            "semester": c.semester,
            "module_name": c.module_name,
            "chapter_num": c.chapter_num,
            "chapter_name": c.chapter_name,
            "section_num": c.section_num,
            "section_name": c.section_name,
            "parent_id": c.parent_id,
            "sort_order": c.sort_order,
        } for c in chapters]

    async def get_chapter_tree(self, version_id: int = 1) -> List[Dict]:
        """获取章节树形结构"""
        result = await self.db.execute(
            select(TextbookChapter)
            .where(TextbookChapter.version_id == version_id)
            .order_by(TextbookChapter.sort_order)
        )
        chapters = result.scalars().all()

        # 按模块分组
        modules = {}
        for c in chapters:
            if c.module_name not in modules:
                modules[c.module_name] = {
                    "module_name": c.module_name,
                    "grade": c.grade,
                    "semester": c.semester,
                    "chapters": []
                }
            modules[c.module_name]["chapters"].append({
                "id": c.id,
                "chapter_num": c.chapter_num,
                "chapter_name": c.chapter_name,
                "section_num": c.section_num,
                "section_name": c.section_name,
            })

        return list(modules.values())

    async def create_chapter(
        self,
        version_id: int,
        grade: str,
        module_name: str,
        chapter_num: int,
        chapter_name: str,
        semester: str = None,
        section_num: int = None,
        section_name: str = None,
        parent_id: int = None,
    ) -> Dict:
        """创建章节"""
        # 计算排序值
        result = await self.db.execute(
            select(func.max(TextbookChapter.sort_order))
            .where(TextbookChapter.version_id == version_id)
        )
        max_order = result.scalar() or 0

        chapter = TextbookChapter(
            version_id=version_id,
            grade=grade,
            semester=semester,
            module_name=module_name,
            chapter_num=chapter_num,
            chapter_name=chapter_name,
            section_num=section_num,
            section_name=section_name,
            parent_id=parent_id,
            sort_order=max_order + 1,
        )
        self.db.add(chapter)
        await self.db.flush()

        logger.info(f"[教材服务] 创建章节: {module_name} - {chapter_name}")
        return {"id": chapter.id, "chapter_name": chapter.chapter_name}

    async def find_or_create_chapter(
        self,
        version_id: int,
        chapter_name: str,
        chapter_num: int = None,
        module_name: str = "未分类",
        grade: str = "高中",
        semester: str = None,
    ) -> Dict:
        """查找或创建章节（用于整本教材上传）"""
        # 先尝试查找现有章节
        query = select(TextbookChapter).where(
            and_(
                TextbookChapter.version_id == version_id,
                TextbookChapter.chapter_name == chapter_name,
            )
        )
        if module_name:
            query = query.where(TextbookChapter.module_name == module_name)

        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"[教材服务] 找到现有章节: {chapter_name}")
            return {"id": existing.id, "chapter_name": existing.chapter_name}

        # 创建新章节
        result = await self.db.execute(
            select(func.max(TextbookChapter.sort_order))
            .where(TextbookChapter.version_id == version_id)
        )
        max_order = result.scalar() or 0

        # 如果没有指定章节号，自动分配
        if chapter_num is None:
            result = await self.db.execute(
                select(func.max(TextbookChapter.chapter_num))
                .where(
                    and_(
                        TextbookChapter.version_id == version_id,
                        TextbookChapter.module_name == module_name,
                    )
                )
            )
            max_chapter_num = result.scalar() or 0
            chapter_num = max_chapter_num + 1

        chapter = TextbookChapter(
            version_id=version_id,
            grade=grade,
            semester=semester,
            module_name=module_name,
            chapter_num=chapter_num,
            chapter_name=chapter_name,
            sort_order=max_order + 1,
        )
        self.db.add(chapter)
        await self.db.flush()

        logger.info(f"[教材服务] 创建新章节: {module_name} - {chapter_name}")
        return {"id": chapter.id, "chapter_name": chapter.chapter_name}

    async def find_chapter_by_num(
        self,
        version_id: int,
        chapter_num: int,
        module_name: str = None,
    ) -> Optional[Dict]:
        """根据章节号查找章节"""
        query = select(TextbookChapter).where(
            and_(
                TextbookChapter.version_id == version_id,
                TextbookChapter.chapter_num == chapter_num,
            )
        )
        if module_name:
            query = query.where(TextbookChapter.module_name == module_name)

        result = await self.db.execute(query)
        chapter = result.scalar_one_or_none()

        if chapter:
            return {
                "id": chapter.id,
                "chapter_num": chapter.chapter_num,
                "chapter_name": chapter.chapter_name,
                "module_name": chapter.module_name,
            }
        return None

    # ==================== 内容管理 ====================

    async def add_content(
        self,
        chapter_id: int,
        content: str,
        content_type: str = "text",
        title: str = None,
        page_num: int = None,
        embedding: List[float] = None,
    ) -> Dict:
        """添加教材内容"""
        # 计算排序值
        result = await self.db.execute(
            select(func.max(TextbookContent.sort_order))
            .where(TextbookContent.chapter_id == chapter_id)
        )
        max_order = result.scalar() or 0

        content_obj = TextbookContent(
            chapter_id=chapter_id,
            content_type=content_type,
            title=title,
            content=content,
            content_embedding=embedding,
            page_num=page_num,
            sort_order=max_order + 1,
        )
        self.db.add(content_obj)
        await self.db.flush()

        logger.info(f"[教材服务] 添加内容到章节{chapter_id}: {title or content[:30]}...")
        return {"id": content_obj.id}

    async def get_chapter_contents(self, chapter_id: int) -> List[Dict]:
        """获取章节的所有内容"""
        result = await self.db.execute(
            select(TextbookContent)
            .where(TextbookContent.chapter_id == chapter_id)
            .order_by(TextbookContent.sort_order)
        )
        contents = result.scalars().all()

        return [{
            "id": c.id,
            "content_type": c.content_type,
            "title": c.title,
            "content": c.content,
            "page_num": c.page_num,
        } for c in contents]

    async def get_all_contents(
        self,
        page: int = 1,
        page_size: int = 50,
        book_id: str = None,
        keyword: str = None,
    ) -> Dict:
        """获取所有教材切片内容（带分页和筛选）- 使用textbook_chunks表"""
        from sqlalchemy import func, and_, text

        # 使用原生SQL查询textbook_chunks表
        count_sql = "SELECT COUNT(*) FROM textbook_chunks WHERE 1=1"
        query_sql = """
            SELECT
                tc.id, tc.page_id, tc.book_id, tc.chunk_index, tc.chunk_content,
                tc.page_num, tc.chapter_info, tc.created_at,
                tp.book_name
            FROM textbook_chunks tc
            LEFT JOIN textbook_pages tp ON tc.page_id = tp.id
            WHERE 1=1
        """

        params = {}
        if book_id:
            count_sql += " AND book_id = :book_id"
            query_sql += " AND tc.book_id = :book_id"
            params["book_id"] = book_id
        if keyword:
            count_sql += " AND chunk_content ILIKE :keyword"
            query_sql += " AND tc.chunk_content ILIKE :keyword"
            params["keyword"] = f"%{keyword}%"

        # 获取总数
        total_result = await self.db.execute(text(count_sql), params)
        total = total_result.scalar()

        # 分页查询
        offset = (page - 1) * page_size
        query_sql += " ORDER BY tc.id DESC LIMIT :limit OFFSET :offset"
        params["limit"] = page_size
        params["offset"] = offset

        result = await self.db.execute(text(query_sql), params)
        rows = result.fetchall()

        items = [{
            "id": row[0],
            "page_id": row[1],
            "book_id": row[2],
            "chunk_index": row[3],
            "content": row[4],
            "page_num": row[5],
            "chapter_info": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "book_name": row[8],
        } for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
        }

    async def get_books_list(self) -> List[Dict]:
        """获取所有教材列表"""
        from sqlalchemy import text
        sql = """
            SELECT tc.book_id, tp.book_name, COUNT(*) as chunk_count
            FROM textbook_chunks tc
            JOIN textbook_pages tp ON tc.page_id = tp.id
            GROUP BY tc.book_id, tp.book_name
            ORDER BY tc.book_id
        """
        result = await self.db.execute(text(sql))
        rows = result.fetchall()
        return [{"book_id": row[0], "book_name": row[1], "chunk_count": row[2]} for row in rows]

    async def update_chunk(self, chunk_id: int, content: str) -> Dict:
        """更新切片内容"""
        from sqlalchemy import text
        sql = "UPDATE textbook_chunks SET chunk_content = :content WHERE id = :id"
        await self.db.execute(text(sql), {"id": chunk_id, "content": content})
        await self.db.commit()
        return {"success": True}

    async def delete_chunk(self, chunk_id: int) -> Dict:
        """删除切片"""
        from sqlalchemy import text
        sql = "DELETE FROM textbook_chunks WHERE id = :id"
        await self.db.execute(text(sql), {"id": chunk_id})
        await self.db.commit()
        return {"success": True}

    async def search_content(
        self,
        query: str,
        query_embedding: List[float] = None,
        limit: int = 10,
        version_id: int = None,
        module_name: str = None,
    ) -> List[Dict]:
        """搜索教材内容（支持向量相似度搜索）"""

        if query_embedding:
            # 向量相似度搜索
            embedding_str = f"[{','.join(map(str, query_embedding))}]"

            sql = text(f"""
                SELECT
                    tc.id,
                    tc.title,
                    tc.content,
                    tc.content_type,
                    ch.chapter_name,
                    ch.module_name,
                    1 - (tc.content_embedding <=> :embedding::vector) as similarity
                FROM textbook_contents tc
                JOIN textbook_chapters ch ON tc.chapter_id = ch.id
                WHERE tc.content_embedding IS NOT NULL
                {"AND ch.version_id = :version_id" if version_id else ""}
                {"AND ch.module_name = :module_name" if module_name else ""}
                ORDER BY tc.content_embedding <=> :embedding::vector
                LIMIT :limit
            """)

            params = {"embedding": embedding_str, "limit": limit}
            if version_id:
                params["version_id"] = version_id
            if module_name:
                params["module_name"] = module_name

            result = await self.db.execute(sql, params)
        else:
            # 关键词搜索
            sql = text("""
                SELECT
                    tc.id,
                    tc.title,
                    tc.content,
                    tc.content_type,
                    ch.chapter_name,
                    ch.module_name,
                    1.0 as similarity
                FROM textbook_contents tc
                JOIN textbook_chapters ch ON tc.chapter_id = ch.id
                WHERE tc.content ILIKE :query
                LIMIT :limit
            """)
            result = await self.db.execute(sql, {"query": f"%{query}%", "limit": limit})

        rows = result.fetchall()
        return [{
            "id": row.id,
            "title": row.title,
            "content": row.content[:500] + "..." if len(row.content) > 500 else row.content,
            "content_type": row.content_type,
            "chapter_name": row.chapter_name,
            "module_name": row.module_name,
            "similarity": float(row.similarity) if row.similarity else None,
        } for row in rows]

    # ==================== 知识点管理 ====================

    async def add_knowledge_point(
        self,
        name: str,
        chapter_id: int = None,
        description: str = None,
        difficulty_level: int = 3,
        importance_level: int = 3,
        keywords: List[str] = None,
        embedding: List[float] = None,
    ) -> Dict:
        """添加知识点"""
        kp = KnowledgePoint(
            name=name,
            chapter_id=chapter_id,
            description=description,
            description_embedding=embedding,
            difficulty_level=difficulty_level,
            importance_level=importance_level,
            keywords=keywords,
        )
        self.db.add(kp)
        await self.db.flush()

        logger.info(f"[教材服务] 添加知识点: {name}")
        return {"id": kp.id, "name": kp.name}

    async def get_knowledge_points(
        self,
        chapter_id: int = None,
        keyword: str = None,
        limit: int = 100,
    ) -> List[Dict]:
        """获取知识点列表"""
        query = select(KnowledgePoint).limit(limit)

        if chapter_id:
            query = query.where(KnowledgePoint.chapter_id == chapter_id)
        if keyword:
            query = query.where(
                or_(
                    KnowledgePoint.name.ilike(f"%{keyword}%"),
                    KnowledgePoint.description.ilike(f"%{keyword}%"),
                )
            )

        result = await self.db.execute(query)
        kps = result.scalars().all()

        return [{
            "id": kp.id,
            "name": kp.name,
            "chapter_id": kp.chapter_id,
            "description": kp.description,
            "difficulty_level": kp.difficulty_level,
            "importance_level": kp.importance_level,
            "keywords": kp.keywords,
        } for kp in kps]

    async def search_knowledge_points(
        self,
        query_embedding: List[float],
        limit: int = 5,
    ) -> List[Dict]:
        """向量搜索知识点"""
        embedding_str = f"[{','.join(map(str, query_embedding))}]"

        sql = text("""
            SELECT
                kp.id,
                kp.name,
                kp.description,
                ch.chapter_name,
                ch.module_name,
                1 - (kp.description_embedding <=> :embedding::vector) as similarity
            FROM knowledge_points kp
            LEFT JOIN textbook_chapters ch ON kp.chapter_id = ch.id
            WHERE kp.description_embedding IS NOT NULL
            ORDER BY kp.description_embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = await self.db.execute(sql, {"embedding": embedding_str, "limit": limit})
        rows = result.fetchall()

        return [{
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "chapter_name": row.chapter_name,
            "module_name": row.module_name,
            "similarity": float(row.similarity),
        } for row in rows]

    # ==================== 统计信息 ====================

    async def get_stats(self) -> Dict:
        """获取教材资料统计信息"""
        # 版本数量
        result = await self.db.execute(select(func.count(TextbookVersion.id)))
        version_count = result.scalar() or 0

        # 页面数量 (使用 textbook_pages 表)
        result = await self.db.execute(text("SELECT COUNT(*) FROM textbook_pages"))
        page_count = result.scalar() or 0

        # 切片数量 (使用 textbook_chunks 表)
        result = await self.db.execute(text("SELECT COUNT(*) FROM textbook_chunks"))
        chunk_count = result.scalar() or 0

        # 知识点数量
        result = await self.db.execute(select(func.count(KnowledgePoint.id)))
        kp_count = result.scalar() or 0

        # 有向量的切片数量
        result = await self.db.execute(
            text("SELECT COUNT(*) FROM textbook_chunks WHERE embedding IS NOT NULL")
        )
        embedded_chunk_count = result.scalar() or 0

        # 各教材的统计
        result = await self.db.execute(
            text("SELECT book_id, COUNT(*) as count FROM textbook_chunks GROUP BY book_id ORDER BY book_id")
        )
        book_stats = {row[0]: row[1] for row in result.fetchall()}

        return {
            "versions": version_count,
            "pages": page_count,
            "chunks": chunk_count,
            "knowledge_points": kp_count,
            "embedded_chunks": embedded_chunk_count,
            "book_stats": book_stats,
        }

    # ==================== Admin CRUD Operations ====================

    async def get_chapter_by_id(self, chapter_id: int) -> Optional[Dict]:
        """根据ID获取章节"""
        result = await self.db.execute(
            select(TextbookChapter).where(TextbookChapter.id == chapter_id)
        )
        chapter = result.scalar_one_or_none()

        if not chapter:
            return None

        return {
            "id": chapter.id,
            "chapter_name": chapter.chapter_name,
            "module_name": chapter.module_name,
            "chapter_num": chapter.chapter_num,
            "grade": chapter.grade,
        }

    async def get_content_by_id(self, content_id: int) -> Optional[Dict]:
        """根据ID获取内容"""
        result = await self.db.execute(
            select(TextbookContent).where(TextbookContent.id == content_id)
        )
        content = result.scalar_one_or_none()

        if not content:
            return None

        return {
            "id": content.id,
            "content": content.content,
            "content_type": content.content_type,
            "title": content.title,
            "page_num": content.page_num,
        }

    async def get_knowledge_point_by_id(self, kp_id: int) -> Optional[Dict]:
        """根据ID获取知识点"""
        result = await self.db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )
        kp = result.scalar_one_or_none()

        if not kp:
            return None

        return {
            "id": kp.id,
            "name": kp.name,
            "description": kp.description,
            "chapter_id": kp.chapter_id,
        }

    async def get_version_by_id(self, version_id: int) -> Optional[Dict]:
        """根据ID获取版本"""
        result = await self.db.execute(
            select(TextbookVersion).where(TextbookVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            return None

        return {
            "id": version.id,
            "name": version.name,
            "description": version.description,
        }

    async def update_chapter(self, chapter_id: int, update_data: Dict) -> Optional[Dict]:
        """更新章节"""
        result = await self.db.execute(
            select(TextbookChapter).where(TextbookChapter.id == chapter_id)
        )
        chapter = result.scalar_one_or_none()

        if not chapter:
            return None

        for key, value in update_data.items():
            if hasattr(chapter, key) and value is not None:
                setattr(chapter, key, value)

        await self.db.commit()
        logger.info(f"[教材服务] 更新章节: id={chapter_id}")
        return {"id": chapter.id, "chapter_name": chapter.chapter_name}

    async def delete_chapter(self, chapter_id: int) -> bool:
        """删除章节（同时删除关联的内容）"""
        result = await self.db.execute(
            select(TextbookChapter).where(TextbookChapter.id == chapter_id)
        )
        chapter = result.scalar_one_or_none()

        if not chapter:
            return False

        # 删除关联的内容
        await self.db.execute(
            select(TextbookContent).where(TextbookContent.chapter_id == chapter_id)
        )

        from sqlalchemy import delete
        await self.db.execute(
            delete(TextbookContent).where(TextbookContent.chapter_id == chapter_id)
        )

        # 删除章节
        await self.db.delete(chapter)
        await self.db.commit()
        logger.info(f"[教材服务] 删除章节: id={chapter_id}")
        return True

    async def update_content(self, content_id: int, update_data: Dict) -> Optional[Dict]:
        """更新内容"""
        result = await self.db.execute(
            select(TextbookContent).where(TextbookContent.id == content_id)
        )
        content = result.scalar_one_or_none()

        if not content:
            return None

        for key, value in update_data.items():
            if hasattr(content, key) and value is not None:
                setattr(content, key, value)

        await self.db.commit()
        logger.info(f"[教材服务] 更新内容: id={content_id}")
        return {"id": content.id, "title": content.title}

    async def delete_content(self, content_id: int) -> bool:
        """删除内容"""
        result = await self.db.execute(
            select(TextbookContent).where(TextbookContent.id == content_id)
        )
        content = result.scalar_one_or_none()

        if not content:
            return False

        await self.db.delete(content)
        await self.db.commit()
        logger.info(f"[教材服务] 删除内容: id={content_id}")
        return True

    async def update_knowledge_point(self, kp_id: int, update_data: Dict) -> Optional[Dict]:
        """更新知识点"""
        result = await self.db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )
        kp = result.scalar_one_or_none()

        if not kp:
            return None

        for key, value in update_data.items():
            if hasattr(kp, key) and value is not None:
                setattr(kp, key, value)

        await self.db.commit()
        logger.info(f"[教材服务] 更新知识点: id={kp_id}")
        return {"id": kp.id, "name": kp.name}

    async def delete_knowledge_point(self, kp_id: int) -> bool:
        """删除知识点"""
        result = await self.db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )
        kp = result.scalar_one_or_none()

        if not kp:
            return False

        await self.db.delete(kp)
        await self.db.commit()
        logger.info(f"[教材服务] 删除知识点: id={kp_id}")
        return True

    async def update_version(self, version_id: int, update_data: Dict) -> Optional[Dict]:
        """更新教材版本"""
        result = await self.db.execute(
            select(TextbookVersion).where(TextbookVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            return None

        for key, value in update_data.items():
            if hasattr(version, key) and value is not None:
                setattr(version, key, value)

        await self.db.commit()
        logger.info(f"[教材服务] 更新版本: id={version_id}")
        return {"id": version.id, "name": version.name}

    async def delete_version(self, version_id: int) -> bool:
        """删除教材版本（需检查是否有关联章节）"""
        # 检查是否有关联章节
        result = await self.db.execute(
            select(func.count(TextbookChapter.id))
            .where(TextbookChapter.version_id == version_id)
        )
        chapter_count = result.scalar()

        if chapter_count > 0:
            raise Exception(f"该版本下有 {chapter_count} 个章节，无法删除")

        result = await self.db.execute(
            select(TextbookVersion).where(TextbookVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            return False

        await self.db.delete(version)
        await self.db.commit()
        logger.info(f"[教材服务] 删除版本: id={version_id}")
        return True
