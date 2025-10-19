#!/usr/bin/env python3
"""
处理真实文档并保存各阶段数据
用于测试和调试，不依赖完整的API流程
"""
import sys
import json
from pathlib import Path

# 添加backend路径
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from document_processor import DocumentProcessor
from logger import get_logger

logger = get_logger()

# 输入文件路径
WORD_FILE = r"C:\Users\liang\OneDrive\Desktop\精品解析：2025年高考山东卷生物真题试卷（原卷版）.docx"
PDF_FILE = r"C:\Users\liang\OneDrive\Desktop\精品解析：2025年高考山东卷生物真题试卷（原卷版）.pdf"

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "test_data"
OUTPUT_DIR.mkdir(exist_ok=True)

def save_json(data, filename):
    """保存JSON数据"""
    output_path = OUTPUT_DIR / filename
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 数据已保存: {output_path}")
    print(f"✅ 数据已保存: {output_path}")

def process_word_document():
    """处理Word文档 - 阶段1"""
    print(f"\n{'='*60}")
    print("阶段1：Word文档内容提取")
    print(f"{'='*60}\n")

    if not Path(WORD_FILE).exists():
        print(f"❌ 文件不存在: {WORD_FILE}")
        return None

    # 提取Word内容
    print(f"📄 正在处理: {WORD_FILE}")
    word_content = DocumentProcessor.extract_word_content(WORD_FILE)

    # 统计信息
    print(f"\n提取结果统计:")
    print(f"  📝 文字: {len(word_content['text'])} 字符")
    print(f"  🖼️  图片: {len(word_content['images'])} 张")
    print(f"  📊 元素: {len(word_content['elements'])} 个")

    # 分类统计
    element_types = {}
    for elem in word_content['elements']:
        elem_type = elem['type']
        element_types[elem_type] = element_types.get(elem_type, 0) + 1

    print(f"\n元素类型统计:")
    for elem_type, count in element_types.items():
        print(f"  - {elem_type}: {count} 个")

    # 保存阶段1数据（不含图片二进制数据，只保留base64）
    stage1_data = {
        "file": WORD_FILE,
        "text": word_content['text'],
        "elements": word_content['elements'],
        "stats": {
            "text_length": len(word_content['text']),
            "image_count": len(word_content['images']),
            "element_count": len(word_content['elements']),
            "element_types": element_types
        }
    }

    save_json(stage1_data, "stage1_word_extraction.json")

    # 预览文字内容
    print(f"\n文字内容预览（前500字）:")
    print("-" * 60)
    print(word_content['text'][:500])
    print("-" * 60)

    return word_content

def process_pdf_document():
    """处理PDF文档 - 阶段1备选"""
    print(f"\n{'='*60}")
    print("阶段1备选：PDF文档处理")
    print(f"{'='*60}\n")

    if not Path(PDF_FILE).exists():
        print(f"❌ 文件不存在: {PDF_FILE}")
        return None

    print(f"📄 正在处理: {PDF_FILE}")
    images = DocumentProcessor.process_pdf(PDF_FILE, dpi=300)

    print(f"\n提取结果统计:")
    print(f"  📄 页数: {len(images)} 页")
    for idx, img in enumerate(images):
        print(f"  - 第{idx+1}页: {img.size[0]}x{img.size[1]} 像素")

    # 保存统计信息
    stage1_pdf_data = {
        "file": PDF_FILE,
        "page_count": len(images),
        "pages": [
            {"page": idx+1, "width": img.size[0], "height": img.size[1]}
            for idx, img in enumerate(images)
        ]
    }

    save_json(stage1_pdf_data, "stage1_pdf_extraction.json")

    return images

def create_mock_stage2_data(word_content):
    """创建模拟的阶段2数据（题目拆分）"""
    print(f"\n{'='*60}")
    print("创建模拟阶段2数据（供测试用）")
    print(f"{'='*60}\n")

    # 基于提取的文字，创建模拟的题目拆分结果
    # 这里简单地按照题号分割（真实场景会调用API）

    text = word_content['text']

    # 简单的题目识别（查找题号）
    import re
    question_pattern = r'(\d+)\.\s+'
    matches = list(re.finditer(question_pattern, text))

    questions = []
    for i, match in enumerate(matches[:5]):  # 只取前5道题作为示例
        start = match.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)

        question_text = text[start:end].strip()

        questions.append({
            "id": int(match.group(1)),
            "content": question_text[:500] + "..." if len(question_text) > 500 else question_text,
            "image_indices": [0],
            "structured_content": word_content['elements']  # 附加元素
        })

    stage2_data = {
        "questions": questions,
        "total": len(questions)
    }

    save_json(stage2_data, "stage2_mock_split.json")

    print(f"✅ 创建了 {len(questions)} 道模拟题目")
    for q in questions:
        print(f"  - 题目{q['id']}: {len(q['content'])} 字符")

    return stage2_data

def create_mock_stage3_data(stage2_data):
    """创建模拟的阶段3数据（题目分析）"""
    print(f"\n{'='*60}")
    print("创建模拟阶段3数据（供测试用）")
    print(f"{'='*60}\n")

    # 为每道题创建模拟的分析结果
    analyzed_questions = []

    for question in stage2_data['questions']:
        analyzed_question = {
            **question,
            "analysis": {
                "knowledge_points": ["遗传学", "基因分离定律", "概率计算"],
                "detailed_analysis": "这是一道关于遗传学的题目。主要考查学生对基因分离定律的理解和概率计算能力。解题关键在于：1）正确识别基因型；2）推断配子类型；3）计算后代概率。",
                "difficulty": "中等",
                "common_mistakes": [
                    "混淆常染色体遗传和伴性遗传",
                    "计算概率时忘记考虑杂合子",
                    "对纯合子的定义理解不清"
                ],
                "answer": "D"
            }
        }
        analyzed_questions.append(analyzed_question)

    stage3_data = {
        "questions": analyzed_questions,
        "total": len(analyzed_questions)
    }

    save_json(stage3_data, "stage3_mock_analysis.json")

    print(f"✅ 创建了 {len(analyzed_questions)} 道题目的模拟分析")

    return stage3_data

if __name__ == "__main__":
    print("\n" + "="*60)
    print("真实文档处理 - 分阶段测试数据生成器")
    print("="*60)

    # 阶段1：Word文档提取
    word_content = process_word_document()

    # 阶段1备选：PDF文档处理
    pdf_images = process_pdf_document()

    if word_content:
        # 创建模拟的后续阶段数据
        stage2_data = create_mock_stage2_data(word_content)
        stage3_data = create_mock_stage3_data(stage2_data)

    print(f"\n{'='*60}")
    print("✅ 所有测试数据已生成完毕！")
    print(f"{'='*60}")
    print(f"\n📁 输出目录: {OUTPUT_DIR}")
    print(f"\n生成的文件:")
    for file in sorted(OUTPUT_DIR.glob("*.json")):
        print(f"  - {file.name}")

    print(f"\n💡 使用方法:")
    print(f"  1. 查看各阶段数据: cat test_data/stage*.json")
    print(f"  2. 前端测试: 直接用stage3_mock_analysis.json测试渲染")
    print(f"  3. 单独测试拆分: 用stage1数据 + API调用")
