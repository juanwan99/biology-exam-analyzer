"""
重新处理失败的文件
"""
import os
import json
import time
from pathlib import Path
from gaokao_extractor_v2 import GaokaoExtractorV2
from logger import get_logger

logger = get_logger()


def reprocess_failed():
    """重新处理之前失败的文件"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_base = os.environ.get("DEEPSEEK_API_BASE")

    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        return

    extractor = GaokaoExtractorV2(api_key, api_base)

    # 读取之前的批量结果
    results_path = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted/batch_results.json")
    if results_path.exists():
        with open(results_path, 'r', encoding='utf-8') as f:
            prev_results = json.load(f)
        failed_files = [f['file'] for f in prev_results.get('failed', [])]
    else:
        print("未找到之前的批量结果文件")
        return

    print(f"\n{'='*60}")
    print(f"重新处理失败文件")
    print(f"{'='*60}")
    print(f"失败文件数: {len(failed_files)}")
    print(f"{'='*60}\n")

    # 查找失败文件的完整路径
    input_dir = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/gaokao_zhenti/7.高考真题分类/2023年（含）前高考真题分类")

    results = {
        "success": [],
        "failed": [],
        "total_questions": 0,
        "total_images": 0,
        "total_tables": 0
    }

    for idx, filename in enumerate(failed_files):
        file_path = input_dir / filename
        if not file_path.exists():
            print(f"[{idx+1}/{len(failed_files)}] 文件不存在: {filename}")
            results["failed"].append({
                "file": filename,
                "error": "文件不存在"
            })
            continue

        print(f"\n[{idx+1}/{len(failed_files)}] 处理: {filename}")
        print("-" * 50)

        try:
            start_time = time.time()
            questions = extractor.extract(str(file_path))
            elapsed = time.time() - start_time

            # 统计
            num_images = sum(1 for q in questions if q.get('image_ids'))
            num_tables = sum(1 for q in questions if q.get('table_index'))

            results["success"].append({
                "file": filename,
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
            if idx < len(failed_files) - 1:
                time.sleep(3)

        except Exception as e:
            results["failed"].append({
                "file": filename,
                "error": str(e)
            })
            print(f"❌ 失败: {e}")

    # 输出总结
    print(f"\n{'='*60}")
    print("重新处理完成")
    print(f"{'='*60}")
    print(f"成功: {len(results['success'])} 个文件")
    print(f"失败: {len(results['failed'])} 个文件")
    print(f"总计: {results['total_questions']} 道题")
    print(f"含图片: {results['total_images']} 道")
    print(f"含表格: {results['total_tables']} 道")

    if results["failed"]:
        print(f"\n仍然失败的文件:")
        for f in results["failed"]:
            print(f"  - {f['file']}: {f['error']}")

    # 保存结果
    output_path = Path("/home/ubuntu/biology-exam-analyzer/uploads/textbooks/extracted")
    with open(output_path / "reprocess_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path / 'reprocess_results.json'}")

    return results


if __name__ == "__main__":
    reprocess_failed()
