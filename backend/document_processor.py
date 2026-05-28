try:
    from pdf2image import convert_from_path
except ImportError as exc:
    def convert_from_path(*args, **kwargs):
        raise RuntimeError("pdf2image dependency missing") from exc
try:
    import pdfplumber
except ImportError as exc:
    class _MissingPdfPlumber:
        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("pdfplumber dependency missing") from exc
    pdfplumber = _MissingPdfPlumber()
try:
    from docx import Document
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import _Cell, Table
    from docx.text.paragraph import Paragraph
except ImportError as exc:
    def Document(*args, **kwargs):
        raise RuntimeError("python-docx dependency missing") from exc
    CT_Tbl = CT_P = _Cell = Table = Paragraph = object
from PIL import Image
import io
import os
import re
import subprocess
import tempfile
import base64
from typing import List, Dict, Any
from logger import get_logger

logger = get_logger()

class DocumentProcessor:
    """文档处理器：将PDF/Word转换为图片"""

    @staticmethod
    def extract_word_content(file_path: str) -> Dict[str, Any]:
        """
        高精度提取Word文档内容（文字+表格+图片）
        保持原始文档的元素顺序

        Args:
            file_path: Word文件路径

        Returns:
            {
                "text": "完整文本（包含Markdown表格）",
                "images": [{"index": 0, "data": bytes, "position": 1}],  # 图片数据和位置
                "elements": [  # 文档元素顺序
                    {"type": "paragraph", "content": "..."},
                    {"type": "table", "markdown": "..."},
                    {"type": "image", "index": 0}
                ]
            }
        """
        logger.info(f"开始高精度提取Word内容: {file_path}")

        try:
            doc = Document(file_path)
            extracted_images = []
            content_parts = []
            elements = []
            image_counter = 0
            failure_events = []

            # 遍历文档的所有块级元素（保持顺序）
            for block in doc.element.body:
                # 处理段落
                if isinstance(block, CT_P):
                    paragraph = Paragraph(block, doc)
                    para_text = paragraph.text.strip()

                    # 检查段落中是否有图片
                    if paragraph.runs:
                        for run in paragraph.runs:
                            logger.debug(f"检查run: {run.text[:20] if run.text else '(空)'}")

                            # 方法1：提取内联图片（inline shapes）- 检查drawing元素
                            drawing_elements = run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing')
                            if drawing_elements:
                                logger.debug(f"  ✓ Run包含{len(drawing_elements)}个drawing元素")
                                for drawing in drawing_elements:
                                    blips = drawing.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
                                    for blip in blips:
                                        embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                                        if embed:
                                            try:
                                                image_part = doc.part.related_parts[embed]
                                                image_bytes = image_part.blob
                                                # 转换为base64
                                                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                                                extracted_images.append({
                                                    "index": image_counter,
                                                    "data": image_bytes,
                                                    "base64": image_base64,
                                                    "position": len(elements)
                                                })
                                                elements.append({
                                                    "type": "image",
                                                    "index": image_counter,
                                                    "base64": image_base64,
                                                    "caption": para_text if para_text else f"图片{image_counter + 1}"
                                                })
                                                logger.debug(f"提取到内联图片 #{image_counter}, 大小: {len(image_bytes) / 1024:.2f}KB")
                                                image_counter += 1
                                            except Exception as e:
                                                logger.warning(f"提取内联图片失败: {e}")
                                                failure_events.append({
                                                    "stage": "document_media_extraction",
                                                    "severity": "blocked",
                                                    "file_type": "docx",
                                                    "media_type": "inline_image",
                                                    "reason": str(e),
                                                })

                    # 添加段落文字。即使段落中同时含图，也要保留文本边界。
                    if para_text:
                        content_parts.append(para_text)
                        elements.append({
                            "type": "paragraph",
                            "content": para_text
                        })

                # 处理表格
                elif isinstance(block, CT_Tbl):
                    table = Table(block, doc)
                    table_markdown = DocumentProcessor._table_to_markdown(table)
                    table_html = DocumentProcessor._markdown_table_to_html(table_markdown)
                    content_parts.append(table_markdown)
                    elements.append({
                        "type": "table",
                        "markdown": table_markdown,
                        "html": table_html,
                        "rows": len(table.rows),
                        "cols": len(table.columns)
                    })
                    logger.debug(f"提取表格: {len(table.rows)}行 x {len(table.columns)}列")

            # 提取浮动图片（shapes）
            if hasattr(doc, 'inline_shapes'):
                for shape in doc.inline_shapes:
                    try:
                        if hasattr(shape, '_inline') and hasattr(shape._inline, 'graphic'):
                            # 这部分已在段落中处理
                            pass
                    except Exception as e:
                        logger.warning(f"处理浮动图片失败: {e}")
                        failure_events.append({
                            "stage": "document_media_extraction",
                            "severity": "blocked",
                            "file_type": "docx",
                            "media_type": "floating_image",
                            "reason": str(e),
                        })

            complete_text = "\n\n".join(content_parts)
            logger.info(f"Word内容提取完成: {len(complete_text)} 字符, {len(extracted_images)} 张图片, {len(elements)} 个元素")

            return {
                "text": complete_text,
                "images": extracted_images,
                "elements": elements,
                "failure_events": failure_events,
            }

        except Exception as e:
            logger.error(f"Word内容提取失败: {str(e)}", exc_info=True)
            return {
                "text": "",
                "images": [],
                "elements": [],
                "failure_events": [{
                    "stage": "document_extraction",
                    "severity": "blocked",
                    "file_type": "docx",
                    "reason": str(e),
                }],
            }

    @staticmethod
    def extract_pdf_content(file_path: str) -> Dict[str, Any]:
        """
        高精度提取PDF文档内容（文字+表格+图片）
        保持原始文档的元素顺序

        Args:
            file_path: PDF文件路径

        Returns:
            {
                "text": "完整文本（包含Markdown表格）",
                "images": [{"index": 0, "data": bytes, "base64": "..."}],
                "elements": [  # 保持文档元素顺序
                    {"type": "paragraph", "content": "..."},
                    {"type": "table", "markdown": "...", "html": "..."},
                    {"type": "image", "index": 0, "base64": "..."}
                ]
            }
        """
        logger.info(f"开始高精度提取PDF内容: {file_path}")

        try:
            extracted_images = []
            content_parts = []
            elements = []
            image_counter = 0
            failure_events = []

            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    logger.debug(f"处理第 {page_num + 1}/{len(pdf.pages)} 页")

                    # 提取文字（按段落）
                    page_text = page.extract_text()
                    if page_text:
                        # 将页面文字按段落分割
                        paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            if para:
                                content_parts.append(para)
                                elements.append({
                                    "type": "paragraph",
                                    "content": para
                                })

                    # 提取表格
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            if table and len(table) > 0:
                                # 将表格转换为Markdown格式
                                table_markdown = DocumentProcessor._pdf_table_to_markdown(table)
                                table_html = DocumentProcessor._markdown_table_to_html(table_markdown)

                                content_parts.append(table_markdown)
                                elements.append({
                                    "type": "table",
                                    "markdown": table_markdown,
                                    "html": table_html,
                                    "rows": len(table),
                                    "cols": len(table[0]) if table else 0
                                })
                                logger.debug(f"提取到表格: {len(table)}行 × {len(table[0]) if table else 0}列")

                    # 提取图片
                    if hasattr(page, 'images'):
                        for img_info in page.images:
                            try:
                                # 获取图片对象
                                x0, y0, x1, y1 = img_info['x0'], img_info['y0'], img_info['x1'], img_info['y1']

                                # 使用page对象的within_bbox方法提取图片区域
                                img_bbox = (x0, y0, x1, y1)
                                cropped = page.within_bbox(img_bbox)

                                # 转换为PIL Image
                                img_obj = cropped.to_image(resolution=150)
                                img_pil = img_obj.original

                                # 转换为bytes
                                img_buffer = io.BytesIO()
                                img_pil.save(img_buffer, format='PNG')
                                image_bytes = img_buffer.getvalue()
                                image_base64 = base64.b64encode(image_bytes).decode('utf-8')

                                extracted_images.append({
                                    "index": image_counter,
                                    "data": image_bytes,
                                    "base64": image_base64,
                                    "position": len(elements)
                                })

                                elements.append({
                                    "type": "image",
                                    "index": image_counter,
                                    "base64": image_base64,
                                    "caption": f"图片{image_counter + 1}"
                                })

                                image_counter += 1
                                logger.debug(f"提取到图片 {image_counter}")

                            except Exception as img_error:
                                logger.warning(f"提取图片失败: {img_error}")
                                failure_events.append({
                                    "stage": "document_media_extraction",
                                    "severity": "blocked",
                                    "file_type": "pdf",
                                    "media_type": "embedded_image",
                                    "page": page_num + 1,
                                    "reason": str(img_error),
                                })

            complete_text = "\n\n".join(content_parts)
            logger.info(f"PDF内容提取完成: {len(complete_text)} 字符, {len(extracted_images)} 张图片, {len(elements)} 个元素")

            return {
                "text": complete_text,
                "images": extracted_images,
                "elements": elements,
                "failure_events": failure_events,
            }

        except Exception as e:
            logger.error(f"PDF内容提取失败: {str(e)}", exc_info=True)
            return {
                "text": "",
                "images": [],
                "elements": [],
                "failure_events": [{
                    "stage": "document_extraction",
                    "severity": "blocked",
                    "file_type": "pdf",
                    "reason": str(e),
                }],
            }

    @staticmethod
    def _pdf_table_to_markdown(table: List[List[str]]) -> str:
        """
        将PDF表格（二维列表）转换为Markdown格式

        Args:
            table: PDF提取的表格数据（二维列表）

        Returns:
            Markdown格式的表格字符串
        """
        if not table or len(table) == 0:
            return ""

        markdown_lines = []

        # 表头（第一行）
        header = table[0]
        header_cells = [str(cell).strip() if cell else "" for cell in header]
        markdown_lines.append("| " + " | ".join(header_cells) + " |")

        # 分隔线
        markdown_lines.append("|" + "|".join(["---" for _ in header_cells]) + "|")

        # 数据行
        for row in table[1:]:
            row_cells = [str(cell).strip().replace("\n", " ") if cell else "" for cell in row]
            # 确保行的列数与表头一致
            while len(row_cells) < len(header_cells):
                row_cells.append("")
            markdown_lines.append("| " + " | ".join(row_cells[:len(header_cells)]) + " |")

        return "\n".join(markdown_lines)

    @staticmethod
    def _markdown_table_to_html(markdown_table: str) -> str:
        """
        将Markdown表格转换为HTML表格

        Args:
            markdown_table: Markdown格式的表格字符串

        Returns:
            HTML格式的表格字符串
        """
        if not markdown_table.strip():
            return ""

        lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]

        if len(lines) < 3:  # 至少需要表头、分隔线、一行数据
            return markdown_table  # 不是有效的Markdown表格，返回原始内容

        html_parts = ['<table class="word-table">']

        # 表头
        header_line = lines[0]
        header_cells = [cell.strip() for cell in header_line.split('|')[1:-1]]  # 去掉首尾空白单元格
        html_parts.append('<thead><tr>')
        for cell in header_cells:
            html_parts.append(f'<th>{cell}</th>')
        html_parts.append('</tr></thead>')

        # 表体（跳过分隔线）
        html_parts.append('<tbody>')
        for line in lines[2:]:
            row_cells = [cell.strip() for cell in line.split('|')[1:-1]]
            html_parts.append('<tr>')
            for cell in row_cells:
                html_parts.append(f'<td>{cell}</td>')
            html_parts.append('</tr>')
        html_parts.append('</tbody>')

        html_parts.append('</table>')
        return ''.join(html_parts)

    @staticmethod
    def _table_to_markdown(table: Table) -> str:
        """
        将Word表格转换为Markdown格式
        精确保留所有单元格内容

        Args:
            table: python-docx Table对象

        Returns:
            Markdown格式的表格字符串
        """
        if not table.rows:
            return ""

        markdown_lines = []

        # 表头
        header_cells = [cell.text.strip() for cell in table.rows[0].cells]
        markdown_lines.append("| " + " | ".join(header_cells) + " |")

        # 分隔线
        markdown_lines.append("|" + "|".join(["---" for _ in header_cells]) + "|")

        # 数据行
        for row in table.rows[1:]:
            row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            markdown_lines.append("| " + " | ".join(row_cells) + " |")

        return "\n".join(markdown_lines)

    @staticmethod
    def process_pdf(file_path: str, dpi: int = 300) -> List[Image.Image]:
        """
        处理PDF文件：高精度混合策略
        1. 用 pdfplumber 提取文字、表格和图片
        2. 用 pdf2image 转换为图片（用于布局参考）
        3. 合并提取的内容和图片

        Args:
            file_path: PDF文件路径
            dpi: 图片分辨率，默认300

        Returns:
            PIL Image对象列表（第一张图片包含提取的文字和元素信息）
        """
        logger.info(f"开始处理PDF: {file_path}，DPI: {dpi}")

        try:
            # 1. 高精度提取PDF内容（文字+表格+图片）
            pdf_content = DocumentProcessor.extract_pdf_content(file_path)
            extracted_text = pdf_content.get("text", "")
            extracted_images = pdf_content.get("images", [])
            elements = pdf_content.get("elements", [])
            failure_events = pdf_content.get("failure_events", [])

            logger.info(f"PDF内容提取: {len(extracted_text)} 字符, {len(extracted_images)} 张图片, {len(elements)} 个元素")

            # 2. 转换PDF为图片（用于布局参考和视觉识别）
            layout_images = convert_from_path(
                file_path,
                dpi=dpi,
                fmt='jpeg'
            )
            logger.info(f"PDF转换完成，共{len(layout_images)}页")

            # 3. 将提取的文字和元素信息附加到图片对象
            if layout_images:
                # 将提取的文字存储到第一张图片的 info 属性
                layout_images[0].info['extracted_text'] = extracted_text
                layout_images[0].info['elements'] = elements
                layout_images[0].info['failure_events'] = failure_events

                # 如果提取到了嵌入图片，也存储起来（供后续使用）
                if extracted_images:
                    layout_images[0].info['extracted_images'] = extracted_images
                    logger.info(f"PDF中提取到 {len(extracted_images)} 张嵌入图片")

            return layout_images

        except Exception as e:
            logger.error(f"PDF处理失败: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def process_docx(file_path: str) -> List[Image.Image]:
        """
        处理Word文档：高精度混合策略
        1. 用 python-docx 提取文字、表格和嵌入图片
        2. 用 LibreOffice 转 PDF 获取布局参考图
        3. 合并提取的内容和图片

        Args:
            file_path: Word文件路径

        Returns:
            PIL Image对象列表（第一张图片包含提取的文字信息）
        """
        logger.info(f"开始处理Word文档: {file_path}")

        # 方案1：高精度提取Word内容
        word_content = DocumentProcessor.extract_word_content(file_path)
        extracted_text = word_content.get("text", "")
        extracted_images = word_content.get("images", [])
        elements = word_content.get("elements", [])
        failure_events = word_content.get("failure_events", [])

        if extracted_text:
            logger.info(f"成功提取Word内容，共 {len(extracted_text)} 字符")
        if extracted_images:
            logger.info(f"成功提取 {len(extracted_images)} 张嵌入图片")

        # 方案2：LibreOffice 转 PDF 再转图片（保留布局）
        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = None

        try:
            # 1. 使用LibreOffice将Word转换为PDF
            logger.debug(f"调用LibreOffice转换Word → PDF")
            result = subprocess.run(
                [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', temp_dir,
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.error(f"LibreOffice转换失败: {result.stderr}")
                raise RuntimeError(f"Word转PDF失败: {result.stderr}")

            # 2. 找到生成的PDF文件
            original_filename = os.path.splitext(os.path.basename(file_path))[0]
            temp_pdf_path = os.path.join(temp_dir, f"{original_filename}.pdf")

            if not os.path.exists(temp_pdf_path):
                raise FileNotFoundError(f"转换后的PDF未找到: {temp_pdf_path}")

            logger.info(f"Word → PDF转换完成: {temp_pdf_path}")

            # 3. 将PDF转换为图片（用于布局参考）
            layout_images = DocumentProcessor.process_pdf(temp_pdf_path, dpi=300)

            # 4. 将提取的文字和元素信息附加到图片对象
            if layout_images:
                # 将提取的文字存储到第一张图片的 info 属性
                layout_images[0].info['extracted_text'] = extracted_text
                existing_failure_events = layout_images[0].info.get('failure_events', [])
                layout_images[0].info['elements'] = elements
                layout_images[0].info['failure_events'] = list(existing_failure_events or []) + list(failure_events or [])

                # 如果提取到了嵌入图片，也存储起来（供后续使用）
                if extracted_images:
                    layout_images[0].info['extracted_images'] = extracted_images
                    logger.debug(f"已附加 {len(extracted_images)} 张提取图片的元数据")

            logger.info(f"Word文档处理完成，共{len(layout_images)}页布局图")
            return layout_images

        except subprocess.TimeoutExpired:
            logger.error("LibreOffice转换超时（60秒）")
            raise RuntimeError("Word文档转换超时，请检查文件大小")
        except Exception as e:
            logger.error(f"Word文档处理失败: {str(e)}", exc_info=True)
            raise
        finally:
            # 清理临时文件
            try:
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
                os.rmdir(temp_dir)
                logger.debug(f"临时文件已清理: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")

    @staticmethod
    def images_to_bytes(images: List[Image.Image]) -> List[bytes]:
        """
        将PIL Image转换为字节流（用于视觉分析 API）

        Args:
            images: PIL Image列表

        Returns:
            图片字节流列表
        """
        logger.debug(f"开始转换{len(images)}张图片为字节流")
        result = []
        for idx, img in enumerate(images):
            buffer = io.BytesIO()
            # 压缩以减少内存占用（质量85平衡清晰度和大小）
            img.save(buffer, format='JPEG', quality=85, optimize=True)
            img_bytes = buffer.getvalue()
            result.append(img_bytes)

            # 验证JPEG格式
            if img_bytes[:2] == b'\xff\xd8':
                logger.debug(f"图片{idx+1}转换完成，大小: {len(img_bytes) / 1024:.2f}KB，格式: JPEG ✓")
            else:
                logger.error(f"图片{idx+1}格式异常！前10字节: {img_bytes[:10].hex()}")
        return result

    @staticmethod
    def match_elements_to_questions(questions: List[Dict[str, Any]], elements: List[Dict[str, Any]]) -> None:
        """
        智能匹配：将提取的元素（表格、图片）分配给对应的题目

        策略：
        1. 在元素流中识别每道题的起止边界
        2. 只把边界内的表格、图片绑定到该题
        3. 发现题干提示图表但边界内缺失时显式标记 warning

        Args:
            questions: 题目列表
            elements: 提取的元素列表（paragraph, table, image）
        """
        if not elements or not questions:
            logger.debug("[智能匹配] 无元素或题目，跳过匹配")
            return

        logger.info(f"[智能匹配] 开始为 {len(questions)} 道题目匹配 {len(elements)} 个元素")

        def element_text(element: Dict[str, Any]) -> str:
            return str(
                element.get("content")
                or element.get("caption")
                or element.get("text")
                or ""
            ).strip()

        def starts_question(text: str, q_id: Any) -> bool:
            if not isinstance(q_id, int):
                return False
            return bool(re.match(rf"^\s*{q_id}[.、．]\s*", text))

        start_by_id: Dict[int, int] = {}
        for idx, element in enumerate(elements):
            text = element_text(element)
            if not text:
                continue
            for question in questions:
                q_id = question.get("id")
                if q_id in start_by_id:
                    continue
                if starts_question(text, q_id):
                    start_by_id[q_id] = idx
                    break

        ordered_starts = sorted(
            (idx, q_id) for q_id, idx in start_by_id.items()
        )
        next_start_by_id: Dict[int, int] = {}
        for pos, (start_idx, q_id) in enumerate(ordered_starts):
            next_start_by_id[q_id] = (
                ordered_starts[pos + 1][0]
                if pos + 1 < len(ordered_starts)
                else len(elements)
            )

        table_cue = re.compile(r"(如下表|下表|结果如下表|表中|表格|表\s*\d+|table)", re.IGNORECASE)
        image_cue = re.compile(r"(如下图|下图|如图|图中|图\s*\d+|曲线|电泳|figure|fig)", re.IGNORECASE)

        unmatched_media = 0
        for question in questions:
            q_id = question.get("id")
            question["structured_content"] = []
            if q_id not in start_by_id:
                question.setdefault("warnings", []).append("media_boundary_missing")
                logger.warning(f"[智能匹配] 题目{q_id} 未找到元素边界，跳过媒体绑定")
                continue

            start_idx = start_by_id[q_id]
            end_idx = next_start_by_id[q_id]
            media = [
                element for element in elements[start_idx:end_idx]
                if element.get("type") in ("table", "image")
            ]
            question["structured_content"] = media

            table_count = sum(1 for e in media if e.get("type") == "table")
            image_count = sum(1 for e in media if e.get("type") == "image")
            q_content = str(question.get("content") or "")
            expected_table = bool(table_cue.search(q_content))
            expected_image = bool(image_cue.search(q_content))
            integrity_warnings = []
            if expected_table and table_count == 0:
                integrity_warnings.append("table_media_missing")
            if expected_image and image_count == 0:
                integrity_warnings.append("image_media_missing")

            question["media_integrity"] = {
                "status": "ok" if not integrity_warnings else "failed",
                "expected_table": expected_table,
                "expected_image": expected_image,
                "actual_tables": table_count,
                "actual_images": image_count,
                "warnings": integrity_warnings,
            }
            if integrity_warnings:
                question.setdefault("warnings", []).extend(
                    warning for warning in integrity_warnings
                    if warning not in question.get("warnings", [])
                )

            if media:
                logger.info(f"✅ 题目 {q_id} 边界匹配完成：{table_count}个表格，{image_count}张图片")
            else:
                logger.debug(f"题目 {q_id} 边界内无附加媒体")

        assigned_ranges = [
            (start_by_id[q.get("id")], next_start_by_id[q.get("id")])
            for q in questions if q.get("id") in start_by_id
        ]
        for idx, element in enumerate(elements):
            if element.get("type") not in ("table", "image"):
                continue
            if not any(start <= idx < end for start, end in assigned_ranges):
                unmatched_media += 1

        if unmatched_media:
            logger.warning(f"[智能匹配] {unmatched_media} 个媒体元素不在任何题目边界内，已保留未分配状态")
