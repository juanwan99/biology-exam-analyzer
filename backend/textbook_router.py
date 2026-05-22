"""
教材资料管理API路由
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import os
import re
import docx
import pdfplumber
from io import BytesIO

from database import get_db, init_db
from sqlalchemy.ext.asyncio import AsyncSession
from textbook_service import TextbookService
from pdf_parser import PDFParser, parse_pdf as parse_pdf_advanced
from logger import get_logger
from parsers.document_parsers import chinese_to_num, parse_docx, parse_pdf, parse_docx_with_chapters, parse_pdf_with_chapters
from auth_router import require_auth, log_operation

logger = get_logger()

router = APIRouter(prefix="/api/textbook", tags=["教材管理"])


# ============ 向量搜索相关 Models ============

class VectorSearchRequest(BaseModel):
    """向量语义搜索请求"""
    query: str
    top_k: int = 5
    book_name: Optional[str] = None


class VectorProcessRequest(BaseModel):
    """向量处理请求"""
    pdf_path: str
    book_name: str
    version_id: Optional[int] = None


# ============ Pydantic Models ============

class ChapterCreate(BaseModel):
    """创建章节请求"""
    version_id: int = 1
    grade: str
    module_name: str
    chapter_num: int
    chapter_name: str
    semester: Optional[str] = None
    section_num: Optional[int] = None
    section_name: Optional[str] = None


class ContentCreate(BaseModel):
    """添加内容请求"""
    chapter_id: int
    content: str
    content_type: str = "text"
    title: Optional[str] = None
    page_num: Optional[int] = None


class KnowledgePointCreate(BaseModel):
    """添加知识点请求"""
    name: str
    chapter_id: Optional[int] = None
    description: Optional[str] = None
    difficulty_level: int = 3
    importance_level: int = 3
    keywords: Optional[List[str]] = None


class ContentSearch(BaseModel):
    """内容搜索请求"""
    query: str
    limit: int = 10
    version_id: Optional[int] = None
    module_name: Optional[str] = None


# ============ API Endpoints ============

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取教材资料统计信息"""
    service = TextbookService(db)
    stats = await service.get_stats()
    return {"success": True, "data": stats}


@router.get("/versions")
async def get_versions(db: AsyncSession = Depends(get_db)):
    """获取所有教材版本"""
    service = TextbookService(db)
    versions = await service.get_versions()
    return {"success": True, "data": versions}


@router.get("/chapters")
async def get_chapters(
    version_id: int = None,
    module_name: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取章节列表"""
    service = TextbookService(db)
    chapters = await service.get_chapters(version_id, module_name)
    return {"success": True, "data": chapters}


@router.get("/chapters/tree")
async def get_chapter_tree(
    version_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """获取章节树形结构"""
    service = TextbookService(db)
    tree = await service.get_chapter_tree(version_id)
    return {"success": True, "data": tree}


@router.post("/chapters")
async def create_chapter(
    data: ChapterCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建章节"""
    service = TextbookService(db)
    result = await service.create_chapter(
        version_id=data.version_id,
        grade=data.grade,
        module_name=data.module_name,
        chapter_num=data.chapter_num,
        chapter_name=data.chapter_name,
        semester=data.semester,
        section_num=data.section_num,
        section_name=data.section_name,
    )
    return {"success": True, "data": result}


@router.get("/chapters/{chapter_id}/contents")
async def get_chapter_contents(
    chapter_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取章节内容"""
    service = TextbookService(db)
    contents = await service.get_chapter_contents(chapter_id)
    return {"success": True, "data": contents}


@router.get("/contents/list")
async def get_all_contents(
    page: int = 1,
    page_size: int = 50,
    book_id: str = None,
    keyword: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取所有教材切片内容（带分页和筛选）"""
    service = TextbookService(db)
    result = await service.get_all_contents(
        page=page,
        page_size=page_size,
        book_id=book_id,
        keyword=keyword,
    )
    return {"success": True, **result}


@router.get("/books")
async def get_books_list(db: AsyncSession = Depends(get_db)):
    """获取所有教材列表"""
    service = TextbookService(db)
    books = await service.get_books_list()
    return {"success": True, "data": books}


@router.put("/chunks/{chunk_id}")
async def update_chunk(
    chunk_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    """更新切片内容"""
    service = TextbookService(db)
    result = await service.update_chunk(chunk_id, data.get("content", ""))
    return {"success": True, **result}


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(
    chunk_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除切片"""
    service = TextbookService(db)
    result = await service.delete_chunk(chunk_id)
    return {"success": True, **result}


@router.post("/contents")
async def add_content(
    data: ContentCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加教材内容"""
    service = TextbookService(db)
    result = await service.add_content(
        chapter_id=data.chapter_id,
        content=data.content,
        content_type=data.content_type,
        title=data.title,
        page_num=data.page_num,
    )
    return {"success": True, "data": result}


@router.post("/contents/search")
async def search_content(
    data: ContentSearch,
    db: AsyncSession = Depends(get_db)
):
    """搜索教材内容"""
    service = TextbookService(db)
    results = await service.search_content(
        query=data.query,
        limit=data.limit,
        version_id=data.version_id,
        module_name=data.module_name,
    )
    return {"success": True, "data": results}


@router.get("/knowledge-points")
async def get_knowledge_points(
    chapter_id: int = None,
    keyword: str = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """获取知识点列表"""
    service = TextbookService(db)
    kps = await service.get_knowledge_points(chapter_id, keyword, limit)
    return {"success": True, "data": kps}


@router.post("/knowledge-points")
async def add_knowledge_point(
    data: KnowledgePointCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加知识点"""
    service = TextbookService(db)
    result = await service.add_knowledge_point(
        name=data.name,
        chapter_id=data.chapter_id,
        description=data.description,
        difficulty_level=data.difficulty_level,
        importance_level=data.importance_level,
        keywords=data.keywords,
    )
    return {"success": True, "data": result}


# ============ 文件上传解析 ============

@router.post("/upload/document")
async def upload_document(
    file: UploadFile = File(...),
    chapter_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    上传教材文档（Word/PDF），自动解析并存储内容到指定章节

    Args:
        file: 上传的文件（.docx 或 .pdf）
        chapter_id: 关联的章节ID
    """
    logger.info(f"[教材上传] 收到文件: {file.filename}, 章节ID: {chapter_id}")

    # 检查文件类型
    filename = file.filename.lower()
    if not (filename.endswith('.docx') or filename.endswith('.pdf')):
        raise HTTPException(400, "只支持 .docx 和 .pdf 格式的文件")

    try:
        content = await file.read()
        service = TextbookService(db)

        if filename.endswith('.docx'):
            # 解析Word文档
            paragraphs = parse_docx(content)
        else:
            # 解析PDF文档
            paragraphs = parse_pdf(content)

        logger.info(f"[教材上传] 解析出 {len(paragraphs)} 个段落")

        # 存储内容
        added_count = 0
        for i, para in enumerate(paragraphs):
            if para.get("content", "").strip():
                await service.add_content(
                    chapter_id=chapter_id,
                    content=para["content"],
                    content_type=para.get("type", "text"),
                    title=para.get("title"),
                    page_num=para.get("page_num"),
                )
                added_count += 1

        logger.info(f"[教材上传] 成功添加 {added_count} 条内容")
        return {
            "success": True,
            "message": f"成功解析并存储 {added_count} 条内容",
            "data": {
                "filename": file.filename,
                "chapter_id": chapter_id,
                "paragraphs_count": len(paragraphs),
                "added_count": added_count,
            }
        }

    except Exception as e:
        logger.error(f"[教材上传] 处理失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.post("/upload/textbook")
async def upload_textbook(
    file: UploadFile = File(...),
    version_id: int = Form(1),
    db: AsyncSession = Depends(get_db)
):
    """
    上传整本教材（Word/PDF），自动识别章节结构并存储

    使用改进的PDF解析器：
    - 从PDF目录/书签提取章节结构
    - 按页码范围分配内容
    - 提取并保存图片

    Args:
        file: 上传的文件（.docx 或 .pdf）
        version_id: 教材版本ID（默认1=人教版）
    """
    logger.info(f"[整本教材上传] 收到文件: {file.filename}, 版本ID: {version_id}")

    # 检查文件类型
    filename = file.filename.lower()
    if not (filename.endswith('.docx') or filename.endswith('.pdf')):
        raise HTTPException(400, "只支持 .docx 和 .pdf 格式的文件")

    try:
        content = await file.read()
        service = TextbookService(db)

        if filename.endswith('.docx'):
            # 解析Word文档并识别章节
            chapters_data = parse_docx_with_chapters(content)
        else:
            # 使用改进的PDF解析器
            parse_result = parse_pdf_advanced(content, file.filename)
            chapters_data = parse_result["chapters"]
            logger.info(f"[整本教材上传] PDF目录项: {len(parse_result.get('toc', []))}")

        logger.info(f"[整本教材上传] 解析出 {len(chapters_data)} 个章节")

        # 存储章节和内容
        total_contents = 0
        total_images = 0
        chapters_created = 0

        for ch_data in chapters_data:
            # 查找或创建章节
            chapter = await service.find_or_create_chapter(
                version_id=version_id,
                chapter_name=ch_data.get("chapter_name", ch_data.get("title", "未命名章节")),
                chapter_num=ch_data.get("chapter_num"),
                module_name=ch_data.get("module_name", "未分类"),
                grade=ch_data.get("grade", "高中"),
            )
            chapters_created += 1

            # 添加该章节的内容
            for para in ch_data.get("contents", []):
                if para.get("content", "").strip():
                    await service.add_content(
                        chapter_id=chapter["id"],
                        content=para["content"],
                        content_type=para.get("type", "text"),
                        title=para.get("title"),
                        page_num=para.get("page_num"),
                    )
                    total_contents += 1

            # 记录图片信息
            images = ch_data.get("images", [])
            total_images += len(images)
            for img in images:
                # 添加图片引用到内容中
                await service.add_content(
                    chapter_id=chapter["id"],
                    content=f"[图片] {img.get('filename', '')}",
                    content_type="image",
                    page_num=img.get("page_num"),
                )
                total_contents += 1

        logger.info(f"[整本教材上传] 完成: {chapters_created}个章节, {total_contents}条内容, {total_images}张图片")
        return {
            "success": True,
            "message": f"成功解析整本教材：{chapters_created}个章节，{total_contents}条内容，{total_images}张图片",
            "data": {
                "filename": file.filename,
                "version_id": version_id,
                "chapters_count": chapters_created,
                "contents_count": total_contents,
                "images_count": total_images,
            }
        }

    except Exception as e:
        logger.error(f"[整本教材上传] 处理失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.post("/upload/batch")
async def upload_batch(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    批量上传教材内容（支持JSON格式）

    JSON格式示例:
    {
        "contents": [
            {
                "chapter_id": 1,
                "content": "内容...",
                "content_type": "text",
                "title": "标题"
            },
            ...
        ]
    }
    """
    import json

    if not file.filename.endswith('.json'):
        raise HTTPException(400, "只支持 .json 格式的文件")

    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        service = TextbookService(db)
        added_count = 0

        for item in data.get("contents", []):
            await service.add_content(
                chapter_id=item["chapter_id"],
                content=item["content"],
                content_type=item.get("content_type", "text"),
                title=item.get("title"),
                page_num=item.get("page_num"),
            )
            added_count += 1

        return {
            "success": True,
            "message": f"成功添加 {added_count} 条内容",
            "data": {"added_count": added_count}
        }

    except json.JSONDecodeError:
        raise HTTPException(400, "JSON格式错误")
    except Exception as e:
        logger.error(f"[批量上传] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.post("/upload/smart")
async def upload_smart(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    智能上传教材（使用AI分析）

    - 逐页分析PDF，使用AI提取知识点和章节信息
    - 支持指定页码范围进行测试
    - 返回分析结果并保存到数据库

    Args:
        file: PDF文件
        start_page: 起始页码（1-based），默认1
        end_page: 结束页码（1-based），默认到最后一页
    """
    from textbook_processor import TextbookProcessor
    from config import UPLOAD_DIR

    logger.info(f"[智能教材处理] 收到文件: {file.filename}, 页码范围: {start_page}-{end_page}")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "智能处理目前只支持PDF格式")

    try:
        # 保存上传的文件
        content = await file.read()
        pdf_path = UPLOAD_DIR / file.filename
        with open(pdf_path, "wb") as f:
            f.write(content)
        logger.info(f"[智能教材处理] 文件已保存: {pdf_path}")

        # 使用AI处理
        processor = TextbookProcessor()
        try:
            result = await processor.process_pdf(
                str(pdf_path),
                start_page=start_page,
                end_page=end_page,
                save_results=True
            )
        finally:
            await processor.close()

        return {
            "success": True,
            "message": f"智能分析完成：处理了 {result['processed_range']} 页，提取了 {len(result['knowledge_points'])} 个知识点",
            "data": {
                "filename": file.filename,
                "total_pages": result["total_pages"],
                "processed_range": result["processed_range"],
                "knowledge_points_count": len(result["knowledge_points"]),
                "chapters_detected": result["chapters_detected"],
                "knowledge_points": result["knowledge_points"][:20],  # 只返回前20个预览
            }
        }

    except Exception as e:
        logger.error(f"[智能教材处理] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/smart/results/{filename}")
async def get_smart_results(filename: str):
    """获取智能处理的结果文件"""
    import json
    from config import UPLOAD_DIR

    result_path = UPLOAD_DIR / f"{filename}_analysis.json"
    if not result_path.exists():
        raise HTTPException(404, "分析结果不存在")

    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {"success": True, "data": data}


@router.post("/smart/save-to-db")
async def save_smart_results_to_db(
    filename: str = Form(...),
    version_id: int = Form(1),
    db: AsyncSession = Depends(get_db)
):
    """
    将AI智能分析结果保存到数据库

    - 根据章节号匹配数据库中的章节
    - 将知识点和内容保存到对应章节
    - 处理raw_response中的部分JSON数据
    """
    import json
    import re
    from config import UPLOAD_DIR

    def try_parse_raw_response(raw: str) -> dict:
        """尝试从raw_response中解析部分JSON"""
        if not raw:
            return {}
        try:
            # 尝试直接解析
            return json.loads(raw)
        except:
            pass
        # 尝试提取chapter_info
        result = {}
        try:
            ch_match = re.search(r'"chapter_info"\s*:\s*\{[^}]+\}', raw)
            if ch_match:
                ch_str = "{" + ch_match.group(0) + "}"
                ch_data = json.loads(ch_str)
                result["chapter_info"] = ch_data.get("chapter_info", {})
        except:
            pass
        # 尝试提取knowledge_points
        try:
            kp_match = re.search(r'"knowledge_points"\s*:\s*\[([\s\S]*?)\]', raw)
            if kp_match:
                kp_str = "[" + kp_match.group(1) + "]"
                # 修复不完整的JSON
                kp_str = re.sub(r',\s*$', '', kp_str)
                if not kp_str.endswith("]"):
                    kp_str += "]"
                try:
                    result["knowledge_points"] = json.loads(kp_str)
                except:
                    pass
        except:
            pass
        return result

    # 构建文件路径 - 处理带或不带_analysis后缀的情况
    if filename.endswith("_analysis.json"):
        result_path = UPLOAD_DIR / filename
    elif filename.endswith(".pdf"):
        result_path = UPLOAD_DIR / f"{filename[:-4]}_analysis.json"
    else:
        result_path = UPLOAD_DIR / f"{filename}_analysis.json"

    if not result_path.exists():
        raise HTTPException(404, f"分析结果不存在: {result_path}")

    logger.info(f"[保存到数据库] 读取文件: {result_path}")

    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    service = TextbookService(db)

    # 统计
    saved_kps = 0
    saved_contents = 0
    saved_images = 0
    matched_chapters = set()

    # 遍历每一页
    for page_data in data.get("pages", []):
        page_num = page_data.get("page")

        # 处理raw_response中的数据
        if "raw_response" in page_data and page_data.get("raw_response"):
            parsed = try_parse_raw_response(page_data["raw_response"])
            if parsed.get("chapter_info"):
                page_data["chapter_info"] = parsed["chapter_info"]
            if parsed.get("knowledge_points"):
                page_data["knowledge_points"] = parsed.get("knowledge_points", [])

        ch_info = page_data.get("chapter_info", {})

        if not ch_info:
            continue

        # 尝试匹配章节
        chapter_num = ch_info.get("chapter_num")
        section_num = ch_info.get("section_num")
        module = ch_info.get("module", "")

        # 确定模块名称
        module_name = None
        if "必修1" in str(module) or "分子与细胞" in str(ch_info.get("chapter_name", "")):
            module_name = "必修1：分子与细胞"
        elif "必修2" in str(module):
            module_name = "必修2：遗传与进化"

        # 根据章节号查找数据库中的章节
        chapter = None
        if chapter_num:
            try:
                chapter_num_int = int(chapter_num) if str(chapter_num).isdigit() else None
                if chapter_num_int:
                    chapter = await service.find_chapter_by_num(
                        version_id=version_id,
                        chapter_num=chapter_num_int,
                        module_name=module_name
                    )
            except:
                pass

        if chapter:
            matched_chapters.add(chapter["id"])

            # 构建标签信息（用于向量检索）
            tags = []
            if ch_info.get("chapter_name"):
                tags.append(ch_info["chapter_name"])
            if ch_info.get("section_name"):
                tags.append(ch_info["section_name"])
            concepts = page_data.get("concepts", [])
            tags.extend(concepts[:10])  # 最多取10个概念

            # 从知识点提取关键词
            for kp in page_data.get("knowledge_points", []):
                kw = kp.get("keywords", [])
                tags.extend(kw[:5])

            # 1. 保存原文内容（带标签）
            text_content = page_data.get("text", "")
            if text_content and text_content.strip():
                try:
                    # 标签作为title字段存储，便于检索
                    tag_str = " | ".join(list(set(tags))[:15]) if tags else None
                    await service.add_content(
                        chapter_id=chapter["id"],
                        content=text_content,
                        content_type="text",
                        title=tag_str,  # 标签存在title中
                        page_num=page_num,
                    )
                    saved_contents += 1
                    logger.info(f"[保存原文] P{page_num}: {len(text_content)}字, 标签: {tag_str[:50] if tag_str else 'N/A'}...")
                except Exception as e:
                    logger.warning(f"[保存原文失败] P{page_num}: {e}")

            # 2. 保存页面截图引用
            page_image = page_data.get("page_image")
            if page_image:
                try:
                    await service.add_content(
                        chapter_id=chapter["id"],
                        content=f"/uploads/images/{page_image}",
                        content_type="page_image",
                        title=f"第{page_num}页截图",
                        page_num=page_num,
                    )
                    saved_images += 1
                except Exception as e:
                    logger.warning(f"[保存页面截图失败] P{page_num}: {e}")

            # 3. 保存独立图片引用
            for img_info in page_data.get("images", []):
                try:
                    await service.add_content(
                        chapter_id=chapter["id"],
                        content=f"/uploads/images/{img_info['filename']}",
                        content_type="image",
                        title=f"第{page_num}页图片-{img_info['filename']}",
                        page_num=page_num,
                    )
                    saved_images += 1
                except Exception as e:
                    logger.warning(f"[保存图片失败] {img_info.get('filename')}: {e}")

            # 4. 保存知识点（如果需要的话）
            for kp in page_data.get("knowledge_points", []):
                try:
                    importance = kp.get("importance", "一般")
                    importance_level = 5 if importance == "核心" else (3 if importance == "重要" else 1)

                    await service.add_knowledge_point(
                        name=kp.get("name", "未命名"),
                        chapter_id=chapter["id"],
                        description=kp.get("description"),
                        importance_level=importance_level,
                        keywords=kp.get("keywords"),
                    )
                    saved_kps += 1
                except Exception as e:
                    logger.warning(f"[保存知识点失败] {kp.get('name')}: {e}")

            # 保存图表描述
            diagram_desc = page_data.get("diagram_description")
            if diagram_desc:
                try:
                    await service.add_content(
                        chapter_id=chapter["id"],
                        content=f"图表: {diagram_desc}",
                        content_type="diagram",
                        page_num=page_num,
                    )
                    saved_contents += 1
                except Exception as e:
                    logger.warning(f"[保存图表描述失败] P{page_num}: {e}")

    logger.info(f"[保存到数据库] 完成: {saved_contents}条原文, {saved_images}张图片, {saved_kps}个知识点, 匹配{len(matched_chapters)}个章节")

    return {
        "success": True,
        "message": f"成功保存: {saved_contents}条原文, {saved_images}张图片, {saved_kps}个知识点",
        "data": {
            "contents_saved": saved_contents,
            "images_saved": saved_images,
            "knowledge_points_saved": saved_kps,
            "chapters_matched": len(matched_chapters),
        }
    }


# ============ 辅助函数 ============

# 章节识别正则表达式模式
CHAPTER_PATTERNS = [
    # 第X章 章节名
    r'^第\s*([一二三四五六七八九十\d]+)\s*章\s*[：:\s]*(.+)$',
    # 第X节 节名
    r'^第\s*([一二三四五六七八九十\d]+)\s*节\s*[：:\s]*(.+)$',
    # Chapter X: Name
    r'^Chapter\s*(\d+)\s*[：:\s]*(.+)$',
    # 1.1 节名 / 1.2 节名
    r'^(\d+\.\d+)\s+(.+)$',
    # 一、二、三 开头的大标题
    r'^([一二三四五六七八九十]+)[、.．]\s*(.+)$',
]

# 模块识别模式（必修1、选修1等）
MODULE_PATTERNS = [
    r'(必修\s*[一二三1-3])[：:\s]*(.+)',
    r'(选择性必修\s*[一二三1-3])[：:\s]*(.+)',
    r'(选修\s*[一二三1-3])[：:\s]*(.+)',
]

# ============ 向量索引 API ============

@router.post("/vector/process")
async def vector_process_textbook(
    file: UploadFile = File(...),
    book_name: str = Form(...),
    version_id: Optional[int] = Form(None),
):
    """
    处理教材：解析PDF -> 生成章节切片 -> 创建向量索引

    使用父子文档索引策略：
    - 父文档：完整章节内容（用于LLM上下文）
    - 子文档：切片+向量（用于精准检索）

    Args:
        file: PDF教材文件
        book_name: 教材名称（如"生物学必修1"）
        version_id: 教材版本ID（可选）

    Returns:
        处理统计信息
    """
    from vector_service import VectorService
    from config import UPLOAD_DIR

    logger.info(f"[向量处理] 收到文件: {file.filename}, 教材名: {book_name}")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "只支持PDF格式")

    try:
        # 保存文件
        content = await file.read()
        pdf_path = UPLOAD_DIR / file.filename
        with open(pdf_path, "wb") as f:
            f.write(content)

        # 处理教材
        service = VectorService()
        stats = await service.process_textbook(
            str(pdf_path),
            book_name,
            version_id
        )

        return {
            "success": True,
            "message": f"向量索引创建完成：{stats['sections_processed']}个章节，{stats['chunks_with_embeddings']}个向量",
            "data": stats
        }

    except Exception as e:
        logger.error(f"[向量处理] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.post("/vector/search")
async def vector_search(data: VectorSearchRequest):
    """
    语义搜索：使用向量相似度找到最相关的教材内容

    这是实现"题目回溯知识点"的核心API：
    1. 将查询（如题目或关键词）转换为向量
    2. 在向量数据库中找到最相似的切片
    3. 返回匹配的内容及其章节信息

    Args:
        query: 搜索查询（如"ATP的作用"或一道题目的文字）
        top_k: 返回结果数量（默认5）
        book_name: 限定教材名称（可选）

    Returns:
        相似内容列表，包含：
        - content: 匹配的文本内容
        - chapter_num/chapter_title: 章节信息
        - section_num/section_title: 小节信息
        - page_num: 页码
        - similarity: 相似度分数
    """
    from vector_service import VectorService

    logger.info(f"[向量搜索] 查询: {data.query[:50]}..., top_k={data.top_k}")

    try:
        service = VectorService()
        results = await service.search_similar(
            query=data.query,
            top_k=data.top_k,
            book_name=data.book_name
        )

        return {
            "success": True,
            "message": f"找到 {len(results)} 个相关内容",
            "data": {
                "query": data.query,
                "results": results
            }
        }

    except Exception as e:
        logger.error(f"[向量搜索] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/vector/section/{section_id}")
async def get_section_context(section_id: int):
    """
    获取完整章节内容（用于LLM上下文）

    当找到相关切片后，可以用此API获取完整的章节内容，
    为LLM提供更完整的上下文进行分析或生成。

    Args:
        section_id: 章节ID（从搜索结果中获得）

    Returns:
        完整的章节信息和内容
    """
    from vector_service import VectorService

    try:
        service = VectorService()
        section = await service.get_section_context(section_id)

        if not section:
            raise HTTPException(404, f"章节不存在: {section_id}")

        return {
            "success": True,
            "data": section
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[获取章节] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/vector/book/{book_name}")
async def clear_book_vectors(book_name: str):
    """
    清除指定教材的所有向量数据

    用于重新处理教材时清除旧数据

    Args:
        book_name: 教材名称
    """
    from vector_service import VectorService

    try:
        service = VectorService()
        service.clear_book_data(book_name)

        return {
            "success": True,
            "message": f"已清除教材数据: {book_name}"
        }

    except Exception as e:
        logger.error(f"[清除数据] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/vector/stats")
async def get_vector_stats():
    """
    获取向量索引统计信息

    Returns:
        - 教材列表及各教材的章节数、切片数
        - 总向量数量
    """
    from sqlalchemy import create_engine, text
    import os

    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://biology:biology123@postgres:5432/biology_edu"
    )

    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            # 按教材统计
            result = conn.execute(text("""
                SELECT
                    s.book_name,
                    COUNT(DISTINCT s.id) as section_count,
                    COUNT(c.id) as chunk_count,
                    COUNT(c.embedding) as vector_count
                FROM textbook_sections s
                LEFT JOIN textbook_chunks c ON s.id = c.section_id
                GROUP BY s.book_name
                ORDER BY s.book_name
            """))

            books = []
            total_sections = 0
            total_chunks = 0
            total_vectors = 0

            for row in result:
                books.append({
                    "book_name": row[0],
                    "section_count": row[1],
                    "chunk_count": row[2],
                    "vector_count": row[3]
                })
                total_sections += row[1]
                total_chunks += row[2]
                total_vectors += row[3]

        return {
            "success": True,
            "data": {
                "books": books,
                "total": {
                    "sections": total_sections,
                    "chunks": total_chunks,
                    "vectors": total_vectors
                }
            }
        }

    except Exception as e:
        logger.error(f"[向量统计] 失败: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


# ============ Admin CRUD Endpoints ============


# Pydantic Models for Update
class ChapterUpdate(BaseModel):
    """更新章节请求"""
    grade: Optional[str] = None
    module_name: Optional[str] = None
    chapter_num: Optional[int] = None
    chapter_name: Optional[str] = None
    semester: Optional[str] = None
    section_num: Optional[int] = None
    section_name: Optional[str] = None


class ContentUpdate(BaseModel):
    """更新内容请求"""
    content: Optional[str] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    page_num: Optional[int] = None


class KnowledgePointUpdate(BaseModel):
    """更新知识点请求"""
    name: Optional[str] = None
    chapter_id: Optional[int] = None
    description: Optional[str] = None
    difficulty_level: Optional[int] = None
    importance_level: Optional[int] = None
    keywords: Optional[List[str]] = None


class VersionCreate(BaseModel):
    """创建教材版本请求"""
    name: str
    publisher: str
    year: Optional[int] = None
    description: Optional[str] = None


class VersionUpdate(BaseModel):
    """更新教材版本请求"""
    name: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None


# ============ 章节管理 ============

@router.put("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: int,
    request: Request,
    data: ChapterUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新章节（需要登录）"""
    logger.info(f"[教材] {user['username']} 更新章节: id={chapter_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_chapter_by_id(chapter_id)
        if not old_data:
            raise HTTPException(404, detail="章节不存在")

        result = await service.update_chapter(chapter_id, data.model_dump(exclude_unset=True))

        # 记录操作日志
        await log_operation(
            db, user, "update", "chapter",
            target_id=chapter_id,
            target_name=old_data.get("chapter_name", ""),
            old_value={"chapter_name": old_data.get("chapter_name"), "module_name": old_data.get("module_name")},
            new_value=data.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "章节更新成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 更新章节失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除章节（需要登录）"""
    logger.info(f"[教材] {user['username']} 删除章节: id={chapter_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_chapter_by_id(chapter_id)
        if not old_data:
            raise HTTPException(404, detail="章节不存在")

        result = await service.delete_chapter(chapter_id)

        # 记录操作日志
        await log_operation(
            db, user, "delete", "chapter",
            target_id=chapter_id,
            target_name=old_data.get("chapter_name", ""),
            old_value={"chapter_name": old_data.get("chapter_name"), "module_name": old_data.get("module_name")},
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "章节删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 删除章节失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


# ============ 内容管理 ============

@router.put("/contents/{content_id}")
async def update_content(
    content_id: int,
    request: Request,
    data: ContentUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新内容（需要登录）"""
    logger.info(f"[教材] {user['username']} 更新内容: id={content_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_content_by_id(content_id)
        if not old_data:
            raise HTTPException(404, detail="内容不存在")

        result = await service.update_content(content_id, data.model_dump(exclude_unset=True))

        # 记录操作日志
        await log_operation(
            db, user, "update", "content",
            target_id=content_id,
            target_name=old_data.get("title") or (old_data.get("content", "")[:30] + "..."),
            old_value={"content_type": old_data.get("content_type"), "title": old_data.get("title")},
            new_value=data.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "内容更新成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 更新内容失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/contents/{content_id}")
async def delete_content(
    content_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除内容（需要登录）"""
    logger.info(f"[教材] {user['username']} 删除内容: id={content_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_content_by_id(content_id)
        if not old_data:
            raise HTTPException(404, detail="内容不存在")

        result = await service.delete_content(content_id)

        # 记录操作日志
        await log_operation(
            db, user, "delete", "content",
            target_id=content_id,
            target_name=old_data.get("title") or (old_data.get("content", "")[:30] + "..."),
            old_value={"content_type": old_data.get("content_type"), "title": old_data.get("title")},
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "内容删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 删除内容失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


# ============ 知识点管理 ============

@router.put("/knowledge-points/{kp_id}")
async def update_knowledge_point(
    kp_id: int,
    request: Request,
    data: KnowledgePointUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新知识点（需要登录）"""
    logger.info(f"[教材] {user['username']} 更新知识点: id={kp_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_knowledge_point_by_id(kp_id)
        if not old_data:
            raise HTTPException(404, detail="知识点不存在")

        result = await service.update_knowledge_point(kp_id, data.model_dump(exclude_unset=True))

        # 记录操作日志
        await log_operation(
            db, user, "update", "knowledge_point",
            target_id=kp_id,
            target_name=old_data.get("name", ""),
            old_value={"name": old_data.get("name"), "description": old_data.get("description")},
            new_value=data.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "知识点更新成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 更新知识点失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/knowledge-points/{kp_id}")
async def delete_knowledge_point(
    kp_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除知识点（需要登录）"""
    logger.info(f"[教材] {user['username']} 删除知识点: id={kp_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_knowledge_point_by_id(kp_id)
        if not old_data:
            raise HTTPException(404, detail="知识点不存在")

        result = await service.delete_knowledge_point(kp_id)

        # 记录操作日志
        await log_operation(
            db, user, "delete", "knowledge_point",
            target_id=kp_id,
            target_name=old_data.get("name", ""),
            old_value={"name": old_data.get("name"), "description": old_data.get("description")},
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "知识点删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 删除知识点失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


# ============ 版本管理 ============

@router.post("/versions")
async def create_version(
    request: Request,
    data: VersionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """创建教材版本（需要登录）"""
    logger.info(f"[教材] {user['username']} 创建版本: {data.name}")

    service = TextbookService(db)
    try:
        result = await service.create_version(
            name=data.name,
            publisher=data.publisher,
            year=data.year,
            description=data.description
        )

        # 记录操作日志
        await log_operation(
            db, user, "create", "version",
            target_id=result.get("id"),
            target_name=data.name,
            new_value={"name": data.name, "publisher": data.publisher, "year": data.year},
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "版本创建成功", "data": result}
    except Exception as e:
        logger.error(f"[教材] 创建版本失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.put("/versions/{version_id}")
async def update_version(
    version_id: int,
    request: Request,
    data: VersionUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新教材版本（需要登录）"""
    logger.info(f"[教材] {user['username']} 更新版本: id={version_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_version_by_id(version_id)
        if not old_data:
            raise HTTPException(404, detail="版本不存在")

        result = await service.update_version(version_id, data.model_dump(exclude_unset=True))

        # 记录操作日志
        await log_operation(
            db, user, "update", "version",
            target_id=version_id,
            target_name=old_data.get("name", ""),
            old_value={"name": old_data.get("name"), "publisher": old_data.get("publisher")},
            new_value=data.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "版本更新成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 更新版本失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/versions/{version_id}")
async def delete_version(
    version_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除教材版本（需要登录）"""
    logger.info(f"[教材] {user['username']} 删除版本: id={version_id}")

    service = TextbookService(db)
    try:
        # 获取旧数据用于日志
        old_data = await service.get_version_by_id(version_id)
        if not old_data:
            raise HTTPException(404, detail="版本不存在")

        result = await service.delete_version(version_id)

        # 记录操作日志
        await log_operation(
            db, user, "delete", "version",
            target_id=version_id,
            target_name=old_data.get("name", ""),
            old_value={"name": old_data.get("name"), "publisher": old_data.get("publisher")},
            ip_address=request.client.host if request.client else None
        )

        return {"success": True, "message": "版本删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[教材] 删除版本失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")
