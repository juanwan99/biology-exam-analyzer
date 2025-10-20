"""
测试向量检索准确性
构建必修1前50页的向量索引，测试检索效果
"""
import fitz
from sentence_transformers import SentenceTransformer
import chromadb
import time

def extract_chunks(pdf_path, max_pages=50, chunk_size=800):
    """
    提取PDF前N页，按段落切分

    Args:
        pdf_path: PDF路径
        max_pages: 最大页数
        chunk_size: 每个chunk的目标字数

    Returns:
        List[Dict]: chunks列表
    """
    print(f"📚 开始提取PDF内容...")
    doc = fitz.open(pdf_path)
    chunks = []

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        text = page.get_text()

        # 跳过空页和过短的页（如封面、版权页）
        if len(text.strip()) < 100:
            continue

        # 简单切分：按段落（双换行）切分
        paragraphs = text.split('\n\n')

        current_chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果当前chunk+新段落不超过chunk_size，则合并
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                # 保存当前chunk
                if current_chunk:
                    chunks.append({
                        "content": current_chunk.strip(),
                        "page": page_num + 1,
                        "textbook": "必修1",
                        "chapter": "待识别"
                    })
                # 开始新chunk
                current_chunk = para + "\n\n"

        # 保存最后一个chunk
        if current_chunk:
            chunks.append({
                "content": current_chunk.strip(),
                "page": page_num + 1,
                "textbook": "必修1",
                "chapter": "待识别"
            })

    print(f"✅ 提取完成：{len(chunks)} 个片段")
    return chunks


def build_index(chunks):
    """构建向量索引"""
    print(f"\n🔨 开始构建向量索引...")

    # 加载中文embedding模型
    print("  加载embedding模型...")
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    # 创建临时数据库（内存）
    print("  创建向量数据库...")
    client = chromadb.Client()
    collection = client.create_collection(
        name="test_biology",
        metadata={"hnsw:space": "cosine"}
    )

    # 批量添加
    print(f"  向量化{len(chunks)}个片段...")
    batch_size = 10
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]

        # 生成embeddings
        texts = [c['content'] for c in batch]
        embeddings = model.encode(texts)

        # 添加到数据库
        collection.add(
            ids=[f"chunk_{j}" for j in range(i, i+len(batch))],
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=[{
                "page": c['page'],
                "textbook": c['textbook']
            } for c in batch]
        )

        print(f"  进度: {min(i+batch_size, len(chunks))}/{len(chunks)}")

    print(f"✅ 索引构建完成！")
    return collection, model


def test_retrieval(collection, model):
    """测试检索准确性"""
    print(f"\n🔍 开始测试检索...")
    print("="*70)

    # 测试查询（针对必修1的典型知识点）
    test_queries = [
        {
            "query": "细胞膜的结构和功能",
            "expected_chapter": "第3章或第4章",
            "expected_keywords": ["细胞膜", "磷脂双分子层", "流动镶嵌模型"]
        },
        {
            "query": "被动运输和主动运输的区别",
            "expected_chapter": "第4章",
            "expected_keywords": ["被动运输", "主动运输", "渗透", "载体蛋白"]
        },
        {
            "query": "ATP的结构和功能",
            "expected_chapter": "第5章",
            "expected_keywords": ["ATP", "腺苷", "高能磷酸键"]
        },
        {
            "query": "光合作用的过程",
            "expected_chapter": "第5章",
            "expected_keywords": ["光合作用", "叶绿体", "光反应", "暗反应"]
        },
        {
            "query": "细胞呼吸的类型",
            "expected_chapter": "第5章",
            "expected_keywords": ["有氧呼吸", "无氧呼吸", "线粒体"]
        }
    ]

    total_score = 0

    for i, test in enumerate(test_queries, 1):
        print(f"\n【测试 {i}】")
        print(f"查询: {test['query']}")
        print(f"期望章节: {test['expected_chapter']}")
        print(f"期望关键词: {', '.join(test['expected_keywords'])}")
        print("-"*70)

        # 向量检索
        query_embedding = model.encode(test['query'])
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=5  # 返回Top 5
        )

        # 分析结果
        hit_count = 0
        for j, doc in enumerate(results['documents'][0]):
            page = results['metadatas'][0][j]['page']
            similarity = 1 - results['distances'][0][j]

            # 检查是否包含期望关键词
            keyword_hits = [kw for kw in test['expected_keywords'] if kw in doc]

            print(f"\n  Top {j+1}: (页码: {page}, 相似度: {similarity:.3f})")
            if keyword_hits:
                print(f"  ✅ 命中关键词: {', '.join(keyword_hits)}")
                hit_count += 1
            else:
                print(f"  ❌ 未命中关键词")

            # 显示内容预览
            preview = doc[:150].replace('\n', ' ')
            print(f"  内容: {preview}...")

        # 计算该查询的得分
        query_score = hit_count / 5  # Top 5中命中的比例
        total_score += query_score

        print(f"\n  📊 该查询得分: {query_score:.1%} ({hit_count}/5命中)")
        print("="*70)

    # 总体评估
    avg_score = total_score / len(test_queries)
    print(f"\n" + "="*70)
    print(f"📊 总体检索准确率: {avg_score:.1%}")
    print("="*70)

    if avg_score >= 0.8:
        print("✅ 检索准确率优秀！可以继续下一步")
        return True
    elif avg_score >= 0.6:
        print("⚠️  检索准确率中等，建议优化检索策略")
        return True
    else:
        print("❌ 检索准确率较低，需要调整方案")
        return False


if __name__ == "__main__":
    print("="*70)
    print("🧪 向量检索准确性测试")
    print("="*70)
    print("测试范围: 必修1前50页\n")

    # PDF路径
    pdf_path = r"D:\学术\人教版\高中生物\普通高中教科书·生物学必修1分子与细胞.pdf"

    # 第1步：提取chunks
    chunks = extract_chunks(pdf_path, max_pages=50)

    # 第2步：构建索引
    collection, model = build_index(chunks)

    # 第3步：测试检索
    success = test_retrieval(collection, model)

    print(f"\n" + "="*70)
    if success:
        print("✅ 测试通过！可以进行下一步（LLM关联度分析）")
    else:
        print("❌ 测试失败！需要优化检索策略")
    print("="*70)
