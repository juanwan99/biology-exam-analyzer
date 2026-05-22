#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理所有教材 PDF
使用 AI 2.5 Flash 视觉模型提取Markdown并生成向量
"""
import asyncio
import os
import sys
from pathlib import Path

# 设置环境变量
os.environ.setdefault('DEEPSEEK_API_KEY_2', os.environ.get('DEEPSEEK_API_KEY', ''))
os.environ.setdefault('DEEPSEEK_API_BASE', os.environ.get('DEEPSEEK_API_BASE', ''))

from vision_processor import VisionProcessor

# 教材配置：(文件名, 起始页, 结束页)
# 跳过封面、目录等前面几页
TEXTBOOKS = [
    ("普通高中教科书·生物学必修1分子与细胞.pdf", 6, None),          # 从第6页开始
    ("普通高中教科书·生物学必修2遗传与进化.pdf", 6, None),
    ("普通高中教科书·生物学选择性必修1稳态与调节.pdf", 6, None),
    ("普通高中教科书·生物学选择性必修2生物与环境.pdf", 6, None),
    ("普通高中教科书·生物学选择性必修3生物技术与工程.pdf", 6, None),
]


async def process_all():
    """处理所有教材"""
    processor = VisionProcessor()

    uploads_dir = Path("uploads")

    all_stats = []

    for filename, start_page, end_page in TEXTBOOKS:
        pdf_path = uploads_dir / filename

        if not pdf_path.exists():
            print(f"❌ 文件不存在: {pdf_path}")
            continue

        print(f"\n{'='*60}")
        print(f"📚 开始处理: {filename}")
        print(f"   起始页: {start_page}")
        print('='*60)

        try:
            stats = await processor.process_pdf(
                str(pdf_path),
                start_page=start_page,
                end_page=end_page,
                skip_existing=True,  # 跳过已处理的页面
                delay=1.5  # API调用间隔
            )
            all_stats.append(stats)

            print(f"\n✅ 完成: {stats['pages_processed']}页, {stats['chunks_with_embeddings']}个向量")
            if stats['errors']:
                print(f"⚠️ 错误: {len(stats['errors'])}个")

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            all_stats.append({"book_name": filename, "error": str(e)})

    # 总结
    print(f"\n\n{'='*60}")
    print("📊 处理总结")
    print('='*60)

    total_pages = 0
    total_chunks = 0

    for stats in all_stats:
        if 'error' in stats:
            print(f"❌ {stats.get('book_name', 'Unknown')}: 失败 - {stats['error']}")
        else:
            total_pages += stats.get('pages_processed', 0)
            total_chunks += stats.get('chunks_with_embeddings', 0)
            print(f"✅ {stats['book_name']}: {stats['pages_processed']}页, {stats['chunks_with_embeddings']}个向量")

    print(f"\n总计: {total_pages}页, {total_chunks}个向量")

    # 显示数据库统计
    print("\n数据库统计:")
    db_stats = processor.get_book_stats()
    for s in db_stats:
        print(f"  {s['book_id']}: {s['page_count']}页, {s['chunk_count']}切片, {s['embedding_count']}向量")


async def process_single(book_index: int):
    """处理单本教材"""
    if book_index < 0 or book_index >= len(TEXTBOOKS):
        print(f"无效的索引: {book_index}")
        return

    filename, start_page, end_page = TEXTBOOKS[book_index]
    processor = VisionProcessor()

    pdf_path = Path("uploads") / filename

    print(f"开始处理: {filename}")
    stats = await processor.process_pdf(
        str(pdf_path),
        start_page=start_page,
        end_page=end_page,
        skip_existing=True,
        delay=1.5
    )

    print(f"完成: {stats}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 处理指定的教材
        book_idx = int(sys.argv[1])
        asyncio.run(process_single(book_idx))
    else:
        # 处理所有教材
        asyncio.run(process_all())
