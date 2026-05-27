import os as _os
import pytest

__test__ = False

pytestmark = pytest.mark.skipif(
    not _os.environ.get("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量（集成测试）"
)

# -*- coding: utf-8 -*-
"""
测试 AI 视觉模型对教材页面的文本提取效果
对比 deepseek-1.5-pro 和 deepseek-2.5-pro
"""
import os
import base64
import asyncio
import httpx
import fitz  # PyMuPDF
from pathlib import Path

# API配置 - 使用第二个API Key
API_KEY = os.environ.get("DEEPSEEK_API_KEY_2", os.environ.get("DEEPSEEK_API_KEY", ""))
API_BASE = os.environ.get("DEEPSEEK_API_BASE", "")

# 测试的模型 - 使用flash版本（更便宜且通常可用）
MODELS = ["deepseek-2.5-flash", "deepseek-1.5-flash"]

# 优化后的提示词
PROMPT = """你是一个专业的教材数字化专家。请阅读这张图片，将其内容转换为标准的 Markdown 格式。

**要求：**
1. **排版识别：** 严格区分主栏正文和侧栏（如"相关信息"、"小贴士"等）。侧栏内容请使用引用格式 `>` 包裹，并在合适位置插入。
2. **章节标题：** 如果有章节标题（如"第X章"、"第X节"），请使用 ## 或 ### 标记。
3. **过滤噪音：** 自动去除页眉、页脚和页码。
4. **图片描述：** 如果遇到图表或插图，请插入 `[图片: 对图片的简短描述]`。
5. **表格还原：** 如果有表格，输出为 Markdown Table 格式。
6. **公式：** 如果遇到生物/化学公式，使用行内格式表示。
7. **纯净输出：** 不要输出任何解释或闲聊，只输出 Markdown 内容。"""


async def test_model(model: str, image_base64: str, page_num: int) -> dict:
    """测试单个模型"""
    print(f"\n{'='*60}")
    print(f"测试模型: {model} (第{page_num}页)")
    print('='*60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [
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
                                    "text": PROMPT
                                }
                            ]
                        }
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.1
                }
            )

            if response.status_code != 200:
                print(f"❌ API错误: {response.status_code}")
                print(response.text[:500])
                return {"model": model, "error": response.status_code, "content": None}

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # 统计信息
            usage = result.get("usage", {})

            print(f"\n✅ 成功!")
            print(f"Token使用: 输入={usage.get('prompt_tokens', 'N/A')}, 输出={usage.get('completion_tokens', 'N/A')}")
            print(f"\n--- 输出内容 ---")
            print(content[:2000])
            if len(content) > 2000:
                print(f"\n... (共 {len(content)} 字符)")

            return {
                "model": model,
                "content": content,
                "usage": usage,
                "length": len(content)
            }

        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return {"model": model, "error": str(e), "content": None}


async def main():
    # 选择一个有代表性的页面（有正文+侧栏+图片的页面）
    pdf_path = "uploads/普通高中教科书·生物学必修1分子与细胞.pdf"

    if not Path(pdf_path).exists():
        print(f"❌ PDF文件不存在: {pdf_path}")
        return

    doc = fitz.open(pdf_path)

    # 测试页面：选择第15页（正文内容丰富）和第95页（有实验内容）
    test_pages = [15, 95]

    results = {}

    for page_num in test_pages:
        if page_num > doc.page_count:
            print(f"跳过第{page_num}页（超出范围）")
            continue

        page = doc[page_num - 1]  # 0-based

        # 渲染为高清图片 (2x缩放 ≈ 144 DPI)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        print(f"\n\n{'#'*60}")
        print(f"# 测试第 {page_num} 页")
        print(f"# 图片大小: {len(img_bytes)/1024:.1f} KB")
        print('#'*60)

        results[page_num] = {}

        for model in MODELS:
            result = await test_model(model, img_base64, page_num)
            results[page_num][model] = result

            # 避免API限流
            await asyncio.sleep(2)

    doc.close()

    # 输出对比总结
    print("\n\n")
    print("="*60)
    print("对比总结")
    print("="*60)

    for page_num, page_results in results.items():
        print(f"\n第 {page_num} 页:")
        for model, result in page_results.items():
            if result.get("content"):
                print(f"  {model}: {result['length']} 字符, tokens={result.get('usage', {})}")
            else:
                print(f"  {model}: ❌ 失败 - {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
