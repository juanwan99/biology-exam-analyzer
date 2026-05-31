"""Calibration helpers for model-produced exam analysis structures.

The functions here are deliberately deterministic. An evidence service supplies
the textbook/rubric anchors in the prompt and metadata; this module then keeps
the downstream score math stable by normalizing noisy model labels before they
are aggregated.
"""
from __future__ import annotations

from typing import Any

from logger import get_logger

logger = get_logger()


_NON_TEXTBOOK_PATTERNS = (
    "实验设计",
    "基因功能验证",
    "抑制剂实验",
    "控制变量",
    "变量控制",
    "实验变量的检测与设计",
    "实验变量的控制",
    "多变量实验",
    "实验数据分析",
    "实验数据的分析",
    "实验结果分析",
    "实验结果的逻辑分析",
    "实验结果对比分析",
    "实验结果的对比分析",
    "实验结果对照分析",
    "实验结果的数据比较与解读",
    "实验结果的分析与解读",
    "实验结果的分析与比较",
    "实验结果的图表分析",
    "实验结果与结论的逻辑关系",
    "实验设计中的等量原则",
    "实验数据的读取",
    "实验数据读取",
    "实验数据比较",
    "实验数据的比较",
    "实验数据的解读",
    "实验数据的处理",
    "实验结果的读取与比较",
    "处理与估算",
    "实验数据的完整获取",
    "实验逻辑推断",
    "实验推理与评估",
    "数据分析",
    "图表中变量关系",
    "图表信息",
    "图表分析",
    "图表趋势",
    "数据图表",
    "数据关联分析",
    "数据趋势解读",
    "双轴图",
    "双轴图表",
    "图表趋势解读",
    "图表数据的趋势分析与因果关系",
    "图表数据的解读",
    "图表数据的解读与分析",
    "图表数据的解读与判断",
    "双变量曲线图",
    "曲线图",
    "曲线趋势分析",
    "提取与分析",
    "分析与决策",
    "比较与分析",
    "数据比较与解读",
    "变量关系的综合分析",
    "变量相关性",
    "变量相关性的判断",
    "变量间正相关关系的判断",
    "正相关的概念与判断",
    "正相关的概念",
    "正相关关系的判断",
    "数据的相关性分析",
    "相关性分析",
    "相关性判断",
    "数据处理",
    "统计方法",
    "实验数据的统计分析要求",
    "电泳结果分析",
    "电泳图读图",
    "电泳解读",
    "泳道",
    "bp条带",
    "遗传分析与电泳",
    "可能为携带者",
    "子女遗传而非突变",
    "综合系谱和电泳推断致病机制",
    "实验对照分析",
    "实验对照设计",
    "实验对照与变量",
    "实验对照与结果分析",
    "实验的平行重复与检测指标",
    "实验平行重复",
    "平行重复",
    "检测指标",
    "实验操作注意事项",
    "实验中排除干扰",
    "抑制剂的验证作用",
    "信息获取",
    "信息处理",
    "逻辑推理",
    "逻辑推断",
    "模型建构",
    "科学探究能力",
    "分析与结论",
    "数据解读",
    "实验结论",
    "结论推导",
    "对照组",
    "对照设置",
    "设置原则",
    "严谨性",
    "科学结论的证据强度",
    "实验目的",
    "目的与对照",
    "单一变量原则",
    "细胞共培养",
    "外泌体内容物检测",
    "外泌体内容物分析",
    "外泌体内容物的检测",
    "外泌体的内容物分析",
    "细胞纤维化标志",
    "细胞纤维化",
    "成纤维细胞活化",
    "胶原沉积",
    "细胞纤维化的标志蛋白",
    "口腔黏膜纤维化",
    "纤维化的细胞学机制",
    "纤维化相关蛋白",
    "纤维化形成",
    "纤维化标志",
    "α-SMA",
    "炎症与纤维化",
    "槟榔碱的致病机制",
    "槟榔碱的致病",
    "槟榔碱的作用机制",
    "槟榔碱通过",
    "致纤维化",
    "miR-155",
    "健康生活",
    "疾病防治",
    "疾病诊断逻辑",
    "慢性炎症",
    "食欲调控",
    "体重管理",
    "FoxP3",
    "食品添加剂",
    "安全性评估",
    "食品安全性评价",
    "食品安全性的评估",
    "食品安全评估",
    "等量原则",
    "药物应用",
    "应用推断",
    "应用价值",
    "外泌体内含物",
    "外泌体的内含物",
    "代谢产物活性",
    "活性的动态变化",
    "乳酸菌密度与代谢产物",
    "乳酸菌密度与代谢产物的动态变化",
    "细菌素的产量与培养时间的关系",
    "配子类型分析",
    "配子类型与受精条件分析",
    "基因导入与遗传分析",
    "异常蛋白积累",
    "致病机理",
    "根据题干信息分析",
    "根据题干信息分析致病机制",
    "致病机制分析",
    "致病分子机制",
    "分析致病分子机制",
    "产物分离",
    "工业应用",
    "基于序列的连接点分析",
    "连接点分析",
    "假说演绎法",
    "LEC2",
)


_CANONICAL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("PCR", "引物"), "PCR技术扩增目的基因"),
    (("PCR", "目的基因"), "PCR技术扩增目的基因"),
    (("基因扩增", "原理"), "PCR技术扩增目的基因"),
    (("目的基因", "扩增"), "PCR技术扩增目的基因"),
    (("模板结合区域",), "PCR技术扩增目的基因"),
    (("In-Fusion",), "In-Fusion克隆"),
    (("同源臂",), "In-Fusion克隆"),
    (("表达载体", "构建"), "基因表达载体构建"),
    (("基因表达载体",), "基因表达载体构建"),
    (("限制酶",), "限制酶"),
    (("质粒",), "质粒"),
    (("性激素", "化学本质"), "细胞中的糖类和脂质"),
    (("脂质", "种类", "功能"), "细胞中的糖类和脂质"),
    (("脂质", "分类"), "细胞中的糖类和脂质"),
    (("脂质", "固醇"), "细胞中的糖类和脂质"),
    (("生长素", "化学本质"), "植物生长素"),
    (("植物激素", "化学本质"), "植物生长素"),
    (("色氨酸", "前体"), "生长素的化学本质"),
    (("胰岛素", "化学本质"), "蛋白质是生命活动的主要承担者"),
    (("胰岛素", "本质"), "蛋白质是生命活动的主要承担者"),
    (("胰岛素", "性质"), "蛋白质是生命活动的主要承担者"),
    (("胰岛素", "合成场所"), "核糖体"),
    (("胰岛细胞", "受体"), "激素调节的过程"),
    (("胰岛细胞", "功能"), "激素调节的过程"),
    (("靶细胞", "受体"), "激素调节的过程"),
    (("体液运输", "靶细胞"), "激素调节的过程"),
    (("食欲调节", "体重控制"), "激素调节的过程"),
    (("蛋白质", "合成场所"), "核糖体"),
    (("多肽", "化学性质"), "蛋白质是生命活动的主要承担者"),
    (("核苷酸", "组成"), "核酸是遗传信息的携带者"),
    (("核膜", "周期"), "细胞的有丝分裂"),
    (("根尖", "解离"), "观察根尖分生区组织细胞的有丝分裂"),
    (("解离", "作用"), "观察根尖分生区组织细胞的有丝分裂"),
    (("解离", "目的"), "观察根尖分生区组织细胞的有丝分裂"),
    (("解离", "时间"), "观察根尖分生区组织细胞的有丝分裂"),
    (("解离", "操作"), "观察根尖分生区组织细胞的有丝分裂"),
    (("中期", "识别"), "细胞的有丝分裂"),
    (("中期", "数目计算"), "细胞的有丝分裂"),
    (("染色单体", "概念"), "细胞的有丝分裂"),
    (("间期", "时长"), "细胞周期"),
    (("细胞数量", "时长"), "细胞周期"),
    (("细胞数量", "相对长短"), "细胞周期"),
    (("细胞比例", "观察实验"), "细胞周期"),
    (("细胞比例", "应用"), "细胞周期"),
    (("显微观察", "周期", "局限"), "细胞周期"),
    (("抑菌活性",), "发酵工程及其应用"),
    (("乳酸菌", "细菌素"), "发酵工程及其应用"),
    (("细菌", "生长曲线", "代谢产物"), "发酵工程及其应用"),
    (("细菌素", "产生", "积累"), "发酵工程及其应用"),
    (("细菌素", "菌密度"), "发酵工程及其应用"),
    (("CO₂", "培养"), "动物细胞培养"),
    (("CO2", "培养"), "动物细胞培养"),
    (("竞争", "捕食"), "种间关系"),
    (("竞争力", "存活率"), "种间关系"),
    (("竞争力", "强弱"), "种间关系"),
    (("竞争关系",), "种间关系"),
    (("捕食关系",), "种间关系"),
    (("捕食者", "猎物"), "种间关系"),
    (("捕食者", "被捕食者"), "种间关系"),
    (("捕食者",), "种间关系"),
    (("被捕食者",), "种间关系"),
    (("环境容纳量",), "种群数量的变化"),
    (("环境阻力", "资源限制"), "种群数量的变化"),
    (("环境阻力", "S形曲线"), "种群数量的变化"),
    (("非生物因素", "影响"), "环境因素参与调节植物的生命活动"),
    (("生态因子", "影响"), "环境因素参与调节植物的生命活动"),
    (("钾离子", "生理作用"), "人体内环境稳态"),
    (("钾离子", "体液", "分布"), "人体内环境稳态"),
    (("钾离子", "渗透压"), "人体内环境稳态"),
    (("钾", "渗透压"), "人体内环境稳态"),
    (("无机盐", "渗透压"), "人体内环境稳态"),
    (("离子", "渗透压"), "人体内环境稳态"),
    (("细胞内液", "细胞外液", "离子"), "人体内环境稳态"),
    (("K+", "渗透压"), "人体内环境稳态"),
    (("低血钾",), "人体内环境稳态"),
    (("低钾血",), "人体内环境稳态"),
    (("物质丢失", "电解质"), "人体内环境稳态"),
    (("电解质平衡",), "人体内环境稳态"),
    (("电解质",), "人体内环境稳态"),
    (("膜", "选择透过性"), "细胞膜的结构和功能"),
    (("扩散", "能量消耗"), "自由扩散"),
    (("扩散", "耗能"), "自由扩散"),
    (("信号肽",), "蛋白质的定向转运"),
    (("受体", "识别"), "蛋白质的定向转运"),
    (("生物大分子", "跨膜"), "蛋白质的定向转运"),
    (("受体蛋白", "功能"), "细胞间信息交流"),
    (("受体上调", "下调"), "细胞间信息交流"),
    (("受体", "敏感性", "调节"), "细胞间信息交流"),
    (("前体蛋白", "成熟蛋白"), "蛋白质的定向转运"),
    (("前体蛋白",), "蛋白质的定向转运"),
    (("人工合成生物学",), "人工光合"),
    (("合成生物学",), "人工光合"),
    (("初生代谢", "次级代谢"), "次级代谢产物"),
    (("初生代谢", "次生代谢"), "次级代谢产物"),
    (("次生代谢", "初生代谢"), "次级代谢产物"),
    (("多倍体", "育种"), "多倍体形成"),
    (("杂种优势",), "杂交育种"),
    (("质子浓度梯度",), "光合作用的光反应"),
    (("跨膜质子梯度",), "光合作用的光反应"),
    (("质子动力势",), "光合作用的光反应"),
    (("化学渗透",), "光合作用的光反应"),
    (("光系统I", "光系统II"), "光合作用的光反应"),
    (("光系统I和II", "功能"), "光合作用的光反应"),
    (("光呼吸", "能量效率"), "光合作用"),
    (("pH", "离子浓度"), "光合作用的光反应"),
    (("pH", "质子梯度"), "光合作用的光反应"),
    (("人工膜系统",), "人工光合"),
    (("代谢途径", "顺序"), "人工光合"),
    (("代谢途径", "综合调节"), "人工光合"),
    (("代谢途径", "定向优化"), "人工光合"),
    (("环境污染", "防治"), "全球性生态环境问题"),
    (("环境污染", "治理"), "全球性生态环境问题"),
    (("水体污染", "治理"), "全球性生态环境问题"),
    (("水体修复植物",), "水体污染的生物净化"),
    (("植物修复", "原理"), "水体污染的生物净化"),
    (("基因致死",), "遗传致死"),
    (("基因敲除", "致死"), "遗传致死"),
    (("CGG", "重复"), "基因突变"),
    (("三核苷酸", "重复"), "基因突变"),
    (("突变类型",), "基因突变"),
    (("重复扩增",), "基因突变"),
    (("动态突变",), "基因突变"),
    (("前突变", "传递"), "基因突变"),
    (("基因型", "表型"), "基因表达与性状的关系"),
    (("红色荧光蛋白", "表达"), "基因表达与性状的关系"),
    (("脆性X", "分子机制"), "遗传病"),
    (("外显率", "表现度"), "遗传病"),
    (("凋亡", "坏死"), "细胞凋亡"),
    (("细胞坏死",), "细胞的衰老和死亡"),
    (("多肽", "消化"), "蛋白质是生命活动的主要承担者"),
    (("分离定律",), "基因的分离定律"),
    (("基因的分离", "配子"), "基因的分离定律"),
    (("遗传", "分离比"), "基因的分离定律"),
    (("自交后代", "分离"), "基因的分离定律"),
    (("自交后代", "比例"), "基因的分离定律"),
    (("自交后代", "基因型"), "基因的分离定律"),
    (("自交后代", "选择"), "基因的分离定律"),
    (("自交后代", "基因型", "表现型"), "基因的分离定律"),
    (("自由组合",), "基因的自由组合定律"),
    (("配子", "形成", "受精"), "受精作用"),
    (("配子类型", "受精"), "受精作用"),
    (("配子类型", "可育性"), "受精作用"),
    (("自交", "受精限制"), "受精作用"),
    (("配子结合", "限制"), "受精作用"),
    (("配子结合", "条件"), "受精作用"),
    (("受精", "细胞质", "分配"), "细胞质遗传"),
    (("配子类型", "多样性"), "基因的分离定律"),
    (("细胞质基因", "遗传特点"), "细胞质遗传"),
    (("细胞质基因", "传递特点"), "细胞质遗传"),
    (("母系遗传",), "细胞质遗传"),
    (("基因导入位置", "遗传"), "细胞质遗传"),
    (("导入位置", "遗传"), "细胞质遗传"),
    (("基因连锁", "配子"), "基因的连锁与互换定律"),
    (("连锁", "配子选择"), "基因的连锁与互换定律"),
    (("基因的连锁", "分离"), "基因的连锁与互换定律"),
    (("基因的连锁", "交换"), "基因的连锁与互换定律"),
    (("基因连锁", "标记基因"), "基因的连锁与互换定律"),
    (("基因连锁", "遗传规律"), "基因的连锁与互换定律"),
    (("基因连锁", "遗传"), "基因的连锁与互换定律"),
    (("荧光标记基因", "遗传"), "基因的连锁与互换定律"),
    (("荧光标记基因", "应用"), "基因的连锁与互换定律"),
    (("基因的连锁", "应用"), "基因的连锁与互换定律"),
    (("连锁遗传",), "基因的连锁与互换定律"),
    (("基因插入", "功能缺失"), "基因突变"),
    (("遗传杂交", "致死"), "遗传致死"),
    (("致死基因",), "遗传致死"),
    (("胚胎致死",), "遗传致死"),
    (("花粉致死",), "遗传致死"),
    (("花粉致死", "遗传效应"), "遗传致死"),
    (("生态工程", "原理"), "生态工程的基本原理"),
    (("系统学", "工程学"), "生态工程的基本原理"),
    (("生态修复", "植物"), "生态工程"),
    (("整体性原理",), "生态工程的基本原理"),
    (("防止二次污染",), "生态工程的基本原理"),
    (("废弃物", "资源化"), "生态工程的基本原理"),
    (("经济效益", "生态效益"), "生态工程的基本原理"),
    (("水体治理",), "水体污染的生物净化"),
    (("物质传递", "形式"), "物质循环"),
    (("雄性不育", "育种"), "雄性不育系与杂交育种"),
    (("不育系", "保持系"), "雄性不育系与杂交育种"),
    (("不育系", "繁殖"), "雄性不育系与杂交育种"),
    (("保持系", "功能"), "雄性不育系与杂交育种"),
    (("保持系", "概念"), "雄性不育系与杂交育种"),
    (("保持系", "优势退化"), "雄性不育系与杂交育种"),
    (("智能保持系",), "杂交育种"),
    (("保持系", "自交"), "杂交育种"),
    (("水稻育种", "保持系"), "杂交育种"),
    (("次生代谢产物",), "次级代谢产物"),
    (("琼脂糖凝胶电泳",), "PCR技术扩增目的基因"),
    (("电泳图谱",), "PCR技术扩增目的基因"),
    (("电泳", "技术原理"), "PCR技术扩增目的基因"),
    (("茎尖", "脱毒"), "茎尖脱毒"),
    (("植物脱毒",), "茎尖脱毒"),
    (("脱毒苗", "培育"), "茎尖脱毒"),
    (("脱毒苗", "获取"), "茎尖脱毒"),
    (("脱毒苗", "原理"), "茎尖脱毒"),
    (("脱毒苗", "培养"), "茎尖脱毒"),
    (("茎尖分生", "病毒"), "茎尖脱毒"),
    (("植物病毒", "脱毒"), "茎尖脱毒"),
    (("植物病毒", "茎尖"), "茎尖脱毒"),
    (("病毒", "脱毒"), "茎尖脱毒"),
    (("茎尖分生组织",), "茎尖脱毒"),
    (("茎尖组织培养", "脱毒苗"), "茎尖脱毒"),
    (("花药", "离体培养"), "细胞全能性"),
    (("转运肽",), "蛋白质的定向转运"),
    (("蛋白分选", "运输"), "蛋白质的定向转运"),
    (("不完全外显",), "遗传病"),
    (("遗传咨询",), "遗传病"),
    (("TOC-TIC",), "细胞器之间的分工合作"),
    (("优势种",), "群落结构"),
    (("富集作用",), "生物富集"),
    (("富集植物",), "生物富集"),
    (("细胞间", "信息交流"), "细胞间信息交流"),
    (("细胞间", "间接作用"), "细胞间信息交流"),
    (("外泌体", "细胞间", "通讯"), "细胞间信息交流"),
    (("外泌体", "细胞通讯"), "细胞间信息交流"),
    (("外泌体", "功能"), "细胞间信息交流"),
    (("巨噬细胞",), "免疫系统的组成和功能"),
    (("细胞与工程",), "细胞工程"),
    (("生态因子", "生长"), "环境因素参与调节植物的生命活动"),
    (("NADPH", "生成"), "光合作用的光反应"),
    (("人工系统",), "人工光合"),
    (("人工固碳",), "人工光合"),
    (("自然固碳", "卡尔文"), "碳固定"),
    (("卡尔文循环",), "碳固定"),
    (("能量利用效率",), "光合作用的光反应"),
    (("反应条件优化",), "人工光合"),
    (("基因漂移", "生态风险"), "生物安全"),
    (("基因逃逸", "生态风险"), "生物安全"),
    (("基因逃逸", "环境污染"), "生物安全"),
    (("基因逃逸", "环境影响"), "生物安全"),
    (("遗传设计", "安全"), "生物安全"),
    (("生态安全",), "生物安全"),
    (("分子水平", "进化证据"), "生物进化的证据"),
    (("分子生物学证据",), "生物进化的证据"),
    (("生物进化", "分子证据"), "生物进化的证据"),
    (("基因序列", "比较"), "生物进化的证据"),
    (("RNaseH",), "核酸是遗传信息的携带者"),
    (("引物", "位置", "方向"), "PCR技术扩增目的基因"),
    (("引物位置", "产物大小"), "PCR技术扩增目的基因"),
    (("产物大小", "计算"), "PCR技术扩增目的基因"),
    (("引物", "功能序列", "设计"), "PCR技术扩增目的基因"),
    (("引物序列", "分析"), "PCR技术扩增目的基因"),
    (("序列分析", "阅读序列图"), "PCR技术扩增目的基因"),
    (("引物方向", "扩增"), "PCR技术扩增目的基因"),
    (("基因插入", "方向"), "PCR技术扩增目的基因"),
    (("引物结合位点", "距离"), "PCR技术扩增目的基因"),
    (("重组子", "鉴定"), "基因工程的基本操作程序"),
    (("基因定位", "插入失活"), "基因工程的基本操作程序"),
    (("致死机制", "基因定位"), "基因工程的基本操作程序"),
    (("基因定点整合",), "基因工程的基本操作程序"),
    (("CRISPR",), "基因工程"),
    (("人工浮床",), "生态工程"),
    (("浮床", "植物选择"), "生态工程"),
    (("细胞培养", "条件控制"), "动物细胞培养"),
    (("细胞培养", "处理条件"), "动物细胞培养"),
    (("细胞培养", "刺激条件"), "动物细胞培养"),
    (("杂交后代", "基因型"), "遗传的基本规律"),
    (("遗传变异", "类型"), "基因突变"),
    (("配子类型", "比例"), "基因的分离定律"),
    (("配子类型", "概率"), "基因的分离定律"),
    (("杂交水稻", "繁育体系"), "雄性不育系与杂交育种"),
    (("杂交水稻", "育种原理"), "雄性不育系与杂交育种"),
    (("育种流程", "设计"), "雄性不育系与杂交育种"),
    (("基因定位", "功能"), "基因工程的基本操作程序"),
    (("规避蛋白定位",), "蛋白质的定向转运"),
    (("蛋白定位干扰",), "蛋白质的定向转运"),
    (("基因漂移",), "种群基因组成的变化"),
    (("基因频率",), "种群基因组成的变化"),
    (("GLP-1",), "激素调节的过程"),
    (("表观遗传",), "表观遗传"),
    (("基因甲基化", "表达调控"), "表观遗传"),
    (("甲基化", "表达调控"), "表观遗传"),
    (("腹泻", "电解质"), "人体内环境稳态"),
    (("腹泻", "K+"), "人体内环境稳态"),
    (("腹泻", "钾"), "人体内环境稳态"),
    (("腹泻", "无机盐"), "人体内环境稳态"),
    (("细胞数目", "时间比例"), "细胞周期"),
    (("受精", "限制", "条件"), "受精作用"),
)


def is_non_textbook_skill_point(value: Any) -> bool:
    """Return True for ability/method tags that should not dilute content scores."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    return any(pattern in text for pattern in _NON_TEXTBOOK_PATTERNS)


def canonicalize_knowledge_point(
    value: Any,
    *,
    knowledge_mapper: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    """Map a model knowledge label to a stable aggregation label.

    The canonical label remains concept-level when possible. If the model emits
    an unmapped or overly broad phrase, the fallback is the textbook section
    name produced by ``KnowledgeMapper`` rather than the raw phrase.
    """
    raw = " ".join(str(value or "").strip().split())
    if not raw:
        return "", {"mapped": False, "reason": "empty"}
    if raw == "PCR技术":
        return raw, {
            "mapped": True,
            "strategy": "stable_exact_label",
            "original": raw,
        }

    for tokens, canonical in _CANONICAL_RULES:
        if all(token in raw for token in tokens):
            return canonical, {
                "mapped": True,
                "strategy": "canonical_rule",
                "original": raw,
            }

    mapper = knowledge_mapper
    synonyms = getattr(mapper, "_synonyms", {}) if mapper is not None else {}
    for alias, canonical in synonyms.items():
        if alias and alias in raw:
            return str(canonical), {
                "mapped": True,
                "strategy": "synonym",
                "original": raw,
                "alias": alias,
            }

    keyword = _best_keyword_match(raw, mapper)
    if keyword:
        label = _keyword_to_label(keyword)
        return label, {
            "mapped": True,
            "strategy": "keyword",
            "original": raw,
            "keyword": keyword,
        }

    mapped = _map_with_mapper(raw, mapper)
    if mapped and mapped.get("mapped") is True:
        section_name = str(mapped.get("section_name") or "").strip()
        chapter_name = str(mapped.get("chapter_name") or "").strip()
        label = section_name or chapter_name or raw
        return label, {
            "mapped": True,
            "strategy": "textbook_section",
            "original": raw,
            "textbook": mapped.get("textbook"),
            "chapter": mapped.get("chapter"),
            "section": mapped.get("section"),
        }

    return raw, {"mapped": False, "strategy": "raw", "original": raw}


def normalize_knowledge_links(
    links: list[dict[str, Any]] | None,
    *,
    knowledge_mapper: Any | None = None,
    max_links: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Canonicalize, merge and renormalize knowledge links for one SEU."""
    buckets: dict[str, float] = {}
    diagnostics = {
        "before_count": len(links or []),
        "after_count": 0,
        "changed": False,
        "unmapped_count": 0,
    }
    for link in links or []:
        if not isinstance(link, dict):
            continue
        point = link.get("knowledge_point")
        if not isinstance(point, str) or not point.strip():
            continue
        if is_non_textbook_skill_point(point):
            diagnostics["changed"] = True
            continue
        canonical, meta = canonicalize_knowledge_point(
            point,
            knowledge_mapper=knowledge_mapper,
        )
        if not canonical:
            continue
        if canonical != point.strip():
            diagnostics["changed"] = True
        if not meta.get("mapped"):
            diagnostics["unmapped_count"] += 1
        share = _positive_float(link.get("share"), 1.0)
        buckets[canonical] = buckets.get(canonical, 0.0) + share

    if not buckets:
        return [], diagnostics

    ranked = sorted(buckets.items(), key=lambda item: (-item[1], item[0]))
    if max_links > 0 and len(ranked) > max_links:
        diagnostics["changed"] = True
        ranked = ranked[:max_links]
    total = sum(weight for _, weight in ranked)
    if total <= 0:
        total = float(len(ranked))
        ranked = [(name, 1.0) for name, _ in ranked]
    normalized = [
        {"knowledge_point": name, "share": round(weight / total, 4)}
        for name, weight in ranked
    ]
    diagnostics["after_count"] = len(normalized)
    if diagnostics["after_count"] != diagnostics["before_count"]:
        diagnostics["changed"] = True
    return normalized, diagnostics


def calibrate_fine_grained_analysis(
    analysis: dict[str, Any],
    *,
    knowledge_mapper: Any | None = None,
    max_links_per_seu: int = 3,
) -> dict[str, Any]:
    """Normalize SEU knowledge links in-place and refresh summary knowledge points."""
    if not isinstance(analysis, dict):
        return analysis
    fine = analysis.get("_fine_grained")
    if not isinstance(fine, dict):
        fine = {}
    scoring_units = fine.get("scoring_units") or analysis.get("scoring_units") or []
    if not isinstance(scoring_units, list) or not scoring_units:
        return analysis

    changed_units = 0
    unmapped_links = 0
    for unit in scoring_units:
        if not isinstance(unit, dict):
            continue
        normalized, diagnostics = normalize_knowledge_links(
            unit.get("knowledge_links") or [],
            knowledge_mapper=knowledge_mapper,
            max_links=max_links_per_seu,
        )
        if normalized:
            unit["knowledge_links"] = normalized
        if diagnostics["changed"]:
            changed_units += 1
        unmapped_links += int(diagnostics["unmapped_count"] or 0)

    if fine.get("scoring_units") is not scoring_units:
        fine["scoring_units"] = scoring_units
        analysis["_fine_grained"] = fine
    if analysis.get("scoring_units") is not scoring_units and "scoring_units" in analysis:
        analysis["scoring_units"] = scoring_units

    weighted: dict[str, float] = {}
    for unit in scoring_units:
        if not isinstance(unit, dict):
            continue
        unit_share = _positive_float(unit.get("score_share"), 0.0)
        for link in unit.get("knowledge_links") or []:
            point = link.get("knowledge_point") if isinstance(link, dict) else None
            if not point:
                continue
            weighted[str(point)] = weighted.get(str(point), 0.0) + unit_share * _positive_float(link.get("share"), 0.0)
    if weighted:
        analysis["knowledge_points"] = [
            point for point, _ in sorted(weighted.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]

    if changed_units:
        calibration = analysis.setdefault("_calibration", {})
        calibration["knowledge_standardization"] = {
            "status": "applied",
            "method": "textbook_anchor_and_deterministic_merge",
            "changed_scoring_units": changed_units,
            "unmapped_links_after": unmapped_links,
            "max_links_per_seu": max_links_per_seu,
        }
        logger.info(
            "[校准] SEU知识点标准化完成: changed_units=%s unmapped_links_after=%s",
            changed_units,
            unmapped_links,
        )
    return analysis


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _map_with_mapper(value: str, mapper: Any | None) -> dict[str, Any] | None:
    if mapper is None:
        return None
    try:
        return mapper.map_knowledge_point(value)
    except Exception:
        return None


def _best_keyword_match(value: str, mapper: Any | None) -> str | None:
    mapping = getattr(mapper, "KEYWORD_MAPPING", None)
    if not isinstance(mapping, dict):
        try:
            from knowledge_mapper import KnowledgeMapper

            mapping = KnowledgeMapper.KEYWORD_MAPPING
        except Exception:
            mapping = {}
    if value in mapping:
        return value
    best = ""
    for keyword in mapping:
        if keyword and keyword in value and len(keyword) > len(best):
            best = str(keyword)
    return best or None


def _keyword_to_label(keyword: str) -> str:
    if keyword == "分离定律":
        return "基因的分离定律"
    if keyword == "自由组合":
        return "基因的自由组合定律"
    if keyword == "PCR":
        return "PCR技术扩增目的基因"
    return keyword
