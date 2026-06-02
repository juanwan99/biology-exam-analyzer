#!/usr/bin/env python3
"""
在Docker容器内处理真实文档并保存各阶段数据
"""
import sys
sys.path.insert(0, '/app')

import json
from pathlib import Path
from document_processor import DocumentProcessor
from logger import get_logger

logger = get_logger()

# 容器内的文件路径（需要先复制文件到容器）
WORD_FILE = "/app/uploads/test_real_document.docx"

# 输出目录
OUTPUT_DIR = Path("/app/test_data")
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
        print(f"提示: 请先将文件复制到容器内:")
        print(f"  docker cp \"文件路径\" biology_backend:/app/uploads/test_real_document.docx")
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

    # 保存阶段1数据（包含base64图片）
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

def create_mock_questions(word_content):
    """创建模拟题目数据（阶段2+3）"""
    print(f"\n{'='*60}")
    print("创建模拟测试数据（阶段2+3）")
    print(f"{'='*60}\n")

    # 模拟两道题
    mock_questions = [
        {
            "id": 7,
            "content": "7. 某动物家系的系谱图如图所示。a1、a2、a3、a4是位于X染色体上的等位基因，Ⅰ-1基因型为XalXa2，Ⅰ-2基因型为Xa3Y，Ⅱ-1和Ⅱ-4基因型均为Xa4Y，Ⅳ-1为纯合子的概率为（    ）\n\nA. 3/64\tB. 3/32\tC. 1/8\tD. 3/16",
            "image_indices": [0],
            "structured_content": word_content['elements'][:5],  # 前5个元素
            "analysis": {
                "knowledge_points": ["伴性遗传（X染色体遗传）", "基因型推断", "概率计算"],
                "detailed_analysis": "这是一道伴性遗传题。解题关键：1）推断各代个体基因型；2）计算配子类型概率；3）计算纯合子概率。答案应该是 D (3/16)。",
                "difficulty": "困难",
                "common_mistakes": [
                    "混淆常染色体遗传和伴性遗传",
                    "计算概率时遗漏某些基因型组合",
                    "对纯合子定义理解不清"
                ],
                "answer": "D"
            }
        },
        {
            "id": 15,
            "content": "15. 深海淤泥中含有某种能降解纤维素的细菌。探究实验如下表所示（实验条件：培养基 + 碳源 + 压力条件）...",
            "image_indices": [0],
            "structured_content": word_content['elements'][5:],  # 后续元素（包含表格）
            "analysis": {
                "knowledge_points": ["微生物培养", "纤维素降解", "实验设计"],
                "detailed_analysis": "这是一道微生物实验题。主要考查对照实验设计和结论推导。关键在于分析不同培养条件下的实验结果。",
                "difficulty": "中等",
                "common_mistakes": [
                    "混淆平板划线法和稀释涂布法",
                    "对高压灭菌顺序理解错误",
                    "实验对照组设计不当"
                ],
                "answer": "C"
            }
        }
    ]

    # 保存完整数据
    full_data = {
        "questions": mock_questions,
        "total": len(mock_questions)
    }

    save_json(full_data, "stage3_full_analysis_with_elements.json")

    print(f"✅ 创建了 {len(mock_questions)} 道完整题目（含表格和图片）")
    for q in mock_questions:
        elem_count = len(q['structured_content'])
        print(f"  - 题目{q['id']}: {elem_count} 个元素")

    return full_data

if __name__ == "__main__":
    print("\n" + "="*60)
    print("真实文档处理 - Docker容器版")
    print("="*60)

    word_content = process_word_document()

    if word_content:
        full_data = create_mock_questions(word_content)

        print(f"\n{'='*60}")
        print("✅ 测试数据已生成！")
        print(f"{'='*60}")
        print(f"\n📁 输出目录: {OUTPUT_DIR}")
        print(f"\n💡 使用方法:")
        print(f"  1. 查看数据: docker exec biology_backend cat /app/test_data/stage3_full_analysis_with_elements.json")
        print(f"  2. 复制到本地: docker cp biology_backend:/app/test_data ./")
        print(f"  3. 前端测试: 直接使用JSON数据测试渲染")
