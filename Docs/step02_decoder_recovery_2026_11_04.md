# Decoder 2.4: destekli bölge kurtarma ve yeniden test

Tarih: 4 Kasım 2026. İstenen decoder değişikliği uygulandı ve yeniden test edildi.
DINOv2 encoder ve eğitilmiş segmentation/keypoint decoder ağırlıkları aynı kaldı.
Yeni eğitim veya checkpoint seçimi yapılmadı.

**Sonuç:** Eski test grubunda doğru bölgeler **19/26 → 24/26**, opening konumları
**4/20 → 8/20**, owner referansıyla doğrulanabilen doğru bağlantılar **4/19 → 7/19**.
Sentetik kontrolde doğru bağlı opening **91/160 → 133/160**. Buna karşılık eski
testte fazla bölgeler 2'den 4'e çıktı ve sentetikte bir yanlış bağlantı oluştu.
İnsan bağlantı recall hedefi hâlâ karşılanmadı; DINO adayı deneysel/review-required
kalıyor, global varsayılan model değiştirilmedi.

## Uygulanan değişiklik

Yeni kod `region_recovery.py`; parametreler `region_recovery.v1.json`, sürüm
`shape-region-recovery/1.1`. `decoder_refined.decode` varsayılan olarak bu yolu
kullanıyor ve `shape-decoder/2.4` kaydediyor. Eski `decoder.py` değiştirilmedi;
baseline profil aynı, eski refined bölge yolu `region_policy='legacy'` ile
karşılaştırma kontrolü olarak çalışabiliyor.

1. **Ortak sınırları birlikte uzlaştırma.** Yakın karşılıklı sınırlar, ortak duvar
   veya destekli corridor/interface kanıtıyla gruplandırılıyor. Bir T junction'a
   bağlı sınırlar tek koordinata taşınıyor; gözlenen ink üzerinden eksen fit'i
   yapılıyor. Kayma hem görüntü kenarına hem bölge boyutuna göre sınırlı. Derin,
   desteksiz veya çözülemeyen örtüşmeler hâlâ reddediliyor; yalnızca doğru bölgeyi
   tamamen silmeye dayanan eski dar snap davranışı iyileştirildi.
2. **Küçük/parçalı bölgelerde destekli ikinci kontrol.** Eski alan/doluluk
   koşuluna takılan her component kabul edilmiyor. Minimum alan/boyut, model
   yanıtı, doluluk ve gerçek görüntüde uzun duvar desteği birlikte gerekiyor.
   Koridorda iki paralel uzun duvar; odada en az üç destekli kenar ve kalan
   kenarda da asgari destek aranıyor. Sahte model wall yanıtı, boş görüntü veya
   sayı yazısı tek başına bu desteği sağlamıyor.
3. **Yuvarlak endpoint haritalarının yönü.** DINO'nun endpoint başlığı yuvarlak
   yanıtlar üretebiliyor. Eski maskenin en/boy oranından tick yönü çıkarma işlemi
   bu durumda yanlış yön seçebiliyordu. Yeni mantıksal sınır kapanışı, endpoint
   çiftinin hizasını ve gözlenen paired tick + collinear wall + clear gap kanıtını
   kullanıyor. Böylece bir kapı boşluğunda birleşmiş iki region ayrılabiliyor.
   Bu kapanış fiziksel duvar veya kabul edilmiş passage kaydı oluşturmuyor.

Fiziksel opening algılamasındaki `ink_evidence`, `fit_axis`, `tick_evidence`,
`opening_candidates` ve diğer mevcut yardımcıların AST'si eski kaynakla birebir
aynı. Opening kanıt eşikleri değiştirilmedi. Region kurtarma, gap-only veya tek
tick'i kapıya dönüştürmek için kullanılmıyor. Sayı/OCR okuması ve fiziksel ölçü
kullanımı eklenmedi; authoring acceptance pending kalıyor.

## Geliştirme ve karşılaştırma protokolü

Eski kod/config/manifest `decoder_recovery/v1/before/` altında donduruldu.
İlk aday (`shape-region-recovery/1.0`) yalnızca 5 validation + 6 sentetik kontrolde
ölçüldü. Region recall yükselse de sentetikte bir yanlış owner oluştu. Yuvarlak
endpoint yönü ve destekli corridor uçlarının ortak sınırı ele alışı düzeltilerek
1.1 adayı yine aynı küçük kontrolde ölçüldü: 18/18 sentetik region, doğru bağlı
15/16 opening ve sıfır yanlış bağlantı.

Ardından 1.1 adayı 50 insan ve 60 sentetik örnekte karşılaştırıldı. Son tekrar
yalnızca gerçek decoder süresini kaydetti; önceki geniş karşılaştırmayla bütün
geometri/topoloji metrikleri aynı kaldı. İlk aday ve ara sonuçlar silinmedi.

İki kol da aynı kaydedilmiş native DINO maskelerini kullanıyor. Her iki tahmin
referanslar okunmadan önce kaydediliyor. Eski kolun region/opening geometrisi
**110 örneğin tamamında** önceki model raporuyla birebir eşleşiyor. Model
değişmediği için kazanım yeni model eğitimi olarak raporlanmıyor.

Bu planlar önceki çalışmalarda incelenmiş development verisi. Ayrı tutulan eski
train/validation/test rolleri kaydediliyor; bu yeni kör test veya yeni-yazar
başarısı değil. İnsan etiketleri ve owner atamaları yaklaşık; bağımsız exact
topology ve gerçek kullanıcı düzeltme süresi hâlâ ölçülmedi.

## Sonuçlar

| Küme / decoder | Region doğru / öneri / referans | Opening konumu doğru / öneri / referans | Doğru bağlı opening / öneri / owner referansı |
| --- | ---: | ---: | ---: |
| Train 35, eski 2.3 | 78 / 85 / 99 | 32 / 32 / 85 | 31 / 31 / 78 |
| Train 35, yeni 2.4 | 97 / 104 / 99 | 59 / 61 / 85 | 58 / 60 / 78 |
| Validation 5, eski | 15 / 17 / 19 | 9 / 9 / 14 | 9 / 9 / 14 |
| Validation 5, yeni | 17 / 19 / 19 | 11 / 11 / 14 | 11 / 11 / 14 |
| Eski test 10, eski | 19 / 21 / 26 | 4 / 4 / 20 | 4 / 4 / 19 |
| Eski test 10, yeni | 24 / 28 / 26 | 8 / 8 / 20 | 7 / 7 / 19 |
| Sentetik 60, eski | 151 / 181 / 180 | 91 / 91 / 160 | 91 / 91 / 160 |
| Sentetik 60, yeni | 174 / 204 / 180 | 134 / 134 / 160 | 133 / 134 / 160 |

İnsan region metrikleri yalnızca region referansı olan planları kapsıyor:
train 29/35, validation 5/5, eski test 8/10. Owner referansı bilinmeyen opening'ler
bağlantı metriğinden çıkarılıyor. Eski testte Data 5'te bulunan bir opening'in
konumu eşleşiyor, fakat owner referansı yok; bu nedenle 8 konum / 7 doğrulanabilen
bağlantı ayrımı var. Sekizinin tamamının owner'ı doğrulandı denmiyor.

Eski test region recall **%73.1 → %92.3**, precision **%90.5 → %85.7**, F1
**0.809 → 0.889**. Doğru bağlı opening recall **%21.1 → %36.8**; hedef %50.
Yeni decoder daha çok doğru bölge bulsa da iki ek fazla bölge üretiyor.

Sentetik doğru bağlı opening recall **%56.9 → %83.1**, precision
**%100 → %99.25**. Exact topology **20/60 → 30/60**. `2001_stray` örneğinde bir
opening'in konumu doğru, bağlı bölge yanlış: yanlış/duplicate bağlantı sayısı
0'dan 1'e çıktı. Bu hata saklanmadı ve otomasyonun hazır olduğu iddia edilmiyor.

Train'de iki konum eşleşmeyen opening Data 38 ve Data 42'de. İnsan referansları
yaklaşık olduğundan bunlar bağımsız adjudication ile teyit edilmiş exact-topology
hata sayısı değil; kayıtlı referansa göre fazla önerilerdir. Düzeltme arayüzünde
review gerekliliği korunuyor.

`regression-inventory.json`, önceki doğru region ve doğru owner'lı opening
referanslarını tek tek karşılaştırıyor. **Hiçbir önceki doğru referans kaybolmadı.**
Yeni doğru bağlı opening'ler: train +27, validation +2, eski test +3, sentetik +42.
Bu olumlu sonuç, yeni false positive'lerin olmadığı anlamına gelmiyor; yukarıda
fazla bölgeler ve yanlış bağlantılar ayrıca raporlandı.

## Teşhisteki eksikler ne oldu?

Decoder kapılarına takılan 9 validation/eski test bölgesinin **7'si geri geldi**:
Data 18 rC, 23 rB, 25 rB, 31 rB, 39 rB, 43 cH, 48 cV2. Data 47 cH ve Data 48
cV1 hâlâ güvenli kurtarma koşullarını geçmiyor. Data 8'deki yanlış tür/ayrıştırma
sorunu olan iki region da çözülmedi.

Region'ların geri gelmesi bütün kapıların otomatik bulunmasını sağlamadı.
Örneğin Data 23'te iki oda korunuyor, fakat opening kanıtı henüz geçmiyor. Yeni
worker smoke testi de iki region ve sıfır opening üretti. Modelin görmediği veya
fiziksel kanıtı geçmeyen kapıya sırf iki oda yaklaştı diye bağlantı eklenmedi.

## Testler ve gerçek worker

**143 benzersiz test geçti:** ilgili suite 142, gerçek loopback HTTP/token testi 1.
Dokuz yeni test: dar örtüşmede ortak sınır, T junction ve sıra bağımsızlığı, derin
örtüşme reddi, gerçek paralel duvarla küçük koridor, destekli parçalı oda,
sayı/gürültü reddi, iki yönde yuvarlak endpoint'ler, sahte marker'dan kapı
oluşturmama ve public decoder contract/legacy kontrolü.

Gerçek seçilmiş DINO checkpoint'i `ShapeJobs` worker'ında Data 23 ile tekrar
çalıştırıldı. Native model maskelerinin eski kayda göre maksimum farkı **0.0**;
değişiklik model çıktısından sonra uygulanıyor. Son geometri cached-mask
karşılaştırmasıyla aynı; authoring contract geçti, OCR kapalı, acceptance pending.
Bu kontrol browser veya kullanıcı arayüzü ekran görüntüsü testi değildir.

440 cached karşılaştırma girdisi ve 4.961 Data dosyası değişmedi. DINO decoder ve
backbone ağırlıkları, global varsayılan model lock'u ve eski baseline decoder aynı.
Fiziksel opening fonksiyonları AST ve opening config alanları korundu. Eski
kullanıcı draft'ları ve kaydedilmiş öneriler otomatik overwrite edilmedi.

## Çalıştırma ve çıktı yolları

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.evaluate_region_recovery --study Saved/ShapeFirst/dinov2/v1 --output Saved/ShapeFirst/dinov2/decoder_recovery/new-run
Saved/Training/v1/python/bin/python -m unittest SketchPipeline.tests.test_shape_region_recovery -v
```

`Saved/ShapeFirst/dinov2/decoder_recovery/v2/`:

- `final/report.json`, `final/gallery.html`: nihai 110 örnek karşılaştırması.
- `final/freeze.json`, `final/source_snapshot/`: kullanılan kod, policy ve input hash'leri.
- `regression-inventory.json`: korunan/yeni/kaybolan doğru referansların dökümü.
- `worker-smoke.json`: gerçek model + yeni decoder entegrasyonu.
- `verification.json`, `tests.log`, `http-test.log`, `recovery-tests.log`: kontroller.
- `Data18-before-after.png`: aynı model maskeleriyle eski/yeni geometri örneği.

`dinov2-candidate.lock.json` güncel decoder sürümünü ve karşılaştırma yolunu
gösteriyor; ilk eğitimde başarısız olan guard ile güncel decoder guard'ları ayrı.
Checkpoint SHA aynı: `e2376f20f05d54701ee2b796b46a1ac8798cdf0746a680237052d414d3353201`.

Mevcut deney arayüzündeki yeni analiz worker'ları güncel decoder kodunu yükler:
http://127.0.0.1:8768/ . Eski kaydedilmiş bir job kendiliğinden yeniden hesaplanmaz;
yeni çizim yüklemek veya manuel edit içermeyen job'da retry gerekir. Browser bu
tur açılmadı; yukarıdaki doğrulama kod, cached tahminler ve yerel worker üzerindedir.
