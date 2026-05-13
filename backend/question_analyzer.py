import json
import re
import base64
import time
from logger import get_logger
from config import PROMPT_DIR
from llm_client import llm_call

logger = get_logger()


def _downsample_image(img_bytes: bytes, max_width: int = 1024, quality: int = 75) -> bytes:
    """降采样图片以减少 LLM API 传输延迟。"""
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(img_bytes))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        result = buf.getvalue()
        if len(result) < len(img_bytes):
            return result
    except Exception:
        pass
    return img_bytes



class QuestionAnalyzer:
    """LLM 分析器：题目拆分和分析（统一 fallback 客户端）。"""

    def __init__(self):
        self.logger = get_logger()
        self.logger.info("LLM 分析器初始化完成")

    @staticmethod
    def extract_json(text: str) -> str:
        """
        从模型返回中提取纯JSON
        处理可能的Markdown代码块包裹并清理控制字符
        """
        # 移除markdown代码块标记
        text = text.strip()

        # 尝试提取 ```json ... ``` 或 ``` ... ``` 中的内容
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            logger.debug("[JSON提取] 检测到Markdown代码块，已提取")
            text = json_match.group(1).strip()

        # 清理JSON字符串中的控制字符（保留 \n \t \r，但转义其他控制字符）
        # 先尝试解析，如果失败则进行清理
        try:
            # 快速测试是否可以直接解析
            json.loads(text)
            return text
        except json.JSONDecodeError:
            # 需要清理控制字符
            # 替换所有ASCII控制字符（0x00-0x1F），除了合法的转义字符
            cleaned = ''.join(
                char if ord(char) >= 32 or char in '\n\r\t' else ' '
                for char in text
            )
            logger.debug("[JSON提取] 已清理控制字符")
            return cleaned

    async def split_questions(self, image_bytes: list, extracted_text: str = None) -> list:
        """
        第一次调用：拆分试卷为单独题目

        Args:
            image_bytes: 文档图片字节流列表
            extracted_text: 从Word提取的纯文字（可选，用于提升识别准确率）

        Returns:
            [
                {
                    "id": 1,
                    "content": "题目文本内容",
                    "image_indices": [0, 1]  # 对应原始图片的索引
                }
            ]
        """
        logger.info(f"[拆分] 开始调用LLM，图片数量: {len(image_bytes)}")

        # 加载拆分Prompt
        prompt_path = str(PROMPT_DIR / "split_prompt.txt")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                split_prompt = f.read()
            logger.debug(f"[拆分] Prompt加载成功，长度: {len(split_prompt)} 字符")
        except FileNotFoundError:
            split_prompt = self._get_default_split_prompt()
            logger.warning(f"[拆分] 使用默认Prompt（未找到{prompt_path}）")

        # 如果有提取的文字，添加到 Prompt 前面
        if extracted_text:
            logger.info(f"[拆分] 检测到Word提取文字，长度: {len(extracted_text)} 字符")
            enhanced_prompt = f"""**重要提示**：以下是从Word文档中提取的纯文字内容（100%准确），请优先使用这些文字而非OCR识别图片：

---开始提取文字---
{extracted_text}
---结束提取文字---

{split_prompt}

**注意**：图片仅用于查看题目布局和图表，文字内容请使用上面提取的纯文字。"""
            split_prompt = enhanced_prompt
        else:
            logger.debug("[拆分] 未检测到提取文字，使用纯OCR模式")

        # 构建OpenAI格式的消息（支持多图）
        message_content = [{"type": "text", "text": split_prompt}]

        # 添加图片（使用base64格式）
        for idx, img_bytes in enumerate(image_bytes):
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
            logger.debug(f"[拆分] 已添加图片 {idx + 1}/{len(image_bytes)}")

        try:
            logger.debug("[拆分] 准备调用 llm_call（统一 fallback 客户端）")
            logger.debug("[拆分] 请求参数 - max_tokens: 8192, temperature: 0")

            # P0-2: 按题型动态 max_tokens（选择题输出短，大题输出长）
            if question_type in ("single_choice", "multiple_choice"):
                _max_tokens = 2048
            elif question_type in ("fill_blank",):
                _max_tokens = 3072
            else:
                _max_tokens = 4096
            response_text = await llm_call(
                messages=[{"role": "user", "content": message_content}],
                max_tokens=_max_tokens,
                temperature=0,
                timeout=120.0,
                stage=f"analyze_q{question_id}",
            )
            finish_reason = "stop"  # fallback 客户端已处理截断重试

            logger.info(f"[拆分] API响应长度: {len(response_text) if response_text else 0}")
            logger.debug(f"[拆分] 完成原因: {finish_reason}")
            logger.debug(f"[拆分] 原始返回:\n{response_text}")

            # 检查是否被截断（优先检查）
            if finish_reason == 'length':
                logger.error(f"[拆分] 内容被截断！响应长度: {len(response_text) if response_text else 0}")
                logger.error(f"[拆分] 可能原因：试卷题目过多或内容过长，超出max_tokens限制")
                raise ValueError("题目拆分内容被截断，请优化prompt或增加max_tokens")

            # 检查返回是否为空
            if not response_text or response_text.strip() == "":
                logger.error("[拆分] API返回为空！")
                raise ValueError("API返回内容为空")

            # 提取并解析JSON
            json_text = self.extract_json(response_text)
            questions = json.loads(json_text)
            logger.info(f"[拆分] 成功识别 {len(questions)} 道题目")
            return questions

        except json.JSONDecodeError as e:
            logger.error(f"[拆分] JSON解析失败: {e}\n原始文本: {response_text}")
            raise
        except Exception as e:
            logger.error(f"[拆分] API调用失败: {str(e)}", exc_info=True)
            raise

    async def analyze_question(
        self,
        question_text: str,
        question_images: list,
        question_id: int,
        question_type: str = "unknown",
        section_header: str = None
    ) -> dict:
        """
        第二次调用：分析单道题目

        Args:
            question_text: 题目文本
            question_images: 题目相关图片
            question_id: 题目ID
            question_type: 题目类型 (single_choice/multiple_choice/fill_blank/short_answer/experiment/unknown)
            section_header: 分节标题 (如"一、单选题（1-15题，每题2分，共30分）")

        Returns:
            {
                "knowledge_points": ["遗传学", "基因分离定律"],
                "detailed_analysis": "步骤1:...",
                "difficulty": "中等",
                "common_mistakes": ["..."],
                "answer": "...",  # 根据题型返回不同格式
                "sub_questions": [...]  # 如果有子题
            }
        """
        logger.info(f"[分析] 开始分析题目 {question_id}，题型: {question_type}，分节: {section_header}")

        # 加载分析Prompt
        prompt_path = str(PROMPT_DIR / "analysis_prompt.txt")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                analysis_prompt_template = f.read()
            logger.debug(f"[分析] Prompt加载成功")
        except FileNotFoundError:
            analysis_prompt_template = self._get_default_analysis_prompt()
            logger.warning(f"[分析] 使用默认Prompt")

        # 替换参数
        analysis_prompt = analysis_prompt_template.replace("{question_type}", question_type)
        analysis_prompt = analysis_prompt.replace("{section_header}", section_header or "未提供")

        # 构造完整Prompt
        full_prompt = f"{analysis_prompt}\n\n题目内容：\n{question_text}"

        # 构建消息内容
        message_content = [{"type": "text", "text": full_prompt}]

        # 添加题目图片（P1-2: 降采样减少延迟）
        if question_images:
            for idx, img_bytes in enumerate(question_images):
                img_bytes = _downsample_image(img_bytes)
                base64_image = base64.b64encode(img_bytes).decode('utf-8')
                message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })

        try:
            logger.debug(f"[分析] 准备调用 llm_call 分析题目{question_id}")
            logger.debug(f"[分析] 请求包含 {len(question_images)} 张图片")
            if question_images:
                total_img_size = sum(len(img) for img in question_images)
                logger.debug(f"[分析] 图片总大小: {total_img_size / 1024:.2f} KB")

            response_text = await llm_call(
                messages=[{"role": "user", "content": message_content}],
                max_tokens=8192,
                temperature=0,
                timeout=120.0,
            )
            finish_reason = "stop"  # fallback 客户端已处理截断重试

            response_length = len(response_text) if response_text else 0
            logger.info(f"[分析] 题目{question_id} API响应长度: {response_length}")
            logger.debug(f"[分析] 题目{question_id} 完成原因: {finish_reason}")
            logger.info(f"[分析] 题目{question_id} 原始返回:\n{response_text[:500]}")  # 只显示前500字符

            # 检查是否被截断
            if finish_reason == 'length':
                logger.error(f"[分析] 题目{question_id} 内容被截断！响应长度: {response_length}")
                logger.warning(f"[分析] 建议：如果经常出现截断，请优化prompt或增加max_tokens")
                # 不抛出异常，继续处理（返回部分内容总比完全失败好）

            # 检查返回是否为空
            if not response_text or response_text.strip() == "":
                logger.error(f"[分析] 题目{question_id} API返回为空！")
                raise ValueError(f"题目{question_id} API返回内容为空")

            # 提取并解析JSON（兜底：找最外层 { ... }）
            json_text = self.extract_json(response_text)
            if not json_text.startswith('{'):
                start = json_text.find('{')
                if start != -1:
                    json_text = json_text[start:]
            if not json_text.endswith('}'):
                end = json_text.rfind('}')
                if end != -1:
                    json_text = json_text[:end + 1]
            logger.debug(f"[分析] 题目{question_id} 提取的JSON前500字符:\n{json_text[:500]}")

            try:
                result = json.loads(json_text)
                from llm_schemas import validate_llm_output, AnalysisResult
                result, ext_conf, val_errors = validate_llm_output(result, AnalysisResult, f"题目{question_id}")
                result["_extraction_confidence"] = ext_conf
                if val_errors:
                    result["_validation_errors"] = val_errors
                logger.info(f"[分析] 题目{question_id} 分析完成 (extraction_confidence={ext_conf})")
                return result
            except json.JSONDecodeError as json_err:
                logger.error(f"[分析] 题目{question_id} JSON解析失败: {str(json_err)}")
                logger.error(f"[分析] 问题JSON末尾500字符:\n{json_text[-500:]}")

                # 如果是因为截断导致的JSON格式错误，返回降级结果
                if finish_reason == 'length':
                    logger.warning(f"[分析] 题目{question_id} 检测到内容被截断（finish_reason=length），返回降级结果")
                    return {
                        "knowledge_points": ["解析失败-内容被截断"],
                        "detailed_analysis": f"题目{question_id}分析内容超出长度限制被截断。建议：①优化Prompt降低输出长度 ②增加max_tokens限制。",
                        "difficulty": "中等",
                        "common_mistakes": ["内容被截断，无法提供易错点"],
                        "answer": "解析失败"
                    }
                else:
                    # 非截断导致的JSON错误，继续抛出
                    raise

        except json.JSONDecodeError as e:
            logger.error(f"[分析] 题目{question_id} JSON解析失败（外层捕获）: {e}")
            raise
        except Exception as e:
            logger.error(f"[分析] 题目{question_id} API调用失败: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def _get_default_split_prompt() -> str:
        return """请分析这份生物试卷，将其拆分为单独的题目。

返回纯JSON数组格式（不要markdown代码块）：
[
    {
        "id": 1,
        "content": "题目完整文本（包括选项）",
        "image_indices": [0]  // 该题目涉及的图片页码（从0开始）
    }
]

注意：
1. 确保每道题完整独立
2. 图片页码准确对应
3. 严格返回JSON格式"""

    @staticmethod
    def _get_default_analysis_prompt() -> str:
        return """请深入分析这道生物题目，返回纯JSON格式（不要markdown代码块）：

{
    "knowledge_points": ["知识点1", "知识点2"],
    "detailed_analysis": "详细解题步骤...",
    "difficulty": "简单/中等/困难",
    "common_mistakes": ["易错点1", "易错点2"],
    "answer": "标准答案"
}"""


# Backward compatibility
GeminiAnalyzer = QuestionAnalyzer
