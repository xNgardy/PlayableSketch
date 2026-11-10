# Step 2 — Decoder ölçeği ve kapı/tick düzeltmeleri

> **4 Kasım 2026 ölçüm düzeltmesi:** Önceki insan opening paydası incidental bir kırığı da içeriyordu. Aynı altılıda 18 yerine 17 gerçek geçiş var. Eski deney kayıtları korunuyor; [düzeltme notunu](shape_opening_metric_correction_2026_11_04.md) esas al.

Tarih: 3 Kasım 2026. Önceki [görüntü hazırlama teşhisinin](step02_human_input_diagnosis_2026_11_03.md)
sonrasındaki uygulama ve karşılaştırma turu.

**Teslim:** Ölçeği sabitleyen, yüksek çözünürlüklü kapı kanıtını koruyan yeni decoder
ve bunu gerçek CLI/job/review akışında çalıştıran iki açık deneysel profil eklendi.
Aynı 512 kare girdide insan opening sonucu 1 doğru / 2 öneriden **6 doğru / 6
öneriye** çıktı; toplam referans 18 olduğu için recall hâlâ yalnızca %33,3.
%50 recall hedefi karşılanmadı. Güvenilir insan otomasyonu tamamlandı denmiyor.
Varsayılan profil `baseline` olarak korundu; yeniden eğitim yapılmadı.

## Düzeltilen davranış

`decoder_refined.py` ve `decoder_refined.config.json`, `shape-decoder/2.3`
sözleşmesiyle ayrı bir decoder tanımlıyor. Önceki `decoder.py` değiştirilmedi ve
karşılaştırma için korunuyor.

1. **Ortak geometri koordinatı.** Bölge çıkarımı 256 uzun kenarlı sabit çalışma
   koordinatında yapılır. Native maskeler doğru dönüşümle bu koordinata taşınır;
   dolgu alanındaki model yanıtı kanıt olarak kullanılmaz. Aynı maskenin uniform
   yeniden örneklemesi, bölge geometrisini aynı tolerans içinde korur.
2. **Native opening kanıtı.** Kapı incelemesi yüksek çözünürlüklü görüntü/maskelerde
   yapılır, sonuç mevcut supporting wall üzerine çalışma koordinatında yansıtılır.
   Böylece ince işaretler son geometri için 256 piksele küçültülmüş gri görüntüden
   okunmaya çalışılmaz. Working/native transformları ve ayrı raw maskeler saklanır.
3. **Tick merkezi ve fiziksel destek.** Learned tick yanıtı marker merkezinde
   aranır. Karşılıklı iki endpoint'in her iki tarafında gerçek perpendicular ink ve
   bağlantılı merkez hâlâ gerekir. Semantic yanıt, tek tick'i veya kırık çizgiyi
   tek başına kapıya çeviremez.
4. **Ayrı geometri destek yolu.** `paired_raw` modunda, merkezde model yanıtı zayıf
   olsa da güçlü çift taraflı tick + iki uçta duvar devamlılığı + gerçek boşluk
   ayrıca öneri oluşturabilir. Bu yol `paired_raw_geometry` diye kaydedilir;
   yeni bir AI modeli veya yeniden eğitim başarısı olarak sunulmaz. Region
   önerileri ve open-interface kanıtı mevcut gerçek segmentation modelinden gelir.
5. **Dalgalı duvar ve distractor ink.** Bounded axis fit ve duvar yönündeki uzun
   stroke maskesi kullanılır. Her koyu pikseli doğrudan wall projection'a katmak,
   kapı içine taşan yazılarla açıklığı parçalayabiliyordu. Faint periodic grid
   suppression korunur; raw görüntü değiştirilmez ve ayrıca saklanır.
6. **Yoğun junction/cap.** Local median background, yoğun koyu T/cross noktalarını
   background sayıp kısa wall cap'i silebiliyordu. Güçlü koyu ink, local contrast'a
   ek olarak korunur. Geçerli kısa açıklıkları eleyen gerekçesiz dört-stroke clear
   width koşulu kaldırıldı; observed gap ile iki marker arası açıklık ayrı ele alınır.
7. **Attachment ve interval.** İki mevcut region owner, opening containment,
   çakışmayan interval ve aynı supporting wall şartları korunur. Başka duvara sessiz
   reattachment yok. Kanıt yetersizse diagnostic/Needs attention kalır.

Çıktılar hâlâ `proposed`, acceptance `pending`, physical values boş ve
`review_required: true`. Fiziksel ölçü, kullanıcı onayı veya validated Unreal
geometry üretilmez. Normal kullanıcıya yeni teknik pipeline seçtirilmedi;
profil seçimi CLI/server başlatma ayarıdır.

## Aynı geliştirme örneklerinde sonuçlar

Model ve görüntüler sabit: altı insan çizimi; bölge etiketli dört çizimde 15 region,
altı çizimin tamamında 18 opening (16 door + 2 open passage). Model ağırlıkları
öncekiyle aynı. Bunlar birçok kez incelenmiş development örnekleridir; yeni writer
veya holdout sonucu değildir. Kullanıcı correction time ve insan exact topology
ölçülmedi.

| Giriş ve decoder | Bölge: eşleşen / önerilen (15 ref.) | Opening: eşleşen / önerilen (18 ref.) |
| --- | ---: | ---: |
| Eski 256 + eski decoder | 0 / 4 | 0 / 0 |
| 512 kare + eski decoder | 10 / 11 | 1 / 2 |
| 512 kare + yeni model-center modu | 10 / 11 | 1 / 1 |
| 512 kare + yeni paired-raw modu | 10 / 11 | **6 / 6** |
| Kırpma + 512 kare + eski decoder | 12 / 14 | 0 / 1 |
| Kırpma + 512 kare + yeni paired-raw modu | **12 / 14** | **4 / 4** |

Kırpılmış profil daha fazla bölgeyi buluyor, fakat daha az doğru opening çıkarıyor.
Bir profil bütün ölçütlerde diğerinden üstün değil. Bu nedenle ikisi ayrı tutuldu.
Tam görüntü paired-raw profilinin opening precision'ı bu küçük sette %100,
recall'ı %33,3. Kırpılmış profilinki %100 / %22,2. Bu precision sonucu bağımsız
negatif insan çizimlerinde garanti değildir; false-positive guard testleri ayrıca var.

Tam görüntü paired-raw per-image opening sonucu:

| Çizim | Doğru / önerilen / referans |
| --- | ---: |
| Data 3 | 0 / 0 / 1 |
| Data 8 | 0 / 0 / 2 |
| Data 18 | 0 / 0 / 2 |
| Data 31 | 0 / 0 / 2 |
| Data 41 | 1 / 1 / 4 |
| Data 45 | 5 / 5 / 7 |

İyileşmenin ağırlığı Data 45 ve Data 41'de. Diğer örneklerde eksik bölgeler veya
marker/gap desteği hâlâ ciddi kayıp yaratıyor. Sadece iyi örnek gösterilip bütün
insan çizimlerinin çözüldüğü iddia edilmemeli.

**60 sentetik kontrol:** aynı cached model maskeleriyle eski decoder 141/141
opening'i 160 referansa eşledi; yeni decoder 142/142 eşledi. Exact topology iki
sistemde de 43/60. Yeni 142 eşleşmenin tamamında doğru region attachment var;
ölçülen false/duplicate connection sayısı sıfır. Modelden gelen region sonuçları
180 referansa karşı 170/187 olarak aynı kaldı. Yeni exact-topology dağılımı: clean 10/12,
wavy 10/12, grid 9/12, stray 8/12, broken 6/12. Kontroller aynı development
plan aileleridir; bağımsız insan genellemesi sağlamaz.

## Başarısız adaylar ve hedefler

İlk aday 57/160 doğru opening, ikinci aday 107/160 verdi; bunlar sentetik
regression nedeniyle elendi. Üçüncü aday 141/160'a ulaştı ama bir short T-wall cap
kaybıyla exact topology 42/60'a düştü. Bu kayıp düzeltildikten sonra dördüncü
aday 142/160 ve 43/60 verdi. Son v5 tekrarı, entegre CLI/job kaynaklarının
hash'leriyle aynı sonuçları doğruladı. Önceki sürümler/çıktılar silinmedi.

Karşılaştırmadan önce hedefler yazıldı: insan region P≥0.85/R≥0.80, opening
P≥0.80/R≥0.50; sentetik opening P≥0.98/R≥0.88125 ve exact topology≥43/60.
Kırpılmış paired-raw profil bölge ve precision hedeflerini ve sentetik koşulları
karşılıyor; **insan opening recall hedefini karşılamıyor**. Daha düşük semantic-only
sonuçlar da raporda tutuluyor. Yeni decoder varsayılan yapılmadı.

## Kullanım

Bir çizimi tam görüntü deneysel profille çalıştır:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.propose \
  --image Data/Data_45.png \
  --output Saved/ShapeFirst/refined-example \
  --profile refined-full
```

`--profile refined`, otomatik kırpma + 512 kare girişini kullanır.
`--profile baseline` önceki davranıştır ve CLI/server default'u olarak kalır.
Manual ve classical backend'ler refined AI profili çalıştırmaz. Yeni profillerde
model bulunamazsa veya inference başarısızsa image + manual fallback korunur.

Ayrı review sunucusu:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.server \
  --profile refined-full --port 8767 --output Saved/ShapeFirst/refined-jobs
```

Şu an [yerel deneysel review](http://127.0.0.1:8767/) açık. Her job seçilen profili
kaydeder; retry aynı profili kullanır. Eski job'lar profile alanı yoksa baseline
olarak yorumlanır. Normal review görüntüsü ve authoring koordinatları 256 çalışma
frame'inde kalır; yüksek çözünürlüklü kanıt ayrı `evidence.png`,
`evidence-cleaned.png`, `native_probabilities` ve `evidence_preprocessing` alanlarında
saklanır. `profile_config_sha256` ve profile/revision bağı, yeni ve eski yorumların
karışmasını önler. V2 metadata strict canonical Unreal JSON'una eklenmez.

## Doğrulama ve artefaktlar

`Saved/ShapeFirst/decoder_refinement/v5/`:

- `protocol.json`, `candidate-freeze.json`: hedefler, 234 cached input dosyasının
  hash'leri, decoder/config ve entegre CLI/job/server kaynak hash'leri.
- `report.json`, `gallery.html`, her örnek/profil/decoder için normal prediction,
  metrik, opening evidence ve karşılaştırma paneli.
- `tests.log`, `http-test.log`, `verification.json`.
- `live-api.json`, `live-review.jpg`: gerçek upload→worker→model→proposals→browser
  denemesi. Bu çıktı manuel çizim değildir.

Gerçek API testinde Data 45 PNG'si yeni local job'a yüklendi. Yeni model inference'ı
çalıştı, 6 region ve 5 opening döndü; source hash eşleşti, authoring contract geçti,
acceptance pending kaldı. Browser'da altı region listesi ve çizim üstündeki öneriler
görsel olarak kontrol edildi. Bu örneğin 7 referans opening'i olduğundan 2'si hâlâ
kaçırılıyor. Model SHA-256 önceki paketlenmiş ağırlıklarla aynı:

```text
e8f6637b5be5f2b399f43f1417944e41105a4afbe58008331330d088b8affbde
```

83 ilgili test geçti: 82 test sandbox içinde, mevcut loopback HTTP/token testi
port açma izniyle ayrı geçti. Bu tur 11 decoder testi ve 3 profil/worker testi eklendi.
Pozitif ve negatif kapsam: iki ayrı door, iki orientation, 1×/2×/3× görüntü ölçeği,
marker merkezinde semantic yanıt, sahte yüksek semantic yanıtta fiziksel kanıt
zorunluluğu, gap-only/single-tick/one-sided-tick/stray/digit reddi, faint grid,
short clear span, short T/cycle cap, contract, native/working frame, profile
propagation, unavailable model ve manual fallback. Bunlar insan precision
benchmark'ının yerine geçmez.

4.961 Data dosyası ve 234 cached input artefaktı değişmeden kaldı. Model ağırlıkları,
model lock'u, eski decoder ve eski config korunuyor. Önceki baseline deney artefaktları,
accepted v1 tasarımlar ve Unreal kaynakları bu çalışmada değiştirilmedi.

## Kalan iş

- Aynı develop çizimlerinde bile en iyi profil 12/18 opening'i kaçırıyor; mevcut
  paired raw yolunun precision'ı bağımsız negatif insan örneklerinde ölçülmeli.
- Eksik region/corridor yorumları düzeltilmeden bunlara bağlı kapılar üretilmemeli.
- Geriye kalan gerçek tick ve yazı karışmaları için hedefli kontrol edilmiş insan
  geometry/keypoint etiketleri ve gerektiğinde marker model eğitimi gerekiyor.
- Yeni writer/evaluation verisi, bu geliştirme örneklerinden ayrı tutulmalı.
- Step 3, manuel düzeltilmiş topology üzerinden ilerleyebilir; insan çizimi
  otomasyonunun tamamlandığı kabul edilmemeli.
