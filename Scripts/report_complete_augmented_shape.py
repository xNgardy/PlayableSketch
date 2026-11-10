import html
import json
from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.report_augmented_shape import percent, PROFILES, LABELS, KEYS, NAMES

OUT = ROOT / "Saved/ShapeFirst/augmented_robustness/v2"


def main():
    r = json.loads((OUT / "report.json").read_text())
    v = json.loads((OUT / "verification.json").read_text())
    scopes = {"all70": r["summary"]["human"], **r["cohorts"]}
    labels = {
        "all70": "Bütün 70 insan çizimi",
        "old50": "Data_1–50",
        "new20": "Data_51–70",
        "synthetic": "Sentetik kaynaklar",
    }
    lines = [
        "# Tüm 70 insan çizimi ve türevleri — son sistem değerlendirmesi",
        "",
        "## Kapsam",
        "",
        "Data_51–70 için önceki deneyle aynı döndürme, perspektif, ışık, çekim etkisi ve birleşik profilleri kullanılarak 100 yeni görüntü oluşturuldu. Kaynak görüntüler, orijinal etiketler ve model ağırlıkları değiştirilmedi. İnsan çizimleri için yoğun piksel maskesi uydurulmadı; bölge poligonları ve açıklık uçları aynı homografiyle aktarıldı. Bölge sahipleri ve açıklık türleri korundu. 100 görüntüde sınır ve koordinat ileri–geri kontrolleri geçti.",
        "",
        "Tam kapsam: **70 insan + 70 sentetik kaynak = 140 özgün görüntü; 350 insan + 350 sentetik türev = 700 artırılmış görüntü; toplam 840 tahmin**. Önceki 720 tahmin, model/kaynak kodu ve arşiv hash eşitliği doğrulanarak yeniden kullanıldı. Yeni 20 özgün + 100 türev için 120 taze çıkarım yapıldı. Model yeniden eğitilmedi ve eşikler ayarlanmadı.",
        "",
        "Her görüntüde aynı DINO refined-full üretim girişi, normalizasyon ve üç alternatif kullanıldı. Puanlar sabit birincil alternatiften; toplam 2.520 öneri belgesi şema geçerli ve kullanıcı onayı bekliyor. Önceki 60 sentetik kontrol bu 70 sentetik kaynak setinden farklıdır; önceki 130 örnek değerlendirmesi ayrı kontrol raporu olarak korunmaktadır.",
        "",
        "## Metrikler ve referans sınırları",
        "",
        "Precision = doğru / tahmin; recall = doğru / referans; F1 = 2PR/(P+R). Tablolar mikro toplamadır; train/validation/test karışık toplamlar bağımsız test skoru değildir. Bölge metriği kutu IoU ≥ 0,5 ile türden bağımsız konum eşleşmesidir. Açıklık/kapı doğru tür ve uç hatası çalışma kenarının en fazla %4’ü olmalıdır. Doğru bağlı kapı ve bağlantı ayrıca iki doğru bölge sahibini gerektirir.",
        "",
        "Bütün grupları karşılaştırabilmek için birleşik bağlantı metriği açıklık başına aynı eşleştirme kuralıyla hesaplandı. Data_51–70 için benzersiz bölge çifti metrikleri de her örneğin `unique_pair_metrics` alanında korunur. Bunlar doğrudan aynı metrikmiş gibi toplanmaz. Eski 50 insan çiziminde sahiplik yaklaşık poligon yakınlığıyla, yeni 20’de açık yapısal bölge kimlikleriyle belirlenir; bu referans kalitesi farkı nedeniyle gruplar ayrıca gösterilir.",
        "",
        "Data_63 g003 için önceki denetimde sabitlenen uç düzeltmesi yalnızca değerlendirme referansına, bütün türevlere aynı homografiyle uygulanır. Özgün eğitim etiketleri ve oluşturulan ham kaynak-etiket aktarımları değiştirilmedi. Kullanılan değerlendirme referansları `evaluation_references/` altında saklanır. Yeni kör test veya yeni yazar genellemesi iddiası yoktur.",
        "",
        "## Bütün insan çizimleri — dönüşüm bazında",
        "",
        "Her dönüşüm aynı 70 insan çiziminin bir görünümüdür. 350 türev bağımsız 350 plan değildir.",
        "",
        "| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Bağlantı F1 | Doğru bağlı kapı F1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    index = lines.index("## Bütün insan çizimleri — dönüşüm bazında")
    lines[index:index] = [
        "Bölge referansı 70 insan kaynağının 62’sinde vardır; bölge oranları özgünlerde 62, türevlerde 310 görüntüden hesaplanır. Referansı eksik 8 kaynak başarı sayılmaz. Sahipliği belirsiz iki eski kaynak kapısı, doğru bağlı kapı recall paydasına alınmaz; bütün insan kaynaklarında kapı konumu referansı 99, sahipliği belirli kapı referansı 97’dir.",
        "",
    ]
    for p in ["original"] + PROFILES + ["augmented_all"]:
        m = scopes["all70"][p]
        lines.append(
            "| "
            + LABELS[p]
            + " | "
            + str(m["samples"])
            + " | "
            + " | ".join((percent(m[k]["f1"]) for k in KEYS))
            + " |"
        )
    lines += [
        "",
        "## Önceki 50, yeni 20 ve sentetik set ayrımı",
        "",
        "| Grup | Koşul | Görüntü | Bölge F1 | Kapı F1 | Bağlantı F1 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for c in ["old50", "new20", "synthetic"]:
        for p in ["original", "augmented_all"]:
            m = scopes[c][p]
            lines.append(
                "| "
                + labels[c]
                + " | "
                + LABELS[p]
                + " | "
                + str(m["samples"])
                + " | "
                + " | ".join((percent(m[k]["f1"]) for k in ["regions", "doors", "connections"]))
                + " |"
            )
    lines += [
        "",
        "## Precision / recall / F1",
        "",
        "| Grup | Koşul | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for c in ["all70", "new20", "synthetic"]:
        for p in ["original", "augmented_all"]:
            for k in KEYS:
                m = scopes[c][p][k]
                lines.append(
                    "| "
                    + labels[c]
                    + " | "
                    + LABELS[p]
                    + " | "
                    + NAMES[k]
                    + " | "
                    + " / ".join((str(m[x]) for x in ["true_positive", "predicted", "reference"]))
                    + " | "
                    + " | ".join((percent(m[x]) for x in ["precision", "recall", "f1"]))
                    + " |"
                )
    lines += [
        "",
        "## Yeni 20 çizimde hangi dönüşüm etkili?",
        "",
        "| Koşul | Bölge F1 | Kapı F1 | Bağlantı F1 |",
        "|---|---:|---:|---:|",
    ]
    for p in ["original"] + PROFILES + ["augmented_all"]:
        m = scopes["new20"][p]
        lines.append(
            "| "
            + LABELS[p]
            + " | "
            + " | ".join((percent(m[k]["f1"]) for k in ["regions", "doors", "connections"]))
            + " |"
        )
    lines += [
        "",
        "## Kaynakların eğitim / doğrulama / test ayrımı",
        "",
        "Türevler kaynaklarının ayrımını devralır. Önceden incelenmiş test kaynaklarının türevleri yeni bağımsız holdout değildir.",
        "",
        "| Grup | Bölüm | Koşul | Görüntü | Kapı F1 | Bağlantı F1 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for c in ["all70", "old50", "new20"]:
        for split, profiles in r["human_split_summary"][c].items():
            for p in ["original", "augmented_all"]:
                m = profiles[p]
                lines.append(
                    "| "
                    + labels[c]
                    + " | "
                    + split
                    + " | "
                    + LABELS[p]
                    + " | "
                    + str(m["samples"])
                    + " | "
                    + percent(m["doors"]["f1"])
                    + " | "
                    + percent(m["connections"]["f1"])
                    + " |"
                )
    lines += ["", "## Yorum", ""]
    for c in ["all70", "new20", "synthetic"]:
        worst = min(PROFILES, key=lambda p: scopes[c][p]["connections"]["f1"])
        a = scopes[c]["original"]["connections"]["f1"]
        b = scopes[c][worst]["connections"]["f1"]
        lines.append(
            "- "
            + labels[c]
            + ": en düşük bağlantı F1 **"
            + LABELS[worst]
            + "**, "
            + percent(a)
            + " → "
            + percent(b)
            + "."
        )
    lines += [
        "",
        "Özgün Data_51–70 zaten önceki 50’den daha düşük başarıya sahiptir; bu farkı yalnızca görüntü bozulmasına bağlayamayız. İlgili türevlerin başarısı aynı kaynakların özgün haliyle karşılaştırılmalıdır. Oda/koridor türü, kusursuz geometri ve cm/3B çıktı doğruluğu ana bölge F1 ile ölçülmez. Maskeler ayrı çizim veya ağ girdisi değildir; bu çalışma piksel Dice/IoU ölçümü yapmaz.",
        "",
        "Plan grubu düzeyinde 5.000 eşleştirilmiş bootstrap tekrarı `paired_intervals.json` içindedir. Aynı planın özgün ve farklı stilleri birlikte örneklenir. Bu aralıklar mevcut verideki değişkenlik içindir; yeni yazar başarısı garantisi değildir.",
        "",
        "## Veri bütünlüğü ve çıktılar",
        "",
        "- Data_1–70 kaynaklarının tümü ve her biri için beş profil kapsanmıştır.",
        "- 840 tahmin, 2.520 şema geçerli belge; tümü onay bekliyor.",
        "- 120 yeni çıkarım; önceki 720 arşiv aynı model, kod ve içerik hash’leriyle doğrulandı.",
        "- " + str(v["protected_files_checked"]) + " korunan dosya değişmedi.",
        "- Ham etiketler ve Data_63 eğitim etiketleri değiştirilmedi; sayısal OCR veya fiziksel ölçü eğitimi yok.",
        "",
        "- `report.json`: bütün 840 örnek ve grup sonuçları",
        "- `metrics.csv`: grup/dönüşüm bazında precision / recall / F1",
        "- `paired.csv`: aynı kaynakla F1 farkları",
        "- `paired_intervals.json`: plan grubu bootstrap aralıkları",
        "- `gallery.html`: yeni 20 çizimin özgün ve beş türevi; en büyük kayıplar",
        "- `protocol.json`, `verification.json`: kaynak, veri, model ve sayım doğrulamaları",
        "- Yeni görüntüler: `Data/augmented/new20_v1`",
        "- Önceki 720 arşiv: `Saved/ShapeFirst/augmented_robustness/v1/predictions`",
        "- Yeni 120 arşiv: `Saved/ShapeFirst/augmented_robustness/v2/predictions`",
    ]
    lines += [
        "",
        "Dört değerlendirme testi geçti: proje dönüşümü ve ileri–geri kontrol, kaynak etiketleri değiştirmeme, tür/sahiplik koruma ve doğru konumdaki kapının yanlış sahiplerle başarı sayılmaması.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "report_tr.md").write_text(text)
    (ROOT / "Docs/complete_augmented_shape_2026_11_07.md").write_text(text)
    rowmap = {row["sample_id"]: row for row in r["rows"]}

    def picture(sid):
        directory = ROOT / rowmap[sid]["prediction_directory"]
        path = os.path.relpath(directory / "working.png", OUT)
        return (
            "<figure><figcaption>"
            + html.escape(sid)
            + '</figcaption><img loading="lazy" src="'
            + html.escape(path)
            + '"></figure>'
        )

    sections = []
    for n in range(51, 71):
        sid = f"Data_{n}"
        sections.append(
            "<section><h2>"
            + sid
            + "</h2><div>"
            + picture(sid)
            + "".join((picture(f"AUG_{sid}_{p}") for p in PROFILES))
            + "</div></section>"
        )
    worst = sorted(
        [p for p in r["paired"] if p["metric"] == "connections" and p["delta_f1"] is not None],
        key=lambda p: p["delta_f1"],
    )[:20]
    for p in worst:
        sections.append(
            "<section><h2>"
            + html.escape(p["sample_id"])
            + ": "
            + percent(p["original_f1"])
            + " → "
            + percent(p["augmented_f1"])
            + "</h2><div>"
            + picture(p["source_id"])
            + picture(p["sample_id"])
            + "</div></section>"
        )
    (OUT / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Tüm çizimler: yeni 20 türevleri</title><style>body{font:16px system-ui;margin:20px;background:#f5f6f8}section{background:white;margin:20px 0;padding:16px}section>div{display:flex;gap:12px;overflow:auto}figure{flex:1;min-width:180px;margin:0}img{width:100%}figcaption{font-size:12px}</style><h1>Data_51–70: özgün ve beş türev</h1><p>Son bölüm bütün veri kümesindeki en büyük 20 bağlantı F1 kaybıdır. Seçki yalnızca hata incelemesi içindir.</p>'
        + "".join(sections)
    )
    print(
        json.dumps(
            {
                c: {
                    p: {
                        k: round(scopes[c][p][k]["f1"] * 100, 2)
                        for k in ["regions", "doors", "connections", "attached_doors"]
                    }
                    for p in ["original", "augmented_all"]
                }
                for c in scopes
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
