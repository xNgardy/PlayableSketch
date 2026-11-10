import csv
import html
import json
from collections import Counter
from pathlib import Path
import shutil
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from SketchPipeline.preprocessing.prepare import project
from .diagnose_new20 import ROOT, ARMS, SENSITIVITY, FONT
from .synthetic import write_json
from .dino_model import sha

OUT = ROOT / "Saved/ShapeFirst/new20_diagnosis/v5"
NOTES = {
    51: "İki kapı ve düz koridor fotoğrafla tutarlı. Üst kapı açık geçiş olarak yorumlanmış; referans uç müdahalesi bunu kapıya çeviriyor.",
    52: "Solda kapı, sağda işaretsiz açık geçiş var. Oda sınırları bulunmuş; aradaki koridor eksik.",
    53: "İnce uzun koridor eksik. Alt kapının kalın, eğik uçlarında 512 kanıt çözünürlüğünde açıklık daralıyor.",
    54: "İki kapı doğru tamamlanıyor. Koridorun oda diye sınıflandırılması tür hatası; konum eşleştirmesi türü zorlamıyor.",
    55: "İki oda arasındaki L yol işaretsiz açık. Yanlış ek odalar ve eksik yatay koridor var; dirsekteki bölme çizgisi geometrik bir etiketleme uzlaşımı.",
    56: "L yolun yatay kolu eksik, dik kol kısa. Üst kapı açık geçiş sayılıyor. Sol kapıda duvar desteği referanslı deneyde de sınır altında.",
    57: "Üst bağlantı açık, altta kapı var. Her iki L kolu tahminde kayıp; ayrıca görüntü dışı fazladan oda önerisi var.",
    58: "L yolu büyük bir oda dikdörtgeniyle temsil edilmiş. Referans geometri iki kapıyı kurtarıyor; dirsek açık arayüz yanıtı düşük.",
    59: "İki kapı ve L geçişi mevcut yöntemde eşleşiyor; ayrıca fazladan oda var. Referans geometride CV-kurtarma geçmişi kaldırılınca iç geçiş kayboluyor; duyarlılık koşulu bunu geri getiriyor.",
    60: "Üç açık geçiş; kapı işareti yok. Dik koridor kısmen bulunmuş, yatay kol eksik. Dirsek geçişi referanslarla da eşiklerde kalıyor.",
    61: "Üstte tek kapı ve iki dirsekli yol var. Koridorlar kayıp. Referanslarla üst açıklık önce açık geçiş olarak tutuluyor; sonraki kapı kanıtı bunu değiştiremiyor.",
    62: "U yol, iki oda ve kapısız açık girişler fotoğrafla tutarlı. İki kısa dik koridor tahmini bütün yolu temsil etmiyor. Koridor içi kesitlerin kesin konumu uzlaşımsal.",
    63: "T yapısında üç kapı var. Koridorların yerinde/çevresinde yanlış oda dikdörtgenleri oluşmuş. g003 alt uç etiketi 35 piksel aşağıda duvara konmuş; fotoğrafa dayalı referans düzeltmesiyle iki referans koşulu üç kapıyı da buluyor.",
    64: "Dört kapı fotoğrafta görünür; iki kapılı rehbere dönüştürülmedi. Merkez ve kollar yanlış bölündüğünden konumu doğru iki kapı bile referans bölge çiftine bağlanmıyor.",
    65: "Üç oda, iki koridor ve dört kapı fotoğrafla tutarlı. Üst koridor oda sayılmış, orta oda ve alt koridor kaçmış. Referans bölgeler dört kapıyı da kurtarıyor.",
    66: "Üç oda, iki kapı, iki açık bağlantı. Dik ve yatay koridor tahminleri parçalı; boş alanda fazladan bölgeler var. Referans geometri dört bağlantıyı da kurtarıyor.",
    67: "Üstte kapı, altta kesintisiz kapalı sınır var. Alt sınırda geçiş referansı yok ve üretilmiyor.",
    68: "İki ayrık kapalı oda var. Üretim CV kurtarma altı yanlış koridor bölgesi ekliyor; buna rağmen tamamlanmış kapı/bağlantı sayısı sıfır.",
    69: "İki kapı var; dirsekte çizilmiş kapalı ayırıcı geçiş sayılmıyor. Dik kol eksik; yatay kol oda sayılmış. Sağ kapıda duvar desteği eşiğin altında.",
    70: "Sol üst kapı ve L yol; sağ üst oda bağımsız. Model gerçek L yerine sağdaki iki oda arasına yanlış koridor koyuyor; tamamlanmış bağlantı üretmiyor.",
}
REASONS = {
    "missing_region_or_corridor": "Bölge/koridor bulunamadı veya IoU eşiğinde eşleşmedi",
    "missing_or_wrong_shared_boundary": "Ortak sınır oluşmadı/yanlış",
    "physical_check_rejected": "Yakın adayda fiziksel kontrol reddi kaydı var",
    "endpoint_localization_or_candidate_search": "Uç konumu/aday araması; uç müdahalesiyle kurtarıldı",
    "location_detected_but_wrong_region_ownership": "Açıklık konumu bulundu, bölge sahipliği yanlış/eşleşmedi",
    "opening_type_mismatch": "Kapı/açık geçiş türü yanlış",
    "multiple_or_unresolved": "Birden fazla neden veya açıklanamıyor",
    "reference_endpoint_label_error": "Özgün referans uç etiketi hatalı; fotoğraftan düzeltilmiş yan referans kullanıldı",
    "matched": "Eşleşti",
    "recorded_physical_or_semantic_rejection": "Fiziksel ya da öğrenilmiş arayüz kontrolünde ret",
    "opening_type_mismatch_or_precedence": "Tür/öncelik kuralı; kapı yerine açık geçiş tutuldu",
    "boundary_attachment_rejected": "Ortak sınıra bağlama reddedildi",
    "candidate_search_or_early_filter_unresolved": "Aday araması/erken filtre; kesin neden çözülmedi",
    "type_location_ownership_or_matching": "Tür/konum/sahiplik/eşleştirme sorunu",
}
LABELS = {
    "baseline": "Mevcut yöntem",
    "reference_regions": "Referans sınırlar",
    "reference_endpoints": "Referans kapı uçları",
    "reference_both": "Referans sınırlar + uçlar",
    "reference_regions_recovery_fallback": "Referans sınırlar + fiziksel koridor ek kontrolü",
    "reference_both_recovery_fallback": "İki referans + fiziksel koridor ek kontrolü",
}


def crop_opening(n, gap, coordinates, dest):
    original = Image.open(ROOT / f"Data/Data_{n}.png").convert("RGB")
    raw = np.asarray(original)
    matrix = coordinates["working"]["working_to_original"]
    points = project(gap["reference_points_working"], matrix)
    scale = max(np.linalg.norm(np.asarray(matrix)[:2, :2], axis=0))
    margin = 28 * scale
    lo = np.maximum(0, np.floor(points.min(0) - margin)).astype(int)
    hi = np.minimum(original.size, np.ceil(points.max(0) + margin)).astype(int)
    folder = ROOT / coordinates["source_folder"]
    evidence = cv2.imread(str(folder / "evidence.png"))
    evidence = cv2.cvtColor(evidence, cv2.COLOR_BGR2RGB)
    evidence = cv2.warpPerspective(
        evidence, np.asarray(coordinates["evidence"]["working_to_original"]), original.size
    )
    canvas = Image.new("RGB", (900, 450), "#f4f6f8")
    font = ImageFont.truetype(FONT, 16)
    for k, (im, title) in enumerate(
        [(raw, "Özgün fotoğraf"), (evidence, "512 kanıt; aynı özgün koordinat penceresi")]
    ):
        patch = Image.fromarray(im[lo[1] : hi[1], lo[0] : hi[0]])
        s = min(420 / patch.width, 380 / patch.height)
        patch = patch.resize((round(patch.width * s), round(patch.height * s)))
        off = np.array([450 * k + (450 - patch.width) // 2, 45])
        canvas.paste(patch, tuple(off))
        draw = ImageDraw.Draw(canvas)
        draw.text((450 * k + 10, 10), title, font=font, fill="#111827")
        p = (points - lo) * s + off
        draw.line([tuple(v) for v in p], fill="#16a34a", width=2)
        for x, y in p:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline="#16a34a", width=2)
    path = dest / f"{gap['opening_id']}_crop.png"
    canvas.save(path)
    return path


def main():
    if (OUT / "verification_final.json").exists():
        raise ValueError("Finalized review package; preserve it and choose a new run")
    report = json.loads((OUT / "report.json").read_text())
    protocol = json.loads((OUT / "protocol.json").read_text())
    failures = json.loads((OUT / "failures.json").read_text())
    audits = []
    figure_review = []
    for n in range(51, 71):
        sample = f"Data_{n}"
        folder = OUT / sample
        ref = json.loads((folder / "reference.json").read_text())
        coordinates = json.loads((folder / "coordinates.json").read_text())
        records = [r for r in failures if r["sample_id"] == sample]
        internal = []
        for r in records:
            internal_cut = all(
                (
                    next((v for v in ref["regions"] if v["id"] == owner))["type"]
                    == "corridor_segment"
                    for owner in r["owners"]
                )
            )
            r["label_audit"] = {
                "semantic_label": "No unambiguous contradiction found in visual review",
                "geometry_precision": "Approximate centerline/endpoints; not pixel-exact clear edges",
                "internal_corridor_partition_conventional": internal_cut,
                "reference_modified": False,
            }
            if n == 63 and r["opening_id"] == "g003":
                r["label_audit"].update(
                    confirmed_endpoint_label_error=True,
                    reference_modified=True,
                    original_dataset_modified=False,
                    correction_sidecar="../label_audit_overrides_v1.json",
                )
                r["reasons"].append("reference_endpoint_label_error")
            if internal_cut:
                internal.append(r["opening_id"])
            r["reasons_tr"] = [REASONS.get(v, v) for v in r["reasons"]]
            r["both_reference_remaining_reason_tr"] = REASONS.get(
                r["gate_audits"]["reference_both"]["stage_evidence"]
            )
            crop_opening(n, r, coordinates, folder)
        raw = json.loads(
            (ROOT / f"Data/ground_truth/structural_v1/{sample}.structural.json").read_text()
        )
        annotation = json.loads(
            (ROOT / f"Data/annotations/v1/{sample}.annotations.json").read_text()
        )
        gaps = [g for g in annotation["gaps"] if g["kind"] in ("door", "open_passage")]
        assert [(g["id"], g["kind"], g["start_px"], g["end_px"]) for g in gaps] == [
            (g["id"], g["kind"], g["start_px"], g["end_px"]) for g in raw["openings"]
        ]
        audit = {
            "sample_id": sample,
            "notes_tr": NOTES[n],
            "source_sha256": sha(ROOT / f"Data/{sample}.png"),
            "door_count": sum((r["type"] == "door" for r in records)),
            "opening_count": len(records),
            "internal_partition_uncertainty_ids": internal,
            "confirmed_semantic_label_error": False,
            "pixel_perfect_labels_claimed": False,
            "annotation_sidecar_openings_equal": True,
            "label_changes": (
                ["g003 endpoint corrected in diagnostic sidecar only"] if n == 63 else []
            ),
            "visual_review": "Original contact sheets and six-panel source/reference/prediction atlas opened by agent.",
            "atlas_sha256": sha(folder / "atlas.png"),
        }
        audits.append(audit)
        write_json(folder / "label_audit.json", audit)
        write_json(folder / "failures.json", records)
        table = "<table><tr><th>Açıklık</th><th>Tür</th><th>Mevcut: kanıtlanan/olası engel</th><th>İki referans sonrası</th></tr>"
        for r in records:
            cause = "Eşleşti" if r["attached_by_arm"]["baseline"] else "; ".join(r["reasons_tr"])
            table += f"""<tr><td><a href="{sample}/{r['opening_id']}_crop.png">{r['opening_id']}</a></td><td>{r['type']}</td><td>{html.escape(cause)}</td><td>{html.escape(r['both_reference_remaining_reason_tr'] or '')}</td></tr>"""
        table += "</table>"
        figure_review.append((sample, f"<p>{html.escape(NOTES[n])}</p>" + table))
    write_json(OUT / "failures.json", failures)
    write_json(
        OUT / "label_audit.json",
        {
            "review_date": "2026-11-06",
            "samples": audits,
            "original_labels_modified": False,
            "conclusion_tr": "Data_63 g003 alt uç etiketi fotoğrafla çelişiyor; ayrı teşhis referansında düzeltildi. Özgün etiketler korundu. Diğer yaklaşık uçlar ve mantıksal koridor kesitlerinin kesin konumu belirsiz.",
            "reference_adapted_to_predictions": False,
        },
    )
    with (OUT / "opening_failures.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "sample",
                "opening",
                "type",
                "baseline_attached",
                "reference_regions",
                "reference_endpoints",
                "reference_both",
                "reasons_tr",
                "remaining_both_tr",
                "label_partition_uncertain",
            ]
        )
        for r in failures:
            writer.writerow(
                [
                    r["sample_id"],
                    r["opening_id"],
                    r["type"],
                    *[r["attached_by_arm"][a] for a in ARMS],
                    "; ".join(r["reasons_tr"]),
                    r["both_reference_remaining_reason_tr"],
                    r["label_audit"]["internal_corridor_partition_conventional"],
                ]
            )
    page = (OUT / "gallery.html").read_text()
    for sample, table in figure_review:
        start = page.index(f'<section id="{sample}">')
        end = page.index("</section>", start)
        page = page[:end] + table + page[end:]
    page = page.replace(
        "<h1>PlayableSketch · 20 çizim teşhis atlası</h1>",
        '<h1>PlayableSketch · 20 çizim teşhis atlası</h1><p><a href="report_tr.md">Türkçe rapor</a> · <a href="metrics.csv">Koşul ölçümleri CSV</a> · <a href="opening_failures.csv">58 açıklık teşhisi CSV</a> · <a href="label_audit.json">Etiket denetimi</a></p>',
    )
    (OUT / "gallery.html").write_text(page)
    for path in protocol["hashes_before"]:
        if path.startswith("SketchPipeline/shape_authoring/") and (not "/models/" in path):
            dest = OUT / "source_snapshot" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, dest)
    for file in [Path(__file__), ROOT / "SketchPipeline/tests/test_new20_diagnosis.py"]:
        dest = OUT / "source_snapshot" / file.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, dest)
    from SketchPipeline.tests.test_new20_diagnosis import New20DiagnosisTests
    from .diagnose_new20 import oracle_door_stage
    from . import door_geometry

    gray, segments, points = New20DiagnosisTests().scene(True)
    ordinary, ordinary_detail = door_geometry.opening_candidates([], segments, gray, np.eye(3))
    oracle, oracle_detail = oracle_door_stage([], segments, gray, np.eye(3), points)
    cv2.imwrite(str(OUT / "closed_wall_negative_control.png"), gray)
    write_json(
        OUT / "physical_negative_control.json",
        {
            "production_candidate_count": len(ordinary),
            "oracle_adapter_candidate_count": len(oracle),
            "production_diagnostics": ordinary_detail,
            "oracle_diagnostics": oracle_detail,
            "limitation": "The same physical verifier can find gap clearance off the actual closed wall, while its wider flank support ribbon still sees wall ink. Baseline morphology did not propose jambs here. Oracle intervention is not a safe deployment path.",
        },
    )

    def metric_table(split, arms):
        lines = [
            "| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |",
            "|---|---:|---|---:|---|---:|---:|",
        ]
        fmt = lambda x: "—" if x is None else f"{x:.3f}"
        for a in arms:
            m = report["summary"][split][a]
            d = m["doors"]
            c = m["connections"]
            lines.append(
                f"| {LABELS[a]} | {d['true_positive']}/{d['predicted']}/{d['reference']} | "
                + "/".join((fmt(d[k]) for k in ["precision", "recall", "f1"]))
                + f" | {c['true_positive']}/{c['predicted']}/{c['reference']} | "
                + "/".join((fmt(c[k]) for k in ["precision", "recall", "f1"]))
                + f" | {m['unmatched_produced_connections']} | {m['missed_connections']} |"
            )
        return "\n".join(lines)

    text = "# PlayableSketch: 20 gerçek çizimde bileşen teşhisi — 6 Kasım 2026\n\nAna bulgu: önce bölge/koridor geometrisi ve ortak sınır çıkarımına odaklanmalıyız. Mevcut yöntemin 9/32 doğru kapısı referans sınırlarla 24/32'ye çıkıyor; yalnız kapı ucu müdahalesi 11/32'de kalıyor; ikisi birlikte 28/32. Bu sayılar yeni bir modelin gerçek kullanım başarısı değildir. Referanslı koşullar, aynı kullanıcıdan daha önce görülmüş çizimlerde yapılan teşhis müdahaleleridir.\n\n## Doğrulanan mevcut durum\n\n- Kaynak ve kayıtlı iş yapılandırmaları DINO ağırlığını ve `refined-full`, ink normalization, `shape-decoder/2.8`, `supported-corridors`, `corridor-passages`, `observed-jambs`, `observed-door-jambs/1.5` politikalarını doğruluyor. Decoder'ın çıplak varsayılan çağrısı bu servis seçimleriyle aynı değil.\n- 8772 servisi `/api/bootstrap` isteğine yanıt verdi. `/api/health` kaynakta yok. İlk kısıtlı ağ isteğinin başarısız olması servis kapalı demek değildi. Yeni canlı model işi gönderilmedi; mevcut iş ayarları, dosya hash'leri ve önbelleklerden yeniden çalıştırılan decoder doğrulandı. Bellekte yüklü modelin yeni bir çağrıdaki davranışı ayrıca ölçülmedi.\n- Yeni veri manifestinde 20 insan fotoğrafı, 60 türev, 12 rehber, 20 karmaşık sentetik kayıt: toplam 112. Veri denetimi bölümler arasında ebeveyn/hash sızıntısı bulmadı. Yeni 20 fotoğraf train/validation/test = 12/4/4; bu çalışma sentetikleri başarı toplamına katmıyor.\n- Önceki ensemble seçimi dosyalarda baseline; doğrulamada 26 kapı/28 bağlantı. Eski test 12 kapı/16 bağlantı; yeni test 0 kapı/1 bağlantı; sentetik baseline 123 kapı/141 bağlantı. v3 mevcut kolların dosyalarını v2'den kullanıyor: v3 altında her kol için ayrı baseline dosyası yok. Bu beklenen dosya düzeni farkı kaydedildi.\n- Kodda gece modu, düzenlenebilir otomatik bölge adları ve onaydan önce geometry/gameplay seçimi var. Unreal Pawn hareketi kameranın sağ/yukarı vektörlerinden hesaplanıyor. Ön işleme EXIF dönüşümü ve sınırlı küçük açı düzeltmesi içeriyor; yön koruması dönüşüm metadatasıyla izleniyor. Bu oturumda canlı Unreal/UI uçtan uca testi yapılmadığı için bunlar kaynak doğrulamasıdır.\n- Korunan deneme_1 kaynağı ve önceki inceleme işi bulundu; SHA doğrulandı, önceki 3 oda/3 koridor/2 kapı/3 açık geçiş çıktısı dosyadan doğrulandı. Bu, yeni 20 çizimin sonucu olarak kullanılmadı.\n\n## Deneyin tam tanımı\n\n1. **Mevcut yöntem:** aktif DINO'nun float32 önbellekleri + bugünkü üretim decoder'ı. 20/20 topoloji önceki v2 baseline ile birebir aynı. Kapı aşamasının ayrı yeniden yürütümü de 20/20 aynı açıklıkları verdi.\n2. **Referans sınırlar:** anotasyondaki gerçek poligonlar bölge yerine verildi. Ortak kenarlar yalnız bu poligonlardan çıkarıldı; kapı etiketleri/bağlantı sahipliği bu aşamaya verilmedi. Fiziksel kontrol yatay/dikey sınır istediği için fotoğraftaki ortak kenarlar baskın eksene izdüşürüldü. Bölge poligonları değiştirilmedi. En büyük normal izdüşüm hatası çalışma görüntüsünde 5.311 piksel (Data_64); her kenar için kayıt var. Dolayısıyla bu, kusursuz perspektifli geometri üst sınırı değildir.\n3. **Referans kapı uçları:** sadece kapılara ait, eşleştirilmemiş nokta kümesi verildi. Nokta çiftleri, sahiplik, kabul sonucu, işaret uzunluğu veya açık geçiş uçları verilmedi. Tanı amaçlı bir adaptör bu noktalarda gerçek mürekkep uzanımlarını ölçüp mevcut `detect_pairs` fiziksel doğrulamasına sokuyor. Her iki eksen ve bütün olası çiftler yine deneniyor. Önceki üretim geçiş/kapı yolları korunuyor. Bu, head-6 haritasını değiştirmekle aynı değildir ve öğrenilmiş bir dedektörün üst sınırı diye okunamaz.\n4. **İki referans birlikte:** 2 ve 3 aynı anda, aynı fiziksel/geometrik kabul kurallarıyla.\n\nÜretim kapı yolu modelin **head 6 kapı ucu kanalını doğrudan kullanmıyor**. Head 3 işaret yanıtı, head 5 açık arayüz yanıtı, çizgi çiftleri ve fiziksel görüntü kontrolleri var. Head 6 atlaslarda gösteriliyor; zayıf head 6 yanıtını tek başına üretim hatasının nedeni saymadım. Bu çalışmada deneysel ensemble kodu kullanılmadı.\n\nAna referans-bölge koşullarında CV ile sonradan kurtarıldı geçmişi yok. Üretimdeki yalnız kurtarılmış koridorlara uygulanan ek fiziksel geçiş yolu böylece çalışmıyor. Bu kaynak/provenans farkının etkisini saklamamak için ayrıca iki duyarlılık koşulu çalıştırıldı: referans koridorların tamamı sonradan eklenmiş kabul edilip **mevcut** fiziksel ek kontrol çalıştırıldı; doğru açıklık ya da sahiplik verilmedi. Ana dört koşulun sonuçları bununla değiştirilmedi.\n\n## Değerlendirme\n\nBütün koşullarda aynı maksimum eşleme: bölge bounding-box IoU ≥0.5 (türden bağımsız), açıklık türü aynı ve iki uçta en büyük hata ≤çalışma kenarının %4'ü. Bu görüntülerde tolerans 10.24 çalışma pikseli. Tür doğruluğu ayrıca JSON'da tutulur; IoU eşleşmesi doğru oda/koridor türü demek değildir. Noktalar özgün → 512 kanıt → çalışma dönüşüm matrisleriyle aktarılır. Özgün koordinata gidiş/dönüş sayısal hatası en çok 2.28e-13 piksel.\n\n**Doğru kapı** konum ve tür eşleşmesidir. **Doğru bağlantı** ayrıca doğru referans bölge çifti gerektirir. Ana tabloda tekil bölge çiftleri sayılır; açıklık bazlı sahiplik metrikleri ayrıca `attached_openings` altında JSON/CSV'dedir. Bu kümede referans açıklık ve bağlantı paydaları aynıdır: 58. Aynı çiftin birden fazla açıklığı olursa bu iki metrik farklılaşabilir.\n\nSahiplik referansı eski değerlendiricideki en yakın poligondan türetme yerine yapısal referansın **açıkça kayıtlı entity_ids** alanıdır. Önceki değerlendirme çıktıları değiştirilmedi; eski skorlar her çizimde `legacy_baseline_metrics.json` içinde saklandı. Gerçek veride eski `false_connections=None` değerini toplarken 0'a dönüştürmek sıfır hata kanıtı değildi. Yeni tabloda üretilen−doğru sayısı **referansla eşleşmeyen** bağlantıdır; yaklaşık etiket ve bölge eşleme yüzünden bunu doğrudan fiziksel olarak yanlış kapı sayısı diye sunmuyoruz. Doğrulanmış gerçek dünya false-positive sayısı bu çalışma ile tam belirlenmedi.\n\nP/R/F1 mikro toplamdır. Üretim yoksa precision tanımsız (—), sıfır başarılı sayılmaz. Kör test/bağımsız çizer/genelleme ve toplam model çıkarım süresi iddiası yok. Eğitim başlatılmadı.\n"
    for split, title in [
        ("train", "Train — 12 çizim"),
        ("validation", "Validation — 4 çizim"),
        ("test", "Test — 4 çizim"),
        ("all", "Toplam — yalnız betimleyici"),
    ]:
        text += "\n## " + title + "\n\n" + metric_table(split, ARMS) + "\n"
    text += (
        "\n## Koridor ek kontrolü duyarlılığı\n\nBu ek koşullar ana dört koşula dahil edilmedi. Train/validation/test ayrımları JSON/CSV'de ayrıca var.\n\n"
        + metric_table("all", SENSITIVITY)
        + "\n\nReferans geometride ek kontrol açılınca bağlantı 35'ten 46'ya; iki referansta 39'dan 50'ye çıkıyor. Kapı sayıları değişmiyor. Açık geçişteki eksiğin bir bölümü fiziksel açıklık yokluğundan değil, öğrenilmiş arayüz yanıtı ve koridorun hangi yoldan geldiğine bağlı dallanmadan kaynaklanıyor. Bu, ek kontrolü bütün tahminlere koşulsuz açmanın güvenli olduğunu kanıtlamaz.\n\n## Etiket denetimi ve görsel bulgular\n\n20 fotoğrafın tamamı, referans bindirmeleri ve altı panelli atlaslar açılıp incelendi. Bir somut geometri etiket hatası bulundu: **Data_63 g003 alt ucu** [1121.9473,679.0028] yerine fotoğrafta ikinci kısa çizginin duvarla kesiştiği yaklaşık [1127,644] olmalı. Gözlemdeki l0038 çizgisi de alt duvara konmuş. Önce/sonra, kaynak SHA ve fotoğraf koordinat kanıtı `../label_audit_overrides_v1.json` içinde kayıtlı. Yalnız teşhis referansının bu ucu düzeltildi; **özgün etiketler ve eğitim hedefleri değiştirilmedi**. Tür, sahiplik ve bölgeler korunuyor. Seçim model tahmininden değil özgün fotoğraftan yapıldı. Özgün etiketlerle v4 korunuyor; v5 aynı dört koşulu düzeltilmiş referansla yeniden çalıştırıyor. Ana fark yalnız iki-referans koşulunda: kapı 27→28, bağlantı 38→39; diğer ana koşullar aynı. Eski etiketle bu kapının reddini salt fiziksel kontrol hatası diye yorumlamak yanlıştı. Bu, poligonların ve uçların piksel düzeyinde doğru olduğu anlamına gelmez. Kapı uçları yaklaşık duvar/işaret merkezlerini tarif ediyor; kesin geçiş kenarı ölçümü değil. Koridor dirseklerindeki iç bölme kesitleri çoğu zaman çizilmiş duvar değil mantıksal ayırımdır; kesin kesit konumları uzlaşımsal. Bunlar her açıklık için `label_audit` içinde işaretlendi; referans modele uydurulmadı ve belirsiz örnekler paydadan çıkarılmadı.\n\nData_64'te dört kapı; Data_67'nin alt sınırı kapalı; Data_68'de iki ayrık oda; Data_69'un dirseğinde kapalı ayırıcı; Data_70'te sağ üst odanın ayrıklığı fotoğrafla tutarlı bulundu. Tüm çizimlerin notları aşağıdadır.\n\n| Çizim | Görsel inceleme |\n|---|---|\n"
    )
    for n, note in NOTES.items():
        text += f"| Data_{n} | {note} |\n"
    text += "\n## Açıklık bazında engeller\n\nMevcut yöntem 58 referans açıklığın 9'unu doğru sahipliğe bağladı, 49'u eşleşmedi. Bunların 46'sında en az bir referans bölge IoU eşlemesinde yok; bu, bazen fiziksel yokluk, bazen aşırı kısa/yanlış birleşmiş geometri. Kalan üçünde de tek başına “uç modeli başarısız” denilemez. Neden etiketleri çoklu olabilir; yakındaki reddedilmiş aday başka bir aday da olabilir. Ham kayıt ve müdahale sonucu birlikte okunmalıdır.\n\nReferans sınırlar baseline'ın kaçırdığı 27 bağlantıyı kurtarıyor; Data_59 g002 ise CV-kurtarma geçmişi kaldırıldığından kayboluyor (net +26). Yalnız uç müdahalesi Data_51 g001 ve Data_56 g001'i kurtarıyor. Data_63 g003 için bölge ve uç birlikte gerekli; etiket düzeltmesi bu ayrımı görünür kıldı. Sınır+uç müdahalesinde 19 bağlantı hâlâ kaçıyor: dördü kapı, on beşi açık geçiş. Bunların hepsinin “fiziksel duvar var” diye etiketlenmesi yanlış olur.\n\n| İki referansa rağmen kaçan kapı | Ölçülen engel |\n|---|---|\n| Data_53 g002 | 512 kanıtta gap_clear=0.667; gereken ≥0.85. Kalın/eğik kısa kapı, yaklaşık uç konumu ve çözünürlük birlikte etkili olabilir. |\n| Data_56 g002 | Duvar desteği min=0.636; gereken ≥0.65. |\n| Data_61 g001 | Açık geçiş önce tutulmuş; takip yolu kapı için bütün testleri geçse de `overlap_baseline_or_earlier` ile bastırılmış. Son çizgi-çifti yolunda min duvar desteği 0.214. Tür/öncelik ve fiziksel örnekleme birlikte etkili. |\n| Data_63 g003 — etiket denetimi | Eski referansta gap_clear=0.8125; alt uç etiket hatası. Fotoğraf temelli düzeltmeyle iki-referans koşulunda kapı eşleşiyor; artık kalan kapı hatası sayılmıyor. |\n| Data_69 g002 | min duvar desteği 0.625; gereken ≥0.65. |\n\nÖrnek açık geçişler: Data_55 g002 clear=1.0 iken arayüz yanıtı 0.000242; Data_58 g003 clear=0.944 iken yanıt 0.00000170; Data_64 g005 clear=0.985 iken yanıt 0.4404 (<0.45). Data_64 örneği fiziksel açıklıktan çok semantik eşik tarafından engelleniyor. Bu değerler `failures.json → gate_audits` içinde kayıtlıdır. Ek kontrol duyarlılığı bazılarını kurtarıyor; bütün geçişlerde kurtarmıyor.\n\nEk negatif kontrol, fiziksel doğrulamanın başka bir sınırını gösterdi: kapalı ince duvara referans konumlarda aday sunulduğunda, geniş duvar desteği şeridi duvarı görürken dar açıklık şeridi duvarın biraz dışına kayıp boşluk bulabiliyor. Olağan üretim aday araması bu örnekte aday çıkarmıyor; referans-uç adaptörüyle aynı fiziksel doğrulayıcı bir kapı kabul ediyor. Kalın bariyer ve boş görüntü kontrolleri reddediliyor. Bu açık `physical_negative_control.json` ve bir regresyon testiyle kayda alındı; kapı fiziksel doğrulamasının tam güvenilir olduğu veya uç adaptörünün üretime hazır olduğu iddia edilmiyor. Üretim kuralı bu oturumda değiştirilmedi.\n\nData_68 özellikle önemlidir: 2 gerçek oda karşısında 6 yanlış CV koridor bölgesi ekleniyor ama tamamlanmış bağlantı üretilmiyor. “Yanlış bağlantı 0” bu bölge hatasını gizleyebilir. Bu nedenle bölge ve bağlantı ölçümleri birlikte tutuldu.\n\n## Bir sonraki geliştirme önceliği\n\n1. İnce/uzun ve L/T koridorların geometrisi, bölge türü ve ortak sınır üretimi. Referans geometri validation'da kapıyı 4→9, bağlantıyı 2→10; testte kapıyı 0→3, bağlantıyı 1→10 çıkarıyor. Bu çalışma kapsamındaki en güçlü teşhis kanıtı budur.\n2. Açık geçiş kararının semantik başlık ve koridorun üretildiği yola bağımlılığını ele almak; tür/öncelik çakışmasını (Data_61) ve kaymış açıklık örnekleme negatif kontrolünü ayrı düzeltme hedefleri yapmak. Önce mevcut atlas negatifleriyle ölçmek; eşikleri körlemesine gevşetmemek.\n3. Kapı ucu dedektörü bundan sonra: konum müdahalesi iki mevcut kapıyı kurtarıyor, fakat eksik bölgeyi tamamlamıyor. Tek başına yeni eğitim/ensemble önceliğini desteklemiyor.\n\nBu sonraki geliştirmeler başlatılmadı. Yeni veri istenmedi, eğitim yapılmadı, aktif ağırlık veya üretim kaynakları değiştirilmedi; hiçbir plan otomatik onaylanmadı.\n\n## Teslim ve yeniden çalıştırma\n\n- `gallery.html`: 20 adet altı panelli atlas, dört koşul görüntüleri ve açıklık bazında Türkçe neden tablosu. Her açıklık ID'si özgün fotoğraf/512 kanıt yakınlaştırmasına açılır.\n- `report.json`, `metrics.csv`: dört ana koşul + iki ayrı duyarlılık koşulu, train/validation/test ayrımı ve precision/recall/F1.\n- `failures.json`, `opening_failures.csv`: 58 açıklığın nedenleri, her koşuldaki aşama kayıtları; 32 kapı ayrı tür alanıyla seçilebilir.\n- `label_audit.json`: 20 görsel inceleme notu, iç bölme belirsizlikleri ve teşhis yan referansındaki tek uç düzeltmesinin kaydı.\n- Her çizimde `coordinates.json`, `reference.json`, koşul tahminleri ve `candidates.json` var. Reddedilen numaralar aday kayıtlarına karşılık gelir. Arama öncesinde elenen her olası çizgi çifti kaydedilmiyor; “kayıt yok” tek başına ret nedenini ispatlamaz.\n- `protocol.json`: model, veri, önbellek ve kaynak SHA256 kayıtları; `source_snapshot`: kullanılan yerel kod/politikalar. `service_check.json`: anahtar içermeyen servis durum özeti.\n- 155 korunan dosya değişmedi; üç checkpoint SHA256 özetteki değerlerle eşleşti. 20 baseline topolojisi ve 20 kapı aşaması yeniden yürütümü eşit. Yeni 10 teşhis testi dahil ilgili 41 test geçti. Veri `--check` denetimi 112 kayıtta geçti. Ayrı `verification_final.json` çıktı envanterini ve son kontrolleri içerir.\n\n```sh\nPYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python \\\n  -m SketchPipeline.shape_authoring.diagnose_new20 \\\n  --output Saved/ShapeFirst/new20_diagnosis/NEW_RUN \\n  --label-overrides Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json\n```\n\nMevcut çıktı klasörü üzerine yazılmaz. `review_new20_diagnosis.py` bu oturumdaki elle gözden geçirilmiş notları v5 paketine ekleyen teslim betiğidir. v1 tamamlanmamış yeniden-yürütüm kontrolünde durmuştur; v2/v3 ara çalışmalardır, **teslim sürümü v5**. v4 özgün etiketlerle dört ana koşul ve ek duyarlılıkları içerir; v5 fotoğraftan denetlenmiş tek uç düzeltmesiyle aynı deneyi tekrarlar. İki-referans koşulu 27/32 yerine 28/32 kapı bulur. v4 raporu etiket denetimiyle birlikte okunmalıdır; önceki kesin etiket-hatası-yok ifadesi bu yakın incelemeyle geçersiz kalmıştır.\n"
    (OUT / "report_tr.md").write_text(text)
    (ROOT / "Docs/new20_diagnosis_2026_11_06.md").write_text(text)
    print("Packaged", len(audits), "images;", len(failures), "opening audits")


if __name__ == "__main__":
    main()
