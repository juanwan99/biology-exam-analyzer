"""
高考真题提取器 v2
- 使用精确解析器定位图表
- 图片与题目精确关联
- 表格内容完整保留
"""
import os
import json
import base64
from pathlib import Path
from typing import List, Dict, Any
from openai import OpenAI
import time

from logger import get_logger
from config import PROMPT_DIR
from word_parser_v2 import WordParserV2, ParsedDocument

logger = get_logger()


class GaokaoExtractorV2:
    """高考真题提取器 v2"""

    def __init__(self, api_key: str, api_base: str = None):
        self.api_key = api_key
        self.api_base = api_base or "https://www.chataiapi.com/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        self.model = "deepseek-chat"
        self.parser = WordParserV2()

        # API 频率控制
        self.last_request_time = 0
        self.min_request_interval = 1.0

        logger.info(f"高考真题提取器 v2 初始化完成")

    def _wait_if_needed(self):
        """API 频率控制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()

    def extract(self, file_path: str) -> List[Dict[str, Any]]:
        """
        提取高考真题

        Args:
            file_path: docx 文件路径

        Returns:
            题目列表
        """
        # 1. 解析文档
        parsed = self.parser.parse(file_path)
        logger.info(f"[提取] 文档解析完成: {len(parsed.elements)} 元素, {len(parsed.images)} 图片")

        # 2. 检查图片数量，决定是否分块
        max_images_per_request = 15  # API 限制 16，留一点余量

        if len(parsed.images) <= max_images_per_request:
            # 图片数量在限制内，正常处理
            questions = self._extract_single(parsed)
        else:
            # 图片过多，分块处理
            logger.info(f"[提取] 图片数量 {len(parsed.images)} 超过限制，启用分块处理")
            questions = self._extract_chunked(parsed, max_images_per_request)

        # 保存结果
        self._save_results(parsed.filename, questions, parsed)

        return questions

    def _extract_single(self, parsed: ParsedDocument) -> List[Dict[str, Any]]:
        """单次提取（图片数量在限制内）"""
        marked_text = parsed.to_marked_text()
        prompt = self._build_prompt(parsed.category, parsed.filename, marked_text)
        messages = self._build_messages(prompt, parsed)
        return self._call_api(messages)

    def _extract_chunked(self, parsed: ParsedDocument, max_images: int) -> List[Dict[str, Any]]:
        """
        分块提取（图片过多时）

        策略：简单按图片数量分块，每块最多 max_images 张图片
        """
        all_questions = []
        import re

        # 找出所有图片元素的位置
        image_positions = []
        for i, elem in enumerate(parsed.elements):
            if elem.type == 'image':
                image_positions.append((i, elem.image_id))

        logger.info(f"[分块] 共 {len(image_positions)} 张图片")

        # 按图片数量分块
        chunks = []
        chunk_start = 0

        for batch_idx in range(0, len(image_positions), max_images):
            batch_end = min(batch_idx + max_images, len(image_positions))
            batch_images = image_positions[batch_idx:batch_end]

            # 确定这个块的元素范围
            first_img_pos = batch_images[0][0]
            last_img_pos = batch_images[-1][0]

            # 往前找到合适的起始点（题目开头或段落开头）
            start_pos = chunk_start
            for i in range(first_img_pos - 1, chunk_start - 1, -1):
                elem = parsed.elements[i]
                if elem.type == 'paragraph' and elem.content:
                    # 检查是否是题目开头
                    if re.match(r'^\d+\s*[\.\[．]', elem.content[:20]):
                        start_pos = i
                        break

            # 往后找到合适的结束点
            end_pos = len(parsed.elements)
            if batch_end < len(image_positions):
                # 不是最后一批，找下一个题目开头
                next_img_pos = image_positions[batch_end][0]
                for i in range(last_img_pos + 1, next_img_pos + 1):
                    if i >= len(parsed.elements):
                        break
                    elem = parsed.elements[i]
                    if elem.type == 'paragraph' and elem.content:
                        if re.match(r'^\d+\s*[\.\[．]', elem.content[:20]):
                            end_pos = i
                            break

            chunks.append({
                'start': start_pos,
                'end': end_pos,
                'image_ids': [img_id for _, img_id in batch_images]
            })
            chunk_start = end_pos

        # 如果没有图片，直接返回单块
        if not chunks:
            chunks = [{
                'start': 0,
                'end': len(parsed.elements),
                'image_ids': []
            }]

        logger.info(f"[分块] 分为 {len(chunks)} 块处理")

        # 逐块处理
        for chunk_idx, chunk in enumerate(chunks):
            logger.info(f"[分块] 处理第 {chunk_idx+1}/{len(chunks)} 块 (元素 {chunk['start']}-{chunk['end']}, 图片 {len(chunk['image_ids'])} 张)")

            # 构建该块的文本
            chunk_lines = []
            for elem in parsed.elements[chunk['start']:chunk['end']]:
                if elem.type == 'paragraph':
                    chunk_lines.append(f"[P{elem.index}] {elem.content}")
                elif elem.type == 'table':
                    table_text = parsed._table_to_text(elem.table_data)
                    chunk_lines.append(f"[T{elem.index}] 📊表格:\n{table_text}")
                elif elem.type == 'image':
                    chunk_lines.append(f"[I{elem.index}] 📷[图片 {elem.image_id}]")

            chunk_text = "\n".join(chunk_lines)

            # 构建该块的图片数据
            chunk_images = {img_id: parsed.images[img_id] for img_id in chunk['image_ids'] if img_id in parsed.images}

            # 创建临时 ParsedDocument
            chunk_parsed = ParsedDocument(
                filename=parsed.filename,
                category=parsed.category,
                elements=parsed.elements[chunk['start']:chunk['end']],
                images=chunk_images
            )

            # 构建 prompt
            prompt = self._build_prompt(parsed.category, parsed.filename, chunk_text)
            prompt += f"\n\n注意：这是文档的第 {chunk_idx+1}/{len(chunks)} 部分，请只提取本部分中的题目。"

            # 构建消息
            messages = self._build_messages(prompt, chunk_parsed)

            try:
                chunk_questions = self._call_api(messages)
                all_questions.extend(chunk_questions)
                logger.info(f"[分块] 第 {chunk_idx+1} 块提取到 {len(chunk_questions)} 道题")
            except Exception as e:
                logger.error(f"[分块] 第 {chunk_idx+1} 块处理失败: {e}")

            # 间隔避免限流
            if chunk_idx < len(chunks) - 1:
                time.sleep(2)

        return all_questions

    def _build_prompt(self, category: str, filename: str, marked_text: str) -> str:
        """构建提取 prompt"""
        return f"""你是一位高中生物高考命题专家，请从以下文档内容中提取高考真题。

## 文档信息
- 知识点分类：{category}
- 文件来源：{filename}

## 文档内容（带位置标记）
{marked_text}

## 位置标记说明
- [Pn] 表示第 n 个段落
- [Tn] 表示第 n 个表格
- [In] 📷[图片 IMG_x] 表示第 n 个位置有图片，图片编号为 IMG_x

## 提取要求

### 1. 题目识别
- 题目以"数字.[年份·卷名]"开头，如"4.[2022·海南卷]"
- 有些题目带知识点标签，如"3.A3、J3[2021·河北卷]"
- 选项为 A/B/C/D
- 答案格式为"数字.字母　[解析]"，如"4.A　[解析]..."

### 2. 图表关联（重要！）
- 如果题目后紧跟 [In] 📷[图片 IMG_x]，说明该题包含图片
- 记录 image_ids 字段，如 ["IMG_1"]
- 如果题目包含表格（[Tn]），记录 table_index 字段

### 3. 题型分类
- single_choice: 单选题
- multiple_choice: 多选题
- fill_blank: 填空题
- short_answer: 简答题

## 输出格式（严格 JSON 数组）

```json
[
  {{
    "year": 2022,
    "exam_source": "海南卷",
    "question_number": 4,
    "question_type": "single_choice",
    "stem": "完整题干",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "answer": "A",
    "explanation": "完整解析",
    "knowledge_points": ["知识点1", "知识点2"],
    "difficulty": 3,
    "image_ids": [],
    "table_index": null,
    "element_range": [1, 6]
  }}
]
```

## 字段说明
- element_range: [起始元素索引, 结束元素索引]，用于定位题目在文档中的位置
- image_ids: 题目关联的图片编号列表，如 ["IMG_1", "IMG_2"]
- table_index: 题目关联的表格索引，如 29（对应 [T29]）
- difficulty: 1-5 分，1最简单，5最难

## 注意
1. 确保每道题的图片和表格关联正确
2. element_range 帮助后续验证提取准确性
3. 严格输出 JSON，不要添加额外说明"""

    def _build_messages(self, prompt: str, parsed: ParsedDocument) -> list:
        """构建 API 请求消息"""
        # 获取图片列表
        images = parsed.get_image_list()

        if not images:
            # 无图片，纯文本请求
            return [{"role": "user", "content": prompt}]

        # 有图片，构建多模态请求
        content = [{"type": "text", "text": prompt}]

        for img_id, img_data in images:
            # 判断图片类型
            if img_data[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = "image/png"
            elif img_data[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            else:
                mime_type = "image/png"  # 默认

            base64_img = base64.b64encode(img_data).decode('utf-8')
            content.append({
                "type": "text",
                "text": f"\n[图片 {img_id}]:"
            })
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}
            })

        return [{"role": "user", "content": content}]

    def _call_api(self, messages: list) -> List[Dict]:
        """调用 AI API"""
        self._wait_if_needed()

        try:
            logger.info(f"[API] 开始调用，消息类型: {'多模态' if isinstance(messages[0]['content'], list) else '纯文本'}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=16384,
                temperature=0,
                timeout=180
            )

            response_text = response.choices[0].message.content
            logger.info(f"[API] 响应长度: {len(response_text)}")

            # 解析 JSON
            return self._parse_response(response_text)

        except Exception as e:
            logger.error(f"[API] 调用失败: {e}")
            raise

    def _parse_response(self, response_text: str) -> List[Dict]:
        """解析 API 响应"""
        import re

        text = response_text.strip()

        # 提取 JSON - 尝试多种方式
        # 方式1: 代码块
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()
        else:
            # 方式2: 直接找 JSON 数组
            array_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if array_match:
                text = array_match.group(0)

        # 清理可能的问题字符
        text = text.replace('\n', ' ').replace('\r', ' ')

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return [result]
            return []
        except json.JSONDecodeError as e:
            logger.error(f"[解析] JSON 解析失败: {e}")
            # 尝试修复常见问题
            try:
                # 尝试修复截断的 JSON
                if text.count('[') > text.count(']'):
                    text = text + ']'
                if text.count('{') > text.count('}'):
                    text = text.rsplit(',', 1)[0] + '}]'
                result = json.loads(text)
                if isinstance(result, list):
                    logger.info(f"[解析] JSON 修复成功，提取 {len(result)} 条")
                    return result
            except:
                pass
            logger.debug(f"[解析] 原始文本: {text[:500]}")
            return []

    def _save_results(self, filename: str, questions: List[Dict], parsed: ParsedDocument):
        """保存提取结果"""
        output_dir = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存题目 JSON
        output_path = output_dir / f"{filename}_v2.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        logger.info(f"[保存] 题目保存到: {output_path}")

        # 保存关联的图片
        if parsed.images:
            img_dir = output_dir / f"{filename}_images"
            img_dir.mkdir(exist_ok=True)
            for img_id, img_data in parsed.images.items():
                # 判断格式
                ext = "png" if img_data[:8] == b'\x89PNG\r\n\x1a\n' else "jpg"
                img_path = img_dir / f"{img_id}.{ext}"
                with open(img_path, 'wb') as f:
                    f.write(img_data)
            logger.info(f"[保存] {len(parsed.images)} 张图片保存到: {img_dir}")


def test_extractor():
    """测试提取器"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_base = os.environ.get("DEEPSEEK_API_BASE")

    if not api_key:
        print("请设置 DEEPSEEK_API_KEY 环境变量")
        return

    extractor = GaokaoExtractorV2(api_key, api_base)

    test_file = "/home/ubuntu/biology-exam-analyzer/uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类/细胞的分子组成.docx"

    questions = extractor.extract(test_file)

    print(f"\n提取到 {len(questions)} 道题目")

    # 显示有图片的题目
    print("\n" + "=" * 60)
    print("有图片的题目:")
    print("=" * 60)
    for q in questions:
        if q.get('image_ids'):
            print(f"\n第 {q['question_number']} 题 [{q['year']}·{q['exam_source']}]")
            print(f"  图片: {q['image_ids']}")
            print(f"  题干: {q['stem'][:60]}...")

    # 显示有表格的题目
    print("\n" + "=" * 60)
    print("有表格的题目:")
    print("=" * 60)
    for q in questions:
        if q.get('table_index') is not None:
            print(f"\n第 {q['question_number']} 题 [{q['year']}·{q['exam_source']}]")
            print(f"  表格索引: T{q['table_index']}")
            print(f"  题干: {q['stem'][:60]}...")


if __name__ == "__main__":
    test_extractor()
