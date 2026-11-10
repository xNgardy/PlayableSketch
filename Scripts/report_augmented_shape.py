import html
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Saved/ShapeFirst/augmented_robustness/v1"
PROFILES = ["rotate", "perspective", "lighting", "capture", "combined"]
LABELS = {
    "original": "Özgün kaynak",
    "rotate": "Döndürme",
    "perspective": "Perspektif",
    "lighting": "Işık",
    "capture": "Çekim etkisi",
    "combined": "Birleşik",
    "augmented_all": "Bütün türevler",
}
KEYS = ["regions", "doors", "openings", "connections", "attached_doors"]
NAMES = {
    "regions": "Bölge konumu",
    "doors": "Kapı türü + konumu",
    "openings": "Tüm açıklıklar",
    "connections": "Doğru bağlantı",
    "attached_doors": "Doğru bağlı kapı",
}


def percent(v):
    return "—" if v is None else ("%.1f" % (v * 100)).replace(".", ",") + "%"


def paired_intervals(rows):
    result = []
    for origin in ["human", "synthetic"]:
        allrows = [r for r in rows if r["source_origin"] == origin]
        groups = sorted({r["base_plan_id"] for r in allrows})
        rng = np.random.default_rng(20261107)
        draws = rng.integers(len(groups), size=(5000, len(groups)))
        for profile in PROFILES:
            for key in KEYS:
                arrays = []
                for condition in ["original", profile]:
                    records = []
                    for group in groups:
                        metrics = [
                            r["metrics"][key]
                            for r in allrows
                            if r["base_plan_id"] == group
                            and r["profile"] == condition
                            and (r["metrics"][key] is not None)
                        ]
                        records.append(
                            [
                                sum((m[k] for m in metrics))
                                for k in ["true_positive", "predicted", "reference"]
                            ]
                        )
                    arrays.append(np.asarray(records))
                assert int(arrays[0][:, 2].sum()) == int(arrays[1][:, 2].sum()), (
                    origin,
                    profile,
                    key,
                )
                sums = [a[draws].sum(1) for a in arrays]
                valid = (sums[0][:, 1:].sum(1) > 0) & (sums[1][:, 1:].sum(1) > 0)
                deltas = 2 * sums[1][valid, 0] / sums[1][valid, 1:].sum(1) - 2 * sums[0][
                    valid, 0
                ] / sums[0][valid, 1:].sum(1)
                totals = [a.sum(0) for a in arrays]
                point = [2 * t[0] / (t[1] + t[2]) if t[1] + t[2] else None for t in totals]
                result.append(
                    {
                        "origin": origin,
                        "profile": profile,
                        "metric": key,
                        "base_plan_groups": len(groups),
                        "original_f1": point[0],
                        "augmented_f1": point[1],
                        "delta_f1": point[1] - point[0] if None not in point else None,
                        "paired_cluster_bootstrap_95": (
                            np.percentile(deltas, [2.5, 97.5]).tolist() if len(deltas) else None
                        ),
                    }
                )
    return result


def main():
    report = json.loads((OUT / "report.json").read_text())
    summary = report["summary"]
    intervals = paired_intervals(report["rows"])
    (OUT / "paired_intervals.json").write_text(
        json.dumps(
            {
                "seed": 20261107,
                "replicates": 5000,
                "unit": "base_plan_id, keeping source styles and paired transformations together",
                "rows": intervals,
            },
            indent=2,
        )
        + "\n"
    )
    lines = [
        "# Artırılmış görüntülerde son sistemin dayanıklılığı — 7 Kasım 2026",
        "",
        "## Kapsam ve yöntem",
        "",
        "Son DINO refined-full sistemiyle 600 artırılmış görüntü ve bunların 120 kaynak görüntüsü üzerinde toplam 720 taze çıkarım yapıldı. Her görüntüde üretim girişinin üç alternatifi oluşturuldu; puanlama önceden sabit birincil alternatiften yapıldı. Model ağırlıkları ve üretim kararları değişmedi; yeniden eğitim veya test sonuçlarından eşik seçimi yapılmadı.",
        "",
        "Kaynaklar 50 insan çizimi ve 70 sentetik görüntüdür. 250 insan türevi ve 350 sentetik türev vardır. Sentetik görüntüler 60 adet önceki kontrol setinden farklı bir kümedir. Data_51–70 bu artırılmış sette yoktur. Bu nedenle önceki 130 örnekle birleştirilmiş genel başarı oranı verilmez.",
        "",
        "Tüm tahminler kaydedildikten sonra referanslar okunarak puanlandı. Kaynak poligonları ve açıklık uçları, kayıtlı kaynak→artırılmış dönüşüm ve görüntünün gerçek ön işleme matrisiyle çalışma koordinatlarına taşındı. Kaynak bölge sahipleri dönüşüm sırasında korunur. Referans homografileri modele veya geometri çıkarımına verilmedi.",
        "",
        "Bölge kutu IoU eşiği 0,5; açıklık için doğru tür ve en fazla çalışma kenarının %4’ü kadar uç hatası. Kapı türü/konum metriği doğru bölge bağlantısı gerektirmez; doğru bağlı kapı ve doğru bağlantı ayrıca raporlanır. Bağlantı, açıklık başına doğru tür, konum ve eşleşmiş iki kaynak bölge sahibini gerektirir. İnsan sahiplik referansları yaklaşık kaynak poligon yakınlığına dayanır; sentetik sahiplikler açık üretici bağlantılarından alınır.",
        "",
        "## İnsan çizimleri",
        "",
        "Her dönüşüm satırı aynı 50 çizimin birer türevidir. 250 türev 250 bağımsız plan değildir. F1 değerleri öğe sayıları toplanarak mikro hesaplanmıştır.",
        "",
        "| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Doğru bağlantı F1 | Doğru bağlı kapı F1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in ["original"] + PROFILES + ["augmented_all"]:
        m = summary["human"][profile]
        lines.append(
            "| "
            + LABELS[profile]
            + " | "
            + str(m["samples"])
            + " | "
            + " | ".join((percent(m[k]["f1"]) for k in KEYS))
            + " |"
        )
    lines += [
        "",
        "## Sentetik çizimler",
        "",
        "70 kaynak görüntü, birden çok çizim stilini de içerir; bağımsızlık birimi görüntü yerine temel plan grubudur.",
        "",
        "| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Doğru bağlantı F1 | Doğru bağlı kapı F1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in ["original"] + PROFILES + ["augmented_all"]:
        m = summary["synthetic"][profile]
        lines.append(
            "| "
            + LABELS[profile]
            + " | "
            + str(m["samples"])
            + " | "
            + " | ".join((percent(m[k]["f1"]) for k in KEYS))
            + " |"
        )
    lines += [
        "",
        "## Precision, recall ve F1",
        "",
        "| Grup | Koşul | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for origin, label in [("human", "İnsan"), ("synthetic", "Sentetik")]:
        for profile in ["original", "augmented_all"]:
            for key in KEYS:
                m = summary[origin][profile][key]
                lines.append(
                    "| "
                    + label
                    + " | "
                    + LABELS[profile]
                    + " | "
                    + NAMES[key]
                    + " | "
                    + " / ".join((str(m[k]) for k in ["true_positive", "predicted", "reference"]))
                    + " | "
                    + " | ".join((percent(m[k]) for k in ["precision", "recall", "f1"]))
                    + " |"
                )
    lines += [
        "",
        "## Kaynak çizimin train / validation / test ayrımı",
        "",
        "Türevler kaynak insan çiziminin önceki grup ayrımını devralır. Bu, yeni bağımsız test verisi oluşturmaz.",
        "",
        "| Kaynak grubu | Koşul | Görüntü | Kapı F1 | Bağlantı F1 |",
        "|---|---|---:|---:|---:|",
    ]
    for split, profiles in report["human_parent_split_summary"].items():
        for profile in ["original", "augmented_all"]:
            m = profiles[profile]
            lines.append(
                "| "
                + split
                + " | "
                + LABELS[profile]
                + " | "
                + str(m["samples"])
                + " | "
                + percent(m["doors"]["f1"])
                + " | "
                + percent(m["connections"]["f1"])
                + " |"
            )
    lines += [
        "",
        "## Aynı kaynakla eşleştirilmiş farklar",
        "",
        "Farklar yüzde puandır. %95 aralıklar 5.000 temel plan grubu düzeyinde bootstrap ile hesaplanır; aynı planın stilleri ve özgün/türev çiftleri birlikte tutulur. Yeni yazara genelleme aralığı değildir.",
        "",
        "| Grup | Dönüşüm | Bağlantı F1 farkı | Eşleştirilmiş %95 aralık |",
        "|---|---|---:|---:|",
    ]
    pp = lambda x: ("%+.1f" % (100 * x)).replace(".", ",")
    for v in intervals:
        if v["metric"] != "connections":
            continue
        ci = v["paired_cluster_bootstrap_95"]
        lines.append(
            "| "
            + v["origin"]
            + " | "
            + LABELS[v["profile"]]
            + " | "
            + pp(v["delta_f1"])
            + " | "
            + pp(ci[0])
            + " … "
            + pp(ci[1])
            + " |"
        )
    lines += ["", "## Yorum ve kalan sınırlar", ""]
    for origin, label in [("human", "İnsan çizimleri"), ("synthetic", "Sentetik çizimler")]:
        worst = min(PROFILES, key=lambda p: summary[origin][p]["connections"]["f1"])
        before = summary[origin]["original"]["connections"]["f1"]
        after = summary[origin][worst]["connections"]["f1"]
        lines.append(
            f"- {label}: bağlantı açısından en düşük koşul **{LABELS[worst]}**, F1 {percent(before)} → {percent(after)}. Bu koşul sonraki geliştirme ve hata incelemesinde öncelikli adaydır."
        )
    lines += [
        "- Dönüşümler şekil veya çekim dayanıklılığını ölçer; yeni bir mimari planı anlama ve yeni yazara genelleme başarısını ölçmez.",
        "- İnsanlarda 50 kaynağın 42’sinde bölge referansı vardır: bölge metriği özgünlerde 42, türevlerde 210 görüntü üzerinden hesaplanır. Boş/eksik referans %100 başarı sayılmaz. Doğru bağlı kapı recall paydasında sahipliği belirli 65 kaynak kapı kullanılır; konum metriğinde 67 kapı vardır.",
        "- Maskeler ayrı çizim örnekleri değildir. Mevcut maskeler duvar, söve ve metin renderer katmanlarıdır; tam model çıktısı için altı kanallı yoğun referans oluşturmaz. Bu çalışmada piksel Dice/IoU iddiası yoktur.",
        "- Referansla eşleşmeyen bağlantı fiziksel olarak kesin yanlış demek değildir; insan referansları yaklaşık ve yeni manuel kontrol yapılmamıştır.",
        "- Perspektif altında kutu IoU’nun sınırlılığı vardır; metrik santimetre veya kusursuz poligon geometrisi testi değildir.",
        "- Çalışma süreleri CPU üzerinde seri ve ısınmış modelle ölçülmüştür; canlı servis yük testi değildir.",
        "- Bozulmalara özel parametre veya model değişikliği yapılmadı. Bu rapor teşhis amaçlıdır; iyileştirme etkisi ayrı bir deneyle ölçülmelidir.",
        "",
        "## Doğrulama ve çıktılar",
        "",
        "720 tahmin arşivi ve 2.160 öneri belgesi doğrulandı; tamamı kullanıcı onayı bekliyor. Çalıştırma hatası yok. 5.782 korunan dosya değişmedi. Kaynak/model/veri hash kontrolleri ve örnek sayıları `verification.json` ve `analysis_verification.json` içindedir. Dönüşüm ve yanlış sahiplik kontrolleri için 3 otomatik değerlendirme testi geçti.",
        "",
        "- `report.json`: tüm örnekler ve grup sonuçları",
        "- `metrics.csv`: precision / recall / F1",
        "- `paired.csv`: örnek başına özgün–türev farkları",
        "- `gallery.html`: en büyük 20 bağlantı kaybının görüntü karşılaştırması",
        "- `paired_intervals.json`: temel plan grubu bootstrap farkları",
        "- `protocol.json`, `source_snapshot/`: sabitlenen protokol ve kaynaklar",
        "- `predictions/`: sıkıştırılmış üretim önerileri, birincil authoring belgesi ve görüntü ön izlemeleri",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "report_tr.md").write_text(text)
    (ROOT / "Docs/augmented_shape_robustness_2026_11_07.md").write_text(text)
    worst = sorted(
        [v for v in report["paired"] if v["metric"] == "connections" and v["delta_f1"] is not None],
        key=lambda v: v["delta_f1"],
    )[:20]
    figures = []
    for v in worst:
        title = html.escape(v["sample_id"])
        figures.append(
            "<section><h2>"
            + title
            + "</h2><p>Özgün bağlantı F1: "
            + percent(v["original_f1"])
            + "; türev: "
            + percent(v["augmented_f1"])
            + '</p><div class="pair"><figure><figcaption>Özgün</figcaption><img src="predictions/'
            + html.escape(v["source_id"])
            + '/working.png"></figure><figure><figcaption>'
            + html.escape(LABELS[v["profile"]])
            + '</figcaption><img src="predictions/'
            + title
            + '/working.png"></figure></div></section>'
        )
    (OUT / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Artırma dayanıklılığı: en büyük bağlantı kayıpları</title><style>body{font:16px system-ui;max-width:1100px;margin:24px auto;background:#f5f6f8}section{background:white;padding:20px;margin:20px 0}.pair{display:flex;gap:20px}figure{margin:0;flex:1}img{width:100%;image-rendering:auto}</style><h1>En büyük 20 bağlantı F1 kaybı</h1><p>Bu seçki hata incelemesi içindir. Bütün 600 türev raporda puanlanmıştır. Görüntüler sistemin gerçek çalışma görüntüleridir.</p>'
        + "".join(figures)
    )
    print(
        json.dumps(
            {
                origin: {
                    p: {k: round(summary[origin][p][k]["f1"] * 100, 2) for k in KEYS}
                    for p in ["original"] + PROFILES + ["augmented_all"]
                }
                for origin in ["human", "synthetic"]
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
