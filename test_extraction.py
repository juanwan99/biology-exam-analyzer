#!/usr/bin/env python3
"""测试Word内容提取功能"""
import sys
sys.path.insert(0, '/app')

from document_processor import DocumentProcessor
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

# 创建处理器
processor = DocumentProcessor()

# 测试提取
file_path = '/app/test_with_table_and_image.docx'
print(f"\n{'='*60}")
print(f"测试文件: {file_path}")
print(f"{'='*60}\n")

try:
    extracted_text, extracted_images, extracted_elements = processor.extract_word_content(file_path)

    print(f"\n{'='*60}")
    print("提取结果统计:")
    print(f"{'='*60}")
    print(f"✅ 提取文字: {len(extracted_text)} 字符")
    print(f"✅ 提取图片: {len(extracted_images)} 张")
    print(f"✅ 提取元素: {len(extracted_elements)} 个")

    print(f"\n{'='*60}")
    print("元素详细信息:")
    print(f"{'='*60}")

    for idx, element in enumerate(extracted_elements, 1):
        elem_type = element.get('type', 'unknown')
        print(f"\n[元素 {idx}] 类型: {elem_type}")

        if elem_type == 'paragraph':
            content = element.get('content', '')[:50]
            print(f"  内容: {content}{'...' if len(element.get('content', '')) > 50 else ''}")

        elif elem_type == 'table':
            rows = element.get('rows', 0)
            cols = element.get('cols', 0)
            print(f"  尺寸: {rows}行 x {cols}列")
            html = element.get('html', '')[:100]
            print(f"  HTML: {html}{'...' if len(element.get('html', '')) > 100 else ''}")

        elif elem_type == 'image':
            base64_len = len(element.get('base64', ''))
            caption = element.get('caption', '')
            print(f"  Base64长度: {base64_len}")
            print(f"  标题: {caption}")

    print(f"\n{'='*60}")
    print("测试完成！")
    print(f"{'='*60}\n")

except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
