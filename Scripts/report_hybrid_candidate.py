import csv
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.train_hybrid_candidate import OUT, BASE, write, sha


def run():
    report = json.loads((OUT / "report.json").read_text())
    protocol = json.loads((OUT / "protocol.json").read_text())
    baseline = json.loads((BASE / "report.json").read_text())["test"]["human"]["unet+yolo11n"]
    selection = json.loads((OUT / "validation-selection.json").read_text())["selected"]
    percent = lambda x: f"{x*100:.1f}"
    lines = [
        "# U-Net duvar + YOLO11n kapı adayı — 9 Kasım 2026",
        "",
        "İki ayrı ağ devam eğitimiyle bir aday pakette birleştirildi. U-Net yalnızca duvar maskesi üretir; YOLO11n kapı çentiklerini bulur. Kapı konumları duvar maskesinde geçici kapatılır ve bağlı iç alanlar oda sayılır. Ayırıcısız geniş/dar alanlar tek odadır. Koridor sınıfı yoktur.",
        "",
        "Eğitim: 49 özgün insan çizimi, 120 önceki sentetik plan ve yeni tohumlarla üretilen 120 birleşik U/L/S planı. Doğrulama: 7 insan ve 48 sentetik plan. 14 insan çizimi, 30 eski sentetik plan ve önceki 20 stres örneği eğitime alınmadı. Test çizimleri önceki deneylerde incelendiği için sonuçlar yeni bir kör veya yazar ayrımlı test değildir.",
        "",
        "Görüntü hazırlama 1024 piksel; U-Net eğitim kesitleri 512 piksel; YOLO11n eğitimi 640 piksel. Kapı çıkarımı tam görüntü ve örtüşen 640 piksel kesitlerde yapılır, yinelenen kutular NMS ile birleştirilir. Kesit kenarında yarım kalan işaretler elenir. Eğitimde kısa çizgi silmeleri, kontrast/gölge, bulanıklık ve gürültü kullanıldı. İnsan piksel etiketleri yaklaşık izlerdir; belirsiz pikseller kayıptan dışlanır.",
        "",
        f"U-Net ek eğitim: {report['wall_epochs_run']} dönem; seçilen ağırlığın dönemi {report['selected_wall_epoch']}. YOLO11n ek eğitim: {report['door_epochs_run']} dönem. Başlangıç ağırlıkları önceki bağımsız deneyin yalnız eğitim bölümüyle öğrendiği modellerdir; DINO kullanılmadı.",
        "",
        "Son model çifti, duvar eşiği, kapı eşiği ve kapatma çekirdeği yalnız insan doğrulama bölümünde seçildi. Amaç: oda çokgeni F1 + 0,25 × doğru oda sayısı oranı + 0,25 × kapı F1. Testler ve iki WhatsApp fotoğrafı seçimde kullanılmadı.",
        "",
        "## Eğitim dışında tutulan örnekler",
        "",
        "| Bölüm | Çizim | Kapı P % | Kapı R % | Kapı F1 % | Oda F1 % | Doğru oda sayısı |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for kind, label in [
        ("human", "İnsan"),
        ("synthetic", "Sentetik"),
        ("stress", "Birleşik şekil stresi"),
    ]:
        row = report["test"][kind]
        door = row["doors"]
        room = row["rooms"]
        lines.append(
            f"| {label} | {row['images']} | {percent(door['precision'])} | {percent(door['recall'])} | {percent(door['f1'])} | {percent(room['f1'])} | {row['exact_room_count']}/{row['room_labelled_images']} |"
        )
    lines += [
        "",
        "İnsan bölümünde kapı etiketi 16 adettir. İki çizimde oda referansı yoktur; oda değerlendirmesi 12 çizimde yapılır. Kapı ve oda eşleştirmeleri IoU ≥ 0,5 ile birebir yapılır. Oda sayısını doğru bulmak ile oda sınırlarını doğru çıkarmak ayrı ölçülerdir.",
        "",
        "## Önceki pilotla aynı insan çizimlerinde karşılaştırma",
        "",
        "| Sürüm | Kapı F1 % | Oda F1 % | Doğru oda sayısı |",
        "| --- | ---: | ---: | ---: |",
        f"| Önceki 512 piksel pilot | {percent(baseline['doors']['f1'])} | {percent(baseline['regions']['f1'])} | {round(baseline['room_count_accuracy']*baseline['room_labelled_images'])}/{baseline['room_labelled_images']} |",
    ]
    row = report["test"]["human"]
    lines.append(
        f"| Yeni devam eğitimi ve 1024 piksel akış | {percent(row['doors']['f1'])} | {percent(row['rooms']['f1'])} | {row['exact_room_count']}/{row['room_labelled_images']} |"
    )
    lines += [
        "",
        "Veri, eğitim süresi, çözünürlük ve çıkarım yöntemi birlikte değişti. Bu karşılaştırma tek bir mimari veya tek bir değişikliğin etkisini ayırmaz. Örnek sayısı küçüktür; bu verilerle genel başarı garantisi verilemez.",
        "",
        "## Geliştirme fotoğrafları",
        "",
        "| Fotoğraf | Beklenen oda/kapı | Aday oda/kapı |",
        "| --- | ---: | ---: |",
    ]
    for photo in report["development_photos"]:
        expected = "4/3" if photo["case"] == "L" else "2/1"
        lines.append(
            f"| {photo['case']} | {expected} | {photo['room_count']}/{photo['door_count']} |"
        )
    lines += [
        "",
        "Bu fotoğraflar eğitim ve model seçiminde yoktur; önceki geliştirme çalışmalarında incelendikleri için bağımsız yeni test olarak sayılmadı.",
        "",
        "## Paket ve kullanım",
        "",
        f"Seçilen parametreler: `{json.dumps(report['parameters'],ensure_ascii=False)}`. Model paketi: `Saved/Experiments/hybrid_unet_yolo11_v1/candidate/model-lock.json`; duvar ve kapı ağırlıkları aynı klasördedir. Dosya sağlama toplamları yüklemede kontrol edilir. Çalışan uygulamanın seçili DINO modeli değiştirilmedi.",
        "",
        "```sh",
        "Saved/Experiments/independent_boundaries_v1/python/bin/python Scripts/hybrid_candidate_inference.py \\",
        "  --model-lock Saved/Experiments/hybrid_unet_yolo11_v1/candidate/model-lock.json \\",
        '  --image "/tam/yol/cizim.jpeg" --output Saved/Experiments/yeni_aday_denemesi',
        "```",
        "",
        "Çıktı JSON, duvar maskesi, geçici kapatılmış sınırlar ve görüntü üzerinde oda/kapı çizimini içerir. Bu aday algılama paketidir; uygulamanın düzenleme, ölçülendirme ve Unreal dışa aktarımına henüz bağlanmadı. Elle inceleme gerekir.",
        "",
        "Protokol, eğitim geçmişleri, yalnız doğrulama ile yapılan seçim listesi, görüntü başına test sonuçları, kaynak kod özeti ve paket sürümleri aynı deney klasöründedir.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "report_tr.md").write_text(text)
    destination = ROOT / "Docs/hybrid_unet_yolo11_training_2026_11_09.md"
    destination.write_text(text)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    history = json.loads((OUT / "wall-history.json").read_text())
    door_rows = list(csv.DictReader((OUT / "door-training/yolo11n/results.csv").open()))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for field, label in [("training_loss", "Train"), ("validation_loss", "Validation")]:
        axes[0].plot([r["epoch"] for r in history], [r[field] for r in history], label=label)
    axes[0].set(title="Wall U-Net", xlabel="Additional epoch", ylabel="Masked loss")
    axes[0].legend()
    for field, label in [("metrics/mAP50(B)", "mAP50"), ("metrics/mAP50-95(B)", "mAP50-95")]:
        axes[1].plot(
            [float(r["epoch"]) for r in door_rows],
            [float(r[field]) for r in door_rows],
            label=label,
        )
    axes[1].set(title="YOLO11n validation", xlabel="Additional epoch", ylim=(0, 1))
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(OUT / "training-curves.png", dpi=160)
    plt.close(fig)
    files = [
        "train_hybrid_candidate.py",
        "hybrid_candidate_inference.py",
        "evaluate_hybrid_candidate.py",
        "report_hybrid_candidate.py",
        "independent_boundary_stress_data.py",
        "independent_boundary_experiment.py",
    ]
    source_hashes = {}
    for filename in files:
        source = ROOT / "Scripts" / filename
        target = OUT / "source_snapshot" / filename
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[filename] = sha(source)
    packages = {
        name: importlib.metadata.version(name)
        for name in [
            "torch",
            "torchvision",
            "ultralytics",
            "numpy",
            "opencv-python",
            "shapely",
            "scipy",
        ]
    }
    write(
        OUT / "provenance.json",
        {
            "sources_sha256": source_hashes,
            "packages": packages,
            "selected_checkpoints": {
                key: sha(OUT / "candidate" / (key + ".pt")) for key in ["wall", "door"]
            },
            "production_checkpoint_sha256": sha(
                ROOT / "SketchPipeline/shape_authoring/models/shape-dinov2-all-data-v1.pt"
            ),
            "production_promoted": False,
            "test_scope": report["test_scope"],
        },
    )
    print(destination)


if __name__ == "__main__":
    run()
