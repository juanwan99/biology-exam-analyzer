# -*- coding: utf-8 -*-
"""
教材解析器 V2 - 父子文档索引方案
使用字号识别章节，实现层级化语义索引
"""
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from logger import get_logger

logger = get_logger()


@dataclass
class TextBlock:
    """文本块"""
    text: str
    font_size: float
    page_num: int
    y_position: float  # 垂直位置，用于排序
    is_bold: bool = False


@dataclass
class Section:
    """章节（父文档）"""
    chapter_num: int
    chapter_title: str
    section_num: Optional[int]
    section_title: Optional[str]
    content: str = ""
    page_start: int = 0
    page_end: int = 0
    images: List[str] = field(default_factory=list)

    @property
    def full_title(self) -> str:
        if self.section_title:
            return f"第{self.chapter_num}章 {self.chapter_title} - 第{self.section_num}节 {self.section_title}"
        return f"第{self.chapter_num}章 {self.chapter_title}"


@dataclass
class Chunk:
    """切片（子文档）"""
    content: str
    section_id: int  # 关联的section
    chunk_index: int
    page_num: int


class TextbookParserV2:
    """
    教材解析器 V2

    核心策略：
    1. 通过字号识别章节标题（>15pt为章，>12pt为节）
    2. 按节切分内容（父文档）
    3. 滑动窗口生成切片（子文档）
    """

    # 字号阈值（根据实际PDF分析结果调整）
    # 章标题: 35pt, 节标题: 24pt, 页眉: 9pt
    CHAPTER_FONT_SIZE = 30.0  # 章标题字号阈值 (实际35pt)
    SECTION_FONT_SIZE = 20.0  # 节标题字号阈值 (实际24pt)

    # 切片参数
    CHUNK_SIZE = 400  # 每个切片的目标字数
    CHUNK_OVERLAP = 80  # 切片重叠字数

    # 清洗正则
    PAGE_HEADER_PATTERN = re.compile(r'^\d+\s*第[0-9一二三四五六]章')  # 页眉: "12 第1章"
    PAGE_FOOTER_PATTERN = re.compile(r'^第[0-9一二三四五六]章.*\d+$')  # 页脚
    FIGURE_PATTERN = re.compile(r'^图\s*\d+-\d+')  # 图片标注

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.sections: List[Section] = []
        self.current_section: Optional[Section] = None

    def close(self):
        self.doc.close()

    def parse(self) -> List[Section]:
        """
        解析整本教材，返回章节列表
        """
        logger.info(f"[TextbookParserV2] 开始解析: {self.pdf_path}")
        logger.info(f"[TextbookParserV2] 总页数: {self.doc.page_count}")

        all_blocks: List[TextBlock] = []

        # 1. 提取所有页面的文本块（带字号信息）
        for page_num in range(self.doc.page_count):
            page = self.doc[page_num]
            blocks = self._extract_text_blocks(page, page_num + 1)
            all_blocks.extend(blocks)

        logger.info(f"[TextbookParserV2] 提取文本块: {len(all_blocks)} 个")

        # 2. 合并相邻的大字号文本块（处理拆分的章节标题）
        merged_blocks = self._merge_title_blocks(all_blocks)
        logger.info(f"[TextbookParserV2] 合并后文本块: {len(merged_blocks)} 个")

        # 3. 识别章节结构并组织内容
        self._build_sections(merged_blocks)

        logger.info(f"[TextbookParserV2] 识别章节: {len(self.sections)} 个")

        return self.sections

    def _extract_text_blocks(self, page: fitz.Page, page_num: int) -> List[TextBlock]:
        """
        提取页面中的文本块，保留字号信息
        """
        blocks = []
        text_dict = page.get_text("dict")

        page_height = page.rect.height

        for block in text_dict.get("blocks", []):
            if "lines" not in block:
                continue

            for line in block["lines"]:
                line_text = ""
                max_font_size = 0
                is_bold = False
                y_pos = line["bbox"][1]  # y坐标

                # 大字号标题（章节标题）不应跳过，即使在页眉区域
                # 只跳过小字号的页眉页脚
                is_large_font = False
                for span in line["spans"]:
                    if span["size"] >= self.SECTION_FONT_SIZE:
                        is_large_font = True
                        break

                # 跳过页眉页脚区域的小字号文本
                if not is_large_font:
                    if y_pos < page_height * 0.08 or y_pos > page_height * 0.92:
                        continue

                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        line_text += text
                        font_size = span["size"]
                        if font_size > max_font_size:
                            max_font_size = font_size
                        if "bold" in span.get("font", "").lower():
                            is_bold = True

                if line_text:
                    blocks.append(TextBlock(
                        text=line_text,
                        font_size=max_font_size,
                        page_num=page_num,
                        y_position=y_pos,
                        is_bold=is_bold
                    ))

        return blocks

    def _merge_title_blocks(self, blocks: List[TextBlock]) -> List[TextBlock]:
        """
        合并相邻的大字号文本块
        处理PDF中章节标题被拆分的情况，如 "第1章" 和 "走近细胞" 分开
        """
        if not blocks:
            return blocks

        merged = []
        i = 0

        while i < len(blocks):
            current = blocks[i]

            # 检查是否是潜在的章标题前缀（如 "第1章"）
            if (current.font_size >= self.CHAPTER_FONT_SIZE and
                re.match(r'^第[0-9一二三四五六七八九十]+章$', current.text.strip())):
                # 尝试向后查找同页、相同字号的块来合并
                # 注意：章标题可能垂直间距较大（如50-100像素）
                merged_text = current.text.strip()
                j = i + 1
                while j < len(blocks):
                    next_block = blocks[j]
                    # 同一页、字号相近
                    if (next_block.page_num == current.page_num and
                        next_block.font_size >= self.CHAPTER_FONT_SIZE):
                        # 章标题通常在页面上部，Y距离可以大一些（100像素）
                        if abs(next_block.y_position - current.y_position) < 100:
                            merged_text += " " + next_block.text.strip()
                            j += 1
                        else:
                            break
                    else:
                        break

                # 创建合并后的块
                merged.append(TextBlock(
                    text=merged_text,
                    font_size=current.font_size,
                    page_num=current.page_num,
                    y_position=current.y_position,
                    is_bold=current.is_bold
                ))
                i = j
                logger.info(f"[合并] 章标题: {merged_text} (P{current.page_num})")
                continue

            # 检查是否是潜在的节标题前缀（如 "第1节" 或 "第1 节"）
            if (current.font_size >= self.SECTION_FONT_SIZE and
                re.match(r'^第[0-9一二三四五六七八九十]+\s*节?$', current.text.strip())):
                merged_text = current.text.strip()
                j = i + 1
                while j < len(blocks):
                    next_block = blocks[j]
                    if (next_block.page_num == current.page_num and
                        next_block.font_size >= self.SECTION_FONT_SIZE and
                        abs(next_block.y_position - current.y_position) < 100):
                        merged_text += " " + next_block.text.strip()
                        j += 1
                    else:
                        break

                # 修正 "第1 节" -> "第1节"
                merged_text = re.sub(r'第(\d+)\s+节', r'第\1节', merged_text)

                merged.append(TextBlock(
                    text=merged_text,
                    font_size=current.font_size,
                    page_num=current.page_num,
                    y_position=current.y_position,
                    is_bold=current.is_bold
                ))
                i = j
                logger.info(f"[合并] 节标题: {merged_text} (P{current.page_num})")
                continue

            # 普通块直接添加
            merged.append(current)
            i += 1

        return merged

    def _is_chapter_title(self, block: TextBlock) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        判断是否为章标题
        返回: (是否为章标题, 章号, 章名)
        """
        text = block.text.strip()

        # 字号检测
        if block.font_size < self.CHAPTER_FONT_SIZE:
            return False, None, None

        # 正则匹配: "第1章 走近细胞" 或 "第一章 走近细胞"
        match = re.match(r'^第([0-9一二三四五六七八九十]+)章\s*(.+)', text)
        if match:
            num_str = match.group(1)
            title = match.group(2).strip()

            # 转换中文数字
            num = self._chinese_to_int(num_str)
            return True, num, title

        return False, None, None

    def _is_section_title(self, block: TextBlock) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        判断是否为节标题
        返回: (是否为节标题, 节号, 节名)
        """
        text = block.text.strip()

        # 字号检测
        if block.font_size < self.SECTION_FONT_SIZE:
            return False, None, None

        # 正则匹配: "第1节 细胞是生命活动的基本单位"
        match = re.match(r'^第([0-9一二三四五六七八九十]+)节\s*(.+)', text)
        if match:
            num_str = match.group(1)
            title = match.group(2).strip()
            num = self._chinese_to_int(num_str)
            return True, num, title

        return False, None, None

    def _chinese_to_int(self, s: str) -> int:
        """中文数字转阿拉伯数字"""
        if s.isdigit():
            return int(s)
        mapping = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                   '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        return mapping.get(s, 0)

    def _clean_text(self, text: str) -> str:
        """清洗文本"""
        # 移除页眉页脚模式
        if self.PAGE_HEADER_PATTERN.match(text):
            return ""
        if self.PAGE_FOOTER_PATTERN.match(text):
            return ""
        # 保留图片标注（可能有用）
        return text.strip()

    def _build_sections(self, blocks: List[TextBlock]):
        """
        根据文本块构建章节结构
        """
        current_chapter_num = 0
        current_chapter_title = "前言"
        current_section_num = None
        current_section_title = None
        content_buffer = []
        page_start = 1

        for block in blocks:
            # 检查是否为章标题
            is_chapter, chapter_num, chapter_title = self._is_chapter_title(block)
            if is_chapter:
                # 保存之前的section
                if content_buffer:
                    self._save_section(
                        current_chapter_num, current_chapter_title,
                        current_section_num, current_section_title,
                        "\n".join(content_buffer), page_start, block.page_num - 1
                    )
                    content_buffer = []

                current_chapter_num = chapter_num
                current_chapter_title = chapter_title
                current_section_num = None
                current_section_title = None
                page_start = block.page_num
                logger.info(f"[解析] 发现章: 第{chapter_num}章 {chapter_title} (P{block.page_num}, 字号{block.font_size:.1f})")
                continue

            # 检查是否为节标题
            is_section, section_num, section_title = self._is_section_title(block)
            if is_section and current_chapter_num > 0:
                # 保存之前的section
                if content_buffer:
                    self._save_section(
                        current_chapter_num, current_chapter_title,
                        current_section_num, current_section_title,
                        "\n".join(content_buffer), page_start, block.page_num - 1
                    )
                    content_buffer = []

                current_section_num = section_num
                current_section_title = section_title
                page_start = block.page_num
                logger.info(f"[解析] 发现节: 第{section_num}节 {section_title} (P{block.page_num}, 字号{block.font_size:.1f})")
                continue

            # 普通内容
            cleaned = self._clean_text(block.text)
            if cleaned:
                content_buffer.append(cleaned)

        # 保存最后一个section
        if content_buffer:
            self._save_section(
                current_chapter_num, current_chapter_title,
                current_section_num, current_section_title,
                "\n".join(content_buffer), page_start, self.doc.page_count
            )

    def _save_section(self, chapter_num: int, chapter_title: str,
                      section_num: Optional[int], section_title: Optional[str],
                      content: str, page_start: int, page_end: int):
        """保存一个section"""
        if not content.strip():
            return

        section = Section(
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            section_num=section_num,
            section_title=section_title,
            content=content,
            page_start=page_start,
            page_end=page_end
        )
        self.sections.append(section)
        logger.info(f"[保存] {section.full_title} (P{page_start}-{page_end}, {len(content)}字)")

    def generate_chunks(self, section: Section, section_id: int) -> List[Chunk]:
        """
        为一个section生成切片（滑动窗口）
        """
        content = section.content
        chunks = []

        if len(content) <= self.CHUNK_SIZE:
            # 内容太短，直接作为一个切片
            chunks.append(Chunk(
                content=content,
                section_id=section_id,
                chunk_index=0,
                page_num=section.page_start
            ))
            return chunks

        # 滑动窗口切分
        start = 0
        chunk_index = 0

        while start < len(content):
            end = start + self.CHUNK_SIZE

            # 尽量在句号处断开
            if end < len(content):
                # 向后找句号
                punct_pos = content.find('。', end - 50, end + 50)
                if punct_pos > 0:
                    end = punct_pos + 1

            chunk_text = content[start:end].strip()
            if chunk_text:
                chunks.append(Chunk(
                    content=chunk_text,
                    section_id=section_id,
                    chunk_index=chunk_index,
                    page_num=section.page_start  # 简化处理，后续可以优化
                ))
                chunk_index += 1

            # 滑动窗口
            start = end - self.CHUNK_OVERLAP
            if start >= len(content) - self.CHUNK_OVERLAP:
                break

        return chunks

    def extract_images(self, page_start: int, page_end: int) -> List[str]:
        """
        提取指定页码范围内的图片
        """
        images = []
        for page_num in range(page_start - 1, min(page_end, self.doc.page_count)):
            page = self.doc[page_num]
            image_list = page.get_images(full=True)

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = self.doc.extract_image(xref)
                    if base_image:
                        img_filename = f"section_p{page_num + 1}_img_{img_idx + 1}.{base_image['ext']}"
                        images.append(img_filename)
                except Exception as e:
                    logger.warning(f"提取图片失败: {e}")

        return images


def test_parser():
    """测试解析器"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python textbook_parser_v2.py <pdf_path>")
        return

    pdf_path = sys.argv[1]
    parser = TextbookParserV2(pdf_path)

    try:
        sections = parser.parse()

        print("\n" + "="*60)
        print("解析结果汇总")
        print("="*60)

        for section in sections:
            print(f"\n【{section.full_title}】")
            print(f"  页码: P{section.page_start}-{section.page_end}")
            print(f"  内容长度: {len(section.content)} 字")
            print(f"  内容预览: {section.content[:100]}...")

            # 生成切片
            chunks = parser.generate_chunks(section, section_id=0)
            print(f"  切片数量: {len(chunks)}")

    finally:
        parser.close()


if __name__ == "__main__":
    test_parser()
