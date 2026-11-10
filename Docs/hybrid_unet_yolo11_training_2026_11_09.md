# U-Net duvar + YOLO11n kapı adayı — 9 Kasım 2026

İki ayrı ağ devam eğitimiyle bir aday pakette birleştirildi. U-Net yalnızca duvar maskesi üretir; YOLO11n kapı çentiklerini bulur. Kapı konumları duvar maskesinde geçici kapatılır ve bağlı iç alanlar oda sayılır. Ayırıcısız geniş/dar alanlar tek odadır. Koridor sınıfı yoktur.

Eğitim: 49 özgün insan çizimi, 120 önceki sentetik plan ve yeni tohumlarla üretilen 120 birleşik U/L/S planı. Doğrulama: 7 insan ve 48 sentetik plan. 14 insan çizimi, 30 eski sentetik plan ve önceki 20 stres örneği eğitime alınmadı. Test çizimleri önceki deneylerde incelendiği için sonuçlar yeni bir kör veya yazar ayrımlı test değildir.

Görüntü hazırlama 1024 piksel; U-Net eğitim kesitleri 512 piksel; YOLO11n eğitimi 640 piksel. Kapı çıkarımı tam görüntü ve örtüşen 640 piksel kesitlerde yapılır, yinelenen kutular NMS ile birleştirilir. Kesit kenarında yarım kalan işaretler elenir. Eğitimde kısa çizgi silmeleri, kontrast/gölge, bulanıklık ve gürültü kullanıldı. İnsan piksel etiketleri yaklaşık izlerdir; belirsiz pikseller kayıptan dışlanır.

U-Net ek eğitim: 36 dönem; seçilen ağırlığın dönemi 36. YOLO11n ek eğitim: 28 dönem. Başlangıç ağırlıkları önceki bağımsız deneyin yalnız eğitim bölümüyle öğrendiği modellerdir; DINO kullanılmadı.

Son model çifti, duvar eşiği, kapı eşiği ve kapatma çekirdeği yalnız insan doğrulama bölümünde seçildi. Amaç: oda çokgeni F1 + 0,25 × doğru oda sayısı oranı + 0,25 × kapı F1. Testler ve iki WhatsApp fotoğrafı seçimde kullanılmadı.

## Eğitim dışında tutulan örnekler

| Bölüm | Çizim | Kapı P % | Kapı R % | Kapı F1 % | Oda F1 % | Doğru oda sayısı |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| İnsan | 14 | 100.0 | 81.2 | 89.7 | 82.4 | 7/12 |
| Sentetik | 30 | 95.6 | 100.0 | 97.7 | 98.6 | 28/30 |
| Birleşik şekil stresi | 20 | 100.0 | 100.0 | 100.0 | 100.0 | 20/20 |

İnsan bölümünde kapı etiketi 16 adettir. İki çizimde oda referansı yoktur; oda değerlendirmesi 12 çizimde yapılır. Kapı ve oda eşleştirmeleri IoU ≥ 0,5 ile birebir yapılır. Oda sayısını doğru bulmak ile oda sınırlarını doğru çıkarmak ayrı ölçülerdir.

## Önceki pilotla aynı insan çizimlerinde karşılaştırma

| Sürüm | Kapı F1 % | Oda F1 % | Doğru oda sayısı |
| --- | ---: | ---: | ---: |
| Önceki 512 piksel pilot | 74.1 | 60.0 | 4/12 |
| Yeni devam eğitimi ve 1024 piksel akış | 89.7 | 82.4 | 7/12 |

Veri, eğitim süresi, çözünürlük ve çıkarım yöntemi birlikte değişti. Bu karşılaştırma tek bir mimari veya tek bir değişikliğin etkisini ayırmaz. Örnek sayısı küçüktür; bu verilerle genel başarı garantisi verilemez.

## Geliştirme fotoğrafları

| Fotoğraf | Beklenen oda/kapı | Aday oda/kapı |
| --- | ---: | ---: |
| L | 4/3 | 4/3 |
| U | 2/1 | 2/1 |

Bu fotoğraflar eğitim ve model seçiminde yoktur; önceki geliştirme çalışmalarında incelendikleri için bağımsız yeni test olarak sayılmadı.

## Paket ve kullanım

Seçilen parametreler: `{"wall_threshold": 0.35, "door_threshold": 0.5, "closing_kernel": 5}`. Model paketi: `Saved/Experiments/hybrid_unet_yolo11_v1/candidate/model-lock.json`; duvar ve kapı ağırlıkları aynı klasördedir. Dosya sağlama toplamları yüklemede kontrol edilir. Çalışan uygulamanın seçili DINO modeli değiştirilmedi.

```sh
Saved/Experiments/independent_boundaries_v1/python/bin/python Scripts/hybrid_candidate_inference.py \
  --model-lock Saved/Experiments/hybrid_unet_yolo11_v1/candidate/model-lock.json \
  --image "/tam/yol/cizim.jpeg" --output Saved/Experiments/yeni_aday_denemesi
```

Çıktı JSON, duvar maskesi, geçici kapatılmış sınırlar ve görüntü üzerinde oda/kapı çizimini içerir. Bu aday algılama paketidir; uygulamanın düzenleme, ölçülendirme ve Unreal dışa aktarımına henüz bağlanmadı. Elle inceleme gerekir.

Protokol, eğitim geçmişleri, yalnız doğrulama ile yapılan seçim listesi, görüntü başına test sonuçları, kaynak kod özeti ve paket sürümleri aynı deney klasöründedir.
