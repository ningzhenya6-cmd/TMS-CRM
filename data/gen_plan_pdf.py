#!/usr/bin/env python3
"""生成 龙虾6号 0→1 规划 PDF"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, datetime

HEI_M = "/System/Library/Fonts/STHeiti Medium.ttc"
HEI_L = "/System/Library/Fonts/STHeiti Light.ttc"
pdfmetrics.registerFont(TTFont("Hei", HEI_M, subfontIndex=1))
pdfmetrics.registerFont(TTFont("Hei-Light", HEI_L, subfontIndex=1))

P = HexColor("#1a56db"); D = HexColor("#1e293b"); G = HexColor("#64748b")
LG = HexColor("#f1f5f9"); S = HexColor("#059669"); W = HexColor("#d97706")
B = HexColor("#e2e8f0")

s_t = ParagraphStyle("T", fontName="Hei", fontSize=18, leading=26, textColor=D, alignment=TA_CENTER, spaceAfter=4)
s_st = ParagraphStyle("ST", fontName="Hei-Light", fontSize=9, leading=13, textColor=G, alignment=TA_CENTER, spaceAfter=14)
s_h1 = ParagraphStyle("H1", fontName="Hei", fontSize=13, leading=19, textColor=P, spaceBefore=14, spaceAfter=6)
s_h2 = ParagraphStyle("H2", fontName="Hei", fontSize=10.5, leading=15, textColor=D, spaceBefore=8, spaceAfter=3)
s_body = ParagraphStyle("B", fontName="Hei-Light", fontSize=9, leading=15, textColor=D, alignment=TA_JUSTIFY, spaceAfter=3)
s_bul = ParagraphStyle("BL", fontName="Hei-Light", fontSize=9, leading=15, textColor=D, leftIndent=16, bulletIndent=6, spaceAfter=2)
s_th = ParagraphStyle("TH", fontName="Hei", fontSize=8, leading=11, textColor=white, alignment=TA_CENTER)
s_tc = ParagraphStyle("TC", fontName="Hei-Light", fontSize=8, leading=11, textColor=D, alignment=TA_CENTER)
s_tcl = ParagraphStyle("TCL", fontName="Hei-Light", fontSize=8, leading=11, textColor=D, alignment=TA_LEFT)
s_ft = ParagraphStyle("F", fontName="Hei-Light", fontSize=7, leading=10, textColor=G, alignment=TA_CENTER)

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=B, spaceBefore=5, spaceAfter=5)

def bul(text):
    return Paragraph(f"\u2022 {text}", s_bul)

def header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(P); canvas.setLineWidth(1)
    canvas.line(20*mm, h-17*mm, w-20*mm, h-17*mm)
    canvas.setFont("Hei-Light", 7); canvas.setFillColor(G)
    canvas.drawString(20*mm, h-15*mm, "龙虾6号 \u00b7 预科留学AI引擎 0\u21921 落地规划[)
    canvas.drawRightString(w-20*mm, h-15*mm, datetime.date.today().strftime("%Y-%m-%d"))
    canvas.setStrokeColor(B); canvas.setLineWidth(0.3)
    canvas.line(20*mm, 15*mm, w-20*mm, 15*mm)
    canvas.drawCentredString(w/2, 10*mm, f"\u2014 {doc.page} \u2014")
    canvas.restoreState()

def make_table(headers, rows, col_w):
    data = [[Paragraph(h, s_th) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), s_tcl) for c in row])
    t = Table(data, colWidths=col_w)
    style = [
        ("BACKGROUND", (0,0), (-1,0), P),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("GRID", (0,0), (-1,-1), 0.3, B),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0,i), (-1,i), LG))
    t.setStyle(TableStyle(style))
    return t

def story():
    S = []
    S.append(Spacer(1, 8*mm))
    S.append(Paragraph("龙虾6号 \u00b7 预科留学AI引擎 0\u21921 落地规划[, s_t))
    S.append(Paragraph("从内容基建到商业闭环 \u00b7 2026年5月28日[, s_st))

    # ═══ 一 ═══
    S.append(Paragraph("一、今日已完成（阶段零：内容基建）", s_h1))
    S.append(hr())
    S.append(Paragraph("知识库从200条扩充至228条，新增6个预科分类共28条专业内容。每一条都经过英国和澳洲7所大学官网的实时数据验证。", s_body))

    S.append(make_table(
        ["阶段[, "内容[, "条目[, "状态[],
        [
            ["P0 框架+避坑[, "预科基础/类型/费用/FAQ + 5大避坑信号[, "13条[, "✅ 入库[],
            ["P1 对比+大学[, "G5详解/澳洲7大/六大集团/加拿大/新加坡/KCL/曼大[, "10条[, "✅ 入库[],
            ["P2 场景决策[, "高考后规划/挂科补救/选专业/签证/预科vs复读[, "5条[, "✅ 入库[],
        ],
        [36*mm, 72*mm, 18*mm, 28*mm]
    ))

    S.append(Spacer(1, 3*mm))
    S.append(Paragraph("数据质量：发现并修正9处数据错误，含4处严重错误：", s_h2))
    S.append(bul("LSE没有自己的预科（本地文档误列为[LSE本科预科]）"))
    S.append(bul("帝国理工学院仅接受UCL UPCSE和华威IFP"))
    S.append(bul("澳洲国立大学没有预科项目[))
    S.append(bul("Graduate Route签证2027年1月起从2年缩至18个月[))
    S.append(Paragraph("基础设施：DuckDuckGo+Clash代理恢复全网搜索，web_fetch直连官网通道验证可用。", s_body))

    # ═══ 二 ═══
    S.append(Paragraph("二、0→1 四阶段推进计划[, s_h1))
    S.append(hr())

    S.append(Paragraph("阶段一：内容资产化（第1周）", s_h2))
    S.append(bul("补齐30+所大学预科项目详情 → 知识库 228→270+"))
    S.append(bul("补齐预科学习内容详解（每门课学什么、怎么考）"))
    S.append(bul("补齐预科在读体验（学生真实反馈、常见困难）"))
    S.append(bul("建立每季度爬官网核验的自动化更新机制[))

    S.append(Paragraph("阶段二：产品体验化（第2周）", s_h2))
    S.append(bul("优化AI搜索引擎预科领域回复tone，更专业的顾问角色[))
    S.append(bul("增加预科选校测评功能：输入条件→推荐匹配预科[))
    S.append(bul("增加数据可视化对比表、升学路径图[))
    S.append(bul("目标：从「能答」到「答得好」，用户反馈「有用」率>80%"))

    S.append(Paragraph("阶段三：获客验证化（第3-4周）", s_h2))
    S.append(bul("确定3个平台账号定位（抖音/小红书/视频号各1个）"))
    S.append(bul("制作15-20条短视频+图文（AI生成+人工润色）"))
    S.append(bul("AI引擎嵌入留资入口（搜索→咨询→留线索）"))
    S.append(bul("小规模投放测试（¥1,000-3,000），验证获客成本[))

    S.append(Paragraph("阶段四：闭环商业化（第5-8周）", s_h2))
    S.append(bul("搭建预科申请服务SOP（选校→文书→递交→签证）"))
    S.append(bul("TMS CRM 接入预科线索管理，龙虾1号自动录入[))
    S.append(bul("签约首单，完成0→1突破[))
    S.append(bul("建立案例反馈飞轮：每个签约学生→知识库新增案例[))

    # ═══ 三 ═══
    S.append(Paragraph("三、账号定位策略[, s_h1))
    S.append(hr())
    S.append(Paragraph("核心定位：<b>「用AI帮你看透预科——不贩卖焦虑，只提供真相」</b>", s_body))

    S.append(make_table(
        ["平台[, "内容方向[, "账号风格[, "关键词[],
        [
            ["抖音[, "短视频科普 + 避坑[, "犀利直白，打破信息差[, "预科避坑/名校路径/高考后留学[],
            ["小红书[, "图文对比 + 家长指南[, "温暖专业，妈妈视角[, "预科怎么选/英vs澳/费用揭秘[],
            ["视频号[, "深度讲解 + 直播答疑[, "权威可靠，专家形象[, "G5路径/升学率真相/全攻略[],
        ],
        [24*mm, 40*mm, 40*mm, 50*mm]
    ))

    S.append(Spacer(1, 3*mm))
    S.append(Paragraph("第一批选题（已验证有搜索量）：", s_h2))
    S.append(bul("「LSE没有自己预科——中介不会告诉你的G5真相」"))
    S.append(bul("「帝国理工只认这两个预科，其他都是白花钱」"))
    S.append(bul("「澳洲国立没有预科——八大预科完整对比」"))
    S.append(bul("「Graduate Route从2年变18个月，2027年起」"))
    S.append(bul("「预科五大避坑信号——家长必看」"))

    # ═══ 四 ═══
    S.append(Paragraph("四、核心竞争力[, s_h1))
    S.append(hr())
    S.append(make_table(
        ["维度[, "传统中介[, "我们[],
        [
            ["服务周期[, "申请完就切断[, "申请→在读→辅导→本科全程[],
            ["信息可靠度[, "靠顾问个人经验[, "AI知识库 + 官网实时验证[],
            ["透明度[, "信息不透明[, "每门课考核方式都能拆解[],
            ["后端能力[, "无[, "TMS CRM课业辅导兜底[],
            ["技术壁垒[, "无[, "AI搜索引擎 + 228条知识库[],
        ],
        [28*mm, 55*mm, 71*mm]
    ))

    S.append(Paragraph("竞品不可复制的壁垒：AI搜索引擎+知识库 / 官网实时数据验证能力 / TMS CRM后端辅导闭环 / 龙虾1-5号协同体系。", s_body))

    # ═══ 五 ═══
    S.append(Paragraph("五、风险与应对[, s_h1))
    S.append(hr())
    S.append(make_table(
        ["风险[, "概率[, "应对措施[],
        [
            ["AI回答有误误导用户[, "中[, "每季度爬官网验证数据，关键数据标注来源[],
            ["预科政策突然变化[, "中[, "监控关键词，变化后24h内更新知识库[],
            ["竞品跟进模仿[, "高[, "加速推进，建立先发优势+后端壁垒[],
            ["获客成本高于预期[, "中[, "多平台测试，找到最优渠道再放大[],
            ["用户信任度不够[, "中[, "所有回答带来源标注，用透明度建立信任[],
        ],
        [42*mm, 18*mm, 94*mm]
    ))

    # ═══ 六 ═══
    S.append(Paragraph("六、成功指标[, s_h1))
    S.append(hr())
    S.append(make_table(
        ["阶段[, "指标[, "目标[],
        [
            ["阶段一[, "知识库条目[, "270+"],
            ["阶段二[, "AI回答满意度[, "用户反馈[有用[率 > 80%]],
            ["阶段三[, "单条内容播放量[, "抖音 > 10万 / 小红书 > 1万[],
            ["阶段三[, "留资转化率[, "搜索 → 留资 > 3%"],
            ["阶段四[, "首单签约[, "1单（0→1）"],
            ["阶段四[, "月线索量[, "50+"],
        ],
        [24*mm, 70*mm, 60*mm]
    ))

    # ═══ 七 ═══
    S.append(Paragraph("七、明天立即可启动[, s_h1))
    S.append(hr())
    S.append(Paragraph("不需要等所有东西准备好。", s_body))
    S.append(bul("确定3个平台账号名称+头像+简介[))
    S.append(bul("拍第一条视频：用已验证的LSE/帝国理工/ANU/Graduate Route 4个实锤做「预科最常见5个谎言」"))
    S.append(bul("同步发布到抖音/小红书/视频号，测试哪个平台起量快[))

    S.append(Spacer(1, 10*mm))
    S.append(hr())
    S.append(Paragraph("本规划基于2026年5月28日实时数据整理，随执行迭代更新。", s_ft))

    return S

OUTPUT = os.path.expanduser("~/Desktop/龙虾6号-0到1规划.pdf")
doc = SimpleDocTemplate(OUTPUT, pagesize=A4,
    leftMargin=20*mm, rightMargin=20*mm, topMargin=22*mm, bottomMargin=20*mm,
    title="龙虾6号 预科留学AI引擎 0→1 落地规划[)
doc.build(story(), onFirstPage=header_footer, onLaterPages=header_footer)
print(f"✅ {OUTPUT}")
