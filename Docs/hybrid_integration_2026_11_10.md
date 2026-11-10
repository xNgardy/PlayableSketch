# U-Net + YOLO11n ana uygulama entegrasyonu — 10 Kasım 2026

Ana çalışma alanı ve iki başlatıcı artık `workspace-model.lock.json` üzerinden `hybrid` profilini kullanıyor. U-Net duvar maskesini, YOLO11n kapı işaretlerini buluyor; kapılar geçici kapatılıp bağlı iç alanlar oda oluşturuyor. Ayırıcı olmayan U/L bağlantıları tek oda kalıyor. Yeni çıkarımda koridor sınıfı üretilmiyor.

Modeller deney klasöründen bağımsız olarak `SketchPipeline/shape_authoring/models/hybrid-unet-yolo11-v1/` altında. Başlatıcı `Saved/Runtime/hybrid-v1/python/bin/python` ortamını kullanıyor. Paket ve iki ağırlığın SHA-256 değerleri yüklemeden önce doğrulanıyor. Önceki DINO kilidi/ağırlıkları ve 12 mevcut iş korundu; geçmiş işler kendiliğinden yeniden hesaplanmadı. Yeni sonuçlar ayrı işler olarak eklendi.

Geometri aktarımı küçük girintileri koruyor, kapı kanıtı olan komşu sınırları hizalıyor ve çakışan dik açılı sınır tahminlerini model maskesi desteğine göre ortak bir ızgarada ayırıyor. Şekil örtüşmesi %78 altına düşerse elle düzeltme istiyor. Sinir ağı başarısızlığında eski modele veya ham çizgi çözümleyiciye sessiz geçiş yapılmıyor.

| Fotoğraf | Oda | Kapı | Düzenleme ve ölçülendirme | Geometri dışa aktarımı |
|---|---:|---:|---|---|
| L | 4 | 3 | Geçti | Geçti |
| U | 2 | 1 | Geçti | Geçti |

İki fotoğraf gerçek modellerle, geçici ShapeJobs işlerinde düzenle-kaydet, ölçülendir, onayla, canonical doğrula ve ZIP dışa aktar adımlarından geçti. Canlı uygulamaya ayrıca JPEG olarak yüklendi, Plan görünümü tarayıcıda doğrulandı. Canlı kullanıcı işleri otomatik onaylanmadı veya dışa aktarılmadı. Unreal içinde yeni modele ait oynanış/çarpışma testi yapılmadı.

Testler:

- Mevcut proje ortamında 521 test: 519 geçti, bağımlılık koşullu 2 test atlandı.
- Yeni üretim ortamında eski DINO yeniden işleme dahil 161 şekil testi geçti.
- Hibrit ve model seçimi için üretim ortamında 10 hedefli test geçti.
- İlk ortam denemesinde OpenCV 5, eski Hough çizgi çıktıları ve artırılmış PNG dosyalarının yeniden üretimiyle uyumsuzdu. Üretim ortamı OpenCV 4.13.0.92 ve NumPy 2.4.2 ile sabitlendi; yukarıdaki son kontroller ve fotoğraf çıkarımları bu ortamda yapıldı. İlk başarısız deneme günlüğü de saklandı. OCR bağımlılıkları ayrı mevcut test ortamındadır; hibrit çıkarım OCR kullanmaz.

14 mevcut insan test çizimi ve 2 fotoğrafın üretim denetiminde 15/16 çizim düzenlenebilir topoloji oluşturdu, 13/16 çizim varsayılan ölçülerle hazır plan oluşturdu. Data_39 sınır dönüşümünde şekil kaybı nedeniyle elle düzeltme istiyor. Data_31 ve Data_58 topolojileri oluşuyor ancak varsayılan ölçülerde çözüm uyuşmazlığı var. Bazı diğer çizimlerde ham model odaları birleştiriyor veya kapı ortak sınıra bağlanamıyor; dolayısıyla bu oranlar tespit doğruluğu değildir. Ayrıntılar `production/audit.json` içinde.

Önceki eğitim raporundaki kapı F1 %89,7 ve oda F1 %82,4 ham model/CV hattına aittir; ana uygulamanın uçtan uca doğruluğu olarak kullanılmamalıdır. Bu küçük mevcut test grubu önceki deneylerde görüldü; yeni kör/yeni çizer testi değildir. Plan incelemesi gereklidir.

Kanıtlar `Saved/Integration/hybrid_2026_11_10/` altında: `full-tests.log`, `runtime-shape-tests.log`, `targeted-tests.log`, `production/audit.json`, `roundtrip.json`, `live-verification.json`, `workspace-L.png`, `workspace-U.png`.

Canlı sonuçlar:

- [L planı](http://127.0.0.1:8772/?job=shape_f859a55d997c4ca894ad68dca9082e64)
- [U planı](http://127.0.0.1:8772/?job=shape_57a1d2d9c1a241ed9b925671efd71994)
