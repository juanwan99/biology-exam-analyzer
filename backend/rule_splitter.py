"""
规则引擎题目拆分器
基于正则表达式和坐标信息进行高精度题目识别和拆分
"""

import re
import base64
import io
from PIL import Image
import pdfplumber
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from logger import get_logger

logger = get_logger()


@dataclass
class BoundingBox:
    """边界框坐标"""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int

    def area(self) -> float:
        """计算面积"""
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def iou(self, other: 'BoundingBox') -> float:
        """计算与另一个框的IoU（交并比）"""
        if self.page != other.page:
            return 0.0

        # 计算交集
        x_left = max(self.x0, other.x0)
        y_top = max(self.y0, other.y0)
        x_right = min(self.x1, other.x1)
        y_bottom = min(self.y1, other.y1)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)
        union = self.area() + other.area() - intersection

        return intersection / union if union > 0 else 0.0

    def vertical_distance(self, other: 'BoundingBox') -> float:
        """计算垂直距离（同一页）"""
        if self.page != other.page:
            return float('inf')
        return abs(self.y0 - other.y1)


@dataclass
class TextBlock:
    """文本块"""
    text: str
    bbox: BoundingBox
    font_size: float = 12.0
    is_bold: bool = False


@dataclass
class Question:
    """题目数据结构"""
    id: int
    content: str
    bbox: BoundingBox
    confidence: float  # 置信度 0-1
    warnings: List[str]  # 警告信息
    images: List[Dict[str, Any]]  # 关联的图片
    tables: List[Dict[str, Any]]  # 关联的表格
    has_options: bool  # 是否包含选项（判断是否为选择题）
    cross_page: bool  # 是否跨页


class RuleSplitter:
    """规则引擎题目拆分器"""

    # 题号识别正则表达式（优先级从高到低）
    QUESTION_PATTERNS = [
        # 标准格式：数字. 空格（如"1. "）
        (r'^(\d{1,2})\.\s+', 'standard', 1.0),
        # 标准格式：数字、空格（如"1、"）
        (r'^(\d{1,2})、\s*', 'standard_chinese', 1.0),
        # 带括号：(数字)（如"(1)"）
        (r'^\((\d{1,2})\)\s*', 'parenthesis', 0.9),
        # 中文数字：一、二、三（大题标题）
        (r'^([一二三四五六七八九十]+)、\s*', 'section_header', 0.8),
        # 方括号：[数字]（如"[1]"）
        (r'^\[(\d{1,2})\]\s*', 'bracket', 0.7),
    ]

    # 选项识别正则
    OPTION_PATTERN = r'[A-D][.、．]'

    # 跨页检测关键词
    CROSS_PAGE_KEYWORDS = [
        '见下页', '转下页', '（下转）', '续表', '接上页',
        '如图所示', '下表', '如下图'
    ]

    # 噪声文本过滤模式（页码、版权、题型说明等无效信息）
    NOISE_PATTERNS = [
        # 页码模式
        (r'第\s*\d+\s*页\s*/?\s*共\s*\d+\s*页', 'page_number'),
        (r'^\s*-\s*\d+\s*-\s*$', 'page_dash'),
        (r'^\s*第?\s*\d+\s*页\s*$', 'page_simple'),

        # 版权/机构信息
        (r'学科网', 'copyright_xueke'),
        (r'.*股份有限公司.*', 'copyright_company'),

        # 题型说明（重复出现的指导语）
        (r'^[一二三四五六七八九十]+、\s*(选择题|非选择题|简答题|实验题|综合题)[:：].*?(?:每小题|本题共|全部选对).*', 'instruction_section'),
        (r'^注意事项[:：]', 'instruction_notice'),
        (r'^本题共\d+小题.*?(?:每小题|共\d+分)', 'instruction_question_info'),
    ]

    def __init__(self):
        """初始化拆分器"""
        self.noise_stats = {"removed_count": 0, "removed_types": {}}  # 统计清除的噪声
        logger.info("[规则拆分器] 初始化完成")

    def split_questions(
        self,
        pdf_path: str,
        use_llm_fallback: bool = True
    ) -> Dict[str, Any]:
        """
        主入口：拆分PDF试卷为题目列表

        Args:
            pdf_path: PDF文件路径
            use_llm_fallback: 如果规则拆分失败，是否回退到LLM拆分

        Returns:
            {
                "success": bool,
                "questions": [...],
                "confidence": float,  # 整体置信度
                "warnings": [...],
                "method": "rule" | "llm_fallback"
            }
        """
        logger.info(f"[规则拆分] 开始处理PDF: {pdf_path}")

        # 重置噪声统计
        self.noise_stats = {"removed_count": 0, "removed_types": {}}

        try:
            # 1. 提取结构化内容
            structured_data = self._extract_structured_content(pdf_path)

            # 2. 识别题号位置
            question_markers = self._detect_question_numbers(structured_data)

            if not question_markers:
                logger.warning("[规则拆分] 未检测到题号，可能需要LLM fallback")
                if use_llm_fallback:
                    return {"success": False, "method": "llm_fallback_required"}
                else:
                    return {"success": False, "error": "未检测到题号"}

            # 3. 划分题目边界
            questions = self._segment_questions(question_markers, structured_data)

            # 4. 匹配图片和表格
            self._match_media_to_questions(questions, structured_data)

            # 5. 检测选项（判断是否为选择题）
            self._detect_options(questions)

            # 6. 跨页检测
            self._detect_cross_page_questions(questions, structured_data)

            # 7. 计算置信度
            overall_confidence = self._calculate_overall_confidence(questions)

            # 8. 生成警告
            overall_warnings = self._generate_warnings(questions)

            # 9. 输出噪声过滤统计
            if self.noise_stats["removed_count"] > 0:
                noise_summary = ", ".join([f"{k}:{v}" for k, v in self.noise_stats["removed_types"].items()])
                logger.info(f"[噪声过滤] 已清除{self.noise_stats['removed_count']}条无效信息 ({noise_summary})")

            logger.info(f"[规则拆分] 完成，识别到{len(questions)}道题目，整体置信度: {overall_confidence:.2f}")

            return {
                "success": True,
                "questions": [self._question_to_dict(q) for q in questions],
                "confidence": overall_confidence,
                "warnings": overall_warnings,
                "method": "rule",
                "noise_removed": self.noise_stats["removed_count"]  # 添加噪声清除统计
            }

        except Exception as e:
            logger.error(f"[规则拆分] 失败: {str(e)}", exc_info=True)
            if use_llm_fallback:
                return {"success": False, "method": "llm_fallback_required", "error": str(e)}
            else:
                raise

    def _extract_structured_content(self, pdf_path: str) -> Dict[str, Any]:
        """
        提取PDF的结构化内容（文字+坐标+图片+表格）

        Returns:
            {
                "pages": [
                    {
                        "page_num": 1,
                        "text_blocks": [TextBlock, ...],
                        "images": [{bbox, data}, ...],
                        "tables": [{bbox, markdown}, ...]
                    }
                ],
                "total_pages": int
            }
        """
        logger.info(f"[结构化提取] 开始提取PDF内容")

        pages_data = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                logger.debug(f"[结构化提取] 处理第{page_num}页")

                page_data = {
                    "page_num": page_num,
                    "text_blocks": [],
                    "images": [],
                    "tables": []
                }

                # 1. 提取文字块（带坐标）
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=True
                )

                if words:
                    # 将words按行聚合成text_blocks
                    lines = self._group_words_into_lines(words, page_num)
                    page_data["text_blocks"] = lines

                # 2. 提取图片（方案C：带边距的完整截图）
                if hasattr(page, 'images'):
                    for img_idx, img_info in enumerate(page.images):
                        # 提取图片数据并转换为base64，添加边距保留上下文
                        img_data = None
                        try:
                            # 使用页面的完整尺寸来裁剪，避免坐标越界
                            page_width = page.width
                            page_height = page.height

                            # 添加边距（上下左右各20像素）保留格式上下文
                            margin = 20
                            x0 = max(0, img_info['x0'] - margin)
                            y0 = max(0, img_info['top'] - margin)
                            x1 = min(page_width, img_info['x1'] + margin)
                            y1 = min(page_height, img_info['bottom'] + margin)

                            img_width = x1 - x0
                            img_height = y1 - y0

                            logger.debug(f"[图片提取] 第{page_num}页图片{img_idx}: bbox=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}), 尺寸={img_width:.1f}x{img_height:.1f}")

                            # 只有当bbox有效时才提取图片
                            if x1 > x0 and y1 > y0:
                                bbox = (x0, y0, x1, y1)
                                cropped = page.crop(bbox)
                                img_pil = cropped.to_image(resolution=150).original

                                # 转换为base64
                                buffer = io.BytesIO()
                                img_pil.save(buffer, format='PNG')
                                img_bytes = buffer.getvalue()
                                img_data = base64.b64encode(img_bytes).decode('utf-8')

                                logger.debug(f"[图片提取] 第{page_num}页图片{img_idx}: base64长度={len(img_data)}, PIL尺寸={img_pil.size}")
                        except Exception as e:
                            logger.warning(f"[图片提取] 第{page_num}页图片{img_idx}提取失败: {str(e)}")

                        page_data["images"].append({
                            "bbox": BoundingBox(
                                x0=img_info['x0'],
                                y0=img_info['y0'],
                                x1=img_info['x1'],
                                y1=img_info['y1'],
                                page=page_num
                            ),
                            "width": img_info['width'],
                            "height": img_info['height'],
                            "data": img_data  # 添加base64编码的图片数据
                        })

                # 3. 提取表格（方案C：截图方式，保留格式）
                table_settings = page.find_tables()
                if table_settings:
                    for i, table_obj in enumerate(table_settings):
                        try:
                            # 获取表格bbox
                            table_bbox_raw = table_obj.bbox

                            # 添加边距保留上下文
                            margin = 15
                            page_width = page.width
                            page_height = page.height

                            x0 = max(0, table_bbox_raw[0] - margin)
                            y0 = max(0, table_bbox_raw[1] - margin)
                            x1 = min(page_width, table_bbox_raw[2] + margin)
                            y1 = min(page_height, table_bbox_raw[3] + margin)

                            table_width = x1 - x0
                            table_height = y1 - y0

                            logger.debug(f"[表格提取] 第{page_num}页表格{i}: bbox=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}), 尺寸={table_width:.1f}x{table_height:.1f}")

                            # 裁剪表格区域并转换为图片
                            if x1 > x0 and y1 > y0:
                                bbox = (x0, y0, x1, y1)
                                cropped = page.crop(bbox)
                                table_img_pil = cropped.to_image(resolution=150).original

                                # 转换为base64
                                buffer = io.BytesIO()
                                table_img_pil.save(buffer, format='PNG')
                                table_img_bytes = buffer.getvalue()
                                table_img_data = base64.b64encode(table_img_bytes).decode('utf-8')

                                logger.debug(f"[表格提取] 第{page_num}页表格{i}: base64长度={len(table_img_data)}, PIL尺寸={table_img_pil.size}")

                                page_data["tables"].append({
                                    "bbox": BoundingBox(
                                        x0=table_bbox_raw[0],
                                        y0=table_bbox_raw[1],
                                        x1=table_bbox_raw[2],
                                        y1=table_bbox_raw[3],
                                        page=page_num
                                    ),
                                    "image_data": table_img_data,  # 表格截图的base64数据
                                    "markdown": None  # 不再提取markdown
                                })
                        except Exception as e:
                            logger.warning(f"[表格提取] 第{page_num}页表格{i}提取失败: {str(e)}")

                pages_data.append(page_data)

            logger.info(f"[结构化提取] 完成，共{len(pdf.pages)}页")

            return {
                "pages": pages_data,
                "total_pages": len(pdf.pages)
            }

    def _group_words_into_lines(self, words: List[Dict], page_num: int) -> List[TextBlock]:
        """将单词聚合成文本行"""
        if not words:
            return []

        lines = []
        current_line = []
        current_y = None
        y_tolerance = 3  # 垂直容差

        for word in words:
            word_y = (word['top'] + word['bottom']) / 2

            if current_y is None or abs(word_y - current_y) <= y_tolerance:
                # 同一行
                current_line.append(word)
                current_y = word_y
            else:
                # 新行
                if current_line:
                    lines.append(self._create_text_block_from_words(current_line, page_num))
                current_line = [word]
                current_y = word_y

        # 最后一行
        if current_line:
            lines.append(self._create_text_block_from_words(current_line, page_num))

        # 过滤噪声文本
        filtered_lines = self._filter_noise_from_blocks(lines)

        return filtered_lines

    def _create_text_block_from_words(self, words: List[Dict], page_num: int) -> TextBlock:
        """从单词列表创建TextBlock"""
        text = ' '.join([w['text'] for w in words])

        # 计算边界框
        x0 = min(w['x0'] for w in words)
        y0 = min(w['top'] for w in words)
        x1 = max(w['x1'] for w in words)
        y1 = max(w['bottom'] for w in words)

        # 获取字体大小（取平均值）
        font_size = sum(w.get('height', 12) for w in words) / len(words)

        return TextBlock(
            text=text,
            bbox=BoundingBox(x0, y0, x1, y1, page_num),
            font_size=font_size
        )

    def _is_noise_text(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        判断文本是否为噪声（无效信息）

        Args:
            text: 待检测的文本

        Returns:
            (是否为噪声, 噪声类型)
        """
        text_stripped = text.strip()

        # 空文本
        if not text_stripped or len(text_stripped) < 2:
            return True, 'empty'

        # 遍历所有噪声模式
        for pattern, noise_type in self.NOISE_PATTERNS:
            if re.search(pattern, text_stripped, re.IGNORECASE):
                return True, noise_type

        return False, None

    def _filter_noise_from_blocks(self, text_blocks: List[TextBlock]) -> List[TextBlock]:
        """
        从文本块列表中过滤掉噪声文本

        Args:
            text_blocks: 原始文本块列表

        Returns:
            过滤后的文本块列表
        """
        filtered_blocks = []

        for block in text_blocks:
            is_noise, noise_type = self._is_noise_text(block.text)

            if is_noise:
                # 统计噪声类型
                self.noise_stats["removed_count"] += 1
                if noise_type not in self.noise_stats["removed_types"]:
                    self.noise_stats["removed_types"][noise_type] = 0
                self.noise_stats["removed_types"][noise_type] += 1

                logger.debug(f"[噪声过滤] 移除 [{noise_type}]: {block.text[:50]}...")
            else:
                filtered_blocks.append(block)

        return filtered_blocks

    def _detect_question_numbers(self, structured_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        检测题号位置

        Returns:
            [
                {
                    "id": 1,
                    "text": "1. ",
                    "bbox": BoundingBox,
                    "confidence": 1.0,
                    "pattern_type": "standard"
                }
            ]
        """
        logger.info("[题号检测] 开始识别题号")

        markers = []

        for page_data in structured_data["pages"]:
            for text_block in page_data["text_blocks"]:
                text = text_block.text.strip()

                # 尝试所有题号模式
                for pattern, pattern_type, base_confidence in self.QUESTION_PATTERNS:
                    match = re.match(pattern, text)
                    if match:
                        question_id = match.group(1)

                        # 转换中文数字
                        if pattern_type == 'section_header':
                            question_id = self._chinese_to_arabic(question_id)

                        try:
                            question_id = int(question_id)
                        except ValueError:
                            continue

                        # 计算置信度（基于字体大小、位置等）
                        confidence = self._calculate_marker_confidence(
                            text_block, base_confidence, pattern_type
                        )

                        markers.append({
                            "id": question_id,
                            "text": match.group(0),
                            "bbox": text_block.bbox,
                            "confidence": confidence,
                            "pattern_type": pattern_type,
                            "full_line": text
                        })

                        logger.debug(f"[题号检测] 发现题号{question_id}，置信度{confidence:.2f}")
                        break  # 匹配到一个模式后跳出

        # 按页码和y坐标排序
        markers.sort(key=lambda m: (m["bbox"].page, m["bbox"].y0))

        # 过滤误检（题号不连续）
        markers = self._filter_invalid_markers(markers)

        logger.info(f"[题号检测] 完成，识别到{len(markers)}个题号")
        return markers

    def _calculate_marker_confidence(
        self,
        text_block: TextBlock,
        base_confidence: float,
        pattern_type: str
    ) -> float:
        """计算题号标记的置信度"""
        confidence = base_confidence

        # 字体大小：题号通常字体较大
        if text_block.font_size > 14:
            confidence += 0.05
        elif text_block.font_size < 10:
            confidence -= 0.1

        # 位置：题号通常在左侧
        if text_block.bbox.x0 < 100:  # 左边距小于100pt
            confidence += 0.05

        # 大题标题特殊处理
        if pattern_type == 'section_header':
            if '选择题' in text_block.text or '非选择题' in text_block.text:
                confidence = 0.95

        return min(1.0, max(0.0, confidence))

    def _filter_invalid_markers(self, markers: List[Dict]) -> List[Dict]:
        """过滤无效的题号标记（题号不连续等）"""
        if not markers:
            return []

        # 提取题号序列
        ids = [m["id"] for m in markers]

        # 检查连续性（允许跳号，但不能倒序）
        valid_markers = []
        prev_id = 0

        for marker in markers:
            if marker["id"] > prev_id:
                valid_markers.append(marker)
                prev_id = marker["id"]
            else:
                logger.warning(f"[题号过滤] 丢弃题号{marker['id']}（非递增）")

        return valid_markers

    def _segment_questions(
        self,
        markers: List[Dict],
        structured_data: Dict[str, Any]
    ) -> List[Question]:
        """
        根据题号标记划分题目边界

        策略：
        1. 每个题号标记是一道题的开始
        2. 题目内容从题号开始到下一个题号之前（或页面结束）
        3. 合并文本块构建完整题目内容
        """
        logger.info("[题目分割] 开始划分题目边界")

        questions = []

        for i, marker in enumerate(markers):
            # 确定题目结束位置
            if i < len(markers) - 1:
                next_marker = markers[i + 1]
                end_bbox = next_marker["bbox"]
            else:
                # 最后一题：到文档末尾
                last_page = structured_data["pages"][-1]
                last_block = last_page["text_blocks"][-1] if last_page["text_blocks"] else None
                end_bbox = last_block.bbox if last_block else marker["bbox"]

            # 收集该题目的所有文本块
            content_blocks = self._collect_content_blocks(
                marker["bbox"],
                end_bbox,
                structured_data
            )

            # 合并文本
            content = '\n'.join([block.text for block in content_blocks])

            # 计算题目边界框（合并所有文本块）
            question_bbox = self._merge_bboxes([block.bbox for block in content_blocks])

            # 创建Question对象
            question = Question(
                id=marker["id"],
                content=content,
                bbox=question_bbox,
                confidence=marker["confidence"],
                warnings=[],
                images=[],
                tables=[],
                has_options=False,
                cross_page=(question_bbox.page != end_bbox.page)
            )

            questions.append(question)
            logger.debug(f"[题目分割] 题目{marker['id']}划分完成，内容长度{len(content)}字符")

        logger.info(f"[题目分割] 完成，共{len(questions)}道题目")
        return questions

    def _collect_content_blocks(
        self,
        start_bbox: BoundingBox,
        end_bbox: BoundingBox,
        structured_data: Dict[str, Any]
    ) -> List[TextBlock]:
        """收集题目范围内的所有文本块"""
        blocks = []

        for page_data in structured_data["pages"]:
            page_num = page_data["page_num"]

            # 跳过不在范围内的页面
            if page_num < start_bbox.page or page_num > end_bbox.page:
                continue

            for text_block in page_data["text_blocks"]:
                # 判断是否在范围内
                if self._is_block_in_range(text_block.bbox, start_bbox, end_bbox):
                    blocks.append(text_block)

        return blocks

    def _is_block_in_range(
        self,
        block_bbox: BoundingBox,
        start_bbox: BoundingBox,
        end_bbox: BoundingBox
    ) -> bool:
        """判断文本块是否在题目范围内"""
        # 同一页
        if block_bbox.page == start_bbox.page == end_bbox.page:
            return start_bbox.y0 <= block_bbox.y0 < end_bbox.y0

        # 跨页情况
        if block_bbox.page == start_bbox.page:
            return block_bbox.y0 >= start_bbox.y0
        elif block_bbox.page == end_bbox.page:
            return block_bbox.y0 < end_bbox.y0
        elif start_bbox.page < block_bbox.page < end_bbox.page:
            return True

        return False

    def _merge_bboxes(self, bboxes: List[BoundingBox]) -> BoundingBox:
        """合并多个边界框"""
        if not bboxes:
            return BoundingBox(0, 0, 0, 0, 1)

        min_x0 = min(b.x0 for b in bboxes)
        min_y0 = min(b.y0 for b in bboxes)
        max_x1 = max(b.x1 for b in bboxes)
        max_y1 = max(b.y1 for b in bboxes)
        page = bboxes[0].page  # 使用第一个块的页码

        return BoundingBox(min_x0, min_y0, max_x1, max_y1, page)

    def _match_media_to_questions(
        self,
        questions: List[Question],
        structured_data: Dict[str, Any]
    ) -> None:
        """匹配图片和表格到题目（基于坐标IoU + 位置关系）"""
        logger.info("[媒体匹配] 开始匹配图片和表格")

        for page_data in structured_data["pages"]:
            # 匹配图片
            for img in page_data["images"]:
                best_match = None
                best_score = 0.0
                match_method = ""

                for question in questions:
                    # 方法1：IoU匹配（图片在题目范围内）
                    iou = question.bbox.iou(img["bbox"])

                    # 方法2：垂直距离匹配（图片在题目下方）
                    # 检查图片是否在题目下方且水平对齐
                    if question.bbox.page == img["bbox"].page:
                        # 图片在题目下方
                        if img["bbox"].y0 >= question.bbox.y0:
                            vertical_distance = img["bbox"].y0 - question.bbox.y1
                            # 水平重叠度
                            x_overlap = min(question.bbox.x1, img["bbox"].x1) - max(question.bbox.x0, img["bbox"].x0)
                            x_overlap_ratio = x_overlap / (img["bbox"].x1 - img["bbox"].x0) if x_overlap > 0 else 0

                            # 如果题目包含"如图所示"等关键词，且图片在附近
                            if any(kw in question.content for kw in ["如图所示", "如图", "下图", "见图"]):
                                if vertical_distance < 200 and x_overlap_ratio > 0.3:  # 图片在下方200pt内且有30%水平重叠
                                    proximity_score = 1.0 - (vertical_distance / 200) * (1.0 - x_overlap_ratio)
                                    if proximity_score > best_score:
                                        best_score = proximity_score
                                        best_match = question
                                        match_method = "proximity"

                    # 如果IoU更高，优先使用IoU
                    if iou > best_score:
                        best_score = iou
                        best_match = question
                        match_method = "iou"

                if best_match and best_score > 0.1:  # 阈值
                    best_match.images.append(img)
                    logger.debug(f"[媒体匹配] 图片匹配到题目{best_match.id}，方法={match_method}，得分={best_score:.2f}")

            # 匹配表格（保持原有IoU逻辑）
            for table in page_data["tables"]:
                best_match = None
                best_iou = 0.0

                for question in questions:
                    iou = question.bbox.iou(table["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_match = question

                if best_match and best_iou > 0.1:
                    best_match.tables.append(table)
                    logger.debug(f"[媒体匹配] 表格匹配到题目{best_match.id}，IoU={best_iou:.2f}")

        logger.info("[媒体匹配] 完成")

    def _detect_options(self, questions: List[Question]) -> None:
        """检测题目是否包含选项（选择题）"""
        for question in questions:
            # 检查是否包含A、B、C、D选项
            options_found = re.findall(self.OPTION_PATTERN, question.content)
            question.has_options = len(options_found) >= 2  # 至少2个选项

            if question.has_options:
                logger.debug(f"[选项检测] 题目{question.id}包含{len(options_found)}个选项")

                # 验证选项完整性
                if len(options_found) < 4:
                    question.warnings.append(f"选项不完整（只有{len(options_found)}个）")
                    question.confidence *= 0.9

    def _detect_cross_page_questions(
        self,
        questions: List[Question],
        structured_data: Dict[str, Any]
    ) -> None:
        """检测跨页题目"""
        for question in questions:
            # 方法1：检查关键词
            for keyword in self.CROSS_PAGE_KEYWORDS:
                if keyword in question.content:
                    question.cross_page = True
                    question.warnings.append(f"检测到跨页关键词: {keyword}")
                    logger.debug(f"[跨页检测] 题目{question.id}可能跨页（关键词）")
                    break

            # 方法2：检查选项是否在下一页
            if question.has_options and not question.cross_page:
                # 检查题干是否缺少选项
                options_in_content = re.findall(self.OPTION_PATTERN, question.content)
                if len(options_in_content) < 4:
                    question.cross_page = True
                    question.warnings.append("选项可能在下一页")
                    logger.debug(f"[跨页检测] 题目{question.id}选项不完整，可能跨页")

    def _calculate_overall_confidence(self, questions: List[Question]) -> float:
        """计算整体置信度"""
        if not questions:
            return 0.0

        return sum(q.confidence for q in questions) / len(questions)

    def _generate_warnings(self, questions: List[Question]) -> List[str]:
        """生成整体警告信息"""
        warnings = []

        # 统计低置信度题目
        low_confidence_count = sum(1 for q in questions if q.confidence < 0.7)
        if low_confidence_count > 0:
            warnings.append(f"{low_confidence_count}道题目置信度较低（<0.7），建议人工检查")

        # 统计跨页题目
        cross_page_count = sum(1 for q in questions if q.cross_page)
        if cross_page_count > 0:
            warnings.append(f"{cross_page_count}道题目可能跨页，请仔细检查")

        return warnings

    def _detect_media_position(self, question_content: str, media_bbox: BoundingBox, question_bbox: BoundingBox) -> str:
        """
        检测图表在题目中的插入位置

        Args:
            question_content: 题目文本内容
            media_bbox: 图表边界框
            question_bbox: 题目边界框

        Returns:
            position: "top" | "inline" | "bottom"
        """
        # 检测是否有明确的图表引用关键词
        image_keywords = ["如图", "下图", "见图", "图示", "如图所示"]
        table_keywords = ["如表", "下表", "见表", "表中", "如表所示"]

        has_image_ref = any(kw in question_content for kw in image_keywords)
        has_table_ref = any(kw in question_content for kw in table_keywords)

        # 如果有明确引用，通常是inline位置
        if has_image_ref or has_table_ref:
            return "inline"

        # 根据y坐标判断位置
        question_mid_y = (question_bbox.y0 + question_bbox.y1) / 2

        if media_bbox.y0 < question_mid_y:
            return "top"
        else:
            return "bottom"

    def _question_to_dict(self, question: Question) -> Dict[str, Any]:
        """将Question对象转换为字典（方案C：智能文本与媒体分离）"""
        # 构建media数组，合并图片和表格
        media_list = []

        # 处理图片
        for i, img in enumerate(question.images):
            if "data" in img and img["data"]:
                position = self._detect_media_position(
                    question.content,
                    img["bbox"],
                    question.bbox
                )
                media_list.append({
                    "type": "image",
                    "position": position,
                    "image_base64": f"data:image/png;base64,{img['data']}",
                    "width": img["width"],
                    "height": img["height"],
                    "bbox": {
                        "x0": img["bbox"].x0,
                        "y0": img["bbox"].y0,
                        "x1": img["bbox"].x1,
                        "y1": img["bbox"].y1,
                        "page": img["bbox"].page
                    }
                })

        # 处理表格
        for i, table in enumerate(question.tables):
            if "image_data" in table and table["image_data"]:
                position = self._detect_media_position(
                    question.content,
                    table["bbox"],
                    question.bbox
                )
                media_list.append({
                    "type": "table",
                    "position": position,
                    "image_base64": f"data:image/png;base64,{table['image_data']}",
                    "bbox": {
                        "x0": table["bbox"].x0,
                        "y0": table["bbox"].y0,
                        "x1": table["bbox"].x1,
                        "y1": table["bbox"].y1,
                        "page": table["bbox"].page
                    }
                })

        return {
            "id": question.id,
            "content": question.content,  # 纯文本内容
            "bbox": {
                "x0": question.bbox.x0,
                "y0": question.bbox.y0,
                "x1": question.bbox.x1,
                "y1": question.bbox.y1,
                "page": question.bbox.page
            },
            "confidence": question.confidence,
            "warnings": question.warnings,
            "media": media_list,  # 新的media字段，包含所有图表
            "has_options": question.has_options,
            "cross_page": question.cross_page
        }

    @staticmethod
    def _chinese_to_arabic(chinese_num: str) -> int:
        """中文数字转阿拉伯数字"""
        chinese_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }

        if chinese_num in chinese_map:
            return chinese_map[chinese_num]

        # 处理"十一"、"十二"等
        if chinese_num.startswith('十'):
            if len(chinese_num) == 1:
                return 10
            else:
                return 10 + chinese_map.get(chinese_num[1], 0)

        return 1  # 默认值

    @staticmethod
    def _table_to_markdown(table: List[List[str]]) -> str:
        """将表格转换为Markdown格式"""
        if not table or len(table) == 0:
            return ""

        markdown_lines = []

        # 表头
        header = table[0]
        header_cells = [str(cell).strip() if cell else "" for cell in header]
        markdown_lines.append("| " + " | ".join(header_cells) + " |")

        # 分隔线
        markdown_lines.append("|" + "|".join(["---" for _ in header_cells]) + "|")

        # 数据行
        for row in table[1:]:
            row_cells = [str(cell).strip().replace("\n", " ") if cell else "" for cell in row]
            while len(row_cells) < len(header_cells):
                row_cells.append("")
            markdown_lines.append("| " + " | ".join(row_cells[:len(header_cells)]) + " |")

        return "\n".join(markdown_lines)
