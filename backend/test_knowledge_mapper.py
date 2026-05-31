from knowledge_mapper import KnowledgeMapper
from analysis_calibration import (
    canonicalize_knowledge_point,
    is_non_textbook_skill_point,
    normalize_knowledge_links,
)


def test_zhuzhou_yimo_standard_terms_map_to_textbook_nodes():
    mapper = KnowledgeMapper()
    terms = [
        "现代生物进化理论的主要内容",
        "生物进化的证据",
        "多倍体形成",
        "配子形成",
        "配子的形成与受精",
        "外植体",
        "水体污染的生物净化",
        "营养结构",
        "生态工程的基本原理",
        "系统学与工程学原理",
        "水和无机盐的平衡与调节",
        "无机盐离子与渗透压的关系",
        "K+浓度变化对渗透压的微小影响",
        "细胞质遗传",
        "细胞质基因的传递特点",
        "母系遗传",
        "基因的连锁与互换定律",
        "全球性生态环境问题",
        "细胞间信息交流",
        "细胞间的信息交流",
        "外泌体介导的细胞间通讯",
        "靶细胞和受体的概念",
        "遗传的基本规律",
        "杂交育种",
    ]

    results = mapper.map_knowledge_points(terms)

    assert [item["original"] for item in results] == terms
    assert all(item["mapped"] for item in results)
    assert {item["textbook"] for item in results} >= {"必修1", "必修2", "选择性必修1", "选择性必修2"}


def test_deepseek_fragmented_biotech_terms_are_merged_before_score_aggregation():
    mapper = KnowledgeMapper()

    links, diagnostics = normalize_knowledge_links(
        [
            {"knowledge_point": "PCR引物设计的原则", "share": 0.35},
            {"knowledge_point": "PCR引物与模板的特异性结合", "share": 0.35},
            {"knowledge_point": "引物设计中的模板结合区域", "share": 0.30},
            {"knowledge_point": "实验数据分析", "share": 0.20},
        ],
        knowledge_mapper=mapper,
    )

    assert diagnostics["changed"] is True
    assert links == [{"knowledge_point": "PCR技术扩增目的基因", "share": 1.0}]
    assert mapper.map_knowledge_point(links[0]["knowledge_point"])["mapped"] is True


def test_calibration_maps_deepseek_yimo_unmapped_terms():
    mapper = KnowledgeMapper()
    terms = [
        "基因连锁与配子类型",
        "基因连锁与标记基因",
        "水稻育种流程与保持系功能",
        "致死基因对后代比例的影响",
        "aabb胚胎致死条件",
        "脂质的种类与功能",
        "脂质的分类",
        "整体性原理",
        "次生代谢产物",
        "人工膜系统的构建",
        "琼脂糖凝胶电泳条带分析",
        "富集作用",
        "茎尖组织培养获得脱毒苗的原理",
        "茎尖培养脱毒的原理",
        "植物脱毒技术",
        "转运肽的靶向功能",
        "TOC-TIC复合体的作用",
        "优势种的概念",
        "巨噬细胞功能",
        "外泌体介导的细胞间通讯",
        "NADPH的生成",
        "表观遗传修饰",
        "细胞与工程",
        "分子水平进化证据",
        "胰岛素的化学本质",
        "胰岛素本质",
        "胰岛素的性质",
        "蛋白质的合成场所",
        "胰岛细胞功能与受体",
        "靶细胞和受体的概念",
        "性激素的化学本质",
        "生长素的化学本质",
        "核膜的周期性变化",
        "根尖细胞解离的原理与操作",
        "解离的作用",
        "解离的目的与注意事项",
        "解离时间对实验效果的影响",
        "通过细胞数量占比推断各时期相对长短的方法",
        "细胞数量比例与时长的关系",
        "抑菌活性变化",
        "乳酸菌代谢与细菌素产生",
        "竞争与捕食的相互作用",
        "竞争关系",
        "捕食关系",
        "捕食者对猎物的选择",
        "捕食者与被捕食者的相互关系",
        "捕食者对优势种的调节作用",
        "非生物因素对生物的影响",
        "钾离子的生理作用",
        "钾离子在体液中的分布",
        "钾离子对渗透压的贡献",
        "K+浓度变化对渗透压的微小影响",
        "腹泻导致钾丢失",
        "物质丢失与电解质平衡",
        "电解质稳态",
        "腹泻对水和无机盐平衡的影响",
        "低血钾症的常见诱因",
        "细胞质基因的遗传特点",
        "智能保持系自交后代分离",
        "不育系与保持系的关系",
        "基因的分离与配子类型",
        "配子的形成与受精",
        "配子结合的条件分析",
        "基因连锁与遗传规律",
        "荧光标记基因的遗传",
        "基因插入突变与功能缺失",
        "遗传杂交与致死设计",
        "基因敲除与致死效应",
        "动态突变与前突变传递",
        "突变类型辨析",
        "基因型与表型的关系",
        "连锁遗传",
        "CGG重复扩增的致病机制",
        "三核苷酸重复扩增",
        "膜的选择透过性",
        "扩散与能量消耗",
        "信号肽的作用",
        "受体的识别作用",
        "前体蛋白与成熟蛋白的结构差异",
        "人工合成生物学的应用",
        "初生代谢与次级代谢",
        "杂种优势的利用",
        "pH与质子浓度梯度的关系",
        "环境污染的防治",
        "基因致死机制",
        "细胞死亡类型：凋亡与坏死",
        "细胞坏死的概念",
        "多肽的消化与安全性",
        "RNaseH的作用位点",
        "蛋白分选与运输",
        "引物位置与方向分析",
        "基因插入方向鉴定",
        "引物结合位点距离",
        "重组子鉴定策略",
        "核苷酸的组成",
        "物质传递的形式",
        "不完全外显与遗传咨询",
        "pH对离子浓度的影响",
        "基因的连锁与分离",
        "自交后代分离规律",
        "杂交后代的基因型推断",
        "遗传设计中的安全性策略",
        "细胞间的间接作用",
        "茎尖分生组织病毒含量极低",
        "花药离体培养",
        "基因频率",
        "GLP-1的功能与应用",
        "中期识别与数目计算",
        "解离操作要求",
        "间期时长估算",
        "观察实验中细胞比例的应用",
        "脱毒苗培养的原理",
        "茎尖分生组织特性",
        "植物病毒分布与脱毒",
        "细胞内液与细胞外液的离子分布",
        "化学渗透学说",
        "保持系的功能与优势退化",
        "自交后代比例计算",
        "生态安全评价",
        "自交后代的基因型与表现型",
        "基因定位与插入失活",
        "CRISPR-Cas9原理",
        "环境容纳量",
        "合成生物学应用",
        "人工浮床技术的特点",
        "细胞培养与条件控制",
        "基因逃逸与生态风险",
        "引物序列分析",
    ]

    canonical_terms = [
        canonicalize_knowledge_point(term, knowledge_mapper=mapper)[0]
        for term in terms
    ]
    results = mapper.map_knowledge_points(canonical_terms)

    assert all(item["mapped"] for item in results)
    assert canonical_terms[:7] == [
        "基因的连锁与互换定律",
        "基因的连锁与互换定律",
        "雄性不育系与杂交育种",
        "遗传致死",
        "遗传致死",
        "细胞中的糖类和脂质",
        "细胞中的糖类和脂质",
    ]


def test_canonicalization_does_not_narrow_broad_textbook_terms():
    mapper = KnowledgeMapper()

    assert canonicalize_knowledge_point("光合作用", knowledge_mapper=mapper)[0] == "光合作用"
    assert canonicalize_knowledge_point("光合作用的光反应", knowledge_mapper=mapper)[0] == "光合作用的光反应"


def test_calibration_maps_gamete_fusion_condition_terms():
    mapper = KnowledgeMapper()

    for term in ["配子结合的条件限制", "配子结合限制的应用", "配子的形成与受精", "配子类型与受精"]:
        canonical, meta = canonicalize_knowledge_point(term, knowledge_mapper=mapper)
        assert canonical == "受精作用"
        assert meta["mapped"] is True
        assert mapper.map_knowledge_point(canonical)["mapped"] is True


def test_calibration_maps_current_deepseek_generation_leaks():
    mapper = KnowledgeMapper()

    cases = {
        "核苷酸的组成": "核酸是遗传信息的携带者",
        "物质传递的形式": "物质循环",
        "不完全外显与遗传咨询": "遗传病",
        "pH对离子浓度的影响": "光合作用的光反应",
        "基因的连锁与分离": "基因的连锁与互换定律",
        "不育系与保持系的关系": "雄性不育系与杂交育种",
        "自交后代分离规律": "基因的分离定律",
        "基因敲除与致死效应": "遗传致死",
        "杂交后代的基因型推断": "遗传的基本规律",
        "遗传设计中的安全性策略": "生物安全",
        "植物病毒分布与脱毒": "茎尖脱毒",
        "植物病毒分布与茎尖特点": "茎尖脱毒",
        "细胞内液与细胞外液的离子分布": "人体内环境稳态",
        "化学渗透学说": "光合作用的光反应",
        "保持系的功能与优势退化": "雄性不育系与杂交育种",
        "自交后代比例计算": "基因的分离定律",
        "生态安全评价": "生物安全",
        "自交后代的基因型与表现型": "基因的分离定律",
        "基因定位与插入失活": "基因工程的基本操作程序",
        "CRISPR-Cas9原理": "基因工程",
        "环境容纳量": "种群数量的变化",
        "合成生物学应用": "人工光合",
        "人工浮床技术的特点": "生态工程",
        "细胞培养与条件控制": "动物细胞培养",
        "基因逃逸与生态风险": "生物安全",
        "引物序列分析": "PCR技术扩增目的基因",
        "生物进化的分子证据": "生物进化的证据",
        "脱毒苗培育": "茎尖脱毒",
        "环境污染的治理": "全球性生态环境问题",
        "辨析遗传变异类型": "基因突变",
        "配子类型与比例": "基因的分离定律",
        "杂交水稻育种原理": "雄性不育系与杂交育种",
        "杂交水稻的繁育体系": "雄性不育系与杂交育种",
        "基因漂移": "种群基因组成的变化",
        "基因定位与功能": "基因工程的基本操作程序",
        "引物功能序列设计": "PCR技术扩增目的基因",
        "光系统I和光系统II的功能": "光合作用的光反应",
        "光系统I和II的功能": "光合作用的光反应",
        "光呼吸与能量效率": "光合作用",
        "脱毒苗的获取方法": "茎尖脱毒",
        "基因导入位置对遗传的影响": "细胞质遗传",
        "细胞质基因的传递特点": "细胞质遗传",
        "母系遗传": "细胞质遗传",
        "系统学与工程学原理": "生态工程的基本原理",
        "连锁与配子选择": "基因的连锁与互换定律",
        "不育系的繁殖": "雄性不育系与杂交育种",
        "保持系功能": "雄性不育系与杂交育种",
        "体液运输与靶细胞识别": "激素调节的过程",
        "食欲调节与体重控制": "激素调节的过程",
        "基因序列比较": "生物进化的证据",
        "竞争力与存活率的关系": "种间关系",
        "生物大分子的跨膜转运机制": "蛋白质的定向转运",
        "受体蛋白的功能": "细胞间信息交流",
        "受体上调和下调的调节机制": "细胞间信息交流",
        "受体敏感性调节": "细胞间信息交流",
        "防止二次污染": "生态工程的基本原理",
        "细胞培养与处理条件": "动物细胞培养",
        "育种流程设计": "雄性不育系与杂交育种",
        "脂质中的固醇类": "细胞中的糖类和脂质",
        "多肽的化学性质": "蛋白质是生命活动的主要承担者",
        "序列分析（阅读序列图）": "PCR技术扩增目的基因",
        "引物方向与扩增": "PCR技术扩增目的基因",
        "自然固碳途径（卡尔文循环）": "碳固定",
        "人工固碳系统的特点": "人工光合",
        "能量利用效率": "光合作用的光反应",
        "环境阻力与S形曲线": "种群数量的变化",
        "染色单体的概念": "细胞的有丝分裂",
        "腹泻导致K+丢失": "人体内环境稳态",
        "配子类型与概率": "基因的分离定律",
        "配子类型与可育性": "受精作用",
        "遗传分离比": "基因的分离定律",
        "自交后代基因型变化": "基因的分离定律",
        "自交后代的选择": "基因的分离定律",
        "自交与受精限制": "受精作用",
        "规避蛋白定位干扰的策略": "蛋白质的定向转运",
        "引物位置与产物大小计算": "PCR技术扩增目的基因",
        "基因扩增的原理": "PCR技术扩增目的基因",
        "受精限制条件分析": "受精作用",
        "色氨酸是合成前体而非构成单位": "生长素的化学本质",
        "环境阻力与资源限制": "种群数量的变化",
        "跨膜质子梯度": "光合作用的光反应",
        "富集植物的特性": "生物富集",
        "水体污染治理": "全球性生态环境问题",
        "荧光标记基因的应用": "基因的连锁与互换定律",
        "基因连锁的遗传": "基因的连锁与互换定律",
        "基因连锁与遗传设计": "基因的连锁与互换定律",
        "基因的连锁与应用": "基因的连锁与互换定律",
        "基因的连锁与交换": "基因的连锁与互换定律",
        "花粉致死基因的遗传效应": "遗传致死",
        "细菌生长曲线与代谢产物": "发酵工程及其应用",
        "细菌素产生与菌密度的关系": "发酵工程及其应用",
        "次生代谢与初生代谢": "次级代谢产物",
        "显微观察统计周期的局限性": "细胞周期",
        "受精过程中细胞质的分配": "细胞质遗传",
        "配子类型的多样性": "基因的分离定律",
        "CO₂在培养中的作用": "动物细胞培养",
        "细菌素产生与积累规律": "发酵工程及其应用",
        "脆性X综合征的分子机制": "遗传病",
        "外显率与表现度": "遗传病",
        "代谢途径的顺序性": "人工光合",
        "pH对质子梯度的影响": "光合作用的光反应",
        "代谢途径的综合调节": "人工光合",
        "质子动力势": "光合作用的光反应",
        "代谢途径的定向优化": "人工光合",
        "多倍体育种": "多倍体形成",
        "水体修复植物的生长特性": "水体污染的生物净化",
        "植物修复的原理": "水体污染的生物净化",
        "废弃物资源化": "生态工程的基本原理",
        "经济效益与生态效益结合": "生态工程的基本原理",
        "水体治理方法": "水体污染的生物净化",
        "细胞培养与刺激条件": "动物细胞培养",
        "基因逃逸与环境污染": "生物安全",
        "基因逃逸与环境影响": "生物安全",
        "红色荧光蛋白的表达特点": "基因表达与性状的关系",
        "基因甲基化与表达调控": "表观遗传",
        "致死机制与基因定位": "基因工程的基本操作程序",
        "竞争力相对强弱判断": "种间关系",
        "生态浮床植物选择原则": "生态工程",
        "保持系的概念": "雄性不育系与杂交育种",
        "基因定点整合": "基因工程的基本操作程序",
        "电泳技术原理": "PCR技术扩增目的基因",
    }
    for raw, expected in cases.items():
        canonical, meta = canonicalize_knowledge_point(raw, knowledge_mapper=mapper)
        assert canonical == expected
        assert meta["mapped"] is True
        assert mapper.map_knowledge_point(canonical)["mapped"] is True


def test_calibration_maps_ecology_context_labels_to_textbook_terms():
    mapper = KnowledgeMapper()

    cases = {
        "生态因子对生物的影响": "环境因素参与调节植物的生命活动",
        "生态修复的植物选择原则": "生态工程",
    }
    for raw, expected in cases.items():
        canonical, meta = canonicalize_knowledge_point(raw, knowledge_mapper=mapper)
        assert canonical == expected
        assert meta["mapped"] is True
        assert mapper.map_knowledge_point(canonical)["mapped"] is True


def test_calibration_filters_context_and_method_terms_from_textbook_scores():
    mapper = KnowledgeMapper()
    links, diagnostics = normalize_knowledge_links(
        [
            {"knowledge_point": "细胞共培养技术", "share": 0.4},
            {"knowledge_point": "外泌体内容物检测", "share": 0.3},
            {"knowledge_point": "外泌体内容物分析", "share": 0.3},
            {"knowledge_point": "实验数据的读取与比较", "share": 0.2},
            {"knowledge_point": "实验数据比较分析", "share": 0.2},
            {"knowledge_point": "实验数据的解读与推论", "share": 0.2},
            {"knowledge_point": "实验数据的分析与决策", "share": 0.2},
            {"knowledge_point": "实验数据的比较与分析", "share": 0.2},
            {"knowledge_point": "实验数据的处理与估算", "share": 0.2},
            {"knowledge_point": "实验数据的完整获取", "share": 0.2},
            {"knowledge_point": "实验逻辑推断", "share": 0.2},
            {"knowledge_point": "实验数据的统计分析要求", "share": 0.2},
            {"knowledge_point": "数据的相关性分析", "share": 0.2},
            {"knowledge_point": "相关性分析", "share": 0.2},
            {"knowledge_point": "相关性判断", "share": 0.2},
            {"knowledge_point": "正相关的概念与判断", "share": 0.2},
            {"knowledge_point": "控制变量", "share": 0.2},
            {"knowledge_point": "实验变量的检测与设计", "share": 0.2},
            {"knowledge_point": "实验的平行重复与检测指标", "share": 0.2},
            {"knowledge_point": "显微镜观察统计方法", "share": 0.2},
            {"knowledge_point": "图表中变量关系的综合分析", "share": 0.2},
            {"knowledge_point": "图表信息的提取与分析", "share": 0.2},
            {"knowledge_point": "数据图表的解读", "share": 0.2},
            {"knowledge_point": "图表趋势解读", "share": 0.2},
            {"knowledge_point": "双轴图表的数据关联分析", "share": 0.2},
            {"knowledge_point": "图表数据的趋势分析与因果关系", "share": 0.2},
            {"knowledge_point": "图表数据的解读", "share": 0.2},
            {"knowledge_point": "图表数据的解读与分析", "share": 0.2},
            {"knowledge_point": "双变量曲线图的分析", "share": 0.2},
            {"knowledge_point": "曲线图的综合分析", "share": 0.2},
            {"knowledge_point": "实验结果对照分析", "share": 0.2},
            {"knowledge_point": "实验结果的数据比较与解读", "share": 0.2},
            {"knowledge_point": "实验对照分析", "share": 0.2},
            {"knowledge_point": "实验对照与变量分析", "share": 0.2},
            {"knowledge_point": "实验操作注意事项", "share": 0.2},
            {"knowledge_point": "实验中排除干扰的方法", "share": 0.2},
            {"knowledge_point": "抑制剂的验证作用", "share": 0.2},
            {"knowledge_point": "实验设计中的等量原则", "share": 0.2},
            {"knowledge_point": "食品添加剂的安全性评估", "share": 0.2},
            {"knowledge_point": "食品安全性评价", "share": 0.2},
            {"knowledge_point": "食品安全评估", "share": 0.2},
            {"knowledge_point": "电泳结果分析", "share": 0.2},
            {"knowledge_point": "电泳图读图能力", "share": 0.2},
            {"knowledge_point": "遗传分析与电泳解读", "share": 0.2},
            {"knowledge_point": "健康生活与疾病防治", "share": 0.2},
            {"knowledge_point": "食欲调控与体重管理", "share": 0.2},
            {"knowledge_point": "细胞纤维化的标志蛋白", "share": 0.2},
            {"knowledge_point": "口腔黏膜纤维化的细胞学机制", "share": 0.2},
            {"knowledge_point": "纤维化相关蛋白的表达", "share": 0.2},
            {"knowledge_point": "慢性炎症与疾病", "share": 0.2},
            {"knowledge_point": "槟榔碱的致病机制", "share": 0.1},
            {"knowledge_point": "槟榔碱的致病通路", "share": 0.1},
            {"knowledge_point": "槟榔碱通过外泌体miR-155-5P致纤维化机制", "share": 0.1},
            {"knowledge_point": "细胞纤维化的诱导机制", "share": 0.2},
            {"knowledge_point": "成纤维细胞活化与胶原沉积", "share": 0.2},
            {"knowledge_point": "炎症与纤维化的关系", "share": 0.2},
            {"knowledge_point": "外泌体内含物的检测", "share": 0.2},
            {"knowledge_point": "产物的应用价值", "share": 0.2},
            {"knowledge_point": "药物应用推断", "share": 0.2},
            {"knowledge_point": "FoxP3基因功能", "share": 0.2},
            {"knowledge_point": "代谢产物活性的动态变化", "share": 0.2},
            {"knowledge_point": "乳酸菌密度与代谢产物的动态变化", "share": 0.2},
            {"knowledge_point": "细菌素的产量与培养时间的关系", "share": 0.2},
            {"knowledge_point": "配子类型分析", "share": 0.2},
            {"knowledge_point": "配子类型与受精条件分析", "share": 0.2},
            {"knowledge_point": "基因导入与遗传分析", "share": 0.2},
            {"knowledge_point": "异常蛋白积累的致病机理", "share": 0.2},
            {"knowledge_point": "根据题干信息分析致病机制", "share": 0.2},
            {"knowledge_point": "假说演绎法", "share": 0.2},
            {"knowledge_point": "LEC2的可能作用机制", "share": 0.2},
            {"knowledge_point": "实验结果的分析与解读", "share": 0.2},
            {"knowledge_point": "实验结果的逻辑分析", "share": 0.2},
            {"knowledge_point": "实验结果的分析与比较", "share": 0.2},
            {"knowledge_point": "实验结果的图表分析", "share": 0.2},
            {"knowledge_point": "科学结论的证据强度", "share": 0.2},
            {"knowledge_point": "乳酸菌密度与代谢产物积累", "share": 0.2},
            {"knowledge_point": "分析致病分子机制", "share": 0.2},
            {"knowledge_point": "外泌体内容物的检测", "share": 0.2},
            {"knowledge_point": "外泌体的内含物", "share": 0.2},
            {"knowledge_point": "α-SMA和胶原蛋白的纤维化标志", "share": 0.2},
            {"knowledge_point": "纤维化形成的分子机制", "share": 0.2},
            {"knowledge_point": "单一变量原则", "share": 0.2},
            {"knowledge_point": "产物分离与工业应用", "share": 0.2},
            {"knowledge_point": "基于序列的连接点分析", "share": 0.2},
            {"knowledge_point": "外泌体的功能", "share": 0.5},
            {"knowledge_point": "外泌体的内容物分析", "share": 0.2},
        ],
        knowledge_mapper=mapper,
    )

    assert diagnostics["changed"] is True
    assert is_non_textbook_skill_point("细胞共培养技术") is True
    assert is_non_textbook_skill_point("外泌体内容物检测") is True
    assert is_non_textbook_skill_point("外泌体内容物分析") is True
    assert is_non_textbook_skill_point("健康生活与疾病防治") is True
    assert is_non_textbook_skill_point("疾病诊断逻辑") is True
    assert is_non_textbook_skill_point("FoxP3基因功能") is True
    assert is_non_textbook_skill_point("图表中变量关系的综合分析") is True
    assert is_non_textbook_skill_point("图表信息的提取与分析") is True
    assert is_non_textbook_skill_point("数据图表的解读") is True
    assert is_non_textbook_skill_point("图表趋势解读") is True
    assert is_non_textbook_skill_point("双轴图数据趋势解读") is True
    assert is_non_textbook_skill_point("实验数据的解读与推论") is True
    assert is_non_textbook_skill_point("实验数据比较分析") is True
    assert is_non_textbook_skill_point("双轴图表的数据关联分析") is True
    assert is_non_textbook_skill_point("图表数据的解读与分析") is True
    assert is_non_textbook_skill_point("图表数据的解读与判断") is True
    assert is_non_textbook_skill_point("图表数据的解读") is True
    assert is_non_textbook_skill_point("双变量曲线图的分析") is True
    assert is_non_textbook_skill_point("曲线图的综合分析") is True
    assert is_non_textbook_skill_point("曲线趋势分析") is True
    assert is_non_textbook_skill_point("实验数据的分析与决策") is True
    assert is_non_textbook_skill_point("实验数据的比较与分析") is True
    assert is_non_textbook_skill_point("实验逻辑推断") is True
    assert is_non_textbook_skill_point("实验推理与评估") is True
    assert is_non_textbook_skill_point("实验数据的统计分析要求") is True
    assert is_non_textbook_skill_point("相关性分析") is True
    assert is_non_textbook_skill_point("相关性判断") is True
    assert is_non_textbook_skill_point("正相关的概念与判断") is True
    assert is_non_textbook_skill_point("正相关的概念") is True
    assert is_non_textbook_skill_point("控制变量") is True
    assert is_non_textbook_skill_point("实验变量的检测与设计") is True
    assert is_non_textbook_skill_point("实验变量的控制") is True
    assert is_non_textbook_skill_point("多变量实验的分析方法") is True
    assert is_non_textbook_skill_point("基因功能验证（抑制剂实验）") is True
    assert is_non_textbook_skill_point("实验结果与结论的逻辑关系") is True
    assert is_non_textbook_skill_point("变量间正相关关系的判断") is True
    assert is_non_textbook_skill_point("显微镜观察统计方法") is True
    assert is_non_textbook_skill_point("实验结果对照分析") is True
    assert is_non_textbook_skill_point("实验对照设计") is True
    assert is_non_textbook_skill_point("实验结果的读取与比较") is True
    assert is_non_textbook_skill_point("实验结果的对比分析") is True
    assert is_non_textbook_skill_point("实验结果的数据比较与解读") is True
    assert is_non_textbook_skill_point("实验对照与变量分析") is True
    assert is_non_textbook_skill_point("实验对照与结果分析") is True
    assert is_non_textbook_skill_point("实验中排除干扰的方法") is True
    assert is_non_textbook_skill_point("抑制剂的验证作用") is True
    assert is_non_textbook_skill_point("实验设计中的等量原则") is True
    assert is_non_textbook_skill_point("食品添加剂的安全性评估") is True
    assert is_non_textbook_skill_point("食品安全性评价") is True
    assert is_non_textbook_skill_point("食品安全性的评估") is True
    assert is_non_textbook_skill_point("食品安全评估") is True
    assert is_non_textbook_skill_point("电泳结果分析") is True
    assert is_non_textbook_skill_point("电泳图读图能力") is True
    assert is_non_textbook_skill_point("遗传分析与电泳解读") is True
    assert is_non_textbook_skill_point("II-3泳道有308bp条带，C误说泳道空") is True
    assert is_non_textbook_skill_point("II-5可能为携带者，子女遗传而非突变") is True
    assert is_non_textbook_skill_point("综合系谱和电泳推断致病机制") is True
    assert is_non_textbook_skill_point("细胞纤维化的诱导机制") is True
    assert is_non_textbook_skill_point("成纤维细胞活化与胶原沉积") is True
    assert is_non_textbook_skill_point("炎症与纤维化的关系") is True
    assert is_non_textbook_skill_point("口腔黏膜纤维化的细胞学机制") is True
    assert is_non_textbook_skill_point("外泌体内含物的检测") is True
    assert is_non_textbook_skill_point("槟榔碱的致病通路") is True
    assert is_non_textbook_skill_point("槟榔碱的作用机制") is True
    assert is_non_textbook_skill_point("槟榔碱通过外泌体miR-155-5P致纤维化机制") is True
    assert is_non_textbook_skill_point("产物的应用价值") is True
    assert is_non_textbook_skill_point("药物应用推断") is True
    assert is_non_textbook_skill_point("代谢产物活性的动态变化") is True
    assert is_non_textbook_skill_point("乳酸菌密度与代谢产物的动态变化") is True
    assert is_non_textbook_skill_point("细菌素的产量与培养时间的关系") is True
    assert is_non_textbook_skill_point("变量相关性的判断") is True
    assert is_non_textbook_skill_point("配子类型分析") is True
    assert is_non_textbook_skill_point("配子类型与受精条件分析") is True
    assert is_non_textbook_skill_point("假说演绎法") is True
    assert is_non_textbook_skill_point("LEC2的可能作用机制") is True
    assert is_non_textbook_skill_point("基因导入与遗传分析") is True
    assert is_non_textbook_skill_point("异常蛋白积累的致病机理") is True
    assert is_non_textbook_skill_point("根据题干信息分析致病机制") is True
    assert is_non_textbook_skill_point("实验结果的分析与解读") is True
    assert is_non_textbook_skill_point("实验结果的逻辑分析") is True
    assert is_non_textbook_skill_point("实验结果的分析与比较") is True
    assert is_non_textbook_skill_point("实验结果的图表分析") is True
    assert is_non_textbook_skill_point("科学结论的证据强度") is True
    assert is_non_textbook_skill_point("乳酸菌密度与代谢产物积累") is True
    assert is_non_textbook_skill_point("分析致病分子机制") is True
    assert is_non_textbook_skill_point("外泌体内容物的检测") is True
    assert is_non_textbook_skill_point("外泌体的内含物") is True
    assert is_non_textbook_skill_point("外泌体的内容物分析") is True
    assert is_non_textbook_skill_point("α-SMA和胶原蛋白的纤维化标志") is True
    assert is_non_textbook_skill_point("纤维化形成的分子机制") is True
    assert is_non_textbook_skill_point("单一变量原则") is True
    assert is_non_textbook_skill_point("实验的平行重复与检测指标") is True
    assert is_non_textbook_skill_point("产物分离与工业应用") is True
    assert is_non_textbook_skill_point("基于序列的连接点分析") is True
    assert links == [{"knowledge_point": "细胞间信息交流", "share": 1.0}]
