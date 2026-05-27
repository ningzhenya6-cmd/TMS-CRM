#!/usr/bin/env python3
"""继续扩充：学术写作、研究生申请、更多国家深度内容、更多案例"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge.store import get_store


ENTRIES = []

def add(title, content, category, tags, related_questions=None):
    ENTRIES.append({
        "title": title,
        "content": content,
        "category": category,
        "tags": tags,
        "related_questions": related_questions or [],
    })


# ============================================================
# 学术写作 (academic-writing)
# ============================================================
add(
    "学术写作核心技巧：从Outline到Final Draft",
    "学术写作是留学生最需要掌握的技能之一，直接关系到成绩。\n\n"
    "Outline先行：\n"
    "1. Thesis Statement(论点)：一句话概括你的核心观点\n"
    "2. 每个段落一个Topic Sentence(主题句)\n"
    "3. 每个论点至少配一个Evidence(证据)\n"
    "4. 每个Evidence之后配一个Analysis(分析)\n\n"
    "段落结构(TEAL模型)：\n- T(Topic Sentence)：段落主题句\n"
    "- E(Evidence)：引用文献/数据/案例\n"
    "- A(Analysis)：分析证据如何支持论点\n"
    "- L(Link)：链接回主论点或过渡到下一段\n\n"
    "实用工具：Grammarly(语法检查)、Hemingway Editor(可读性)、"
    "Zotero/Mendeley(文献管理)、Google Scholar(学术搜索)\n\n"
    "避免学术不端：直接引用需加引号+页码，改述也要标注来源，"
    "自引也需要标注，Turnitin查重率超过20-30%可能被标记。",
    "academic-writing",
    ["学术写作", "论文", "参考", "写作技巧", "文献"],
    ["学术论文怎么写", "留学生论文技巧", "如何提高学术写作能力"]
)

add(
    "Reference格式指南：APA/MLA/Chicago/Harvard详解",
    "不同学科使用不同的引用格式，搞错了会扣分。\n\n"
    "APA 7th(心理学/教育/商科)：文中引用(Author, Year)，参考文献Author, A. (Year). Title. Publisher.\n\n"
    "MLA 9th(文学/语言/艺术)：文中引用(Author Page)，参考文献Author. Title. Publisher, Year.\n\n"
    "Chicago(历史/社科)：有脚注格式(Notes-Bibliography)和作者-日期格式(Author-Date)两种\n\n"
    "Harvard(英国/澳洲大学常用)：文中引用(Author, Year)，参考文献按字母排列\n\n"
    "建议使用Zotero/Mendeley/EndNote自动管理引用，确认教授偏好的引用格式。",
    "academic-writing",
    ["学术写作", "引用格式", "APA", "MLA", "Chicago", "参考文献"],
    ["APA和MLA区别", "参考文献格式怎么标", "论文引用工具推荐"]
)

add(
    "如何有效利用教授的Office Hour拿到高分",
    "Office Hour是留学生最容易浪费的资源。每周至少去一次。\n\n"
    "去之前准备：提前发邮件预约（如果教授要求的话），准备具体问题，"
    "带上作业/论文草稿/课堂笔记，列出2-3个想讨论的点。\n\n"
    "在Office Hour可以做的事情：请教授看论文大纲给反馈（考前1-2周最合适），"
    "讨论课堂上不理解的概念，请教职业建议，询问RA机会，建立关系（这对推荐信至关重要）。\n\n"
    "中国学生常见误区：觉得自己问题太简单不敢去（教授不会judge你），"
    "只带问题去（也可以分享思考），全程不听（带笔记本记反馈）。\n\n"
    "研究表明：每学期去5次以上Office Hour的学生，平均成绩高出0.5个GPA点。",
    "academic-writing",
    ["Office Hour", "师生互动", "推荐信", "学习方法", "学术支持"],
    ["Office Hour怎么用", "如何和教授有效沟通", "留学生如何拿推荐信"]
)

add(
    "Presentation技巧：留学生课堂演讲高分指南",
    "课堂展示(Presentation)在课程中通常占10-30%的成绩。\n\n"
    "结构设计：开场(Hook)用问题/数据/故事吸引注意力(30秒)，介绍议程(15秒)，"
    "主体3个核心论点各2-3分钟，总结后进入Q&A。\n\n"
    "PPT设计原则：每页不超过5个bullet points，字体至少24pt，"
    "多用图表少用文字，标明引用来源。\n\n"
    "演讲技巧：不要念稿，用提示卡只写关键词；眼神交流覆盖全场；"
    "英文语速130-150词/分钟；用手势辅助表达。\n\n"
    "Q&A应对技巧：不确定时说That is a great question, my understanding is...，"
    "被challenge时说That is an interesting perspective, I think...。",
    "academic-writing",
    ["Presentation", "演讲技巧", "课堂展示", "PPT", "英语演讲"],
    ["课堂展示怎么做", "英语演讲技巧", "Presentation高分技巧"]
)

add(
    "如何避免Plagiarism：学术诚信完整指南",
    "Plagiarism(抄袭)是留学中最严重的学术违规行为，后果包括作业零分、课程不及格甚至开除。\n\n"
    "什么构成Plagiarism：直接复制他人文字不加引用，改述后不标注来源，"
    "自引(self-plagiarism)即使是自己以前写的作业也需要标注，"
    "使用AI生成内容不声明（部分学校政策）。\n\n"
    "如何避免：做笔记时立即标注来源，直接引用<10%，改述(Paraphrase)为主，"
    "不确定时宁愿多引用(Overcite比Undercite安全)，"
    "使用Turnitin/Grammarly提前查重。\n\n"
    "被指控后应对：收集写作过程证据（草稿、笔记），"
    "诚恳解释并承认错误（如果确实犯了），了解学校的Academic Integrity听证会流程。",
    "academic-writing",
    ["学术诚信", "Plagiarism", "抄袭", "引用", "Turnitin"],
    ["如何避免学术抄袭", "Plagiarism后果", "Turnitin查重率多少安全"]
)

# ============================================================
# 研究生申请 (grad-application)
# ============================================================
add(
    "美国研究生申请全流程时间线",
    "美研申请竞争激烈，提前18个月规划是关键。\n\n"
    "1-3月(提前18个月)：确定方向，准备GRE/GMAT，筛选学校(冲刺/匹配/保底各3-5所)\n"
    "4-6月：第一次GRE考试，联系推荐人(提前3-6个月)，暑假实习/科研安排\n"
    "7-8月：准备简历，写SOP初稿，确认推荐信\n"
    "9-10月：注册网申，递交第一批申请(Rolling Admission)，考第二次GRE\n"
    "11-12月：递交大多数学校申请(多数截止12月-1月)，确认推荐信已提交\n"
    "1-3月：面试，等待录取，Waitlist发Love Letter\n"
    "4月：比较offer，确认入学并交定金\n\n"
    "博士申请和硕士申请策略不同——博士更看重研究匹配度。",
    "grad-application",
    ["研究生申请", "美国", "GRE", "留学申请", "时间线"],
    ["美国研究生申请流程", "留学申请时间规划", "美研申请需要准备什么"]
)

add(
    "个人陈述(SOP)写作指南：让招生官记住你",
    "个人陈述(Statement of Purpose)是申请中最重要的文书之一。\n\n"
    "核心结构：\n"
    "1. 开头(Hook)：具体故事说明为什么对这个领域感兴趣\n"
    "2. 学术背景(Why qualified)：课程、研究、GPA\n"
    "3. 研究/职业经历(Why experienced)：实习、项目、论文\n"
    "4. 为什么选这个项目(Why this program)：具体到教授、课程、资源\n"
    "5. 未来规划(Why this matters)：毕业后想做什么\n\n"
    "原则：Show, don't tell。不要说我热爱CS，要描述做了什么项目。"
    "具体到细节，提到教授的论文标题。每段服务一个主题。\n\n"
    "常见错误：一篇SOP申所有学校，只列经历不分析，忽略Why This Program。\n\n"
    "学管服务：我们的文书导师（均有招生委员会经验）可以提供SOP逐段修改服务。",
    "grad-application",
    ["研究生申请", "个人陈述", "SOP", "文书", "申请文书"],
    ["个人陈述怎么写", "SOP写作技巧", "留学申请文书指南"]
)

add(
    "推荐信策略：选谁、怎么说、什么时候要",
    "推荐信(Recommendation Letter)在申请中权重很高。\n\n"
    "选推荐人：学术推荐人(教过你的教授，成绩A以上)最佳，"
    "研究推荐人(科研导师)对PhD/MRes重要，"
    "实习推荐人(工作主管)对professional master's有帮助。"
    "不要找亲友、政治家、名人。\n\n"
    "时间：至少提前1-2个月联系，提前3个月最礼貌。"
    "当面说效果最好(Office Hour提到)。\n\n"
    "准备一个Packet：简历+SOP草稿+学校列表+截止日期。"
    "明确告诉教授需要强调什么方面。\n\n"
    "理想的推荐信阵容：2封学术+1封实习，或者3封全部学术。",
    "grad-application",
    ["研究生申请", "推荐信", "推荐人", "申请材料", "RL"],
    ["推荐信找谁写", "如何向教授要推荐信", "留学推荐信注意事项"]
)

add(
    "GRE/GMAT备考策略：目标分数与复习计划",
    "GRE/GMAT成绩虽然重要性在下降，但高分会带来明显优势。\n\n"
    "GRE vs GMAT：GRE适合大多数项目，GMAT商学院更喜欢(FIN/ACC方向)。\n\n"
    "GRE各档次分数：冲刺HYMPS: 330+(V160+Q170)，Top20: 325+，Top50: 315+。"
    "Q170是亚洲学生优势。\n\n"
    "备考计划(3-4个月)：第1个月背单词(GRE3000词)，第2个月Verbal+Math题型训练，"
    "第3个月模考每周2-3套+错题分析，第4个月冲刺+针对性补弱。\n\n"
    "免费资源：Magoosh GRE Flashcards, PowerPrep Online, GregMat, 考满分。",
    "grad-application",
    ["研究生申请", "GRE", "GMAT", "备考", "标化考试"],
    ["GRE和GMAT选哪个", "GRE备考多久", "GRE多少分算好成绩"]
)

# ============================================================
# 美国学术补充 (us-academic)
# ============================================================
add(
    "美国大学课堂文化：参与与互动的正确方式",
    "美国大学课堂参与(Class Participation)通常占10-20%成绩。\n\n"
    "发言不需要绝对正确——分享观点、提问、回应同学都算参与。"
    "一节课发言1-2次就够，不说It's a good question开头。\n\n"
    "与教授互动：可以直接称呼教授名(建议先称Professor/Dr.)。"
    "对评分有异议先冷静24小时再发邮件。"
    "合理的延交申请通常会被批准(提前24小时说明)。\n\n"
    "给分构成：出勤+参与5-15%，作业/小测20-30%，期中20-30%，期末项目/考试30-40%。"
    "了解每门课权重对复习策略很重要。",
    "us-academic",
    ["美国", "课堂文化", "课堂参与", "学术适应", "留学生活"],
    ["美国课堂文化特点", "如何参与课堂讨论", "美国大学评分标准"]
)

add(
    "美国大学Drop/Withdrawal政策详解",
    "Drop和Withdrawal是两种不同的退课操作。\n\n"
    "Drop(退课)：开学前1-2周，成绩单不留记录，学费全额退还，不需教授签字。\n\n"
    "Withdrawal(学期中退课)：通常第3-10周，成绩单显示W不计入GPA，"
    "部分学费不退，可能影响F1签证(如果学分低于Full-time要求)。\n\n"
    "Late Withdrawal(第10周后)：成绩单显示WF(计为F)或WP，需要特殊情况证明。\n\n"
    "国际学生特别注意：退课后学分低于Full-time(本科12/研究生9)违反F1要求。"
    "必须先咨询International Student Office再退课。",
    "us-academic",
    ["美国", "退课", "Drop", "Withdrawal", "学术政策"],
    ["美国大学怎么退课", "Drop和Withdrawal区别", "退课影响签证吗"]
)

# ============================================================
# 英国学术补充 (uk-academic)
# ============================================================
add(
    "英国大学评分体系与学位等级详解",
    "英国评分体系与美国和中国完全不同。\n\n"
    "本科评分等级：First Class(1st)70%以上(顶尖)，Upper Second(2:1)60-69%"
    "(多数研究生入学要求)，Lower Second(2:2)50-59%，Third Class(3rd)40-49%。\n\n"
    "研究生评分：Distinction 70%+，Merit 60-69%，Pass 50-59%。\n\n"
    "英美评分区别：英国70%=优秀(相当于美国A)。"
    "英国通常只有一次期末考试，大部分评估通过Essay完成。\n\n"
    "Final Year Weighting：最后一年成绩占总学位的60-70%，"
    "即使前两年成绩一般最后一年冲刺也能拿好学位。",
    "uk-academic",
    ["英国", "评分", "学位等级", "First Class", "2:1"],
    ["英国学位等级怎么看", "英国First Class难拿吗", "英国2:1是什么水平"]
)

add(
    "英国大学论文与考试系统",
    "英国大学的评估系统有自己的特色。\n\n"
    "评估类型：Essay(论文，2000-5000字最普遍)，Exam(闭卷论文题)，"
    "Presentation(小组任务)，Dissertation(学位论文，10,000-20,000字)，"
    "Lab Report(实验报告)。\n\n"
    "牛津剑桥特有考试：Collections(每学期初摸底)，Prelims(第一年末资格考试)，"
    "Mods(牛津第二年考试)，Finals(毕业大考)。\n\n"
    "论文考试技巧：选择一个角度深入分析，15分钟列Outline，"
    "引言写Thesis Statement，正文每段有Topic Sentence，结论简洁。",
    "uk-academic",
    ["英国", "考试系统", "论文", "Prelims", "学位论文"],
    ["英国大学考试形式和区别", "牛津剑桥考试系统", "英国论文怎么写"]
)

# ============================================================
# 职业规划 (career-planning)
# ============================================================
add(
    "留学生求职时间线：大一到大四每个关键节点",
    "留学生在海外求职需要提前规划。\n\n"
    "大一：参加Career Fair探索，加入专业社团，更新LinkedIn，写第一版简历。\n"
    "大二：申请Sophomore Internship/Insight Program，参加Info Session，积累社团领导力。\n"
    "大三：申请Summer Internship(最重要！)，参加On-campus Recruiting，"
    "准备行为面试和案例面试。\n"
    "大四：申请Full-time工作，秋招(9-11月)和春招(1-3月)，OPT/CPT/PSW申请。\n\n"
    "各行业招聘时间线：投行/咨询提前1.5-2年，科技提前1年，四大提前1年。",
    "career-planning",
    ["职业规划", "求职", "实习", "招聘时间线", "校园招聘"],
    ["留学生求职怎么规划", "国外实习怎么找", "留学毕业后如何找工作"]
)

add(
    "留学生简历(CV/Resume)写作指南",
    "美式简历(Resume)：严格1页，不附照片，不包含年龄性别婚姻状态。"
    "格式：姓名→联系方式→教育→经历→技能。用动词过去式开头：Developed, Led, Analyzed。\n\n"
    "英式简历(CV)：可2页，附照片(可选)，更详细教育背景。\n\n"
    "写作原则：量化成果用数字/百分比，STAR法则(Situation-Task-Action-Result)，"
    "针对每个岗位定制，从Job Description提取关键词匹配。\n\n"
    "案例对比：\n"
    "差：Worked on a team project\n"
    "好：Led a 4-person team to develop a web app, resulting in 30% efficiency improvement\n\n"
    "学校Career Center的简历修改服务免费，一定要用。",
    "career-planning",
    ["职业规划", "简历", "CV", "求职", "Resume"],
    ["留学生简历怎么写", "英文简历格式要求", "CV和Resume区别"]
)

add(
    "CPT/OPT实习申请流程与注意事项",
    "CPT(课程实习)：必须与课程相关，分Part-time(≤20h/周)和Full-time。"
    "学校DSO在I-20上批准即可，不需USCIS批准。"
    "Full-time CPT超12个月失去OPT资格。\n\n"
    "OPT(选择性实习)：申请窗口毕业前90天到毕业后60天，"
    "USCIS处理3-5个月(建议提前90天申请)，申请费$470。"
    "批准后有效期12个月(STEM可延24个月)，失业期总共不超过90天。\n\n"
    "申请流程：联系国际学生办公室申请OPT I-20(1-2周)，"
    "准备I-765表格+照片+支票，在线或邮寄递交到USCIS，"
    "收到Receipt Number等待审批，批准后收到EAD卡。\n\n"
    "STEM OPT延期要求：雇主是E-Verify认证，提交I-983培训计划。",
    "career-planning",
    ["职业规划", "OPT", "CPT", "实习", "工作签证", "STEM"],
    ["OPT申请条件", "CPT和OPT区别", "STEM OPT延期怎么申请"]
)

# ============================================================
# 香港、马来西亚补充
# ============================================================
add(
    "香港大学选课与学术体系",
    "港大(HKU)：学分制本科需240学分，Common Core需修6门跨学科课程，"
    "大二确定Major，英语授课。\n\n"
    "港中文(CUHK)：College System(书院制)特色，不同书院有不同通识课要求，"
    "弹性学分制修满123学分毕业，中英双语教学。\n\n"
    "港科大(HKUST)：偏重科技与商科，School-based Admission大一通识大二分专业，"
    "60%+学生有交换经历，GPA计算接近美国。\n\n"
    "香港留学优势：离家近文化适应容易，学历国际认可度高，"
    "毕业后可申请IANG签证留港工作(1年)，待满7年可申请永居。",
    "hk-academic",
    ["香港", "港大", "港中文", "港科大", "选课"],
    ["香港大学选课攻略", "香港留学值不值得", "香港大学学术体系"]
)

add(
    "马来西亚留学指南",
    "马来西亚留学费用低(英美1/3至1/4)。\n\n"
    "主要大学：马来亚大学(公立第一)、博特拉大学(农业/生命科学)、"
    "泰莱大学(酒店管理/商科)、蒙纳士大学马来西亚分校(拿澳洲学位)。\n\n"
    "选课特点：公立大学学分制3-4年，私立大学更灵活有双联课程(Twinning Program)。"
    "双联课程：前2年在马来西亚，后1-2年在欧美本校拿学位。\n\n"
    "生活：英语普及率高，生活费约RM1,500-2,500/月(约$300-500美元)，"
    "多元文化，饮食丰富，全年湿热。\n\n"
    "签证：需Student Pass，需要体检，不允许校外打工。",
    "my-academic",
    ["马来西亚", "留学", "选课", "费用", "双联课程"],
    ["马来西亚留学怎么样", "马来西亚大学选哪个", "马来西亚留学费用"]
)

# ============================================================
# 更多案例 (real-cases)
# ============================================================
add(
    "【案例】DIY申请失败后找学管：一个月逆转录取",
    "学生背景：985院校大四，DIY申请美国CS硕士全部被拒。"
    "剩余最后2所学校截止日期前1个月找到学管顾问。\n\n"
    "分析问题：选校策略激进(全部Top20)、文书没有针对性。\n\n"
    "学管紧急介入：Day1-3重新定位从Top20调整到Top30-50梯度选校；"
    "Day4-10重写SOP突出2段实习经历，针对每个学校定制Why This Program；"
    "Day11-20补充推荐信；Day21-30递交申请、逐项检查网申。\n\n"
    "结果：USC CS(37学分)和NYU Tandon CS双双录取。\n\n"
    "学生反馈：如果能早点找学管规划，不会浪费那么多申请费和精力。",
    "real-cases",
    ["案例", "DIY申请", "CS硕士", "USC", "NYU", "学管"],
    ["DIY申请失败怎么办", "留学申请被拒后如何补救", "找留学顾问的重要性"]
)

add(
    "【案例】从挂科边缘到Honor Roll：澳洲留学生转变",
    "学生背景：澳洲八大商科大一，英语弱，到校3个月出现严重适应困难。\n\n"
    "初期问题：期中2门不及格，课堂听不懂，不敢小组讨论，失眠食欲下降。\n\n"
    "学管介入方案：学术层面退掉一门课减少负荷，注册Academic Skills课程，"
    "每周3次Writing Center，学管教使用Lecture录音+字幕学习。"
    "心理层面联系Counselling Service，加入华人学联，每天30分钟运动。\n\n"
    "转折：第8周期中重考通过C+，找到学习小组。\n\n"
    "成果：4门课全部通过(1 Distinction+2 Credit+1 Pass)，"
    "GPA从危机线恢复到4.5/7.0，第二学期提升到5.2/7.0。",
    "real-cases",
    ["案例", "澳洲", "挂科", "GPA恢复", "学业辅导", "学管"],
    ["澳洲留学挂科了怎么办", "留学生不适应国外学习", "学管辅导经验"]
)

add(
    "【案例】从社区大学到UC Irvine：本科转学Top30",
    "学生背景：国内普高毕业，GPA 2.8，托福85，直接申请美本Top50概率很低。\n\n"
    "学管制定的CC→Top30转学路径。\n\n"
    "CC阶段(2年)：重点通识课(数学、英语、历史、科学)，目标GPA 3.8+完成60可转学分。"
    "学管帮选转学友好州(加州)，参与Honors Program，加入学生会。\n\n"
    "学术提升：第一学期GPA 3.6，第二学期4.0。"
    "Writing Center每周打卡，暑期社区律师事务所做志愿者。\n\n"
    "转学申请：申请6所UC，学管辅导Personal Statement，"
    "TAG申请UCI和UCSB。\n\n"
    "录取结果：UC Davis、UCI、UCSB录取，最终选择UCI Economics。\n\n"
    "关键：CC期间GPA 3.5+才有竞争力，学管对转学协议了解极大减少试错成本。",
    "real-cases",
    ["案例", "社区大学", "转学", "美国", "UC系统", "学管"],
    ["社区大学转学美国名校", "美国CC转学经验", "本科转学申请流程"]
)

add(
    "【案例】英国G5博士全奖申请之路",
    "学生背景：英国Top10大学硕士Distinction毕业。\n\n"
    "优势：成绩优秀，方向明确。劣势：无发表论文，套磁经验不足。\n\n"
    "学管全流程规划(12个月)：\n\n"
    "第1-3个月研究方向和导师筛选：梳理剑桥/牛津/帝国理工/UCL相关导师15位，"
    "阅读每位教授近期3-5篇论文。\n"
    "第4-6个月Research Proposal写作：3轮修改(内容→逻辑→语言)。\n"
    "第7-9个月套磁：设计模板，15封邮件9封回复(5封积极)，3位教授Zoom面谈，"
    "学管安排2次模拟面试。\n"
    "第10-12个月正式申请：递交4所学校，剑桥和帝国理工面试邀请，"
    "3次模拟面试。\n\n"
    "最终结果：剑桥大学全奖博士(含学费+生活津贴£20,000/年)。",
    "real-cases",
    ["案例", "博士申请", "英国G5", "全奖", "剑桥", "学管"],
    ["英国博士申请流程", "博士全奖怎么申请", "博士套磁技巧"]
)

# ============================================================
# 跨文化适应 (cross-cultural)
# ============================================================
add(
    "文化冲击(Culture Shock)的四个阶段与应对",
    "几乎所有留学生都会经历文化冲击。\n\n"
    "阶段一蜜月期(1-3周)：什么都新鲜兴奋。注意这是假象。\n\n"
    "阶段二危机期(1-3个月)：文化差异显现，听不懂笑话和俚语，"
    "思念家乡，每天用英语社交很累。这是最危险阶段，很多人在此期间想放弃。\n\n"
    "阶段三调整期(3-6个月)：开始理解当地文化，交到本地朋友，"
    "课堂主动发言，找到生活节奏。\n\n"
    "阶段四适应期(6个月+)：双语思维切换自然，有自己的社交圈。\n\n"
    "应对策略：阶段二不要做重大决定(不退学不分手)，"
    "找学联学长学姐聊聊，保持和国内联系但不过度，走出舒适圈。",
    "cross-cultural",
    ["跨文化", "文化冲击", "适应", "留学心理", "Culture Shock"],
    ["文化冲击怎么办", "留学适应期多久", "如何快速融入留学生活"]
)

add(
    "留学英语能力提升：全场景指南",
    "托福100分的英语在真实场景下远远不够。\n\n"
    "课堂英语：听不懂就问「Could you clarify what you meant by...」，"
    "请求放慢语速「Could you speak a little slower」，"
    "不要假装听懂，教授更希望你问问题。\n\n"
    "社交英语：Small Talk话题有天气、周末计划、学校活动。"
    "每天和1个外国同学聊天5分钟。听不懂俚语直接问What does that mean?\n\n"
    "学术英语：用However/Furthermore/Therefore替代But/Also/So。"
    "论文用This paper argues/The evidence suggests等学术表达。\n\n"
    "推荐资源：播客The Daily(NYT)、Stuff You Should Know、BBC Global News。"
    "YouTube搜对应课程内容。每天写100字英文日记。",
    "cross-cultural",
    ["跨文化", "英语提升", "学术英语", "社交英语", "留学生英语"],
    ["留学英语怎么提升", "课堂听不懂怎么办", "英语口语怎么练"]
)


def main():
    store = get_store()
    before = len(store.get_all_entries())

    for entry in ENTRIES:
        store.add_entry(entry)
    store.save()

    after = len(store.get_all_entries())
    added = after - before
    print(f"知识库扩充完成：{before} → {after} 条（本次新增 {added} 条）")

    from collections import Counter
    cats = Counter(e.get('category', '') for e in store.get_all_entries())
    print(f"\n分类分布（前15）:")
    for cat, count in cats.most_common(15):
        print(f"  {cat}: {count}条")


if __name__ == '__main__':
    main()
