import json as _content_json
from pathlib import Path as _ContentPath

REPORT_TEXT = _content_json.loads(
    _ContentPath(__file__)
    .with_name("build_three_school_report.content.tr.json")
    .read_text(encoding="utf-8")
)
from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / REPORT_TEXT["text_203"]
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, file in [("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf")]:
    pdfmetrics.registerFont(TTFont(name, "C:/Windows/Fonts/" + file))
pdfmetrics.registerFontFamily(
    "Arial", normal="Arial", bold="Arial-Bold", italic="Arial", boldItalic="Arial-Bold"
)
styles = getSampleStyleSheet()
for name, size, lead, color, bold in [
    ("BodyTR", 10, 14.5, "#253847", False),
    ("TitleTR", 27, 33, "#173C50", True),
    ("HeadTR", 18, 23, "#173C50", True),
    ("SubTR", 12.5, 17, "#087E8B", True),
    ("SmallTR", 8, 11, "#526674", False),
]:
    styles.add(
        ParagraphStyle(
            name=name,
            fontName="Arial-Bold" if bold else "Arial",
            fontSize=size,
            leading=lead,
            textColor=HexColor(color),
            spaceAfter=8,
            spaceBefore=8 if name == "SubTR" else 0,
        )
    )
story = []


def p(t, style="BodyTR"):
    story.append(Paragraph(t, styles[style]))


def h(t):
    p(t, "SubTR")


def item(label, t):
    p("<b>" + label + ":</b> " + t)


def page(t):
    if story:
        story.append(PageBreak())
    p(t, "HeadTR")


S = {
    1: ("UofT - MSc eligibility", "https://web.cs.toronto.edu/graduate/msc"),
    2: ("UofT - Direct-Entry PhD", "https://web.cs.toronto.edu/graduate/phd"),
    3: (
        "UBC - Online application / supervisor contact",
        "https://www.cs.ubc.ca/students/grad/admissions/application-components-required-documents/online-application",
    ),
    4: (
        "Waterloo - Applying and admissions",
        "https://cs.uwaterloo.ca/future-graduate-students/applying-admissions",
    ),
    5: ("Alla Sheffer - Research / recruiting", "https://www.cs.ubc.ca/~sheffa/intro.html"),
    6: ("Sheffer - Prospective students / group", "https://www.cs.ubc.ca/~sheffa/Graduate.html"),
    7: (
        "Ma, Vining, Lefebvre, Sheffer - Game Level Layout (2014)",
        "https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.12314",
    ),
    8: ("LevelSyn - Authors' code and data", "https://github.com/chongyangma/LevelSyn"),
    9: (REPORT_TEXT["text_219"], "https://www.cs.ubc.ca/labs/imager/tr/2022/SketchConnectivity/"),
    10: ("Sheffer - Publications, including 2026", "https://www.cs.ubc.ca/~sheffa/pap_list.html"),
    11: ("Xue Bin Peng - UBC move and research", "https://xbpeng.github.io/"),
    12: (
        "Peng - Current prospective students instructions",
        "https://xbpeng.github.io/prospective_students/index.html",
    ),
    13: ("Peter Yichen Chen - PhysAI research", "https://peterchencyc.com/"),
    14: (
        "UBC - Peter Chen research overview",
        "https://www.cs.ubc.ca/news/2026/01/new-faculty-dr-peter-yichen-chen",
    ),
    15: ("Karan Singh - Research", "https://www.dgp.toronto.edu/~karan/"),
    16: (REPORT_TEXT["text_220"], "https://em-yu.github.io/research/cassie/"),
    17: (
        "Jacobson - Fall 2027 recruiting / publications / FAQ",
        "https://www.cs.toronto.edu/~jacobson/",
    ),
    18: (
        "Jacobson - Progressive Convex Hull Simplification (2026)",
        "https://arxiv.org/abs/2604.14468",
    ),
    19: (
        "Text-guided Controllable Mesh Refinement (2024)",
        "https://text-mesh-refinement-project.github.io/",
    ),
    20: ("Sanja Fidler - Research / general recruiting", "https://www.cs.toronto.edu/~fidler/"),
    21: (REPORT_TEXT["text_221"], "https://arxiv.org/abs/2503.03751"),
    22: ("Aviad Levis - Research", "https://www.aviadlevis.info/"),
    23: ("PI-Vision - Current research / publications", "https://pi-vision.github.io/"),
    24: ("Craig Kaplan - Research and Fall 2026 group", "https://cs.uwaterloo.ca/~csk/"),
    25: (
        "Kaplan - CS898 2025 project ideas",
        "https://cs.uwaterloo.ca/~csk/teaching/cs898/s25/project.html",
    ),
    26: ("Steinberg - Research and publications", "https://ssteinberg.xyz/"),
    27: (
        "Steinberg, Pharr - Wave Tracing (2026)",
        "https://ssteinberg.xyz/2025/08/28/generalizing_the_path_integral/",
    ),
    28: (
        "Batty - Join the Computational Motion Group",
        "https://cs.uwaterloo.ca/~c2batty/join.html",
    ),
    29: ("Batty - Current research / simulation code", "https://cs.uwaterloo.ca/~c2batty/"),
    30: (
        "van de Panne - Intake depends on funding",
        "https://www.cs.ubc.ca/~van/opportunities.html",
    ),
    31: ("Hachisuka - Capacity statement", "https://cs.uwaterloo.ca/~thachisu/index.html"),
}


def ref(*ids):
    p(
        REPORT_TEXT["text_222"]
        + " · ".join(
            (
                '<a href="'
                + S[i][1]
                + '" color="#087E8B">['
                + str(i)
                + "] "
                + escape(S[i][0])
                + "</a>"
                for i in ids
            )
        ),
        "SmallTR",
    )


def table(rows, widths):
    t = Table(
        [[Paragraph(escape(c), styles["SmallTR"]) for c in row] for row in rows],
        colWidths=widths,
        hAlign="LEFT",
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#DAEFF0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#CFDFE3")),
            ]
        )
    )
    story.append(t)


p(REPORT_TEXT["text_001"], "SmallTR")
p("PlayableSketch<br/>UBC · UofT · Waterloo", "TitleTR")
p(REPORT_TEXT["text_002"], "SubTR")
p(REPORT_TEXT["text_003"])
h(REPORT_TEXT["text_004"])
p(REPORT_TEXT["text_005"])
ref(1, 2)
h(REPORT_TEXT["text_006"])
item(REPORT_TEXT["text_007"], REPORT_TEXT["text_008"])
item(REPORT_TEXT["text_009"], REPORT_TEXT["text_010"])
p(REPORT_TEXT["text_011"], "SmallTR")
page(REPORT_TEXT["text_012"])
table(
    [
        [REPORT_TEXT["text_223"], REPORT_TEXT["text_013"], REPORT_TEXT["text_014"]],
        ["Alla Sheffer / UBC", REPORT_TEXT["text_015"], REPORT_TEXT["text_016"]],
        [REPORT_TEXT["text_224"], REPORT_TEXT["text_017"], REPORT_TEXT["text_018"]],
        ["Peter Yichen Chen / UBC", REPORT_TEXT["text_019"], REPORT_TEXT["text_020"]],
        ["Karan Singh / UofT", REPORT_TEXT["text_021"], REPORT_TEXT["text_022"]],
        ["Alec Jacobson / UofT", REPORT_TEXT["text_023"], REPORT_TEXT["text_024"]],
        ["Sanja Fidler / UofT", REPORT_TEXT["text_025"], REPORT_TEXT["text_026"]],
        ["Aviad Levis / UofT", REPORT_TEXT["text_027"], REPORT_TEXT["text_028"]],
        ["Craig Kaplan / Waterloo", REPORT_TEXT["text_029"], REPORT_TEXT["text_030"]],
        ["Shlomi Steinberg / Waterloo", REPORT_TEXT["text_031"], REPORT_TEXT["text_032"]],
        ["Christopher Batty / Waterloo", REPORT_TEXT["text_033"], REPORT_TEXT["text_034"]],
    ],
    [112, 220, 169],
)
p(REPORT_TEXT["text_035"], "SmallTR")
ref(5, 12, 13, 15, 17, 20, 22, 24, 26, 28)
page(REPORT_TEXT["text_036"])
p(REPORT_TEXT["text_037"])
h(REPORT_TEXT["text_038"])
p(REPORT_TEXT["text_039"])
p(REPORT_TEXT["text_040"])
h(REPORT_TEXT["text_041"])
p(REPORT_TEXT["text_042"])
p(REPORT_TEXT["text_043"])
h(REPORT_TEXT["text_204"])
p(REPORT_TEXT["text_044"])
item(REPORT_TEXT["text_045"], REPORT_TEXT["text_046"])
item(REPORT_TEXT["text_047"], REPORT_TEXT["text_048"])
ref(7, 8)
page(REPORT_TEXT["text_049"])
item(REPORT_TEXT["text_050"], REPORT_TEXT["text_051"])
h(REPORT_TEXT["text_052"])
p(REPORT_TEXT["text_053"])
p(REPORT_TEXT["text_054"])
h(REPORT_TEXT["text_205"])
item(REPORT_TEXT["text_055"], REPORT_TEXT["text_056"])
item(REPORT_TEXT["text_057"], REPORT_TEXT["text_058"])
h(REPORT_TEXT["text_059"])
p(REPORT_TEXT["text_060"])
item(REPORT_TEXT["text_061"], REPORT_TEXT["text_062"])
item(REPORT_TEXT["text_063"], REPORT_TEXT["text_064"])
item(REPORT_TEXT["text_206"], REPORT_TEXT["text_065"])
ref(5, 6, 7, 9, 10)
page(REPORT_TEXT["text_066"])
h(REPORT_TEXT["text_067"])
p(REPORT_TEXT["text_068"])
item(REPORT_TEXT["text_069"], REPORT_TEXT["text_070"])
item("Ek", REPORT_TEXT["text_071"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_072"])
item(REPORT_TEXT["text_073"], REPORT_TEXT["text_074"])
ref(11, 12)
h(REPORT_TEXT["text_075"])
p(REPORT_TEXT["text_076"])
item("Ek", REPORT_TEXT["text_077"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_078"])
item(REPORT_TEXT["text_079"], REPORT_TEXT["text_080"])
ref(13, 14)
page(REPORT_TEXT["text_081"])
p(REPORT_TEXT["text_082"])
h(REPORT_TEXT["text_083"])
p(REPORT_TEXT["text_084"])
h(REPORT_TEXT["text_205"])
item(REPORT_TEXT["text_055"], REPORT_TEXT["text_085"])
item(REPORT_TEXT["text_086"], REPORT_TEXT["text_087"])
item(REPORT_TEXT["text_208"], REPORT_TEXT["text_088"])
h(REPORT_TEXT["text_089"])
p(REPORT_TEXT["text_090"])
item(REPORT_TEXT["text_091"], REPORT_TEXT["text_092"])
item(REPORT_TEXT["text_093"], REPORT_TEXT["text_094"])
item("Demo", REPORT_TEXT["text_095"])
item(REPORT_TEXT["text_209"], REPORT_TEXT["text_096"])
ref(15, 16)
page(REPORT_TEXT["text_097"])
p(REPORT_TEXT["text_098"])
h(REPORT_TEXT["text_099"])
item(REPORT_TEXT["text_100"], REPORT_TEXT["text_101"])
item(REPORT_TEXT["text_102"], REPORT_TEXT["text_103"])
h(REPORT_TEXT["text_104"])
p(REPORT_TEXT["text_105"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_106"])
item(REPORT_TEXT["text_210"], REPORT_TEXT["text_107"])
item("Demo", REPORT_TEXT["text_108"])
item(REPORT_TEXT["text_209"], REPORT_TEXT["text_109"])
p(REPORT_TEXT["text_110"], "SmallTR")
ref(17, 18, 19)
page(REPORT_TEXT["text_111"])
h(REPORT_TEXT["text_112"])
p(REPORT_TEXT["text_113"])
item(REPORT_TEXT["text_069"], REPORT_TEXT["text_114"])
item(REPORT_TEXT["text_211"], REPORT_TEXT["text_115"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_116"])
item(REPORT_TEXT["text_212"], REPORT_TEXT["text_117"])
ref(20, 21)
h(REPORT_TEXT["text_118"])
p(REPORT_TEXT["text_119"])
item(REPORT_TEXT["text_211"], REPORT_TEXT["text_120"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_121"])
item(REPORT_TEXT["text_079"], REPORT_TEXT["text_122"])
ref(22, 23)
page(REPORT_TEXT["text_123"])
p(REPORT_TEXT["text_124"])
h(REPORT_TEXT["text_125"])
p(REPORT_TEXT["text_126"])
h(REPORT_TEXT["text_127"])
item(REPORT_TEXT["text_055"], REPORT_TEXT["text_128"])
item(REPORT_TEXT["text_057"], REPORT_TEXT["text_129"])
item(REPORT_TEXT["text_130"], REPORT_TEXT["text_131"])
h(REPORT_TEXT["text_089"])
p(REPORT_TEXT["text_132"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_133"])
item("Demo", REPORT_TEXT["text_134"])
item(REPORT_TEXT["text_209"], REPORT_TEXT["text_135"])
p(REPORT_TEXT["text_136"], "SmallTR")
ref(24, 25)
page("9 | Waterloo - Steinberg ve Batty")
h(REPORT_TEXT["text_137"])
p(REPORT_TEXT["text_138"])
item(REPORT_TEXT["text_069"], REPORT_TEXT["text_139"])
item("Ek", REPORT_TEXT["text_140"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_141"])
item("Karar", REPORT_TEXT["text_142"])
ref(26, 27)
h(REPORT_TEXT["text_143"])
p(REPORT_TEXT["text_144"])
item("Ek", REPORT_TEXT["text_145"])
item(REPORT_TEXT["text_207"], REPORT_TEXT["text_146"])
item("Karar", REPORT_TEXT["text_147"])
ref(28, 29)
page(REPORT_TEXT["text_148"])
table(
    [
        [REPORT_TEXT["text_149"], REPORT_TEXT["text_150"], REPORT_TEXT["text_151"]],
        ["1", REPORT_TEXT["text_152"], REPORT_TEXT["text_153"]],
        ["2", REPORT_TEXT["text_154"], "Validation + stable GUID; Sheffer/Jacobson"],
        ["3", REPORT_TEXT["text_155"], REPORT_TEXT["text_156"]],
        ["4", REPORT_TEXT["text_157"], REPORT_TEXT["text_158"]],
        ["5", REPORT_TEXT["text_159"], REPORT_TEXT["text_160"]],
        ["6", REPORT_TEXT["text_161"], REPORT_TEXT["text_162"]],
    ],
    [36, 257, 208],
)
p(REPORT_TEXT["text_163"], "SmallTR")
h(REPORT_TEXT["text_164"])
p(REPORT_TEXT["text_165"])
h(REPORT_TEXT["text_166"])
item(REPORT_TEXT["text_167"], REPORT_TEXT["text_168"])
item(REPORT_TEXT["text_169"], REPORT_TEXT["text_170"])
item(REPORT_TEXT["text_171"], REPORT_TEXT["text_172"])
item(REPORT_TEXT["text_173"], REPORT_TEXT["text_174"])
page(REPORT_TEXT["text_175"])
p(REPORT_TEXT["text_176"])
item(REPORT_TEXT["text_213"], REPORT_TEXT["text_177"])
item(REPORT_TEXT["text_214"], REPORT_TEXT["text_178"])
item(REPORT_TEXT["text_215"], REPORT_TEXT["text_179"])
item(REPORT_TEXT["text_216"], REPORT_TEXT["text_180"])
item(REPORT_TEXT["text_217"], REPORT_TEXT["text_181"])
item(REPORT_TEXT["text_218"], REPORT_TEXT["text_182"])
h(REPORT_TEXT["text_183"])
item("UBC", REPORT_TEXT["text_184"])
item("Waterloo", REPORT_TEXT["text_185"])
item("UofT", REPORT_TEXT["text_186"])
ref(3, 4, 12)
page(REPORT_TEXT["text_187"])
h(REPORT_TEXT["text_188"])
p(REPORT_TEXT["text_189"])
p(REPORT_TEXT["text_190"])
h(REPORT_TEXT["text_191"])
p(REPORT_TEXT["text_192"])
h(REPORT_TEXT["text_193"])
p(REPORT_TEXT["text_194"])
p(REPORT_TEXT["text_195"])
ref(30, 31)
h(REPORT_TEXT["text_196"])
p(REPORT_TEXT["text_197"])
p(REPORT_TEXT["text_198"], "SmallTR")
p(REPORT_TEXT["text_199"])


def footer(c, doc):
    w, h = doc.pagesize
    c.setStrokeColor(HexColor("#CEDFE3"))
    c.line(47, 42, w - 47, 42)
    c.setFont("Arial", 8)
    c.setFillColor(HexColor("#526674"))
    c.drawString(47, 29, REPORT_TEXT["text_200"])
    c.drawRightString(w - 47, 29, str(doc.page))


doc = SimpleDocTemplate(
    str(OUT),
    pagesize=(595.28, 841.89),
    rightMargin=47,
    leftMargin=47,
    topMargin=43,
    bottomMargin=57,
    title=REPORT_TEXT["text_201"],
    author=REPORT_TEXT["text_202"],
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
