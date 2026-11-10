import json as _content_json
from pathlib import Path as _ContentPath

REPORT_TEXT = _content_json.loads(
    _ContentPath(__file__)
    .with_name("build_professor_report.content.tr.json")
    .read_text(encoding="utf-8")
)
from pathlib import Path
from html import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / REPORT_TEXT["text_182"]
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFontFamily(
    "Arial", normal="Arial", bold="Arial-Bold", italic="Arial", boldItalic="Arial-Bold"
)
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="BodyTR",
        fontName="Arial",
        fontSize=10,
        leading=14.5,
        spaceAfter=8,
        textColor=HexColor("#233445"),
    )
)
styles.add(
    ParagraphStyle(
        name="TitleTR",
        fontName="Arial-Bold",
        fontSize=27,
        leading=32,
        spaceAfter=18,
        textColor=HexColor("#143B49"),
    )
)
styles.add(
    ParagraphStyle(
        name="HeadTR",
        fontName="Arial-Bold",
        fontSize=18,
        leading=23,
        spaceAfter=13,
        textColor=HexColor("#143B49"),
    )
)
styles.add(
    ParagraphStyle(
        name="SubTR",
        fontName="Arial-Bold",
        fontSize=12.5,
        leading=17,
        spaceBefore=10,
        spaceAfter=7,
        textColor=HexColor("#087F8C"),
    )
)
styles.add(
    ParagraphStyle(
        name="SmallTR",
        fontName="Arial",
        fontSize=8,
        leading=11,
        spaceAfter=6,
        textColor=HexColor("#526674"),
    )
)
story = []
md = []


def p(t, style="BodyTR"):
    story.append(Paragraph(t, styles[style]))
    md.append(t.replace("<b>", "**").replace("</b>", "**"))


def h(t):
    p(t, "SubTR")


def page(t):
    if story:
        story.append(PageBreak())
    p(t, "HeadTR")
    md.append("\n")


def item(label, t):
    p("<b>" + label + ":</b> " + t)


sources = {
    1: ("Brandon Haworth - Prospective Students", "https://bhaworth.ca/students/"),
    2: ("Chenxi Liu - CXL Join Us", "https://chenxil21.github.io/joinus/"),
    3: ("Nathan Sturtevant - Prospective Students", "https://www.movingai.com/prospective.html"),
    4: ("Guzdial - GRAIL Lab", "https://guzdial.com/grail-lab/"),
    5: (REPORT_TEXT["text_200"], "https://arxiv.org/abs/1809.09420"),
    6: (
        "Adam Runions - FGS supervisor profile",
        "https://grad.ucalgary.ca/future-students/supervisor/adam-runions",
    ),
    7: (
        "Richard Zhao - FGS profile",
        "https://grad.ucalgary.ca/future-students/supervisor/richard-zhao",
    ),
    8: (
        "Richard Zhao - Prospective Graduate Students",
        "https://cspages.ucalgary.ca/~richard.zhao1/prospective_notes.html",
    ),
    9: ("Mike Katchabaw - Research", "https://www.csd.uwo.ca/~mkatchab/"),
    10: (
        "Umair Rehman - Department profile",
        "https://www.csd.uwo.ca/people/faculty/bios/rehman.html",
    ),
    11: ("Faramarz Samavati - Research", "https://pages.cpsc.ucalgary.ca/~samavati/"),
    12: (
        "Faramarz Samavati - FGS status",
        "https://grad.ucalgary.ca/future-students/supervisor/faramarz-samavati",
    ),
    13: (
        "Yingying Wang - McMaster profile",
        "https://www.eng.mcmaster.ca/cas/faculty/dr-yingying-wang/",
    ),
    14: ("Angel Chang - Research", "https://angelxuanchang.github.io/"),
    15: ("Manolis Savva - Research", "https://msavva.github.io/"),
    16: ("SceneSeer - Text to 3D Scene Design", "https://arxiv.org/abs/1703.00050"),
    17: (
        "Stephen Kelly - Graduate research topics",
        "https://www.eng.mcmaster.ca/future-students/future-graduate-students/graduate-research-projects/computing-and-software/",
    ),
    18: ("Karan Singh - Research", "https://www.dgp.toronto.edu/~karan/"),
    19: ("Craig Kaplan - Research", "https://uwaterloo.ca/math-innovation/contacts/craig-kaplan"),
    20: ("Christopher Batty - Research", "https://cs.uwaterloo.ca/~c2batty/"),
    21: ("Alla Sheffer - Research and students", "https://www.cs.ubc.ca/~sheffa/intro.html"),
    22: (
        "Peter Yichen Chen - UBC research overview",
        "https://www.cs.ubc.ca/news/2026/01/new-faculty-dr-peter-yichen-chen",
    ),
    23: ("Gunho Sohn - Current recruitment and ESSE route", "https://gunhosohn.me/recruitment/"),
    24: (
        "Petros Faloutsos - York research opportunities",
        "https://lassonde.yorku.ca/grad-research-opportunities",
    ),
    25: ("Nick Graham - Research profile", "https://www.cs.queensu.ca/people/Nick/Graham"),
    26: (
        "Jochen Lang - Engineering profile",
        "https://www.uottawa.ca/faculty-engineering/school-electrical-engineering-computer-science/directory/jochen-lang",
    ),
    27: (
        "Teseo Schneider - UVic profile",
        "https://www.uvic.ca/ecs/computerscience/faculty-staff/faculty/schneider-teseo.php",
    ),
    28: (REPORT_TEXT["text_201"], "https://arxiv.org/abs/1703.00061"),
}


def ref(*ids):
    p(
        REPORT_TEXT["text_204"]
        + " · ".join(
            (
                '<a href="'
                + sources[i][1]
                + '" color="#087F8C">['
                + str(i)
                + "] "
                + escape(sources[i][0])
                + "</a>"
                for i in ids
            )
        ),
        "SmallTR",
    )


p("PLAYABLESKETCH", "SmallTR")
p(REPORT_TEXT["text_001"], "TitleTR")
p(REPORT_TEXT["text_002"], "SubTR")
p(REPORT_TEXT["text_003"])
p(REPORT_TEXT["text_004"])
h(REPORT_TEXT["text_005"])
item(REPORT_TEXT["text_183"], REPORT_TEXT["text_006"])
item(REPORT_TEXT["text_007"], REPORT_TEXT["text_008"])
item(REPORT_TEXT["text_009"], REPORT_TEXT["text_010"])
h(REPORT_TEXT["text_011"])
p(REPORT_TEXT["text_012"])
p(REPORT_TEXT["text_013"], "SmallTR")
page(REPORT_TEXT["text_014"])
p(REPORT_TEXT["text_015"])
item(REPORT_TEXT["text_184"], REPORT_TEXT["text_016"])
item(REPORT_TEXT["text_017"], REPORT_TEXT["text_018"])
item(REPORT_TEXT["text_019"], REPORT_TEXT["text_020"])
item(REPORT_TEXT["text_021"], REPORT_TEXT["text_022"])
item(REPORT_TEXT["text_023"], REPORT_TEXT["text_024"])
h(REPORT_TEXT["text_025"])
p(REPORT_TEXT["text_026"])
h(REPORT_TEXT["text_027"])
p(REPORT_TEXT["text_028"])
p(REPORT_TEXT["text_029"])
p(REPORT_TEXT["text_030"], "SmallTR")
page(REPORT_TEXT["text_031"])
h(REPORT_TEXT["text_032"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_033"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_034"])
item(REPORT_TEXT["text_035"], REPORT_TEXT["text_036"])
item(REPORT_TEXT["text_037"], REPORT_TEXT["text_038"])
item(REPORT_TEXT["text_039"], REPORT_TEXT["text_040"])
p(REPORT_TEXT["text_041"], "SmallTR")
ref(1)
h(REPORT_TEXT["text_042"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_043"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_044"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_045"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_046"])
p(REPORT_TEXT["text_047"], "SmallTR")
ref(2)
page(REPORT_TEXT["text_048"])
h(REPORT_TEXT["text_049"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_050"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_051"])
item(REPORT_TEXT["text_189"], REPORT_TEXT["text_052"])
item(REPORT_TEXT["text_190"], REPORT_TEXT["text_053"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_054"])
p(REPORT_TEXT["text_055"], "SmallTR")
ref(3)
h(REPORT_TEXT["text_056"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_057"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_058"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_059"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_060"])
ref(4, 5)
page(REPORT_TEXT["text_061"])
h(REPORT_TEXT["text_062"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_063"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_064"])
item(REPORT_TEXT["text_035"], REPORT_TEXT["text_065"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_066"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_067"])
ref(6)
h(REPORT_TEXT["text_191"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_068"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_069"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_070"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_071"])
ref(7, 8)
page(REPORT_TEXT["text_072"])
h(REPORT_TEXT["text_073"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_074"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_075"])
item(REPORT_TEXT["text_189"], REPORT_TEXT["text_076"])
item(REPORT_TEXT["text_077"], REPORT_TEXT["text_078"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_079"])
ref(9)
h(REPORT_TEXT["text_080"])
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_081"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_082"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_083"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_084"])
ref(10)
p(REPORT_TEXT["text_085"])
page(REPORT_TEXT["text_086"])
h("Faramarz Samavati | University of Calgary")
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_087"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_088"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_089"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_090"])
ref(11, 12)
h("Yingying Wang | McMaster University")
item(REPORT_TEXT["text_185"], REPORT_TEXT["text_091"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_092"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_093"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_094"])
ref(13)
h(REPORT_TEXT["text_192"])
p(REPORT_TEXT["text_095"])
ref(17)
page(REPORT_TEXT["text_096"])
h(REPORT_TEXT["text_097"])
p(REPORT_TEXT["text_098"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_099"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_100"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_101"])
ref(14, 16)
h(REPORT_TEXT["text_102"])
p(REPORT_TEXT["text_103"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_104"])
item(REPORT_TEXT["text_187"], REPORT_TEXT["text_105"])
item(REPORT_TEXT["text_188"], REPORT_TEXT["text_106"])
ref(15, 28)
h(REPORT_TEXT["text_107"])
p(REPORT_TEXT["text_108"])
p(REPORT_TEXT["text_109"], "SmallTR")
page(REPORT_TEXT["text_110"])
h("University of Toronto | Karan Singh")
p(REPORT_TEXT["text_111"])
ref(18)
h("University of Waterloo | Craig Kaplan")
p(REPORT_TEXT["text_112"])
ref(19)
h("University of Waterloo | Christopher Batty")
p(REPORT_TEXT["text_113"])
ref(20)
h("University of British Columbia | Alla Sheffer")
p(REPORT_TEXT["text_114"])
ref(21)
h("University of British Columbia | Peter Yichen Chen")
p(REPORT_TEXT["text_115"])
ref(22)
page(REPORT_TEXT["text_116"])
h("York University | Petros Faloutsos")
p(REPORT_TEXT["text_117"])
ref(24)
h(REPORT_TEXT["text_118"])
p(REPORT_TEXT["text_119"])
item(REPORT_TEXT["text_186"], REPORT_TEXT["text_120"])
item(REPORT_TEXT["text_189"], REPORT_TEXT["text_121"])
ref(23)
h("Queen's University | Nick Graham")
p(REPORT_TEXT["text_122"])
ref(25)
h("University of Ottawa | Jochen Lang")
p(REPORT_TEXT["text_123"])
ref(26)
p(REPORT_TEXT["text_124"], "SmallTR")
ref(27)
page(REPORT_TEXT["text_125"])
h(REPORT_TEXT["text_126"])
rows = [
    [REPORT_TEXT["text_127"], REPORT_TEXT["text_202"], REPORT_TEXT["text_203"]],
    ["1", REPORT_TEXT["text_128"], REPORT_TEXT["text_129"]],
    ["2", REPORT_TEXT["text_130"], "Liu, Guzdial, Singh, Samavati"],
    ["3", REPORT_TEXT["text_131"], "Sturtevant, Guzdial, Runions"],
    ["4", REPORT_TEXT["text_132"], "Haworth, Sturtevant"],
    ["5", REPORT_TEXT["text_133"], REPORT_TEXT["text_134"]],
    ["6", REPORT_TEXT["text_135"], REPORT_TEXT["text_136"]],
]
tbl = Table(
    [[Paragraph(escape(c), styles["SmallTR"]) for c in row] for row in rows],
    colWidths=[48, 278, 175],
    hAlign="LEFT",
)
tbl.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#D9EFF0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#CFDFE3")),
        ]
    )
)
story.append(tbl)
h(REPORT_TEXT["text_137"])
p(REPORT_TEXT["text_138"])
item(REPORT_TEXT["text_139"], REPORT_TEXT["text_140"])
item(REPORT_TEXT["text_141"], REPORT_TEXT["text_142"])
item(REPORT_TEXT["text_193"], REPORT_TEXT["text_143"])
item(REPORT_TEXT["text_144"], REPORT_TEXT["text_145"])
page(REPORT_TEXT["text_146"])
p(REPORT_TEXT["text_147"])
item(REPORT_TEXT["text_194"], REPORT_TEXT["text_148"])
item(REPORT_TEXT["text_195"], REPORT_TEXT["text_149"])
item(REPORT_TEXT["text_196"], REPORT_TEXT["text_150"])
item(REPORT_TEXT["text_197"], REPORT_TEXT["text_151"])
item(REPORT_TEXT["text_198"], REPORT_TEXT["text_152"])
item(REPORT_TEXT["text_199"], REPORT_TEXT["text_153"])
h(REPORT_TEXT["text_154"])
p(REPORT_TEXT["text_155"])
p(REPORT_TEXT["text_156"])
h(REPORT_TEXT["text_157"])
p(REPORT_TEXT["text_158"])
page(REPORT_TEXT["text_159"])
h(REPORT_TEXT["text_160"])
item(REPORT_TEXT["text_161"], REPORT_TEXT["text_162"])
item(REPORT_TEXT["text_163"], REPORT_TEXT["text_164"])
item(REPORT_TEXT["text_165"], REPORT_TEXT["text_166"])
item(REPORT_TEXT["text_167"], REPORT_TEXT["text_168"])
h(REPORT_TEXT["text_169"])
p(REPORT_TEXT["text_170"])
p(REPORT_TEXT["text_171"])
p(REPORT_TEXT["text_172"])
p(REPORT_TEXT["text_173"])
h(REPORT_TEXT["text_174"])
item("1", REPORT_TEXT["text_175"])
item("2", REPORT_TEXT["text_176"])
item("3", REPORT_TEXT["text_177"])
p(REPORT_TEXT["text_178"])


def footer(c, doc):
    w, h = doc.pagesize
    c.setStrokeColor(HexColor("#C9DDE0"))
    c.line(47, 42, w - 47, 42)
    c.setFont("Arial", 8)
    c.setFillColor(HexColor("#526674"))
    c.drawString(47, 29, REPORT_TEXT["text_179"])
    c.drawRightString(w - 47, 29, str(doc.page))


doc = SimpleDocTemplate(
    str(OUT),
    pagesize=(595.28, 841.89),
    rightMargin=47,
    leftMargin=47,
    topMargin=43,
    bottomMargin=57,
    title=REPORT_TEXT["text_180"],
    author=REPORT_TEXT["text_181"],
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
