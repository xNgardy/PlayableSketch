import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.independent_boundary_experiment import OUT, write
from PIL import Image, ImageDraw, ImageFont


def pct(value):
    return f"{value*100:.1f}"


def run():
    result = json.loads((OUT / "report.json").read_text())
    protocol = json.loads((OUT / "protocol.json").read_text())
    names = {
        "cv_only": "CV, kapı ayırmadan",
        "cv+yolov8n": "CV duvar + YOLOv8n",
        "cv+yolo11n": "CV duvar + YOLO11n",
        "cv+fasterrcnn": "CV duvar + Faster R-CNN",
        "unet_only": "U-Net duvar + U-Net kapı",
        "unet+yolo11n": "U-Net duvar + YOLO11n",
        "unet+fasterrcnn": "U-Net duvar + Faster R-CNN",
        "mask2former_only": "Mask2Former duvar + kapı",
        "mask2former+yolo11n": "Mask2Former duvar + YOLO11n",
    }
    lines = [
        "# Bağımsız sınır ve kapı deneyleri — 9 Kasım 2026",
        "",
        "Canlı uygulama ve DINO ağırlıkları korunarak yeni deneyler yapıldı. Yeni modellerin test çizimleri kendi eğitimlerine katılmadı. Üretimdeki DINO tüm 70 özgün çizimle eğitildiği için eski DINO sonuçları bu tutulan test bölümüyle adil bir karşılaştırma değildir.",
        "",
        "Eğitim: 49 özgün insan çizimi + 120 sentetik görüntü. Doğrulama: 7 insan + 24 sentetik. Test: 14 insan + 30 sentetik. Ayrıca eğitime alınmayan 20 birleşik U/L/S şekliyle stres testi yapıldı. Aynı kaynak farklı bölümlerde bulunmuyor; yazar bazında ayrım yok. İki WhatsApp fotoğrafı geliştirme örneğidir, bağımsız başarı kanıtı değildir.",
        "",
        "YOLOv8n ve YOLO11n COCO başlangıcından 20 dönem; U-Net rastgele başlangıçtan 20 dönem; MobileNet V3 tabanlı Faster R-CNN, omurgası dondurularak 20 dönem eğitildi. Mask2Former Swin-Tiny, ADE20K başlangıcından, omurgası dondurularak 5 dönem yalnızca 120 yoğun etiketli sentetik görüntüyle eğitildi. Mask2Former için veri ve güncelleme bütçesi farklıdır; bu pilot mimarilerin genel sıralaması olarak okunamaz.",
        "",
        "Kapı kutuları yaklaşık elle çizilmiş boşluk uçlarından türetildi; ayrıca doğrulanmış nesne kutuları değildir. Kapı eşleştirmesi IoU ≥ 0.5 ve birebir en iyi atama ile yapılır. Güven eşikleri yalnız doğrulamada seçilir. Duvar/kapı maskeleri birleştirilir, kapılar geçici kapatılır ve dış arka planı dışlayan bağlı alanlar oda sayılır. Arada ayırıcı olmayan alanlar tek odadır. Açık geçişlerle bağlanan eski oda/koridor referansları birleştirildi.",
        "",
        "## İnsan çizimleri: tutulan test",
        "",
        "14 test çiziminde toplam 16 kapı etiketi var. Oda referansı olmayan iki görüntü oda değerlendirmesinden çıkarıldı; oda sayısı başarısının paydası 12. Küçük ve yaklaşık etiketli bir testtir.",
        "",
        "| Akış | Kapı P % | Kapı R % | Kapı F1 % | Oda F1 % | Doğru oda sayısı |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method, value in result["test"]["human"].items():
        d = value["doors"]
        r = value["regions"]
        n = value["room_labelled_images"]
        correct = round(value["room_count_accuracy"] * n)
        lines.append(
            f"| {names[method]} | {pct(d['precision'])} | {pct(d['recall'])} | {pct(d['f1'])} | {pct(r['f1'])} | {correct}/{n} |"
        )
    lines += [
        "",
        "Oda F1, referans oda çokgenleriyle alan IoU ≥ 0.5 eşleşmesini ölçer. Yalnız doğru sayıyı bulmak, doğru konum/şekli bulmak anlamına gelmez. CV kontrolünde kapı dedektörü kullanılmaz; bu bir ayırma kontrolüdür.",
        "",
        "## Yeni fotoğraflar",
        "",
        "| Akış | L: oda/kapı (beklenen 4/3) | U: oda/kapı (beklenen 2/1) |",
        "| --- | ---: | ---: |",
    ]
    for method in result["test"]["human"]:
        photos = {r["id"]: r for r in result["development_photos"] if r["method"] == method}
        a, b = photos["photo_L"], photos["photo_U"]
        lines.append(f"| {names[method]} | {a['rooms']}/{a['doors']} | {b['rooms']}/{b['doors']} |")
    for kind, title in [
        ("synthetic", "Ayrı sentetik test"),
        ("stress", "Eğitim dışı birleşik şekiller: stres testi"),
    ]:
        lines += [
            "",
            f"## {title}",
            "",
            "| Akış | Kapı F1 % | Oda F1 % | Doğru oda sayısı |",
            "| --- | ---: | ---: | ---: |",
        ]
        for method, value in result["test"][kind].items():
            n = value["room_labelled_images"]
            correct = round(value["room_count_accuracy"] * n)
            lines.append(
                f"| {names[method]} | {pct(value['doors']['f1'])} | {pct(value['regions']['f1'])} | {correct}/{n} |"
            )
    lines += [
        "",
        "## Yorum ve sonraki adım",
        "",
        "Bu pilotta insan testindeki en yüksek kapı F1 YOLO11n ile %74,1 oldu (10 doğru, 1 fazla, 6 kaçan kapı). YOLOv8n %68,6 verdi (12 doğru, 7 fazla, 4 kaçan). Gönderilen U fotoğrafında doğru 2 oda/1 kapı sonucunu veren bağımsız akış CV duvar + YOLOv8n oldu; görsel sınırlar da kontrol edildi. Buna karşılık L fotoğrafındaki üç küçük kapıyı yeni dedektörlerin hepsi kaçırdı. Bu örnekler modele ve görüntü ölçeğine bağlı hata bulunduğunu gösterir; yalnız model adını değiştirmenin yeterli olduğunu desteklemez.",
        "",
        "U-Net duvar maskesi, insan testindeki bilinen yaklaşık etiketli piksellerde %91,7 F1 verdi. Bu yoğun insan maskesiyle ölçülmüş bir F1 değildir. Buna rağmen kapı kapatma maskesinden nesne çıkarımı %1,7 kapı F1 ile kararsızdı. Aynı YOLO11n kapıları kullanıldığında oda çokgeni F1, CV duvarla %14,6 iken U-Net duvarla %60,0 oldu; doğru oda sayısı ikisinde de 4/12 kaldı. Piksel başarısı ile doğru oda topolojisi farklı ölçülerdir.",
        "",
        "Kapı tespiti ile oda topolojisi ayrı değerlendirilmelidir. Kapı F1 yüksekken oda sayısının düşük kalması, dedektörden sonra duvar maskesi bütünlüğü, kapının duvara oturtulması veya çözünürlük sorunu olduğuna işaret eder. Bu deneyler DINO’nun patch yapısının tek başına hata sebebi olduğunu kanıtlamaz. U-Net ve Mask2Former için daha uzun ve eşit koşullu eğitim, yoğun insan maskeleri ve yeni yazarlardan ayrılmış test gerekir. Hiçbir deney modeli canlı sisteme atanmadı.",
        "",
        "Duvar segmentasyonu için [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k) ve mimari semboller için [FloorPlanCAD](https://floorplancad.github.io/) başlangıç veri kaynakları olabilir. Çentik biçimindeki kapı işaretlerini aynı biçimde etiketleyen kendi verimiz yine gerekir; bu dış veri kümeleri bu deneye indirilmedi veya dahil edilmedi.",
        "",
        "Model kaynakları: [YOLO11](https://docs.ultralytics.com/models/yolo11/), [Faster R-CNN](https://docs.pytorch.org/vision/stable/models/faster_rcnn.html), [Mask2Former](https://huggingface.co/docs/transformers/model_doc/mask2former).",
        "",
        "Yeniden çalıştırma kaynakları: `Scripts/independent_boundary_experiment.py`, `Scripts/independent_boundary_stress_data.py`, `Scripts/independent_mask2former_experiment.py`. Protokoller, eğitim geçmişleri, seçilen ağırlıklar, görüntü başına sonuçlar ve ham rapor bu klasördedir.",
    ]
    (OUT / "report_tr.md").write_text("\n".join(lines) + "\n")
    destination = ROOT / "Docs/independent_boundary_experiments_2026_11_09.md"
    destination.write_text("\n".join(lines) + "\n")
    with (OUT / "results.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "cohort",
                "method",
                "door_precision",
                "door_recall",
                "door_f1",
                "region_f1",
                "room_count_accuracy",
                "room_labelled_images",
            ]
        )
        for kind, methods in result["test"].items():
            for method, value in methods.items():
                writer.writerow(
                    [
                        kind,
                        method,
                        value["doors"]["precision"],
                        value["doors"]["recall"],
                        value["doors"]["f1"],
                        value["regions"]["f1"],
                        value["room_count_accuracy"],
                        value["room_labelled_images"],
                    ]
                )
    methods = [
        "cv+yolov8n",
        "cv+yolo11n",
        "cv+fasterrcnn",
        "unet_only",
        "unet+yolo11n",
        "mask2former_only",
    ]
    methods = [m for m in methods if m in result["test"]["human"]]
    tile = 350
    canvas = Image.new("RGB", (tile * len(methods), 390 * 2), "#f8f8f4")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for row, identifier in enumerate(["photo_L", "photo_U"]):
        for col, method in enumerate(methods):
            figure = (
                Image.open(OUT / "figures" / f"{identifier}_{method.replace('+','_')}.png")
                .convert("RGB")
                .resize((tile, tile))
            )
            canvas.paste(figure, (col * tile, row * 390 + 40))
            record = next(
                r
                for r in result["development_photos"]
                if r["id"] == identifier and r["method"] == method
            )
            draw.text((col * tile + 6, row * 390 + 4), names[method], font=font, fill="#172b38")
            draw.text(
                (col * tile + 6, row * 390 + 23),
                f"{identifier}: {record['rooms']} oda, {record['doors']} kapi",
                font=font,
                fill="#172b38",
            )
    canvas.save(OUT / "comparison.png")
    hashes = {}
    for path in [
        OUT / "unet-best.pt",
        OUT / "fasterrcnn-best.pt",
        OUT / "training/yolov8n/weights/best.pt",
        OUT / "training/yolo11n/weights/best.pt",
    ] + list((OUT / "mask2former-best").glob("*.safetensors")):
        if path.exists():
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    sources = {}
    for filename in [
        "independent_boundary_experiment.py",
        "independent_mask2former_experiment.py",
        "independent_boundary_stress_data.py",
        "report_independent_boundaries.py",
    ]:
        path = ROOT / "Scripts" / filename
        sources[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        target = OUT / "source_snapshot" / filename
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
    packages = {
        name: importlib.metadata.version(name)
        for name in [
            "torch",
            "torchvision",
            "ultralytics",
            "transformers",
            "opencv-python",
            "numpy",
            "shapely",
            "scipy",
        ]
    }
    write(
        OUT / "provenance.json",
        {
            "weights_sha256": hashes,
            "source_snapshot_sha256": sources,
            "packages": packages,
            "production_checkpoint_sha256": hashlib.sha256(
                (
                    ROOT / "SketchPipeline/shape_authoring/models/shape-dinov2-all-data-v1.pt"
                ).read_bytes()
            ).hexdigest(),
        },
    )
    print(destination)


if __name__ == "__main__":
    run()
