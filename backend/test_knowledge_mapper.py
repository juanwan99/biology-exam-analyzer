from knowledge_mapper import KnowledgeMapper


def test_zhuzhou_yimo_standard_terms_map_to_textbook_nodes():
    mapper = KnowledgeMapper()
    terms = [
        "现代生物进化理论的主要内容",
        "生物进化的证据",
        "水和无机盐的平衡与调节",
        "细胞质遗传",
        "基因的连锁与互换定律",
        "全球性生态环境问题",
        "细胞间信息交流",
        "遗传的基本规律",
        "杂交育种",
    ]

    results = mapper.map_knowledge_points(terms)

    assert [item["original"] for item in results] == terms
    assert all(item["mapped"] for item in results)
    assert {item["textbook"] for item in results} >= {"必修1", "必修2", "选择性必修1", "选择性必修2"}
