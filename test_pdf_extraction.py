"""
测试教材PDF文本提取质量
用于验证PDF是否可以正确提取文字
"""
import fitz  # PyMuPDF
import sys

def test_extraction(pdf_path):
    """测试PDF文本提取"""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"❌ 无法打开PDF: {e}")
        return False

    print("="*70)
    print(f"📚 PDF信息")
    print("="*70)
    print(f"文件路径: {pdf_path}")
    print(f"总页数: {len(doc)}")
    print(f"PDF版本: {doc.metadata.get('format', '未知')}")
    print()

    # 测试前3页
    print("="*70)
    print("📄 前3页内容测试")
    print("="*70)
    for i in range(min(3, len(doc))):
        page = doc[i]
        text = page.get_text()

        print(f"\n【第{i+1}页】")
        print(f"字数: {len(text)}")
        if len(text) > 0:
            preview = text[:300].replace('\n', ' ')
            print(f"预览: {preview}...")
        else:
            print("⚠️  该页无文本（可能是图片页）")
        print("-"*70)

    # 测试中间某页（正文）
    mid_idx = len(doc) // 2
    mid_page = doc[mid_idx]
    mid_text = mid_page.get_text()

    print(f"\n【第{mid_idx+1}页（正文页）】")
    print(f"字数: {len(mid_text)}")
    print(f"内容:\n{mid_text[:600]}")
    print("-"*70)

    # 质量检查
    print("\n" + "="*70)
    print("🔍 质量检查")
    print("="*70)

    issues = []
    warnings = []

    # 检查乱码
    if "�" in mid_text:
        issues.append("❌ 检测到乱码字符（�）")
    else:
        print("✅ 无乱码")

    # 检查字数
    if len(mid_text) < 100:
        warnings.append("⚠️  提取字数过少（<100字），可能是扫描版或图片页")
    else:
        print(f"✅ 字数正常（{len(mid_text)}字）")

    # 检查换行密度
    newline_ratio = mid_text.count("\n") / len(mid_text) if len(mid_text) > 0 else 0
    if newline_ratio > 0.1:
        warnings.append(f"⚠️  换行过多（{newline_ratio:.1%}），可能是多栏排版或表格")
    else:
        print(f"✅ 换行正常（{newline_ratio:.1%}）")

    # 检查是否有中文
    chinese_chars = sum(1 for c in mid_text if '\u4e00' <= c <= '\u9fff')
    if chinese_chars < len(mid_text) * 0.3:
        warnings.append(f"⚠️  中文字符占比较低（{chinese_chars/len(mid_text):.1%}）")
    else:
        print(f"✅ 中文字符正常（{chinese_chars/len(mid_text):.1%}）")

    # 统计信息
    print(f"\n📊 统计信息:")
    total_chars = sum(len(page.get_text()) for page in doc)
    print(f"  - 全书总字数（估算）: {total_chars:,}")
    print(f"  - 平均每页字数: {total_chars // len(doc):,}")

    # 输出问题和警告
    if issues:
        print("\n❌ 发现问题:")
        for issue in issues:
            print(f"  {issue}")

    if warnings:
        print("\n⚠️  警告:")
        for warning in warnings:
            print(f"  {warning}")

    # 总结
    print("\n" + "="*70)
    if not issues and len(warnings) <= 1:
        print("✅ 文本提取质量良好，可以继续进行向量化")
        return True
    elif not issues:
        print("⚠️  文本提取基本可用，但可能需要额外处理")
        return True
    else:
        print("❌ 文本提取质量较差，建议检查PDF或使用OCR")
        return False


if __name__ == "__main__":
    # 测试必修1
    pdf_path = r"D:\学术\人教版\高中生物\普通高中教科书·生物学必修1分子与细胞.pdf"

    print("\n" + "="*70)
    print("🧪 教材PDF提取质量测试")
    print("="*70)
    print(f"测试文件: 必修1 分子与细胞\n")

    success = test_extraction(pdf_path)

    print("\n" + "="*70)
    if success:
        print("✅ 测试通过！可以进行下一步（向量索引构建）")
    else:
        print("❌ 测试失败！需要调整方案")
    print("="*70)
