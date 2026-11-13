"""
PDF文档题目拆分器
基于pdfplumber提取文字，按题号规则拆分

前端只收 Word；analyze_auto 的 API 仍收 PDF，走这里。
- 只认「1.」「1、」「一、」作大题号；「（1）」「(1)」是小问，留在所属大题里。
- 第一个分节标题之前的编号条目（卷首说明、注意事项）在分节后题号重新从小号起时丢弃。
- 过半页面都出现的行（页眉页脚、课件题号导航）不进题干；重叠绘制的重复字先去重。
- 【答案】【解析】块不进题干，另存 answer 给报告；页面图上同位置涂白，AI 看图也看不到（#28）。
"""

import re
from collections import Counter
import base64
import io
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import pdfplumber
from pdf2image import convert_from_path
from PIL import ImageDraw
from answer_blocks import answer_line_flags
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
    line_refs: List[Tuple[int, int]] = field(default_factory=list)  # content 每行的 (页, 行号)
    answer: str = ""  # 剥下来的【答案】【解析】原文
    answer_refs: List[Tuple[int, int]] = field(default_factory=list)  # 答案行的 (页, 行号)，页面图上涂白


class PDFQuestionSplitter:
    """PDF文档题目拆分器"""

    # 大题号正则模式（「(1)」「（1）」是小问，不在这里）
    QUESTION_PATTERNS = [
        (r'^(\d+)[.、．]\s*', 1.0, 'standard'),       # 1. 或 1、或 1．
        (r'^([一二三四五六七八九十]+)[.、．]\s*', 0.8, 'chinese'),  # 一、
    ]

    # 一行出现在不少于这个比例的页面上，算页眉页脚 / 导航（页数够 RUNNING_MIN_PAGES 才判）
    RUNNING_LINE_RATIO = 0.5
    RUNNING_MIN_PAGES = 4

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

            # 2. 基于规则识别题目边界，剥掉【答案】【解析】块
            questions = self._split_questions(pages_text)
            logger.info(f"[PDF拆分] 识别到{len(questions)}道题目")

            # 3. 转换PDF为图片（答案块涂白），挂到各题
            page_images = self._convert_to_images(pdf_path, dpi, self._answer_boxes(questions, pages_text))
            logger.info(f"[PDF拆分] 转换为{len(page_images)}张图片")
            self._attach_page_images(questions, page_images)

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
                # 粗体常被画两遍，抽出来字字重复（「选选项项」），先去重
                text_lines = page.dedupe_chars().extract_text_lines()
                pages.append({
                    "page_num": page_num,
                    "lines": [line["text"] for line in text_lines],
                    "boxes": [(line["x0"], line["top"], line["x1"], line["bottom"]) for line in text_lines],
                })
        return pages

    def _convert_to_images(self, pdf_path: str, dpi: int,
                           masks: Optional[Dict[int, List[Tuple[float, float, float, float]]]] = None) -> List[str]:
        """将PDF转换为base64图片列表；masks 里的框（PDF 坐标）涂白"""
        images = convert_from_path(pdf_path, dpi=dpi, fmt='jpeg')
        base64_images = []
        scale = dpi / 72

        for page_num, img in enumerate(images):
            boxes = (masks or {}).get(page_num, [])
            if boxes:
                draw = ImageDraw.Draw(img)
                for x0, top, x1, bottom in boxes:
                    draw.rectangle([(x0 - 2) * scale, (top - 2) * scale, (x1 + 2) * scale, (bottom + 2) * scale],
                                   fill="white")
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            base64_images.append(base64_str)

        return base64_images

    def _split_questions(self, pages_text: List[Dict]) -> List[PDFQuestion]:
        """基于规则识别题目"""
        questions = []
        current_question = None
        current_section_header = None
        running = self._running_lines(pages_text)

        for page_data in pages_text:
            page_num = page_data["page_num"]
            lines = page_data["lines"]

            for line_idx, line in enumerate(lines):
                line = line.strip()
                if not line or line in running:
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
                        section_header=current_section_header,
                        line_refs=[(page_num, line_idx)],
                    )
                    logger.debug(f"[PDF拆分] 识别到题目{question_id}，页{page_num+1}")
                else:
                    # 追加到当前题目
                    if current_question:
                        current_question.content += "\n" + line
                        current_question.line_refs.append((page_num, line_idx))
                        if page_num not in current_question.page_indices:
                            current_question.page_indices.append(page_num)
                            current_question.warnings.append("跨页题目")

        # 添加最后一道题
        if current_question:
            questions.append(current_question)

        questions = self._drop_preamble(questions)
        for q in questions:
            self._strip_answer(q)
        return questions

    def _strip_answer(self, question: PDFQuestion) -> None:
        """【答案】【解析】块移出题干存 answer，答案行位置记 answer_refs。"""
        lines = question.content.split("\n")
        flags = answer_line_flags(lines)
        question.content = "\n".join(line for line, f in zip(lines, flags) if not f)
        question.answer = "\n".join(line for line, f in zip(lines, flags) if f)
        question.answer_refs = [ref for ref, f in zip(question.line_refs, flags) if f]

    def _answer_boxes(self, questions: List[PDFQuestion], pages_text: List[Dict]) -> Dict[int, List[Tuple]]:
        """各页要涂白的答案行框。"""
        masks: Dict[int, List[Tuple]] = {}
        for q in questions:
            for page_num, line_idx in q.answer_refs:
                masks.setdefault(page_num, []).append(pages_text[page_num]["boxes"][line_idx])
        return masks

    def _attach_page_images(self, questions: List[PDFQuestion], page_images: List[str]) -> None:
        """为每道题添加对应的页面图片"""
        for q in questions:
            for page_idx in q.page_indices:
                if page_idx < len(page_images):
                    q.images.append({
                        "type": "page",
                        "page_num": page_idx,
                        "base64": page_images[page_idx]
                    })

    def _running_lines(self, pages_text: List[Dict]) -> set:
        """过半页面都出现的行：页眉页脚、课件题号导航，不进题干。"""
        if len(pages_text) < self.RUNNING_MIN_PAGES:
            return set()
        counts = Counter()
        for page_data in pages_text:
            counts.update({line.strip() for line in page_data["lines"] if line.strip()})
        threshold = len(pages_text) * self.RUNNING_LINE_RATIO
        return {line for line, n in counts.items() if n >= threshold}

    def _drop_preamble(self, questions: List[PDFQuestion]) -> List[PDFQuestion]:
        """第一个分节标题之前的编号条目，若分节后题号重新从小号起，就是卷首说明，丢弃。"""
        first = next((i for i, q in enumerate(questions) if q.section_header), None)
        if not first:
            return questions
        before = questions[:first]
        if questions[first].id <= max(q.id for q in before):
            logger.info(f"[PDF拆分] 丢弃分节前的{len(before)}条卷首说明")
            return questions[first:]
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

        result = {
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
        if question.answer:  # 空串不写：报告见不到卷面答案时回落用 AI 作答
            result["answer"] = question.answer
        return result

    def _has_options(self, content: str) -> bool:
        """检测是否为选择题"""
        option_pattern = r'[A-D][.、．]\s*\S+'
        return bool(re.search(option_pattern, content))
