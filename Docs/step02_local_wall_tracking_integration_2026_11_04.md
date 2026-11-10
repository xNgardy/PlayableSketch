# B kolu: yerel duvar takibinin DINO akışına entegrasyonu

Tarih: 4 Kasım 2026. Entegrasyon tamamlandı; yeni eğitim veya model indirme yok.

## Etkinleşen davranış

`local_wall_tracking.py`, dört kollu deneyin yalnızca B geometrisini içerir.
Endpoint-pair aday üretimi ve deney çalıştırıcıları runtime bağımlılığı değildir.
Mevcut açıklıklar öncelikle korunur; sınırlı yerel duvar yolu üzerinde fiziksel
boşluk ve paired tick kanıtını geçen ek kapılar önerilir. İnterpolasyon mürekkep
oluşturmaz. Açık geçişler ve region çıkarımı bu değişiklikte geliştirilmedi.

`propose.run`, architecture `shape-dinov2/1.0` ve `refined`/`refined-full`
profillerinde `opening_policy=local-tracking` seçer. Bu yol decoder 2.5 kaydeder.
Global varsayılan U-Net, baseline profil ve diğer refined modeller eski yolu
korur. Doğrudan `decoder_refined.decode` çağrılarında varsayılan `legacy` kalır;
tarihsel değerlendirme araçları sessizce yeni davranışa geçmez.

Yeni politika ve sürüm profile_configuration içine girer; config hash ve proposal
revision kimliğine katılır. Eski kaydedilmiş jobs, manuel editler ve accepted
snapshot'lar otomatik yeniden yazılmaz. Yeni DINO analizi veya uygun retry yeni
worker kodunu kullanır. Deney sunucusunun şu anda açık olduğu varsayılmadı.

## Sonuç ve doğrulama

- 50 insan + 60 sentetik cached örnekte entegre yolun geometrisi frozen B ile
  birebir aynı. Legacy yol frozen kontrolle aynı; 440 cached girdi değişmedi.
- Sonuçlar böylece aynı: eski test 24/26 doğru bölge, 13/20 açıklık konumu,
  owner referansıyla doğrulanabilen 12/19 doğru bağlantı. Data 5 owner'ı bilinmeyen
  bir açıklık olduğundan 13 konumun tamamının attachment'ı doğrulandı denmiyor.
- Validation 11/14, sentetik doğru bağlantı 133/160, sentetik exact topology
  30/60 ve mevcut yanlış bağlantı 1 olarak kaldı. Bu geliştirme verisi sonucu;
  yeni yazar genellemesi veya insan exact topology başarısı değil.
- Gerçek `ShapeJobs` subprocess worker'larında açık DINO checkpoint'i,
  `refined-full` ve normalize_ink=True kullanıldı. Data 23: 1 kapı; Data 25: 2;
  Data 31: 2. Üçü de frozen B geometrisiyle aynı.
- Her gerçek worker'da native maskelerin önceki DINO kaydına göre maksimum farkı
  0.0; OCR kapalı, decoder 2.5, acceptance pending. Ağırlıklar ve global model
  lock'u değişmedi.
- 55 benzersiz test geçti: ilgili ana suite 54 + gerçek loopback HTTP testi 1.
  İlk birleşik çalışmada yalnızca HTTP bind sandbox tarafından engellendi;
  test izinli ayrı çalıştırmada geçti. Nihai ana suite bu tek testi dışarıda
  tutuyor; 55 içinde tekrar sayım yok.
- Yeni 5 entegrasyon testi: frozen B ile fiziksel kapı geometrisi eşitliği,
  incidental kırık reddi, kesintisiz tickli duvar reddi, model_center modunda
  strong-raw fallback açılmaması, iki owner gerekliliği.
- Browser etkileşimi veya arayüz ekran görüntüsü testi yapılmadı.

## Model aday kaydı

`dinov2-candidate.lock.json` decoder 2.5, local-wall-tracking/1.0 ve güncel
karşılaştırma/entegrasyon kanıtlarını kaydeder. Development bağlantı recall eşiği
artık geçiyor. Bağımsız yazar doğrulaması yapılmadığından bu koşul açıkça false
kaydedildi; aday experimental/review-required kalır ve global default'a alınmaz.
Kullanıcı düzeltme süresi de henüz ölçülmedi. Önceki decoder raporu yolu korunur.

## Dosyalar

Kanıtlar `Saved/ShapeFirst/dinov2/tracking_integration/v1/` altında:
`verification.json`, `replay.json`, `input-freeze.json`, `worker-smoke.json`,
`jobs/`, `source_snapshot/`, `tests.log`, `http-test.log`.
Dört kollu deney ve galerisi `Saved/ShapeFirst/dinov2/opening_ablation/v1/full/`
altında korunur; eski raporların üzerine yazılmadı.

Sonraki kalite işi: Data 47/48 eksik koridorları ve açık geçişler. B entegrasyonu
bu sorunları çözülmüş saymaz. Yeni shape-first boyutlandırma/Unreal zinciri de
ayrı açık iş olarak kalır.
