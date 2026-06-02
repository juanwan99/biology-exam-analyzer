"""
批量提取高考真题
"""
import os
import json
import time
from pathlib import Path
from gaokao_extractor_v2 import GaokaoExtractorV2
from logger import get_logger

logger = get_logger()


def batch_extract(input_dir: str, output_dir: str = None):
    """
    批量提取目录下所有 Word 文档

    Args:
        input_dir: 输入目录
        output_dir: 输出目录（默认为 extracted/）
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_base = os.environ.get("DEEPSEEK_API_BASE")

    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        return

    extractor = GaokaoExtractorV2(api_key, api_base)

    # 查找所有 .docx 文件
    input_path = Path(input_dir)
    docx_files = list(input_path.glob("**/*.docx"))

    print(f"\n{'='*60}")
    print(f"批量提取高考真题")
    print(f"{'='*60}")
    print(f"输入目录: {input_dir}")
    print(f"找到 {len(docx_files)} 个 .docx 文件")
    print(f"{'='*60}\n")

    # 统计结果
    results = {
        "success": [],
        "failed": [],
        "total_questions": 0,
        "total_images": 0,
        "total_tables": 0
    }

    for idx, file_path in enumerate(docx_files):
        print(f"\n[{idx+1}/{len(docx_files)}] 处理: {file_path.name}")
        print("-" * 50)

        try:
            start_time = time.time()
            questions = extractor.extract(str(file_path))
            elapsed = time.time() - start_time

            # 统计
            num_images = sum(1 for q in questions if q.get('image_ids'))
            num_tables = sum(1 for q in questions if q.get('table_index'))

            results["success"].append({
                "file": file_path.name,
                "questions": len(questions),
                "images": num_images,
                "tables": num_tables,
                "time": elapsed
            })
            results["total_questions"] += len(questions)
            results["total_images"] += num_images
            results["total_tables"] += num_tables

            print(f"✅ 成功: {len(questions)} 道题, {num_images} 图, {num_tables} 表 ({elapsed:.1f}秒)")

            # 间隔避免限流
            if idx < len(docx_files) - 1:
                time.sleep(2)

        except Exception as e:
            results["failed"].append({
                "file": file_path.name,
                "error": str(e)
            })
            print(f"❌ 失败: {e}")

    # 输出总结
    print(f"\n{'='*60}")
    print("批量提取完成")
    print(f"{'='*60}")
    print(f"成功: {len(results['success'])} 个文件")
    print(f"失败: {len(results['failed'])} 个文件")
    print(f"总计: {results['total_questions']} 道题")
    print(f"含图片: {results['total_images']} 道")
    print(f"含表格: {results['total_tables']} 道")

    if results["failed"]:
        print(f"\n失败文件:")
        for f in results["failed"]:
            print(f"  - {f['file']}: {f['error']}")

    # 保存统计结果
    output_path = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted")
    output_path.mkdir(parents=True, exist_ok=True)
    with open(output_path / "batch_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n统计结果已保存到: {output_path / 'batch_results.json'}")

    return results


if __name__ == "__main__":
    # 处理 2023年及之前的高考真题（13个 .docx 文件）
    input_dir = "/home/ubuntu/biology-exam-analyzer/uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类"
    batch_extract(input_dir)
