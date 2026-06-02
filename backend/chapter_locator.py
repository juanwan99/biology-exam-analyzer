"""
章节定位服务
根据页码和教材ID定位到具体章节
"""
import json
import os
import re
from typing import Dict, Optional, Any

# 目录配置文件路径
TOC_FILE = os.path.join(os.path.dirname(__file__), "rules", "textbook_toc.json")

class ChapterLocator:
    """章节定位器"""

    def __init__(self):
        self.toc = self._load_toc()

    def _load_toc(self) -> Dict:
        """加载目录配置"""
        try:
            with open(TOC_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[章节定位] 加载目录失败: {e}")
            return {}

    def get_chapter_info(self, book_id: str, page_num: int) -> Dict[str, Any]:
        """
        根据教材ID和页码获取章节信息

        Args:
            book_id: 教材ID (如 bx1, bx2, xxbx1)
            page_num: PDF页码

        Returns:
            {
                "chapter": "第3章",
                "chapter_title": "细胞的基本结构",
                "section": "第1节",
                "section_title": "细胞膜的结构和功能",
                "location": "必修1 > 第3章 细胞的基本结构 > 第1节 细胞膜的结构和功能"
            }
        """
        if book_id not in self.toc:
            return {}

        book_info = self.toc[book_id]
        chapters = book_info.get("chapters", [])
        short_name = book_info.get("short_name", book_id)

        # 找到对应章节
        current_chapter = None
        current_section = None

        for chapter in chapters:
            chapter_start = chapter.get("start_page", 0)

            # 检查是否在这一章范围内
            if page_num >= chapter_start:
                current_chapter = chapter

                # 在章内查找节
                for section in chapter.get("sections", []):
                    section_start = section.get("start_page", 0)
                    if page_num >= section_start:
                        current_section = section

        if not current_chapter:
            return {}

        result = {
            "chapter": current_chapter.get("chapter", ""),
            "chapter_title": current_chapter.get("title", ""),
        }

        if current_section:
            result["section"] = current_section.get("section", "")
            result["section_title"] = current_section.get("title", "")
            result["location"] = f"{short_name} > {result['chapter']} {result['chapter_title']} > {result['section']} {result['section_title']}"
        else:
            result["section"] = ""
            result["section_title"] = ""
            result["location"] = f"{short_name} > {result['chapter']} {result['chapter_title']}"

        return result

    def extract_section_from_markdown(self, markdown_content: str) -> Optional[str]:
        """
        从Markdown内容中提取小节标题（作为补充）

        Args:
            markdown_content: Markdown文本

        Returns:
            提取到的第一个标题，如 "对细胞膜结构的探索"
        """
        # 匹配 ## 或 ### 开头的标题
        pattern = r'^#{2,3}\s+(.+?)$'
        match = re.search(pattern, markdown_content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def get_full_location(self, book_id: str, page_num: int, markdown_content: str = None) -> Dict[str, Any]:
        """
        获取完整定位信息（结合目录+Markdown标题）

        Returns:
            {
                "book_id": "bx1",
                "page_num": 52,
                "chapter": "第3章",
                "chapter_title": "细胞的基本结构",
                "section": "第1节",
                "section_title": "细胞膜的结构和功能",
                "subsection": "对细胞膜结构的探索",  # 从Markdown提取
                "location": "必修1 > 第3章 > 第1节 > 对细胞膜结构的探索"
            }
        """
        info = self.get_chapter_info(book_id, page_num)
        info["book_id"] = book_id
        info["page_num"] = page_num

        # 尝试从Markdown提取小节标题
        if markdown_content:
            subsection = self.extract_section_from_markdown(markdown_content)
            if subsection:
                info["subsection"] = subsection
                # 更新location，加入小节信息
                if "location" in info:
                    info["location"] = f"{info['location']} > {subsection}"

        return info


# 全局实例
_locator = None

def get_locator() -> ChapterLocator:
    """获取章节定位器单例"""
    global _locator
    if _locator is None:
        _locator = ChapterLocator()
    return _locator


def locate_chapter(book_id: str, page_num: int, markdown_content: str = None) -> Dict[str, Any]:
    """便捷函数：定位章节"""
    return get_locator().get_full_location(book_id, page_num, markdown_content)


# 测试
if __name__ == "__main__":
    locator = ChapterLocator()

    # 测试必修1第52页
    result = locator.get_full_location("bx1", 52, "## 对细胞膜结构的探索\n\n内容...")
    print("必修1第52页:", result)

    # 测试必修1第30页
    result = locator.get_full_location("bx1", 30)
    print("必修1第30页:", result)

    # 测试必修2第50页
    result = locator.get_full_location("bx2", 50)
    print("必修2第50页:", result)
