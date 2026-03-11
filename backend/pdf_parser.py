"""
改进版PDF解析器
使用PyMuPDF提取文本、目录和图片
按PDF书签/目录自动分章节
"""
import os
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from io import BytesIO
import hashlib
from datetime import datetime

from logger import get_logger
from config import UPLOAD_DIR

logger = get_logger()


class PDFParser:
    """PDF解析器 - 支持目录提取、章节分类、图片提取"""

    def __init__(self, save_images: bool = True):
        self.save_images = save_images
        self.image_dir = UPLOAD_DIR / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def parse(self, pdf_content: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
        """
        解析PDF文档

        Returns:
            {
                "toc": [...],  # 目录结构
                "chapters": [...],  # 按章节组织的内容
                "images": [...],  # 提取的图片信息
                "metadata": {...}  # PDF元数据
            }
        """
        doc = fitz.open(stream=pdf_content, filetype="pdf")

        try:
            # 1. 提取PDF元数据
            metadata = self._extract_metadata(doc)
            logger.info(f"[PDF解析] 文件: {filename}, 页数: {doc.page_count}")

            # 2. 提取目录/书签
            toc = self._extract_toc(doc)
            logger.info(f"[PDF解析] 提取到 {len(toc)} 个目录项")

            # 3. 根据目录构建章节页码映射
            chapter_ranges = self._build_chapter_ranges(toc, doc.page_count)
            logger.info(f"[PDF解析] 构建了 {len(chapter_ranges)} 个章节范围")

            # 4. 按章节提取内容和图片
            chapters = self._extract_chapters(doc, chapter_ranges, filename)

            # 5. 统计图片
            total_images = sum(len(ch.get("images", [])) for ch in chapters)
            logger.info(f"[PDF解析] 提取完成: {len(chapters)}个章节, {total_images}张图片")

            return {
                "toc": toc,
                "chapters": chapters,
                "metadata": metadata,
                "filename": filename,
            }
        finally:
            doc.close()

    def _extract_metadata(self, doc: fitz.Document) -> Dict:
        """提取PDF元数据"""
        meta = doc.metadata
        return {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "creator": meta.get("creator", ""),
            "page_count": doc.page_count,
        }

    def _extract_toc(self, doc: fitz.Document) -> List[Dict]:
        """
        提取PDF目录/书签
        返回格式: [{"level": 1, "title": "第1章 走近细胞", "page": 1}, ...]
        """
        toc_raw = doc.get_toc()  # [[level, title, page], ...]
        toc = []

        for item in toc_raw:
            level, title, page = item[0], item[1], item[2]
            toc.append({
                "level": level,
                "title": title.strip(),
                "page": page,  # 1-based
            })

        return toc

    def _build_chapter_ranges(self, toc: List[Dict], total_pages: int) -> List[Dict]:
        """
        根据目录构建章节页码范围

        如果没有目录，尝试从文本中识别章节
        """
        if not toc:
            # 没有目录，返回单个"全书"章节
            logger.warning("[PDF解析] 未找到PDF目录，将尝试从文本识别章节")
            return [{
                "title": "全部内容",
                "level": 1,
                "start_page": 1,
                "end_page": total_pages,
                "chapter_num": 0,
                "module_name": "未分类",
            }]

        # 过滤出章级别的目录项（通常level=1或2是章）
        chapter_items = []
        current_module = "未分类"

        for item in toc:
            title = item["title"]
            level = item["level"]

            # 识别模块（必修1、选修1等）
            module_match = re.match(r'(必修|选择性必修|选修)\s*[一二三1-3]', title)
            if module_match:
                current_module = title
                continue

            # 识别章节
            chapter_match = re.match(r'^第\s*([一二三四五六七八九十\d]+)\s*章\s*(.+)$', title)
            if chapter_match:
                num_str = chapter_match.group(1)
                chapter_name = chapter_match.group(2).strip()
                chapter_num = self._chinese_to_num(num_str)

                chapter_items.append({
                    "title": title,
                    "chapter_name": chapter_name,
                    "chapter_num": chapter_num,
                    "level": level,
                    "page": item["page"],
                    "module_name": current_module,
                })

        # 构建页码范围
        ranges = []
        for i, ch in enumerate(chapter_items):
            start_page = ch["page"]
            # 结束页是下一章的前一页，或者文档末尾
            if i + 1 < len(chapter_items):
                end_page = chapter_items[i + 1]["page"] - 1
            else:
                end_page = total_pages

            ranges.append({
                "title": ch["title"],
                "chapter_name": ch["chapter_name"],
                "chapter_num": ch["chapter_num"],
                "level": ch["level"],
                "start_page": start_page,
                "end_page": end_page,
                "module_name": ch["module_name"],
            })

        # 如果没有识别到章节，将整个目录作为参考
        if not ranges:
            # 使用目录的第一级项目
            level1_items = [t for t in toc if t["level"] == 1]
            if not level1_items:
                level1_items = toc

            for i, item in enumerate(level1_items):
                start_page = item["page"]
                if i + 1 < len(level1_items):
                    end_page = level1_items[i + 1]["page"] - 1
                else:
                    end_page = total_pages

                ranges.append({
                    "title": item["title"],
                    "chapter_name": item["title"],
                    "chapter_num": i + 1,
                    "level": item["level"],
                    "start_page": start_page,
                    "end_page": end_page,
                    "module_name": "未分类",
                })

        return ranges

    def _extract_chapters(self, doc: fitz.Document, chapter_ranges: List[Dict], filename: str) -> List[Dict]:
        """按章节范围提取内容和图片"""
        chapters = []

        for ch_range in chapter_ranges:
            chapter_data = {
                "title": ch_range["title"],
                "chapter_name": ch_range.get("chapter_name", ch_range["title"]),
                "chapter_num": ch_range.get("chapter_num", 0),
                "module_name": ch_range.get("module_name", "未分类"),
                "start_page": ch_range["start_page"],
                "end_page": ch_range["end_page"],
                "contents": [],
                "images": [],
            }

            # 提取该章节范围内的所有页面
            for page_num in range(ch_range["start_page"] - 1, ch_range["end_page"]):  # 0-based
                if page_num >= doc.page_count:
                    break

                page = doc[page_num]

                # 提取文本
                text = page.get_text("text")
                if text.strip():
                    # 按段落分割
                    paragraphs = self._split_paragraphs(text)
                    for para in paragraphs:
                        if para.strip():
                            chapter_data["contents"].append({
                                "content": para.strip(),
                                "type": self._detect_content_type(para),
                                "page_num": page_num + 1,  # 1-based
                            })

                # 提取图片
                if self.save_images:
                    images = self._extract_page_images(page, page_num + 1, filename)
                    chapter_data["images"].extend(images)

            chapters.append(chapter_data)

        return chapters

    def _split_paragraphs(self, text: str) -> List[str]:
        """将文本分割成段落"""
        # 按双换行分割
        paragraphs = re.split(r'\n\s*\n', text)

        result = []
        for para in paragraphs:
            # 合并单个换行（同一段落内的换行）
            para = re.sub(r'(?<!\n)\n(?!\n)', ' ', para)
            para = para.strip()
            if para:
                result.append(para)

        return result

    def _detect_content_type(self, text: str) -> str:
        """检测内容类型"""
        text_lower = text[:50].lower()

        if text.startswith("【") and "】" in text:
            return "concept"
        elif "实验" in text[:20]:
            return "experiment"
        elif re.match(r'^第\s*[一二三四五六七八九十\d]+\s*[章节]', text):
            return "heading"
        elif re.match(r'^\d+[．.、]\s*', text):
            return "list"
        elif "思考" in text[:10] or "讨论" in text[:10]:
            return "discussion"
        elif "练习" in text[:10] or "习题" in text[:10]:
            return "exercise"
        else:
            return "text"

    def _extract_page_images(self, page: fitz.Page, page_num: int, filename: str) -> List[Dict]:
        """提取页面中的图片"""
        images = []
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)

                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image.get("ext", "png")

                    # 生成唯一文件名
                    image_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                    image_filename = f"{Path(filename).stem}_p{page_num}_{img_index}_{image_hash}.{image_ext}"
                    image_path = self.image_dir / image_filename

                    # 保存图片
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)

                    images.append({
                        "filename": image_filename,
                        "path": str(image_path),
                        "page_num": page_num,
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                        "size": len(image_bytes),
                    })
            except Exception as e:
                logger.warning(f"[PDF解析] 提取图片失败 (页{page_num}, 图{img_index}): {e}")

        return images

    def _chinese_to_num(self, chinese: str) -> int:
        """中文数字转阿拉伯数字"""
        mapping = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                   '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if chinese in mapping:
            return mapping[chinese]
        try:
            return int(chinese)
        except:
            return 0


# 便捷函数
def parse_pdf(pdf_content: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
    """解析PDF文档"""
    parser = PDFParser(save_images=True)
    return parser.parse(pdf_content, filename)


def parse_pdf_to_chapters(pdf_content: bytes, filename: str = "document.pdf") -> List[Dict]:
    """解析PDF并返回章节列表（兼容旧接口）"""
    result = parse_pdf(pdf_content, filename)
    return result["chapters"]
