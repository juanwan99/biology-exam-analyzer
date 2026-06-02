"""
Word 文档精确解析器 v2
- 按文档顺序遍历所有元素
- 精确定位图片和表格位置
- 保持图文关联关系
"""
import os
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from docx import Document
from docx.table import Table
from lxml import etree

from logger import get_logger

logger = get_logger()


@dataclass
class DocElement:
    """文档元素"""
    index: int
    type: str  # 'paragraph', 'table', 'image'
    content: str = ""
    image_data: bytes = None
    image_id: str = None
    table_data: List[List[str]] = None


@dataclass
class ParsedDocument:
    """解析后的文档"""
    filename: str
    category: str
    elements: List[DocElement] = field(default_factory=list)
    images: Dict[str, bytes] = field(default_factory=dict)  # image_id -> bytes

    def to_marked_text(self) -> str:
        """转换为带标记的文本，用于发送给 LLM"""
        lines = []
        for elem in self.elements:
            if elem.type == 'paragraph':
                lines.append(f"[P{elem.index}] {elem.content}")
            elif elem.type == 'table':
                # 表格转为文本
                table_text = self._table_to_text(elem.table_data)
                lines.append(f"[T{elem.index}] 📊表格:\n{table_text}")
            elif elem.type == 'image':
                lines.append(f"[I{elem.index}] 📷[图片 {elem.image_id}]")
        return "\n".join(lines)

    def _table_to_text(self, table_data: List[List[str]]) -> str:
        """表格转文本"""
        if not table_data:
            return ""
        lines = []
        for row in table_data:
            lines.append(" | ".join(cell for cell in row))
        return "\n".join(lines)

    def get_image_list(self) -> List[Tuple[str, bytes]]:
        """获取图片列表，按出现顺序"""
        result = []
        for elem in self.elements:
            if elem.type == 'image' and elem.image_id:
                if elem.image_id in self.images:
                    result.append((elem.image_id, self.images[elem.image_id]))
        return result


class WordParserV2:
    """Word 文档精确解析器"""

    def __init__(self):
        self.ns = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
        }

    def parse(self, file_path: str) -> ParsedDocument:
        """
        解析 Word 文档

        Args:
            file_path: docx 文件路径

        Returns:
            ParsedDocument 包含所有元素和图片
        """
        logger.info(f"[解析] 开始解析: {file_path}")

        doc = Document(file_path)
        filename = Path(file_path).stem
        category = filename  # 文件名作为分类

        # 构建图片映射 rId -> bytes
        image_map = {}
        for rel_id, rel in doc.part.rels.items():
            if "image" in rel.reltype:
                image_map[rel_id] = rel.target_part.blob

        logger.info(f"[解析] 发现 {len(image_map)} 张图片")

        # 按顺序遍历文档元素
        elements = []
        element_index = 0
        image_counter = 0

        body = doc.element.body

        for child in body:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

            if tag == 'p':  # 段落
                elem = self._parse_paragraph(child, element_index, image_map)
                if elem:
                    # 如果段落包含图片，拆分为多个元素
                    if elem.get('has_image'):
                        # 先添加文本部分（如果有）
                        if elem['text'].strip():
                            elements.append(DocElement(
                                index=element_index,
                                type='paragraph',
                                content=elem['text']
                            ))
                            element_index += 1

                        # 添加图片元素
                        for img_id in elem['image_ids']:
                            image_counter += 1
                            img_label = f"IMG_{image_counter}"
                            elements.append(DocElement(
                                index=element_index,
                                type='image',
                                image_id=img_label,
                                image_data=image_map.get(img_id)
                            ))
                            # 更新 image_map 使用新标签
                            if img_id in image_map:
                                image_map[img_label] = image_map[img_id]
                            element_index += 1
                    else:
                        # 普通段落
                        if elem['text'].strip():
                            elements.append(DocElement(
                                index=element_index,
                                type='paragraph',
                                content=elem['text']
                            ))
                        element_index += 1
                else:
                    element_index += 1

            elif tag == 'tbl':  # 表格
                table_data = self._parse_table(child)
                if table_data:
                    elements.append(DocElement(
                        index=element_index,
                        type='table',
                        table_data=table_data
                    ))
                element_index += 1

        # 清理 image_map，只保留新标签
        clean_image_map = {k: v for k, v in image_map.items() if k.startswith('IMG_')}

        logger.info(f"[解析] 完成: {len(elements)} 个元素, {len(clean_image_map)} 张图片")

        return ParsedDocument(
            filename=filename,
            category=category,
            elements=elements,
            images=clean_image_map
        )

    def _parse_paragraph(self, para_elem, index: int, image_map: dict) -> Optional[dict]:
        """解析段落元素"""
        # 提取文本
        text_parts = []
        for t in para_elem.iter():
            if t.tag.endswith('}t') and t.text:
                text_parts.append(t.text)
        text = ''.join(text_parts).strip()

        # 查找图片
        image_ids = []
        for blip in para_elem.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
            embed_key = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
            r_id = blip.get(embed_key)
            if r_id and r_id in image_map:
                image_ids.append(r_id)

        return {
            'text': text,
            'has_image': len(image_ids) > 0,
            'image_ids': image_ids
        }

    def _parse_table(self, table_elem) -> List[List[str]]:
        """解析表格元素"""
        rows = []
        for tr in table_elem.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr'):
            cells = []
            for tc in tr.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc'):
                # 提取单元格文本
                cell_text = ''.join(
                    t.text or ''
                    for t in tc.iter()
                    if t.tag.endswith('}t')
                ).strip()
                cells.append(cell_text)
            if cells:
                rows.append(cells)
        return rows


def test_parser():
    """测试解析器"""
    file_path = "/home/ubuntu/biology-exam-analyzer/uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类/细胞的分子组成.docx"

    parser = WordParserV2()
    result = parser.parse(file_path)

    print("=" * 70)
    print(f"文件: {result.filename}")
    print(f"分类: {result.category}")
    print(f"元素数量: {len(result.elements)}")
    print(f"图片数量: {len(result.images)}")
    print("=" * 70)

    # 显示前30个元素
    print("\n前30个元素:")
    for elem in result.elements[:30]:
        if elem.type == 'paragraph':
            print(f"[P{elem.index}] {elem.content[:60]}{'...' if len(elem.content) > 60 else ''}")
        elif elem.type == 'table':
            print(f"[T{elem.index}] 📊 表格 ({len(elem.table_data)}行)")
        elif elem.type == 'image':
            print(f"[I{elem.index}] 📷 {elem.image_id}")

    # 显示图片位置
    print("\n" + "=" * 70)
    print("图片位置:")
    for elem in result.elements:
        if elem.type == 'image':
            # 找前后元素
            prev_elem = next((e for e in reversed(result.elements[:result.elements.index(elem)]) if e.type == 'paragraph'), None)
            next_elem = next((e for e in result.elements[result.elements.index(elem)+1:] if e.type == 'paragraph'), None)

            print(f"\n{elem.image_id} (索引 {elem.index}):")
            if prev_elem:
                print(f"  前: [{prev_elem.index}] {prev_elem.content[:50]}...")
            if next_elem:
                print(f"  后: [{next_elem.index}] {next_elem.content[:50]}...")

    # 输出带标记的文本（部分）
    print("\n" + "=" * 70)
    print("带标记的文本 (前2000字符):")
    print("=" * 70)
    marked_text = result.to_marked_text()
    print(marked_text[:2000])

    return result


if __name__ == "__main__":
    test_parser()
