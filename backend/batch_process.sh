#!/bin/bash
# 批量处理所有教材的脚本
# 顺序处理，避免API限流

cd /home/ubuntu/biology-exam-analyzer/backend
source .env
export DATABASE_URL

echo "=========================================="
echo "开始批量处理所有教材"
echo "=========================================="

# 教材列表
BOOKS=("bx2" "xxbx1" "xxbx2" "xxbx3")

for book in "${BOOKS[@]}"; do
    echo ""
    echo "=========================================="
    echo "正在处理: $book"
    echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="

    python3 process_all_textbooks.py "$book" 2>&1 | tee "/tmp/${book}_process.log"

    echo ""
    echo "$book 处理完成于: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # 等待一下再处理下一本，避免API过于频繁
    sleep 5
done

echo ""
echo "=========================================="
echo "所有教材处理完成!"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 最终状态
python3 -c "
from vision_processor import VisionProcessor
p = VisionProcessor()
stats = p.get_book_stats()
print('\\n最终统计:')
for s in stats:
    print(f\"  {s['book_id']}: {s['page_count']}页, {s['chunk_count']}切片, {s['embedding_count']}向量\")
"
