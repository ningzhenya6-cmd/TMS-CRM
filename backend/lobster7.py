#!/usr/bin/env python3
"""
龙虾7号 · 留学规划报告生成器
用法：编辑下方 STUDENT_DATA，然后 python3 龙虾7号.py 即可
输出：桌面 → 学业风险分析与升学规划报告-{学生}-{学校}.pdf
"""

# ============================================================
# 学生信息 - 由系统调用时传入，也可以直接运行测试
# ============================================================
STUDENT_DATA = None

# ============================================================
# 以下为引擎代码，一般不需要修改
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, PageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, datetime, json, urllib.request, re

# ── 字体（跨平台） ──
_font_dirs = ['/System/Library/Fonts', '/usr/share/fonts/truetype/wqy']
_font_files = [('CN', 'STHeiti Light.ttc'), ('CN-Bold', 'STHeiti Medium.ttc'),
               ('CN', 'wqy-zenhei.ttc'), ('CN-Bold', 'wqy-zenhei.ttc')]
for name, file in _font_files:
    for d in _font_dirs:
        p = os.path.join(d, file)
        if os.path.exists(p):
            try: pdfmetrics.registerFont(TTFont(name, p)); break
            except: pass

# ── 颜色 ──
CC = HexColor('#1a1a2e'); CG = HexColor('#0f3460'); CB = HexColor('#e94560')
CW = white; CL = HexColor('#f8f8f8'); CD = HexColor('#888888')
R = HexColor('#d32f2f'); G = HexColor('#2e7d32'); O = HexColor('#e67e22')

# ── 样式工厂 ──
BODY = ParagraphStyle('body', fontName='CN', fontSize=10, textColor=CC, alignment=TA_JUSTIFY, leading=16, spaceAfter=3)
BODY_B = ParagraphStyle('body_b', fontName='CN-Bold', fontSize=10, textColor=CC, alignment=TA_JUSTIFY, leading=16, spaceAfter=3)
SMALL = ParagraphStyle('small', fontName='CN', fontSize=8, textColor=CD, leading=11)
H1 = ParagraphStyle('h1', fontName='CN-Bold', fontSize=16, textColor=CB, leading=24, spaceAfter=6)
H2 = ParagraphStyle('h2', fontName='CN-Bold', fontSize=13, textColor=CC, leading=20, spaceAfter=4)
H3 = ParagraphStyle('h3', fontName='CN-Bold', fontSize=11, textColor=CG, leading=16, spaceAfter=4)
TITLE = ParagraphStyle('title', fontName='CN-Bold', fontSize=22, textColor=CW, alignment=TA_CENTER, leading=30)
SUB = ParagraphStyle('sub', fontName='CN', fontSize=12, textColor=HexColor('#aabbcc'), alignment=TA_CENTER, leading=18)
GOOD = ParagraphStyle('good', fontName='CN-Bold', fontSize=10, textColor=G, alignment=TA_JUSTIFY, leading=16, spaceAfter=3)
WARN = ParagraphStyle('warn', fontName='CN-Bold', fontSize=10, textColor=R, alignment=TA_JUSTIFY, leading=16, spaceAfter=3)

def P(text, style=BODY): return Paragraph(text, style)

# ── 表格样式 ──
def make_table(data, col_widths, header=True):
    t = Table(data, colWidths=col_widths)
    style = [
        ('GRID',(0,0),(-1,-1),0.5,HexColor('#cccccc')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('FONTSIZE',(0,0),(-1,-1),9),
        ('FONTNAME',(0,1),(-1,-1),'CN'),
    ]
    if header:
        style += [('BACKGROUND',(0,0),(-1,0),CG),('TEXTCOLOR',(0,0),(-1,0),CW),
                   ('FONTNAME',(0,0),(-1,0),'CN-Bold')]
    style += [('ROWBACKGROUNDS',(0,1),(-1,-1),[CW,CL])]
    t.setStyle(TableStyle(style))
    return t

# ── 风险分析引擎 ──
def analyze_risk(student):
    risks = []
    score = student.get('均分','0')
    try: score = float(score)
    except: score = 75
    
    ielts = student.get('雅思','')
    subjects = student.get('各科','')
    
    # 数学风险
    if any(w in subjects for w in ['数学','高数','微积分']):
        for part in subjects.split('，'):
            if any(w in part for w in ['数学','高数','微积分']):
                nums = re.findall(r'(\d+)', part)
                if nums and int(nums[-1]) < 75:
                    risks.append({'维度':'数学基础','等级':'🔴 高','说明':'数学基础薄弱，影响核心课学习'})
                    break
    
    # 均分风险
    if score < 75: risks.append({'维度':'整体均分','等级':'🟡 中','说明':f'均分{score}，处于录取线边缘'})
    elif score >= 80: risks.append({'维度':'整体均分','等级':'🟢 低','说明':f'均分{score}，学术基础良好'})
    
    # 语言风险
    try:
        ielts_score = float(re.findall(r'总分\s*(\d+\.?\d*)', ielts)[0])
        if ielts_score < 6.5: risks.append({'维度':'语言能力','等级':'🟡 中',f'说明':f'雅思{ielts_score}，需提升'})
        else: risks.append({'维度':'语言能力','等级':'🟢 低','说明':f'雅思{ielts_score}，达标'})
    except: pass
    
    # 跨专业风险
    target = student.get('目标专业','')
    current = student.get('在读专业','')
    if any(w in target for w in ['金融','经济','会计']) and any(w in current for w in ['自动化','电子','计算机','机械']):
        risks.append({'维度':'跨专业衔接','等级':'🟡 中','说明':f'{current}→{target}，有相关性但需补专业基础'})
    
    # 预科缓冲
    if student.get('预科','无') != '无':
        risks.append({'维度':'预科缓冲','等级':'🟢 利好','说明':'有预科缓冲期，可弥补短板'})
    
    if not risks:
        risks = [{'维度':'综合','等级':'🟢 低','说明':'基于已有信息，无显著风险点'}]
    
    # 评估整体风险等级
    high = sum(1 for r in risks if '🔴' in r['等级'])
    mid = sum(1 for r in risks if '🟡' in r['等级'])
    if high >= 2: overall = '🔴 高风险'
    elif high >= 1 or mid >= 2: overall = '🟡 中等风险'
    else: overall = '🟢 低风险'
    
    return risks, overall

# ── 学习规划建议引擎 ──
def generate_plan(student, risks):
    plans = []
    subjects = student.get('各科','')
    ielts = student.get('雅思','')
    
    # 阶段一：开学前
    plans.append(('阶段一：开学前准备', [
        '了解目标院校课程设置，明确必修课与选修课',
        '强化薄弱科目（参见风险分析中的高/中风险项）',
        '预习核心专业课英文教材，熟悉专业术语',
        '如雅思未达标（<6.5），优先备考雅思'
    ]))
    
    # 阶段二：第一学期选课策略
    plans.append(('阶段二：第一学期选课建议', [
        '优先选计算机/数据分析相关课程（如有编程基础）',
        '避免第一学期集中选数学密集型课程',
        '主动参加学校Academic Skills辅导',
        '建立学习小组，应对group assignment'
    ]))
    
    # 阶段三
    plans.append(('阶段三：后续学期', [
        '根据第一学期成绩调整选课策略',
        '逐步挑战高难度核心课程',
        '开始准备毕业论文/研究项目选题',
        '关注实习和就业资源'
    ]))
    
    return plans

# ── 抓取课程信息 ──
def fetch_courses(student):
    target = student.get('目标院校','')
    major = student.get('目标专业','')
    
    # 尝试从官网抓取
    urls = {
        '曼彻斯特大学': ('https://www.alliancembs.manchester.ac.uk/study/masters/', 'MSc'),
        '新南威尔士大学': ('https://www.unsw.edu.au/study/postgraduate/', 'Master'),
        'UNSW': ('https://www.unsw.edu.au/study/postgraduate/', 'Master'),
        '利兹大学': ('https://courses.leeds.ac.uk/', 'MSc'),
        '伯明翰大学': ('https://www.birmingham.ac.uk/postgraduate/courses/', 'MSc'),
        '谢菲尔德大学': ('https://www.sheffield.ac.uk/postgraduate/', 'MSc'),
    }
    
    course_info = {
        '来源': '未抓取（请补充官方课表文档以获得精确评估）',
        '学位名称': major,
        '学制': '1-2年（视具体学校而定）',
        '学费': '请参考学校官网最新公示',
        '核心课程': ['（请提供官方课表以获得精确课程列表）'],
        '考核方式': '考试+论文+小组项目（视具体课程）',
    }
    
    # 尝试抓取
    for uni, (base_url, prefix) in urls.items():
        if uni in target or target in uni:
            try:
                # 构造搜索URL
                search_url = f"{base_url}"
                req = urllib.request.Request(search_url, headers={'User-Agent':'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=15)
                html = resp.read().decode('utf-8', errors='ignore')
                
                # 提取课程名称
                course_names = re.findall(r'"title":"([^"]{5,100})"', html)
                if course_names:
                    relevant = [c for c in course_names[:20] if any(w in c.lower() for w in 
                        ['account','finance','economic','management','engineering','electrical',
                         'signal','power','control','business'])]
                    if relevant:
                        course_info['核心课程'] = relevant[:10]
                        course_info['来源'] = f'{uni}官网（提取日期：{datetime.date.today()}）'
                
                # 提取学费
                fees = re.findall(r'[£$€]\s*[\d,]+', html)
                if fees:
                    course_info['学费'] = f'约 {fees[0]}（具体以官网为准）'
            except:
                pass
            break
    
    return course_info

# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════
def main(s=None):
    if s is None:
        s = STUDENT_DATA_TEST
    elif STUDENT_DATA is not None:
        s = STUDENT_DATA
    if s is None:
        print('请提供学生数据')
        return
    today = datetime.date.today().strftime('%Y-%m-%d')
    
    # 基础校验
    if s['姓名'] == '学生姓名':
        print('⚠️ 请先编辑脚本顶部的 STUDENT_DATA，填入真实学生信息！')
        print('   修改完后保存，然后运行：python3 龙虾7号.py')
        return
    
    # 分析
    risks, overall = analyze_risk(s)
    plans = generate_plan(s, risks)
    courses = fetch_courses(s)
    
    # 输出到 BytesIO（返回 bytes，不写文件）
    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=16*mm, bottomMargin=22*mm)
    story = []
    
    # ── 封面 ──
    story.append(Spacer(1, 25*mm))
    story.append(P('学业风险分析', TITLE))
    story.append(P('与升学规划报告', TITLE))
    story.append(Spacer(1, 10*mm))
    story.append(P(f'{s["目标院校"]} · {s["目标专业"]}', SUB))
    story.append(Spacer(1, 8*mm))
    
    cover_data = [
        ['学生姓名', s['姓名']], ['在读院校', f'{s["在读院校"]} · {s["在读专业"]}'],
        ['当前均分', s['均分']], ['雅思成绩', s['雅思']],
        ['目标院校', s['目标院校']], ['目标专业', s['目标专业']],
        ['升学路径', f'{s.get("预科","无")}{"→" if s.get("预科","无")!="无" else ""}{s["目标院校"]}硕士'],
        ['Offer状态', s.get('Offer','未知')], ['报告日期', today],
    ]
    t_cover = Table([[P(k, BODY_B), P(v)] for k,v in cover_data], colWidths=[35*mm, 115*mm])
    t_cover.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('BOTTOMPADDING',(0,0),(-1,-1),3*mm),('TEXTCOLOR',(0,0),(0,-1),CD)]))
    story.append(t_cover)
    story.append(Spacer(1, 8*mm))
    story.append(P(f'<b>综合风险评级：{overall}</b>', BODY_B))
    story.append(P(f'<b>数据来源：</b>{courses.get("来源","基于案例库分析")}，生成日期：{today}', SMALL))
    story.append(PageBreak())
    
    # ── 一、基本情况 ──
    story.append(P('一、学生基本情况', H1))
    story.append(P(f'<b>{s["姓名"]}</b>，就读于{s["在读院校"]}{s["在读专业"]}，当前均分{s["均分"]}。雅思成绩：{s["雅思"]}。目标升读{s["目标院校"]}{s["目标专业"]}。Offer状态：{s.get("Offer","-")}。', BODY))
    if s.get('预科','无') != '无':
        story.append(P(f'升学路径包含{s["预科"]}预科/桥梁课程，再衔接硕士正课。', BODY))
    story.append(Spacer(1, 4*mm))
    
    # 成绩
    story.append(P('各科成绩：', H3))
    for subj in s['各科'].split('，'):
        story.append(P(f'• {subj.strip()}', BODY))
    story.append(Spacer(1, 6*mm))
    
    # ── 二、风险评估 ──
    story.append(P('二、学业风险评估', H1))
    risk_data = [['风险维度','风险等级','说明']]
    for r in risks: risk_data.append([r['维度'], r['等级'], r['说明']])
    story.append(make_table(risk_data, [35*mm, 22*mm, 105*mm]))
    story.append(Spacer(1, 4*mm))
    story.append(P(f'<b>综合风险评级：{overall}</b>', H2))
    story.append(PageBreak())
    
    # ── 三、目标院校分析 ──
    story.append(P('三、目标院校与专业分析', H1))
    story.append(P(f'<b>{s["目标院校"]}</b>', H2))
    
    uni_data = [
        ['项目','内容'],
        ['学位名称', courses['学位名称']],
        ['学制', courses['学制']],
        ['学费（参考）', courses['学费']],
        ['考核方式', courses['考核方式']],
    ]
    story.append(make_table(uni_data, [35*mm, 127*mm]))
    story.append(Spacer(1, 4*mm))
    
    story.append(P('<b>核心课程（参考）</b>', H3))
    for c in courses['核心课程'][:10]:
        story.append(P(f'• {c}', BODY))
    story.append(P(f'<font color="#888888">注：{courses["来源"]}。如有官方课表文档可提供，将获得精确到课程代码的评估。</font>', SMALL))
    story.append(Spacer(1, 8*mm))
    
    # ── 四、学习规划 ──
    story.append(P('四、分阶段学习规划建议', H1))
    for stage_title, items in plans:
        story.append(P(f'<b>{stage_title}</b>', H3))
        for item in items:
            story.append(P(f'• {item}', BODY))
        story.append(Spacer(1, 3*mm))
    
    story.append(PageBreak())
    
    # ── 五、总结 ──
    story.append(P('五、总结', H1))
    summary = f'{s["姓名"]}的升学目标为{s["目标院校"]}{s["目标专业"]}。'
    if overall == '🟢 低风险':
        summary += '基于当前信息，学业风险较低，建议按规划稳步推进即可。'
    elif '中等' in overall:
        summary += '存在一定学业风险，建议重点关注薄弱科目，充分利用开学前窗口期做好准备。'
    else:
        summary += '学业风险较高，需从现在开始系统性准备，重点关注高风险科目的前置学习。'
    story.append(P(summary, BODY))
    story.append(Spacer(1, 10*mm))
    
    story.append(P(f'<b>建议下一步：</b>确认目标院校具体课程设置后，可针对性调整学习计划。如有官方课表，可提供以获得逐课评估。', BODY))
    story.append(Spacer(1, 12*mm))
    
    story.append(P(f'报告生成日期：{today} | 基于学管定制评估 | 数据来源以官网当时显示为准', SMALL))
    
    # ── 生成 ──
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ── 可导入函数 ──
def generate_report(student_data):
    """供系统调用的入口函数"""
    return main(student_data)

if __name__ == '__main__':
    # 测试用数据
    STUDENT_DATA_TEST = {
        "姓名": "学生姓名",
        "在读院校": "XX大学",
        "在读专业": "XX专业",
        "均分": "85",
        "雅思": "总分7.0(听力7阅读7写作6.5口语6.5)",
        "目标院校": "曼彻斯特大学",
        "目标专业": "MSc Accounting and Finance",
        "预科": "无",
        "Offer": "已拿",
        "各科": "会计90，财务管理88，高数75，英语85",
        "备注": "",
    }
    main(STUDENT_DATA_TEST)
