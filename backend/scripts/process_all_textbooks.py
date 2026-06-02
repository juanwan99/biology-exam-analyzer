# -*- coding: utf-8 -*-
"""
批量处理所有教材
使用 Vision Processor 处理5本生物教材
"""
import asyncio
import sys
import os

# 加载.env文件
from dotenv import load_dotenv
load_dotenv()

# 确保环境变量 - 优先使用 KEY_2
api_key = os.environ.get("DEEPSEEK_API_KEY_2") or os.environ.get("DEEPSEEK_API_KEY", "")
os.environ["DEEPSEEK_API_KEY"] = api_key
os.environ["DEEPSEEK_API_KEY_2"] = api_key
# DEEPSEEK_API_BASE from environment

from vision_processor import VisionProcessor

# 教材配置
TEXTBOOKS = [
    {
        "path": "uploads/普通高中教科书·生物学必修1分子与细胞.pdf",
        "book_id": "bx1",
        "name": "必修1",
        "start_page": 6,  # 跳过前面的目录
        "end_page": None  # 处理到末尾
    },
    {
        "path": "uploads/普通高中教科书·生物学必修2遗传与进化.pdf",
        "book_id": "bx2",
        "name": "必修2",
        "start_page": 6,
        "end_page": None
    },
    {
        "path": "uploads/普通高中教科书·生物学选择性必修1稳态与调节.pdf",
        "book_id": "xxbx1",
        "name": "选必1",
        "start_page": 6,
        "end_page": None
    },
    {
        "path": "uploads/普通高中教科书·生物学选择性必修2生物与环境.pdf",
        "book_id": "xxbx2",
        "name": "选必2",
        "start_page": 6,
        "end_page": None
    },
    {
        "path": "uploads/普通高中教科书·生物学选择性必修3生物技术与工程.pdf",
        "book_id": "xxbx3",
        "name": "选必3",
        "start_page": 6,
        "end_page": None
    },
]


async def process_single_book(processor: VisionProcessor, book_config: dict, delay: float = 1.5):
    """处理单本教材"""
    print(f"\n{'='*60}")
    print(f"开始处理: {book_config['name']} ({book_config['book_id']})")
    print(f"{'='*60}")

    result = await processor.process_pdf(
        pdf_path=book_config["path"],
        start_page=book_config["start_page"],
        end_page=book_config["end_page"],
        skip_existing=True,
        delay=delay
    )

    print(f"\n{book_config['name']} 处理完成:")
    print(f"  - 处理页数: {result.get('pages_processed', 0)}")
    print(f"  - 跳过页数: {result.get('pages_skipped', 0)}")
    print(f"  - 切片总数: {result.get('total_chunks', 0)}")
    print(f"  - 向量数量: {result.get('chunks_with_embeddings', 0)}")

    if result.get("errors"):
        print(f"  - 错误: {result['errors'][:5]}")  # 只显示前5个错误

    return result


async def main():
    """主函数"""
    # 解析命令行参数
    book_filter = None
    if len(sys.argv) > 1:
        book_filter = sys.argv[1]  # 可以指定 bx2, xxbx1 等只处理特定教材

    processor = VisionProcessor()

    print("\n" + "="*60)
    print("生物教材批量处理工具")
    print("="*60)

    # 显示当前状态
    stats = processor.get_book_stats()
    print("\n当前处理状态:")
    for s in stats:
        print(f"  {s['book_id']}: {s['page_count']}页, {s['chunk_count']}切片, {s['embedding_count']}向量")

    # 选择要处理的教材
    books_to_process = TEXTBOOKS
    if book_filter:
        books_to_process = [b for b in TEXTBOOKS if b["book_id"] == book_filter]
        if not books_to_process:
            print(f"未找到教材: {book_filter}")
            print(f"可用: {[b['book_id'] for b in TEXTBOOKS]}")
            return

    print(f"\n将处理 {len(books_to_process)} 本教材:")
    for b in books_to_process:
        print(f"  - {b['name']} ({b['book_id']})")

    # 处理每本教材
    all_results = []
    for book_config in books_to_process:
        try:
            result = await process_single_book(processor, book_config)
            all_results.append(result)
        except Exception as e:
            print(f"\n处理 {book_config['name']} 时出错: {e}")
            all_results.append({"error": str(e)})

    # 汇总报告
    print("\n" + "="*60)
    print("处理完成汇总")
    print("="*60)

    total_pages = sum(r.get("pages_processed", 0) for r in all_results)
    total_chunks = sum(r.get("total_chunks", 0) for r in all_results)
    total_embeddings = sum(r.get("chunks_with_embeddings", 0) for r in all_results)

    print(f"总计处理: {total_pages}页, {total_chunks}切片, {total_embeddings}向量")

    # 最终状态
    print("\n最终状态:")
    stats = processor.get_book_stats()
    for s in stats:
        print(f"  {s['book_id']}: {s['page_count']}页, {s['chunk_count']}切片, {s['embedding_count']}向量")


if __name__ == "__main__":
    asyncio.run(main())
