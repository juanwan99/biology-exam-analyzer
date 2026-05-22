"""
PDF文档题目拆分器
基于pdfplumber提取文字，使用AI进行智能拆分
"""

import re
import base64
import io
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
from logger import get_logger

logger = get_logger()


@dataclass
class PDFQuestion:
    """PDF题目数据结构"""
    id: int
    content: str
    page_indices: List[int]  # 题目所在页码
    images: List[Dict[str, Any]]  # 图片列表
    warnings: List[str]
    section_header: Optional[str] = None


class PDFQuestionSplitter:
    """PDF文档题目拆分器"""

    # 题号正则模式
    QUESTION_PATTERNS = [
        (r'^(\d+)[.、．]\s*', 1.0, 'standard'),       # 1. 或 1、或 1．
        (r'^\((\d+)\)\s*', 0.9, 'parenthesis'),       # (1)
        (r'^（(\d+)）\s*', 0.9, 'cn_parenthesis'),    # （1）
        (r'^([一二三四五六七八九十]+)[.、．]\s*', 0.8, 'chinese'),  # 一、
    ]

    # 分节标题模式
    SECTION_PATTERNS = [
        r'^[一二三四五六七八九十]+[.、．]\s*.*(选择题|非选择题|实验题|综合题|填空题|简答题)',
        r'^[一二三四五六七八九十]+[.、．]\s*本题共\d+小题',
        r'^第[一二三四五六七八九十]+部分',
    ]

    def __init__(self):
        logger.info("[PDF拆分器] 初始化完成")

    def split(self, pdf_path: str, dpi: int = 200) -> Dict[str, Any]:
        """
        拆分PDF文档为题目列表

        Args:
            pdf_path: PDF文件路径
            dpi: 图片转换DPI

        Returns:
            {
                "questions": [...],
                "method": "pdf_rule",
                "confidence": 0.8,
                "total_pages": 5
            }
        """
        logger.info(f"[PDF拆分] 开始处理文档: {pdf_path}")

        try:
            # 1. 提取PDF文字
            pages_text = self._extract_text(pdf_path)
            logger.info(f"[PDF拆分] 提取到{len(pages_text)}页文字")

            # 2. 转换PDF为图片
            page_images = self._convert_to_images(pdf_path, dpi)
            logger.info(f"[PDF拆分] 转换为{len(page_images)}张图片")

            # 3. 基于规则识别题目边界
            questions = self._split_questions(pages_text, page_images)
            logger.info(f"[PDF拆分] 识别到{len(questions)}道题目")

            # 4. 计算置信度
            confidence = self._calculate_confidence(questions, pages_text)

            result = {
                "questions": [self._question_to_dict(q) for q in questions],
                "method": "pdf_rule",
                "confidence": confidence,
                "total_pages": len(pages_text),
                "warnings": []
            }

            if confidence < 0.7:
                result["warnings"].append("PDF识别置信度较低，建议人工校验")

            logger.info(f"[PDF拆分] 完成，识别到{len(questions)}道题目，置信度{confidence:.2f}")
            return result

        except Exception as e:
            logger.error(f"[PDF拆分] 失败: {str(e)}", exc_info=True)
            raise

    def _extract_text(self, pdf_path: str) -> List[Dict[str, Any]]:
        """提取每页的文字"""
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append({
                    "page_num": page_num,
                    "text": text,
                    "lines": text.split('\n') if text else []
                })
        return pages

    def _convert_to_images(self, pdf_path: str, dpi: int) -> List[str]:
        """将PDF转换为base64图片列表"""
        images = convert_from_path(pdf_path, dpi=dpi, fmt='jpeg')
        base64_images = []

        for img in images:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            base64_images.append(base64_str)

        return base64_images

    def _split_questions(self, pages_text: List[Dict], page_images: List[str]) -> List[PDFQuestion]:
        """基于规则识别题目"""
        questions = []
        current_question = None
        current_section_header = None

        for page_data in pages_text:
            page_num = page_data["page_num"]
            lines = page_data["lines"]

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 检测分节标题
                section_header = self._detect_section_header(line)
                if section_header:
                    current_section_header = section_header
                    logger.debug(f"[PDF拆分] 识别到分节标题: {section_header[:50]}")
                    continue

                # 检测题号
                question_id, pattern_type = self._detect_question_number(line)

                if question_id is not None:
                    # 保存上一道题
                    if current_question:
                        questions.append(current_question)

                    # 创建新题目
                    current_question = PDFQuestion(
                        id=question_id,
                        content=line,
                        page_indices=[page_num],
                        images=[],
                        warnings=[],
                        section_header=current_section_header
                    )
                    logger.debug(f"[PDF拆分] 识别到题目{question_id}，页{page_num+1}")
                else:
                    # 追加到当前题目
                    if current_question:
                        current_question.content += "\n" + line
                        if page_num not in current_question.page_indices:
                            current_question.page_indices.append(page_num)
                            current_question.warnings.append("跨页题目")

        # 添加最后一道题
        if current_question:
            questions.append(current_question)

        # 为每道题添加对应的页面图片
        for q in questions:
            for page_idx in q.page_indices:
                if page_idx < len(page_images):
                    q.images.append({
                        "type": "page",
                        "page_num": page_idx,
                        "base64": page_images[page_idx]
                    })

        return questions

    def _detect_section_header(self, text: str) -> Optional[str]:
        """检测分节标题"""
        for pattern in self.SECTION_PATTERNS:
            if re.search(pattern, text[:100]):
                return text.strip()
        return None

    def _detect_question_number(self, text: str) -> Tuple[Optional[int], Optional[str]]:
        """检测题号"""
        # 过滤噪音
        noise_patterns = [
            r'^[0-9]+[.、]\s*(答题前|请按|选择题用|考试结束|注意事项)',
            r'^[0-9]+[.、].*(答题卡|试卷|草稿纸|准考证|条形码)',
        ]

        for noise_pattern in noise_patterns:
            if re.search(noise_pattern, text[:50]):
                return None, None

        for pattern, confidence, pattern_type in self.QUESTION_PATTERNS:
            match = re.match(pattern, text)
            if match:
                num_str = match.group(1)

                if pattern_type == 'chinese':
                    question_id = self._chinese_to_num(num_str)
                else:
                    question_id = int(num_str)

                return question_id, pattern_type

        return None, None

    def _chinese_to_num(self, chinese: str) -> int:
        """中文数字转阿拉伯数字"""
        chinese_num_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }

        if chinese in chinese_num_map:
            return chinese_num_map[chinese]

        if chinese.startswith('十'):
            if len(chinese) == 1:
                return 10
            else:
                return 10 + chinese_num_map.get(chinese[1], 0)

        return 0

    def _calculate_confidence(self, questions: List[PDFQuestion], pages_text: List[Dict]) -> float:
        """计算拆分置信度"""
        if not questions:
            return 0.0

        # 基础置信度
        confidence = 0.8

        # 检查题号连续性
        ids = [q.id for q in questions]
        expected_ids = list(range(1, len(ids) + 1))
        if ids == expected_ids:
            confidence += 0.1
        else:
            confidence -= 0.2

        # 检查跨页题目数量
        cross_page_count = sum(1 for q in questions if len(q.page_indices) > 1)
        if cross_page_count > len(questions) * 0.3:
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))

    def _question_to_dict(self, question: PDFQuestion) -> Dict[str, Any]:
        """将Question对象转为字典"""
        # 组装media数据（供AI分析）
        media_for_ai = []

        for img in question.images:
            media_for_ai.append({
                "type": "image",
                "base64": img["base64"]
            })

        return {
            "id": question.id,
            "content": question.content,
            "confidence": 0.8,
            "warnings": question.warnings,
            "has_options": self._has_options(question.content),
            "cross_page": len(question.page_indices) > 1,
            "page_indices": question.page_indices,

            # 内部使用
            "_media_for_ai": media_for_ai,
            "_section_header": question.section_header
        }

    def _has_options(self, content: str) -> bool:
        """检测是否为选择题"""
        option_pattern = r'[A-D][.、．]\s*\S+'
        return bool(re.search(option_pattern, content))
