"""Deterministic plan diagrams and a Turkish drawing collection guide."""

import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Docs/drawing_pack_20"
PDF = ROOT / "output/pdf/PlayableSketch_20_Cizim_Rehberi.pdf"
FONT = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("Guide", FONT))
PLANS = []


def add(title, rooms, corridors, doors, notes, barriers=()):
    n = len(PLANS) + 1
    role = (
        "train"
        if n in [1, 2, 3, 5, 6, 7, 9, 11, 13, 15, 17, 18]
        else "validation" if n in [4, 8, 14, 19] else "test"
    )
    PLANS.append(
        dict(
            id=f"P{n:02}",
            title=title,
            rooms=rooms,
            corridors=corridors,
            doors=doors,
            barriers=barriers,
            notes=notes,
            split=role,
        )
    )


# Coordinates describe diagrams, not labels for future photographed hand drawings.
add(
    "Düz dikey bağlantı",
    [(30, 20, 130, 100), (20, 200, 140, 290)],
    [(65, 100, 95, 200)],
    [0, 1],
    [
        "İki oda arasında tek dikey koridor çiz.",
        "Koridorun iki oda girişinde kapı olsun. Kapı boşluğu koridor genişliğinin yaklaşık yarısı kadar kalsın.",
    ],
)
add(
    "Yatay ve farklı boyda odalar",
    [(20, 40, 100, 140), (210, 20, 340, 170)],
    [(100, 75, 210, 105)],
    [0],
    [
        "Solda küçük, sağda büyük oda; arada yatay koridor.",
        "Yalnız sol girişte kapı çiz. Sağ oda bağlantısı tamamen açık olsun.",
    ],
)
add(
    "Uzun ve dar koridor",
    [(30, 20, 140, 100), (20, 260, 150, 350)],
    [(75, 100, 95, 260)],
    [0, 1],
    [
        "İki oda arasında uzun, dar bir koridor çiz.",
        "İki kapı da dar koridordan daha dar olsun; boşluğu fotoğrafta kaybolacak kadar küçültme.",
    ],
)
add(
    "Geniş ve kısa koridor",
    [(20, 20, 130, 110), (190, 10, 320, 140)],
    [(130, 45, 190, 95)],
    [0, 1],
    [
        "Kısa bağlantıyı önceki örnekten belirgin biçimde geniş çiz.",
        "İki uçta da kapı olsun; büyük açıklığı duvarla kapatma.",
    ],
)
add(
    "Aşağı ve sağa L - açık",
    [(20, 20, 120, 100), (200, 170, 300, 260)],
    [(55, 100, 85, 210), (85, 180, 200, 210)],
    [],
    [
        "Üst odadan aşağı in, sonra sağa dönerek ikinci odaya bağlan.",
        "İki oda girişi ve L dirseği açık. Dönüşte enine çizgi çizme.",
    ],
)
add(
    "Aşağı ve sola L - iki kapı",
    [(190, 20, 290, 100), (10, 170, 110, 260)],
    [(225, 100, 255, 210), (110, 180, 225, 210)],
    [0, 1],
    [
        "Üst sağ odadan aşağı, sonra sola dönen bir L çiz.",
        "Kapılar yalnız odalara girişte olsun. L dönüşünün içinde kapı veya duvar olmasın.",
    ],
)
add(
    "Sağa ve aşağı L - tek kapı",
    [(10, 20, 100, 120), (190, 230, 300, 320)],
    [(100, 55, 260, 85), (230, 85, 260, 230)],
    [1],
    [
        "Sol odadan sağa çık, aşağı dön ve alt sağ odaya gir.",
        "Yalnız alt odanın girişine kapı koy; ilk giriş tamamen açık.",
    ],
)
add(
    "Sağa ve yukarı dar L",
    [(10, 210, 100, 310), (220, 10, 320, 90)],
    [(100, 245, 270, 265), (250, 90, 270, 245)],
    [0, 1],
    [
        "Alt soldan sağa, ardından yukarı giden dar L çiz.",
        "İki oda girişinde kapı olsun. Dar koridorun iki duvarını paralel tut.",
    ],
)
add(
    "Genişliği değişen L",
    [(20, 20, 130, 100), (210, 180, 320, 280)],
    [(60, 100, 85, 230), (85, 180, 210, 230)],
    [0, 1],
    [
        "Dikey kol dar, yatay kol yaklaşık iki kat geniş olsun.",
        "Dirseğin içini açık bırak. Geniş kolun oda girişine de kapı çiz.",
    ],
)
add(
    "Kısa dirsekli L",
    [(20, 20, 140, 120), (190, 130, 300, 240)],
    [(75, 120, 105, 175), (105, 145, 190, 175)],
    [],
    [
        "Dikey kolu kısa, yatay kolu biraz daha uzun çiz.",
        "Kapı işareti yok; oda girişleri ve dönüş tamamen açık.",
    ],
)
add(
    "İki dönüşlü zikzak",
    [(10, 20, 110, 100), (210, 260, 320, 350)],
    [(45, 100, 75, 190), (75, 160, 265, 190), (235, 190, 265, 260)],
    [0],
    [
        "Önce aşağı, sonra sağa, sonra yeniden aşağı: üç koridor parçası.",
        "Yalnız ilk oda çıkışında kapı olsun; iki dönüşü açık bırak.",
    ],
)
add(
    "U biçiminde bağlantı",
    [(10, 20, 110, 110), (220, 20, 320, 110)],
    [(45, 110, 75, 260), (75, 230, 255, 260), (255, 110, 285, 260)],
    [],
    [
        "İki üst oda, aşağı dolanan U koridoruyla bağlansın.",
        "Üç koridor kolu ve iki açık dönüş çiz. Odalar arasına üstten kestirme bağlantı ekleme.",
    ],
)
add(
    "T kavşağı - üç oda",
    [(10, 110, 90, 210), (260, 110, 350, 210), (130, 10, 220, 90)],
    [(90, 145, 260, 175), (160, 90, 190, 145)],
    [0, 1, 2],
    [
        "Solda, sağda ve üstte birer oda; ortada T biçiminde koridor.",
        "Üç oda girişine kapı çiz. T merkezinde ayırıcı duvar olmasın.",
    ],
)
add(
    "Dört kollu kavşak",
    [
        (10, 130, 90, 230),
        (270, 130, 350, 230),
        (130, 10, 230, 90),
        (130, 270, 230, 350),
    ],
    [(90, 165, 270, 195), (165, 90, 195, 165), (165, 195, 195, 270)],
    [0, 2],
    [
        "Dört yönde birer oda ve ortada artı biçimli bağlantı çiz.",
        "Soldaki ve üstteki oda girişleri kapılı, sağ ve alt girişler tamamen açık.",
    ],
)
add(
    "Üç oda, iki düz koridor",
    [(30, 10, 150, 90), (20, 170, 160, 270), (40, 350, 140, 430)],
    [(75, 90, 105, 170), (75, 270, 105, 350)],
    [0, 1, 2, 3],
    [
        "Üç odayı dikey sırala; aralarında iki ayrı koridor olsun.",
        "Her koridorun iki ucuna kapı çiz: toplam dört kapı. Ortadaki oda koridor sayılmaz.",
    ],
)
add(
    "L bağlantısı ve yan oda",
    [(10, 10, 110, 90), (210, 170, 310, 270), (10, 270, 110, 350)],
    [(45, 90, 75, 210), (75, 180, 210, 210), (45, 210, 75, 270)],
    [0, 1],
    [
        "Üst soldan aşağı, sonra sağ odaya dönen L çiz; dikey kol alttaki üçüncü odaya da uzansın.",
        "Üst ve sağ oda girişleri kapılı, alt oda girişi açık olsun.",
    ],
)
add(
    "Kapalı uç - karşı örnek",
    [(20, 10, 130, 90), (20, 200, 130, 290)],
    [(60, 90, 90, 200)],
    [0],
    [
        "Üst oda koridora kapıyla açılsın. Alt oda sınırında koridoru kesen tam bir duvar çiz.",
        "Alt odanın üst kenarı kesintisiz kalsın. Burada kapı veya geçiş YOK.",
    ],
    [(60, 200, 90, 200)],
)
add(
    "Bağlantısız iki oda",
    [(20, 20, 130, 150), (180, 90, 300, 240)],
    [],
    [],
    [
        "Birbirine yakın ama temas etmeyen iki kapalı oda çiz.",
        "Aradaki beyaz alan koridor değildir. İki oda arasında duvar veya kapı ekleme.",
    ],
)
add(
    "L dirseğinde kapalı duvar",
    [(20, 20, 120, 100), (200, 170, 300, 260)],
    [(55, 100, 85, 210), (85, 180, 200, 210)],
    [0, 1],
    [
        "İki oda ve L çiz; oda girişlerine kapı koy.",
        "L dönüşünde iki kolu tamamen ayıran kısa bir duvar çiz. Bu örnekte odalar birbirine GEÇİLEMEZ.",
    ],
    [(85, 180, 85, 210)],
)
add(
    "L yanında bağlantısız oda",
    [(10, 10, 110, 90), (210, 170, 310, 270), (180, 10, 290, 100)],
    [(45, 90, 75, 210), (75, 180, 210, 210)],
    [0],
    [
        "Üst soldaki oda ile alt sağdaki odayı açık dirsekli L ile bağla. İlk giriş kapılı, son giriş açık olsun.",
        "Üst sağa üçüncü, tamamen kapalı bir oda çiz. Yakın dursa da hiçbir koridora değmesin.",
    ],
)


def interfaces(plan):
    result = []
    for i, a in enumerate(plan["rooms"]):
        for j, b in enumerate(plan["corridors"]):
            for normal in (0, 1):
                along = 1 - normal
                for first, second in (
                    (a[normal + 2], b[normal]),
                    (a[normal], b[normal + 2]),
                ):
                    lo = max(a[along], b[along])
                    hi = min(a[along + 2], b[along + 2])
                    if first == second and hi > lo:
                        result.append((normal, first, lo, hi, i, j))
    return result


def exterior(plan):
    rects = plan["rooms"] + plan["corridors"]
    xs = sorted({r[i] for r in rects for i in (0, 2)})
    ys = sorted({r[i] for r in rects for i in (1, 3)})
    cells = {
        (i, j)
        for i in range(len(xs) - 1)
        for j in range(len(ys) - 1)
        if any(
            r[0] <= (xs[i] + xs[i + 1]) / 2 <= r[2]
            and r[1] <= (ys[j] + ys[j + 1]) / 2 <= r[3]
            for r in rects
        )
    }
    lines = []
    for i, j in cells:
        if (i - 1, j) not in cells:
            lines.append((xs[i], ys[j], xs[i], ys[j + 1]))
        if (i + 1, j) not in cells:
            lines.append((xs[i + 1], ys[j], xs[i + 1], ys[j + 1]))
        if (i, j - 1) not in cells:
            lines.append((xs[i], ys[j], xs[i + 1], ys[j]))
        if (i, j + 1) not in cells:
            lines.append((xs[i], ys[j + 1], xs[i + 1], ys[j + 1]))
    return lines


def plan_lines(plan):
    lines = exterior(plan) + list(plan["barriers"])
    ticks = []
    for k, (normal, fixed, lo, hi, *_) in enumerate(interfaces(plan)):
        if k not in plan["doors"]:
            continue
        along = 1 - normal
        mid = (lo + hi) / 2
        half = (hi - lo) * 0.25

        def segment(a, b):
            return (a, fixed, b, fixed) if along == 0 else (fixed, a, fixed, b)

        lines.extend([segment(lo, mid - half), segment(mid + half, hi)])
        for at in (mid - half, mid + half):
            ticks.append(
                (at, fixed - 5, at, fixed + 5)
                if along == 0
                else (fixed - 5, at, fixed + 5, at)
            )
    return lines + ticks


def draw_plan(c, plan, x, y, w, h):
    rects = plan["rooms"] + plan["corridors"]
    maxx = max(r[2] for r in rects)
    maxy = max(r[3] for r in rects)
    scale = min((w - 24) / maxx, (h - 24) / maxy)
    dx = x + (w - maxx * scale) / 2
    dy = y + (h - maxy * scale) / 2
    c.setStrokeColor(HexColor("#152332"))
    c.setLineWidth(1.65)
    c.setLineCap(1)
    for a, b, A, B in plan_lines(plan):
        c.line(
            dx + a * scale,
            dy + (maxy - b) * scale,
            dx + A * scale,
            dy + (maxy - B) * scale,
        )


def text(c, value, x, y, size=11, width=490, color="#273747", leading=17):
    c.setFont("Guide", size)
    c.setFillColor(HexColor(color))
    for line in simpleSplit(value, "Guide", size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def footer(c, n):
    c.setStrokeColor(HexColor("#d9e1e8"))
    c.setLineWidth(0.5)
    c.line(42, 40, 553, 40)
    text(c, "PlayableSketch / 20 yeni el çizimi / 4 Kasım 2026", 42, 26, 8)
    text(c, str(n), 535, 26, 8)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PDF.parent.mkdir(parents=True, exist_ok=True)
    for p in PLANS:
        assert all(i < len(interfaces(p)) for i in p["doors"]), p["id"]
        p["expected_rooms"] = len(p["rooms"])
        p["expected_corridor_segments"] = len(p["corridors"])
        p["expected_doors"] = len(p["doors"])
        p["filename"] = p["id"] + ".png"
        rects = p["rooms"] + p["corridors"]
        mx = max(r[2] for r in rects) + 20
        my = max(r[3] for r in rects) + 20
        lines = "".join(
            f'<line x1="{a}" y1="{b}" x2="{A}" y2="{B}"/>'
            for a, b, A, B in plan_lines(p)
        )
        (OUT / (p["id"] + ".svg")).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {mx} {my}"><rect width="100%" height="100%" fill="white"/><g fill="none" stroke="#152332" stroke-width="2" stroke-linecap="round">{lines}</g></svg>'
        )
    (OUT / "plan_manifest.json").write_text(
        json.dumps(
            {
                "version": "drawing-pack/1.0",
                "purpose": "Reference diagrams only; future photo labels must be traced from actual photographs.",
                "split_policy": "Split by original drawing before augmentation. Never derive training samples from validation or test originals.",
                "plans": PLANS,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    c = canvas.Canvas(str(PDF), pagesize=(595.28, 841.89))
    c.setTitle("PlayableSketch - 20 Çizim Rehberi")
    text(c, "20 yeni çizim", 42, 778, 28)
    text(c, "Koridor, L dönüşü ve kapı öğrenme paketi", 42, 742, 15, color="#147d82")
    y = 700
    for title, body in [
        (
            "Nasıl çizeceksin?",
            "Her planı ayrı, düz beyaz A4 kâğıda, serbest elle çiz. Siyah tükenmez veya koyu kurşun kalem kullan. Cetvelle birebir kopyalama; küçük doğal eğrilikler kalsın. Şemadaki yerleşimi koru; büyüklükleri yaklaşık tutabilirsin.",
        ),
        (
            "Kapı ve açık bağlantı",
            "Kapı: duvarda gerçek bir boşluk ve boşluğun iki ucunda duvara dik kısa işaretler. Açık bağlantı: enine duvar ve kapı işareti olmadan devam eden alan. L dönüşünde ayırıcı çizgi yalnız açıkça istendiğinde çizilir.",
        ),
        (
            "Boyut ve fotoğraf",
            "Plan kâğıdın yaklaşık üçte ikisini kaplasın. Normal koridorlar yaklaşık 1,5-2 cm, dar koridorlar 1-1,2 cm olabilir. Kapı boşlukları fotoğrafta açık seçilsin. Kâğıdı yukarıdan, gölgesiz ve net çek; planın tüm kenarlarını kadraja al.",
        ),
        (
            "Neleri kopyalamayacaksın?",
            "Yalnız siyah plan çizgilerini kopyala. Oda adı, ölçü, sayı, tarama, mobilya ve sayfa başlığı ekleme. Dosyaları P01.png ... P20.png olarak adlandır. 20 ayrı özgün çizim gönder; rehber görsellerini eğitim fotoğrafı olarak gönderme.",
        ),
        (
            "Veriyi nasıl kullanacağız?",
            "12 özgün çizim eğitim, 4 doğrulama, 4 test için önceden ayrıldı. Eğitim çizimlerinden sentetik fotoğraf türevleri üretilecek. Test ve doğrulama çizimlerinin hiçbir türevi eğitimde kullanılmayacak. Fotoğraflar geldikten sonra gerçek oda/koridor/kapı etiketleri ayrıca hazırlanacak.",
        ),
    ]:
        y = text(c, title, 42, y, 13, color="#147d82") - 4
        y = text(c, body, 42, y, 10.5, leading=16) - 20
    footer(c, 1)
    c.showPage()
    text(c, "20 planın tamamı", 42, 790, 23)
    text(
        c,
        "Her planın ayrıntısı sonraki sayfalarda. Bu sayfa hızlı bakış içindir.",
        42,
        765,
        10,
    )
    for i, p in enumerate(PLANS):
        col = i % 4
        row = i // 4
        x = 36 + col * 132
        y = 620 - row * 137
        text(c, p["id"], x + 6, y + 108, 10, color="#147d82")
        draw_plan(c, p, x, y, 122, 105)
    footer(c, 2)
    c.showPage()
    for n, p in enumerate(PLANS, 3):
        text(c, p["id"] + " / " + p["title"], 42, 786, 19)
        text(
            c,
            f"{p['expected_rooms']} oda · {p['expected_corridor_segments']} koridor parçası · {p['expected_doors']} kapı",
            42,
            754,
            11,
            color="#147d82",
        )
        c.setFillColor(HexColor("#f6f8fa"))
        c.roundRect(42, 300, 511, 425, 10, fill=1, stroke=0)
        draw_plan(c, p, 56, 314, 483, 397)
        y = 270
        for i, note in enumerate(p["notes"], 1):
            y = text(c, f"{i}. {note}", 42, y, 11, leading=18) - 10
        y = text(
            c,
            "Çizimde yalnız plan çizgileri olsun. Dosya adı: " + p["filename"],
            42,
            min(y - 8, 154),
            10,
            color="#147d82",
        )
        role = {"train": "Eğitim", "validation": "Doğrulama", "test": "Test"}[
            p["split"]
        ]
        text(
            c,
            "Önceden ayrılan grup: "
            + role
            + ". Fotoğrafın etiketleri ayrıca doğrulanacak.",
            42,
            91,
            9,
        )
        footer(c, n)
        c.showPage()
    c.save()
    print(PDF)


if __name__ == "__main__":
    main()
