import html
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.report_augmented_shape import percent

OUT = ROOT / "Saved/ShapeFirst/all_data_training/v1"
METRICS = {
    "regions": "Bölge konumu",
    "doors": "Kapı türü ve konumu",
    "connections": "Doğru bağlantı",
    "attached_doors": "Doğru bağlı kapı",
}


def main():
    report = json.loads((OUT / "evaluation/report.json").read_text())
    protocol = json.loads((OUT / "protocol.json").read_text())
    history = json.loads((OUT / "training/history.json").read_text())
    verify = json.loads((OUT / "evaluation/verification.json").read_text())
    summary = report["summary"]
    candidate = report["candidate"]
    lines = [
        "# Tüm veriyle yeniden eğitim — 7 Kasım 2026",
        "",
        "## Sonucun kapsamı",
        "",
        "**Bütün raporlanan görüntüler eğitimde kullanıldı. Aşağıdaki precision, recall ve F1 değerleri eğitim verisindeki uyumu gösterir; bağımsız test veya yeni yazara genelleme başarısı değildir.** Önceki train/validation/test grupları bu deneyde eğitime dahil edildi.",
        "",
        "Mevcut DINO çözücü ağırlığından başlanıp bütün çözücü parametreleri altı tam tur eğitildi. DINOv2 omurgası sabit kaldı. AdamW, öğrenme oranı 0,0001, batch 4, seed 71126. Her turda 1.376 örneğin tamamı bir kez görüldü: toplam 8.256 örnek sunumu. Son epoch 6, eğitim öncesinde sabitlendi; sonuçlardan checkpoint seçilmedi.",
        "",
        "## Kullanılan veriler",
        "",
        "| Veri grubu | Görüntü sunumu |",
        "|---|---:|",
    ]
    labels = {
        "old50": "İlk 50 insan çizimi + beşer türev",
        "new20": "Yeni 20 insan çizimi + beşer türev",
        "synthetic": "70 sentetik kaynak + beşer türev",
        "addon_human": "Önceden oluşturulmuş ek insan türevleri",
        "addon_dense": "Rehber ve karmaşık koridor renderları",
        "synthetic_replay": "Önceki eğitim dağılımından basit sentetikler",
        "previous_controls": "Önceki 60 sentetik kontrol; artık eğitimde",
    }
    for group, count in protocol["cohorts"].items():
        lines.append("| " + labels[group] + " | " + str(count) + " |")
    lines += [
        "| **Toplam** | **1.376** |",
        "",
        "Bu sayı bağımsız mimari plan sayısı değildir. Aynı kaynağın farklı görünümleri ve farklı setlerdeki olası tekrarları ayrı sunumlardır. Şema/ön izleme görselleri ve maskeler bağımsız çizim girdisi sayılmadı. Maskeler yalnızca tanımlı hedef kanallarında kullanıldı. Belirsiz insan pikselleri kayba sıfır ağırlıkla girer. Fiziksel ölçü veya sayısal OCR eğitimi yapılmadı.",
        "",
        "Önceden denetlenmiş Data_63 uç ve söve çizgisi düzeltmesi hedef oluşturulurken bellekte uygulandı; kaynak fotoğraflar ve etiket dosyaları değiştirilmedi.",
        "",
        "## Aynı görüntülerde eğitim öncesi / sonrası",
        "",
        "Aşağıdaki özgün ve türevler sabit birincil öneriyle, aynı geometri ve açıklık kurallarıyla puanlandı. Bölge: türden bağımsız kutu IoU ≥ 0,5. Kapı: doğru tür ve çalışma kenarının %4’ü içinde uç konumu. Bağlantı: açıklığın doğru iki bölgeye bağlanması. Eski insan referanslarında sahiplik yaklaşık yakınlık hesabıdır; yeni 20’de açık bölge kimlikleri kullanılır.",
        "",
        "| Grup | Görüntü | Bölge F1 önce → sonra | Kapı F1 önce → sonra | Bağlantı F1 önce → sonra |",
        "|---|---:|---:|---:|---:|",
    ]
    scopes = [
        ("audited_human70", "original", "70 özgün insan çizimi"),
        ("audited_human70", "augmented", "350 insan türevi"),
        ("new20", "original", "Yeni 20 özgün"),
        ("new20", "augmented", "Yeni 20’nin 100 türevi"),
        ("synthetic", "original", "70 özgün sentetik"),
        ("synthetic", "augmented", "350 sentetik türev"),
        ("addon_dense", "all", "32 ek yoğun etiketli örnek"),
        ("previous_controls", "all", "Önceki 60 kontrol (eğitime dahil)"),
        ("all", "all", "Bütün eğitim sunumları"),
    ]
    for group, profile, label in scopes:
        a = summary["before"][group][profile]
        b = summary["after"][group][profile]
        lines.append(
            "| "
            + label
            + " | "
            + str(b["samples"])
            + " | "
            + " | ".join(
                (
                    percent(a[k]["f1"]) + " → " + percent(b[k]["f1"])
                    for k in ["regions", "doors", "connections"]
                )
            )
            + " |"
        )
    lines += [
        "",
        "## İnsan çizimlerinde precision / recall / F1",
        "",
        "| Grup | Model | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for group, profile, label in scopes[:4]:
        for arm, arm_label in [("before", "Önce"), ("after", "Sonra")]:
            m = summary[arm][group][profile]
            for key, metric_label in METRICS.items():
                v = m[key]
                lines.append(
                    "| "
                    + label
                    + " | "
                    + arm_label
                    + " | "
                    + metric_label
                    + " | "
                    + " / ".join((str(v[k]) for k in ["true_positive", "predicted", "reference"]))
                    + " | "
                    + " | ".join((percent(v[k]) for k in ["precision", "recall", "f1"]))
                    + " |"
                )
    lines += [
        "",
        "## Dönüşümlerde bağlantı başarısı",
        "",
        "| Grup | Dönüşüm | Önce F1 | Sonra F1 |",
        "|---|---|---:|---:|",
    ]
    for group, label in [("audited_human70", "70 insan kaynağı"), ("new20", "Yeni 20")]:
        for profile in ["rotate", "perspective", "lighting", "capture", "combined"]:
            lines.append(
                "| "
                + label
                + " | "
                + profile
                + " | "
                + percent(summary["before"][group][profile]["connections"]["f1"])
                + " | "
                + percent(summary["after"][group][profile]["connections"]["f1"])
                + " |"
            )
    lines += [
        "",
        "## Kayıp ve doğrulama",
        "",
        "| Epoch | Ortalama eğitim kaybı | Görülen örnek |",
        "|---|---:|---:|",
    ]
    for row in history:
        lines.append(
            "| "
            + str(row["epoch"])
            + " | "
            + f"{row['loss']:.5f}"
            + " | "
            + str(row["examples_seen"])
            + " |"
        )
    lines += [
        "",
        "Kayıp değeri precision/recall veya doğruluk yüzdesi değildir. Başarı yorumu yukarıdaki son sistem çıktılarının eşleşmesine dayanmalıdır. Eksik bölge referansları bölge puanından çıkarılır; boş referans başarı sayılmaz. Sahipliği belirsiz kapılar bağlı kapı recall paydasına girmez.",
        "",
        "Sabit DINO omurgasının float32 özellikleri önbellekten okundu; mürekkep girdisi inference sırasında float32 yeniden kuruldu. Bu, aynı encoder hesaplamasını tekrar yapmamak içindir. Eğitim hedefleri inference girişine verilmedi. Önceki tam üretim girişinden 840 görüntüyle metrik eşitliği kontrolünde **"
        + str(verify["baseline_parity_equal"])
        + "/"
        + str(verify["baseline_parity_checked"])
        + "** görüntüde beş metriğin tamamı eşleşti. Tam giriş kontrol örnekleri ayrıca `integration/` içinde tutulur. Önbellek karşılaştırmasının süresi tam üretim gecikmesi olarak yorumlanamaz.",
        "",
        "25 eğitim/veri sözleşmesi testi geçti. Adayın ağırlıkları başlangıç modelinden farklıdır; eğitim kaydı ve hash’ler saklandı. Eğitim kodu kaynak veriye ve aktif model dosyasına yazmadı; son kaynak hash kontrolünün sınırı aşağıda açıklanmıştır.",
        "",
        "## Yorum",
        "",
    ]
    for group, profile, label in scopes[:4]:
        a = summary["before"][group][profile]["connections"]
        b = summary["after"][group][profile]["connections"]
        delta = (b["f1"] - a["f1"]) * 100
        lines.append(
            "- "
            + label
            + ": bağlantı F1 "
            + percent(a["f1"])
            + " → "
            + percent(b["f1"])
            + f" ({delta:+.1f} yüzde puan)."
        )
    lines += [
        "",
        "Bunlar mevcut örnekleri öğrenme sonuçlarıdır. Tam veriyle eğitim sonrasında gerçek kullanım başarısını ölçmek için eğitimde ve ayarlarda görülmemiş yeni çizimler gerekir. Eğitimdeki iyi sonuç tek başına otomatik kullanıma hazır olma kanıtı değildir.",
        "",
        "## Model ve çıktılar",
        "",
        "- Yeni aday: `" + candidate["checkpoint_path"] + "`",
        "- Yeni SHA256: `" + candidate["checkpoint_sha256"] + "`",
        "- Başlangıç SHA256: `" + protocol["starting_sha256"] + "`",
        "- Aktif model dosyası değiştirilmedi; yeni aday otomatik etkinleştirilmedi.",
        "- `protocol.json`: sabit eğitim tarifi, kapsanan kayıtlar ve kaynak hash’leri",
        "- `training/history.json`: altı turun kayıpları",
        "- `evaluation/report.json`, `evaluation/metrics.csv`: önce/sonra tüm örnekler ve gruplar",
        "- `evaluation/verification.json`: belge, veri bütünlüğü ve baseline eşitliği",
        "- `evaluation/gallery.html`: en çok iyileşen ve gerileyen insan örnekleri",
    ]
    unavailable = verify.get("post_training_unreadable_files", [])
    if unavailable:
        lines += [
            "",
            "## Son kaynak doğrulamasının sınırı",
            "",
            "Eğitim öncesinde tüm kaynak hash’leri doğrulandı. Son denetimde "
            + str(verify["protected_files_checked"])
            + " korunan dosya yeniden okunup değişmediği doğrulandı; "
            + str(len(unavailable))
            + " eski JPEG işletim sistemi tarafından okunamadı. Yetkili salt okunur deneme de bu dosyalara erişemedi. Eğitim ve ölçüm başlangıçta doğrulanmış önbellek üzerinden tamamlandı. Okunamayan JPEG’lerin son hash’i doğrulanmış gibi sunulmaz. Aktif model ve eğitim/evaluasyon kodu hash’leri doğrulandı. Dosya listesi `evaluation/verification.json` içindedir.",
        ]
    text = "\n".join(lines) + "\n"
    (OUT / "report_tr.md").write_text(text)
    (ROOT / "Docs/all_data_training_2026_11_07.md").write_text(text)
    by = {(r["arm"], r["sample_id"]): r for r in report["rows"]}
    diffs = []
    for row in report["rows"]:
        if row["arm"] != "after" or row["cohort"] not in ("old50", "new20"):
            continue
        before = by["before", row["sample_id"]]["metrics"]["connections"]["f1"]
        after = row["metrics"]["connections"]["f1"]
        if before is not None and after is not None:
            diffs.append((after - before, row["sample_id"], before, after))
    selected = sorted(diffs)[:10] + sorted(diffs, reverse=True)[:10]
    records = {
        e["record"]["id"]: i
        for i, e in enumerate(json.loads((OUT / "cache/manifest.json").read_text())["records"])
    }
    sections = []
    for delta, sid, a, b in selected:
        source = os.path.relpath(OUT / "cache/working" / f"{records[sid]}.png", OUT / "evaluation")
        sections.append(
            "<section><h2>"
            + html.escape(sid)
            + "</h2><p>Bağlantı F1 "
            + percent(a)
            + " → "
            + percent(b)
            + '</p><img src="'
            + html.escape(source)
            + '"><p><a href="before/'
            + html.escape(sid)
            + '/authoring.json">Önce</a> · <a href="after/'
            + html.escape(sid)
            + '/authoring.json">Sonra</a></p></section>'
        )
    (OUT / "evaluation/gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Tüm veri eğitimi: değişimler</title><style>body{font:16px system-ui;max-width:1000px;margin:24px auto}section{display:inline-block;width:45%;margin:1%;vertical-align:top}img{width:100%}</style><h1>Eğitim görüntülerinde en büyük değişimler</h1><p>Bu görüntülerin tamamı eğitimde kullanıldı. Seçki hata incelemesidir.</p>'
        + "".join(sections)
    )
    print(
        json.dumps(
            {
                label: {
                    arm: {k: summary[arm][group][profile][k]["f1"] for k in METRICS}
                    for arm in ["before", "after"]
                }
                for group, profile, label in scopes
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
