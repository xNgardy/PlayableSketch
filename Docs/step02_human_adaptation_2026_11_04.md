# İnsan çizimleri: hata incelemesi ve hedefli eğitim

Tarih: 4 Kasım 2026. Çalışma tamamlandı; otomatik algılama kabul hedefi **karşılanmadı**.
Yeni ağırlıklar araştırma çıktısı olarak tutuldu, varsayılan modele geçirilmedi.

İstenen hata galerisi, eksik region incelemesi, yapısal eğitim etiketleri,
hedefli yeniden eğitim ve ayrı planlarda karşılaştırma uygulandı. Aynı altı
teşhis çiziminde opening konum eşleşmesi 6/17'den 10/17'ye çıktı; bunların
yalnızca 7'sinde bağlı region'lar doğru. Eğitim/model seçimi dışında tutulan
9 planda sonuç 2/18. Sentetik kontrol de geriledi. Bu sonuç otomasyonun hazır
olduğu veya problemin sonraki ürün aşamalarında kendiliğinden çözüleceği anlamına gelmiyor.

## Önceki metriğin düzeltilmesi

Data 41 `g004` işaretsiz, incidental bir çizgi kırığı; kapı değil. Önceki skorlayıcı
bunu opening saymıştı. Doğru altı çizim paydası **16 door + 1 open passage = 17**.
Eski 6 tahmin değişmedi. 6/18 → 6/17 farkı eğitim kazanımı değil.
[Ayrıntılı düzeltme ve eski raporların kapsamı](shape_opening_metric_correction_2026_11_04.md).

11 gerçek eksik opening'in 8'i bağlı region bulunamadığı, 1'i paired tick ink
kontrolünde elendiği, 2'si gap/support aramasında kaçtığı için eksikti. Nedenler,
kaydedilmiş decoder kanıtı ve yaklaşık referanslarla atandı; bağımsız kesin
nedensellik etiketi sayılmamalı. Galerie kaynakları:
`Saved/ShapeFirst/human_adaptation/v1/error_review_corrected/{review.json,gallery.html}`.

## Etiketler ve veri ayrımı

`human_supervision.py`, mevcut wall/tick stroke, junction, gap ve region
geometrisini yapısal gözetim olarak okuyor. Yazı polygon'ları yalnızca yapısal
stroke'lardan uzaktaki mürekkep için negatif örnek; metin içeriği, sayısal
değerler ve kabul edilmiş fiziksel ölçüler eğitime girmiyor.

Data 3 ve Data 8'in eksik region polygon'ları, mevcut junction koordinatlarından
ayrı `curation/human-geometry.v1.json` dosyasına eklendi. Kaynak SHA ile bağlı,
görsel incelemeden geçmiş yaklaşık yorumlardır; çizim sahibinin onayı veya
pixel-perfect insan maskesi değildir. Orijinal annotations değiştirilmedi.
Böylece altı çizimin region referansı eski 15 yerine 20 oldu. Aynı yeni referanslar
bütün karşılaştırma kollarına uygulanıyor.

İnsan maskelerinde bilinmeyen alanların ağırlığı sıfır. Güvenli iç alanlar,
stroke çevresindeki doğrulanmış ink ve geniş belirsizlik marjları kullanıldı;
polygon dışının tamamı dense background ground truth yapılmadı. 35 eğitim
çiziminin her biri için tam görüntü, image-only crop, marker tile ve wall tile
olmak üzere 140 görünüm hazırlandı. Altı denetim sayfası görsel olarak incelendi.

Orijinal `Saved/Evaluation/v1/split.json` korundu: **35 train / 5 validation /
10 test plan grubu**. Resize/crop/augment türevleri parent'ın ayrımını miras alıyor.
Data 31 önceki decoder teşhisinde görüldüğünden ayrı test sonucundan çıkarıldı.
Ayrı değerlendirme 9 plan: **1, 5, 13, 20, 23, 25, 39, 47, 48**. Bu planlar model
seçildikten sonra bir kez değerlendirildi; sonuçlarına bakılarak ağırlık veya
eşik değiştirilmedi.

Bu mevcut development koleksiyonudur; 50 çizim geçmişte zaten etiketlenmişti.
Bilinen `tablet_author_01` yazarının train/test örtüşmesi var, bazı eski çizimlerin
yazarı bilinmiyor. Yeni yazar veya dış veri genellemesi iddiası yok. Data 1 ve 5'te
region referansı bulunmadığından ayrı planlardaki region skoru yalnızca 7 çizimin
etiketli geometrisini kapsıyor. İnsan exact topology ve düzeltme süresi ölçülmedi.

## Eğitim ve başarısız adaylar

Mevcut proje üretimi ShapeUNet başlangıç ağırlığı kullanıldı. Yeni dış veri,
pretrained model veya bulut servisi kullanılmadı. Ağırlıkların dağıtım lisansı
proje içinde hâlâ belirtilmemiş durumda.

| Deney | Değişiklik | Sonuç |
| --- | --- | --- |
| v1 | Tüm ağ, ham insan girdisi | Sentetik validation korumasını geçemedi |
| v2 | Son decoder ve yapısal head'ler, yerel median normalizasyonu | Kontrast işlemi kötüleştirdi; epoch 4 sonrasında göreli yol kayıt hatasıyla durdu |
| v3 | Aynı kısmi eğitim, koşullu global kontrast | Letterbox padding kontrast istatistiğini bozdu; sentetik validation korumasını geçemedi |
| v4 | Yalnızca tick/junction head'leri; içerik sınırından kontrast istatistiği | Validation kontrolünü geçti; tam sentetik ve ayrı insan testinde kabul edilmedi |

Başarısız deney çıktıları ve kaynak snapshot'ları saklandı. Göreli yol hatası
output'u başta absolute çözerek düzeltildi. Normalizasyon artık yalnızca soluk
fotoğrafta uygulanıyor; beyaz digital çizimler pixel-identical kalıyor. Padding
istatistiğe katılmıyor; spatial transform identity. Ham görsel ve review frame'i
korunuyor. CLI/API `normalize_ink=False` varsayılanını koruyor.

v4: seed 41126, 12 epoch, batch 8, Adam LR 0.0002, her epoch 280 insan görünümü
ve 192 sentetik örnek, teacher kayıp ağırlığı 0.5. İnsan gözetimi maskeli;
ayrı teacher terimi eski modelin soft yanıtını korumaya çalışıyor, bilinmeyen
insan pikseline ground-truth etiketi vermiyor. GPU: yerel Apple MPS.

Epoch 4/8/12 yalnızca 5 validation planı ve 6 sentetik kontrol üzerinden
karşılaştırıldı. Sentetik F1 tabanları region 0.85 / opening 0.8. Bu korumayı
geçenler arasında human region F1 + opening F1 ile **epoch 8** seçildi. Bu seçim
insan kabul eşiğini geçti demek değil: validation'da yalnızca 3/14 opening konumu
bulundu; 3'ünün de attachment'ı hatalıydı. Dar validation kontrolünün tam sentetik
seti ve bağlantı doğruluğunu korumaya yetmediği ayrı sonuçlarda da görüldü.

Backbone ve wall/room/corridor/open-interface head ağırlıkları başlangıç modeliyle
bit düzeyinde aynı; yalnızca tick/junction çıktıları eğitildi. Bu, son region
önerilerinin aynı kalmasını garanti etmez: decoder junction kanıtını da kullanıyor.

Seçilmiş deney ağırlığı:
`Saved/ShapeFirst/human_adaptation/v4/training/epoch_8.pt`.
SHA-256: `a5b7b2c4773df0ecd785ae5a80b3a3221695f43c70c4095d0606f84aa3cc1ef7`.
Varsayılan ağırlık SHA-256:
`e8f6637b5be5f2b399f43f1417944e41105a4afbe58008331330d088b8affbde`.

## Son karşılaştırma

İnsan girdilerinde bütün kollar aynı `refined-full` decoder 2.3 kullanıyor.
Opening konum skoru tür + endpoint eşleşmesidir; doğru attachment ayrıca sayılır.

| Küme / yöntem | Region: doğru / öneri / referans | Opening: konumu eşleşen / öneri / referans | Doğru attachment |
| --- | ---: | ---: | ---: |
| Önceden incelenen 6 plan, eski model | 10 / 11 / 20 | 6 / 6 / 17 | 6 / 6 |
| Aynı 6 plan, yalnızca kontrast | 13 / 15 / 20 | 7 / 7 / 17 | 7 / 7 |
| Aynı 6 plan, v4 | 14 / 18 / 20 | 10 / 10 / 17 | 7 / 10 |
| Ayrı 9 plan, eski model | 6 / 9 / 23 | 1 / 1 / 18 | 1 / 1 |
| Ayrı 9 plan, yalnızca kontrast | 6 / 9 / 23 | 1 / 1 / 18 | 1 / 1 |
| Ayrı 9 plan, v4 | 6 / 9 / 23 | 2 / 2 / 18 | 2 / 2 |
| Sentetik 60 kontrol, eski model | 170 / 187 / 180 | 142 / 142 / 160 | 142 / 142 |
| Sentetik 60 kontrol, v4 | 160 / 179 / 180 | 132 / 132 / 160 | 129 / 132 |

Önceki 11 eksikten 4'ünün konumu artık bulunuyor: Data 3 g001, Data 18 g001/g002,
Data 45 g007. Data 18'de attachment hataları sürdüğünden bunların tamamı çözülmüş
bağlantı sayılmaz. Data 8'de region algılama hâlâ boş; Data 41'de üst region hâlâ eksik.

Ayrı insan testinde opening recall **%11.1**, hedef **%50**. Az sayıda önerinin
konum precision'ı %100; bu tam plan doğruluğu değil. Sentetik recall %88.75'ten
%82.5'e, exact topology 43/60'tan 38/60'a düştü; 3 yanlış/duplicate bağlantı oluştu.
Kabul kapıları geçilmedi; checkpoint deploy edilmedi, server varsayılanı değiştirilmedi.

## Kod, doğrulama ve çıktılar

Yeni kod: `human_supervision.py`, `human_error_review.py`, `train_human.py`,
`evaluate_human.py`, `contrast.py`, curation sidecar ve adaptation testleri.
`pilot.py` incidental referans hatasını düzeltiyor; `propose.py` açık opt-in
normalizasyonu kaydedip revision kimliğine katıyor. OCR çağrısı eklenmedi.

**119 test geçti:** ilgili ana suite 117, yeni public photo API testi 1 ve gerçek
loopback HTTP/token testi 1. Sonradan güncellenen kaynaklar için adaptation suite'i
yeniden çalıştırıldı. Sıfır hata/skip. Kapsam: maskeli loss gradient'i, label sınırları,
incidental negatifleri, split hijyeni, head optimizer izolasyonu, padding istatistiği,
digital çizimin değişmemesi, source/frame/revision kaydı ve mevcut proposal/contract kontrolleri.

4.961 Data dosyası hash'i değişmedi. Varsayılan checkpoint ve model lock aynı.
Eğitim/değerlendirme kaynak snapshot hash'leri freeze kayıtlarıyla eşleşiyor.
Unreal kaynakları ve önceki accepted tasarımlar bu çalışmada değiştirilmedi.

Ana çıktı dizini `Saved/ShapeFirst/human_adaptation/v4/`:

- `protocol.json`, `training-freeze.json`, `source_snapshot/`: veri ayrımı ve kaynak izi.
- `label-audit/`, `supervision-manifest.json`: 35 eğitim çiziminin maskeli gözetim denetimi.
- `training_report.json`, `training/validation_epoch_*/`: validation ile model seçimi.
- `evaluation/freeze.json`, `evaluation/gallery.html`: 45 insan karşılaştırma paneli ve dondurulmuş test.
- `report.json`: insan/sentetik metrikler, önceki eksiklerin durumu ve başarısız kabul kapıları.
- `verification.json`, `tests.log`, `photo-api-test.log`, `http-test.log`: kontroller.

Mevcut tarihsel split, sentetik eğitim cache'i ve kaynak görüntülerle yeni bir çıktı
dizininde yeniden çalıştırmak için:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.train_human --output Saved/ShapeFirst/human_adaptation/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.evaluate_human --output Saved/ShapeFirst/human_adaptation/reproduction
```

Bu, aynı development deneyinin tekrarıdır; yeni test kanıtı üretmez. CLI mevcut
training/evaluation dizinlerinin üzerine yazmayı reddeder. Tarihsel tam kaynaklar
v4 snapshot'ında tutulur; mevcut kaynaklarda yalnızca CLI/konfigürasyon açıklıkları
ve hata kontrolü iyileştirildi, test sonucuna göre model yeniden seçilmedi.

Sonraki model çalışması region içlerini ve corridor ayrımını daha iyi öğrenmeye,
yanlış attachment'ı seçim kriterine katmaya ve daha çeşitli gerçek çizim etiketlerine
odaklanmalı. Bu 9 plan artık yeni bir kör test olarak kullanılmamalı. Gerçek genelleme
kontrolü için yeni plan/yazar grupları ayrılmalı. Step 3 boyutlandırma ve Step 4 editing
çalışması ilerleyebilir; insan algılama kalitesi ayrı bir açık iş olarak kalıyor.
