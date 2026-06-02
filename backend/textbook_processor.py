"""
教材智能处理服务
使用 AI 分析教材内容，提取知识点结构
"""
import os
import json
import base64
import asyncio
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
from pathlib import Path
from io import BytesIO
import httpx

from config import UPLOAD_DIR
from logger import get_logger

logger = get_logger()

# 视觉模型 API 配置
QWEN_API_KEY = os.environ.get("QWEN_API_KEY_2", os.environ.get("QWEN_API_KEY", ""))
QWEN_API_BASE = os.environ.get("QWEN_API_BASE", "")


class TextbookProcessor:
    """教材智能处理器"""

    def __init__(self):
        self.api_key = QWEN_API_KEY
        self.api_base = QWEN_API_BASE
        self.model = "qwen-vl-max"  # 使用Flash模型，成本更低
        self.client = httpx.AsyncClient(timeout=120.0)

    async def close(self):
        await self.client.aclose()

    async def process_pdf(
        self,
        pdf_path: str,
        start_page: int = 1,
        end_page: int = None,
        save_results: bool = True
    ) -> Dict[str, Any]:
        """
        处理PDF教材

        Args:
            pdf_path: PDF文件路径
            start_page: 起始页码 (1-based)
            end_page: 结束页码 (1-based, None表示到最后)
            save_results: 是否保存处理结果

        Returns:
            处理结果字典
        """
        logger.info(f"[教材处理] 开始处理: {pdf_path}, 页码范围: {start_page}-{end_page}")

        doc = fitz.open(pdf_path)
        total_pages = doc.page_count

        if end_page is None or end_page > total_pages:
            end_page = total_pages

        results = {
            "file": os.path.basename(pdf_path),
            "total_pages": total_pages,
            "processed_range": f"{start_page}-{end_page}",
            "pages": [],
            "knowledge_points": [],
            "chapters_detected": [],
        }

        # 逐页处理
        for page_num in range(start_page - 1, end_page):  # 0-based
            logger.info(f"[教材处理] 处理第 {page_num + 1}/{end_page} 页...")

            try:
                page_result = await self._process_page(doc, page_num)
                results["pages"].append(page_result)

                # 汇总知识点
                if page_result.get("knowledge_points"):
                    for kp in page_result["knowledge_points"]:
                        kp["page"] = page_num + 1
                        results["knowledge_points"].append(kp)

                # 汇总章节信息
                if page_result.get("chapter_info"):
                    ch_info = page_result["chapter_info"]
                    ch_info["page"] = page_num + 1
                    if ch_info not in results["chapters_detected"]:
                        results["chapters_detected"].append(ch_info)

                # 避免API限流
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[教材处理] 第{page_num + 1}页处理失败: {e}")
                results["pages"].append({
                    "page": page_num + 1,
                    "error": str(e)
                })

        doc.close()

        # 保存结果
        if save_results:
            result_path = UPLOAD_DIR / f"{Path(pdf_path).stem}_analysis.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"[教材处理] 结果已保存: {result_path}")

        logger.info(f"[教材处理] 完成! 共提取 {len(results['knowledge_points'])} 个知识点")
        return results

    async def _process_page(self, doc: fitz.Document, page_num: int) -> Dict[str, Any]:
        """处理单页 - 提取原文、图片，并用AI打标签"""
        page = doc[page_num]

        # 1. 提取完整原文文本
        text = page.get_text("text")

        # 2. 提取页面中的独立图片
        images_info = []
        image_list = page.get_images(full=True)
        for img_idx, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    # 保存图片到文件
                    img_filename = f"page_{page_num + 1}_img_{img_idx + 1}.{image_ext}"
                    img_path = UPLOAD_DIR / "images" / img_filename
                    img_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(img_path, "wb") as f:
                        f.write(image_bytes)
                    images_info.append({
                        "filename": img_filename,
                        "path": str(img_path),
                        "size": len(image_bytes),
                        "ext": image_ext
                    })
            except Exception as e:
                logger.warning(f"[教材处理] 第{page_num + 1}页图片{img_idx + 1}提取失败: {e}")

        # 3. 将整页渲染为缩略图（用于AI分析）
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        # 4. 保存整页截图
        page_img_filename = f"page_{page_num + 1}_full.png"
        page_img_path = UPLOAD_DIR / "images" / page_img_filename
        page_img_path.parent.mkdir(parents=True, exist_ok=True)
        with open(page_img_path, "wb") as f:
            f.write(img_bytes)

        # 5. 调用AI分析获取标签信息
        analysis = await self._analyze_page_with_vision(text, img_base64, page_num + 1)

        return {
            "page": page_num + 1,
            "text": text,  # 保存完整原文
            "text_length": len(text),
            "page_image": page_img_filename,  # 整页截图
            "images": images_info,  # 提取的独立图片列表
            "has_images": len(image_list) > 0,
            **analysis  # AI分析的标签信息
        }

    async def _analyze_page_with_vision(
        self,
        text: str,
        image_base64: str,
        page_num: int
    ) -> Dict[str, Any]:
        """使用AI分析页面内容"""

        # 提供教材的章节结构参考
        textbook_structure = """
这是人教版高中生物学必修1《分子与细胞》的章节结构：
- 前言部分（约1-9页）：封面、版权页、目录、科学家访谈等
- 第1章 走近细胞（约第10页开始）
  - 第1节 细胞是生命活动的基本单位
  - 第2节 细胞的多样性和统一性
- 第2章 组成细胞的分子
  - 第1节 细胞中的元素和化合物
  - 第2节 细胞中的无机物
  - 第3节 细胞中的糖类和脂质
  - 第4节 蛋白质是生命活动的主要承担者
  - 第5节 核酸是遗传信息的携带者
- 第3章 细胞的基本结构
  - 第1节 细胞膜的结构和功能
  - 第2节 细胞器之间的分工合作
  - 第3节 细胞核的结构和功能
- 第4章 细胞的物质输入和输出
  - 第1节 被动运输
  - 第2节 主动运输与胞吞、胞吐
- 第5章 细胞的能量供应和利用
  - 第1节 降低化学反应活化能的酶
  - 第2节 细胞的能量"货币"ATP
  - 第3节 细胞呼吸的原理和应用
  - 第4节 光合作用与能量转化
- 第6章 细胞的生命历程
  - 第1节 细胞的增殖
  - 第2节 细胞的分化
  - 第3节 细胞的衰老和死亡
"""

        prompt = f"""你是一个高中生物教材分析专家。请分析这一页教材内容（第{page_num}页）。

{textbook_structure}

页面文本内容：
{text[:3000]}

请根据页面内容和上述章节结构，判断该页属于哪个章节，并以JSON格式返回分析结果：
{{
    "chapter_info": {{
        "module": "必修1",
        "chapter_num": 章节号(数字，如1、2、3，前言部分填0),
        "chapter_name": "章节名称（如'走近细胞'，前言部分填'前言'）",
        "section_num": 节号(数字，如1、2、3，无则填null),
        "section_name": "节名称（如'细胞是生命活动的基本单位'，无则填null）"
    }},
    "content_type": "封面/目录/前言/正文/实验/练习/附录",
    "knowledge_points": [
        {{
            "name": "知识点名称",
            "description": "简要描述（1-2句话）",
            "keywords": ["关键词1", "关键词2"],
            "importance": "核心/重要/一般"
        }}
    ],
    "concepts": ["本页出现的重要概念术语"],
    "has_diagram": true/false,
    "diagram_description": "图表内容描述（如果有）"
}}

重要提示：
1. chapter_num必须是数字！前言/目录/封面等填0，第1章填1，第2章填2，以此类推
2. 根据页面内容判断属于哪个章节，即使页面上没有明确写"第X章"
3. 如果是封面、目录、科学家访谈等前言内容，chapter_num=0，chapter_name="前言"
4. 如果是正文内容但无法确定具体章节，根据内容主题推断最可能的章节
5. 返回纯JSON，不要包含markdown代码块标记"""

        try:
            # 构建请求
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            response = await self.client.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2000,
                    "temperature": 0.1
                }
            )

            if response.status_code != 200:
                logger.error(f"[Vision] API错误: {response.status_code} - {response.text}")
                return {"error": f"API错误: {response.status_code}"}

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # 解析JSON - 增强容错
            content = content.strip()
            import re

            # 清理可能的markdown标记
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 尝试提取JSON对象 - 使用贪婪匹配
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group(0)

            # 尝试多种解析策略
            def try_parse_json(text):
                """尝试解析JSON，返回解析结果或None"""
                try:
                    return json.loads(text)
                except:
                    return None

            # 策略1: 直接解析
            analysis = try_parse_json(content)
            if analysis:
                logger.info(f"[Vision] 解析成功，chapter_num={analysis.get('chapter_info', {}).get('chapter_num')}")
                return analysis

            # 策略2: 修复尾随逗号
            fixed_content = re.sub(r',\s*}', '}', content)
            fixed_content = re.sub(r',\s*]', ']', fixed_content)
            analysis = try_parse_json(fixed_content)
            if analysis:
                logger.info(f"[Vision] 修复后解析成功，chapter_num={analysis.get('chapter_info', {}).get('chapter_num')}")
                return analysis

            # 策略3: 修复可能被截断的JSON
            # 如果JSON被截断，尝试找到最后一个完整的}
            brace_count = 0
            last_valid_pos = -1
            for i, char in enumerate(content):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        last_valid_pos = i + 1
                        break

            if last_valid_pos > 0:
                truncated_content = content[:last_valid_pos]
                analysis = try_parse_json(truncated_content)
                if analysis:
                    logger.info(f"[Vision] 截断修复后解析成功")
                    return analysis

            logger.warning(f"[Vision] JSON解析失败，原始内容长度: {len(content)}, 前200字符: {content[:200]}...")
            return {"raw_response": content}

        except Exception as e:
            logger.error(f"[Vision] 请求失败: {e}")
            return {"error": str(e)}


async def test_process_textbook(pdf_path: str, start_page: int = 1, end_page: int = 10):
    """测试处理教材"""
    processor = TextbookProcessor()
    try:
        result = await processor.process_pdf(pdf_path, start_page, end_page)
        return result
    finally:
        await processor.close()


# 命令行测试
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python textbook_processor.py <pdf_path> [start_page] [end_page]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    start_page = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end_page = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    result = asyncio.run(test_process_textbook(pdf_path, start_page, end_page))
    print(json.dumps(result, ensure_ascii=False, indent=2))
