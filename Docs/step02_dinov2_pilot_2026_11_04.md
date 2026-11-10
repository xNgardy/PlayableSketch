# DINOv2 ile shape/keypoint deneyi

Tarih: 4 Kasım 2026. Kullanıcının onayladığı aday: standart DINOv2 ViT-S/14 ve
proje içinde eğitilen segmentation/keypoint decoder. Bu belge ilk yerel deneyin
yöntemini ve ölçüm sonuçlarını kaydeder. **Deney tamamlandı. Region algılama
iyileşti; bağlantı recall'ı ve sentetik koruma hedefleri geçilmedi. Varsayılan
model değiştirilmedi.**

## Çalışan uygulama

`dino_model.py`, standart Meta DINOv2-S/14 encoder'ını donduruyor. 448×448 girişten
3., 6., 9. ve 12. transformer bloklarının 384 kanallı 32×32 özellik haritaları
alınıyor. Encoder **22.056.576**, bize ait decoder **218.824** parametre içeriyor.
Ön eğitimli encoder güncellenmiyor. Ham/temiz mürekkebi gören ayrı bir convolution
kolu, 14 piksellik patch'lerin altındaki çizgi ayrıntısını decoder'a taşıyor.

256×256 decoder çıktısında sekiz kanal var: wall, room interior, corridor interior,
tick, junction, open interface, door endpoint ve logical boundary. Kapı endpoint
kanalı yalnızca açıkça door olarak etiketlenmiş gap uçlarından öğreniyor;
incidental kırıklar ve open passage uçları door keypoint etiketi değil.
Mantıksal boundary hedefi kapı boşluğundan da geçiyor; bu fiziksel duvar mürekkebi
olarak kaydedilmiyor. Room/corridor maskeleri boundary yanıtıyla sınırlandırılıyor.
Tick ve endpoint yanıtının maksimumu mevcut decoder'ın marker kanıtına veriliyor.

Bu ilk deneyde ayrıca instance-center/offset başlığı veya öğrenilmiş GNN yok.
Odalar bölge maskeleri ve mantıksal sınırlarla ayrılıyor. Bağlantı çözümü mevcut
decoder 2.3'ün shared-wall ownership, gap, paired raw tick ve duplicate kontrolleri.
Yüksek model yanıtı tek başına kapı oluşturamaz.

`LocalSegmenter` checkpoint architecture alanından DINO adapter'ını tanıyor;
mevcut U-Net yolu korunuyor. `propose` CLI gerçek sekiz kanallı native haritaları
ayrı kaydediyor. Normal shape-authoring contract, pending acceptance ve manuel
düzeltme kullanılabiliyor. Yeni job/server seçenekleri model path + SHA ve fotoğraf
normalizasyonunu job'a kaydediyor; restart/retry aynı ayarları kullanıyor.
Model seçimi HTTP upload içeriğinden yapılamıyor, yalnızca server konfigürasyonundan.

Kullanıcıdan yazılı sayı veya fiziksel ölçü istenmiyor. Numeric OCR çağrısı yok.
Fiziksel ölçüler eğitimde kullanılmıyor. Bu çalışma joint sizing veya yeni Unreal
export adapter'ını implement etmiyor; bunlar guide'ın sonraki aşamaları.

## Kaynak, lisans ve yerel kurulum

Yalnızca standart LVD-142M ViT-S/14 ağırlığı kullanılıyor; tıbbi varyant, hazır
segmentation head, Raster2Seq veya CubiCasa verisi/ağırlığı kullanılmadı.

- Kaynak: [Meta DINOv2](https://github.com/facebookresearch/dinov2).
- Kod revision: `7764ea0f912e53c92e82eb78a2a1631e92725fc8`.
- Model SHA-256: `b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9`.
- Standart encoder kodu/ağırlığı: Apache-2.0; kopya ve atıf
  `SketchPipeline/shape_authoring/licenses/` altında.
- `dinov2.lock.json`: indirilen ağırlık ve 155 Python kaynak dosyasının hash'i.
- Kod `Saved/Dependencies/dinov2`, ağırlık `Saved/Dependencies/dinov2_vits14_pretrain.pth`.
- Çıkarım çevrimdışı; `torch.hub` üzerinden otomatik kod/ağırlık indirme yok.
- Mevcut torch 2.9.1 ortamı kullanıldı; torchvision, timm veya xformers kurulmadı.
  xformers olmadan resmî PyTorch attention yolu çalışıyor.

Bağımlılıkları açıkça indirip hash doğrulamak için:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.setup_dino --download
```

Yalnızca çevrimdışı doğrulama için aynı komutu `--download` olmadan çalıştır.
Model kaynaklarını ve ağırlıklarını biz geliştirmişiz gibi sunmuyoruz; decoder,
gözetim, graph adapter'ı ve uygulama entegrasyonu kendi katkımız.

## Veri ve deney protokolü

Orijinal parent-plan ayrımı korunuyor: 35 insan train / 5 validation / 10 eski test.
35 eğitim çiziminden 140 görünüm: tam plan, image-only crop, kapı endpoint tile ve
wall tile. Görünüm koordinatları görüntü ve etiketlere birlikte uygulanıyor.
Eğitimde etiketle merkezlenen tile kullanılabiliyor; inference crop'u etiket kullanmıyor.

Sentetik eğitim: 1000–1095 parent'ları × clean/wavy/grid/stray = 384 örnek.
Bu ilk kontrollü deneyde sentetik layout aileleri genişletilmedi; mevcut altı aile
veri çeşitliliği sınırı olarak kalıyor. İnsan unknown alanları maskeli loss'ta
sıfır ağırlıkta; yaklaşık polygon dışı otomatik dense negatif ground truth değil.
Yazı polygon'ları yalnızca güvenli negatif ink örnekleri; metin değerleri okunmuyor.

524 girdinin DINO özellikleri yerel Apple MPS'de yaklaşık 22 saniyede çıkarıldı.
Feature cache 2,5 GiB; bu sadece eğitim hızlandırma kaydı. Çıkarımda encoder gerçekten
görüntü üzerinde çalışıyor, eğitim görüntüsü lookup'ı yapılmıyor.

Seed 51104; AdamW LR 0.001 / weight decay 0.0001; batch 8; 40 epoch. Her epoch
140 insan görünümü iki kez ve 384 sentetik örnek kullanılıyor. Maskeli BCE + Dice
loss sekiz kanal üzerinde hesaplanıyor; yalnızca decoder öğreniyor.

Checkpoint'ler epoch 10/20/40. Model seçimi yalnızca 5 validation çizimi ve
2000–2005 wavy sentetik kontrolü üzerinde: human region F1 + **doğru owner ile
opening F1**. Sentetik region F1 ≥0.80 ve doğru owner opening F1 ≥0.75 koruması;
eşitlikte erken epoch. Hiçbiri korumayı geçmezse en iyi validation adayı yalnızca
araştırma çıktısı olarak seçiliyor; otomatik kullanıma kabul edilmiş sayılmıyor.

Ana metrik artık opening konumunu doğru bulup yanlış bölgelere bağlayan tahmini
doğru bağlantı saymıyor. Kapı endpoint başlığı ayrıca referanstan bağımsız bir
peak çıkarma kuralıyla teşhis ediliyor: threshold 0.5, threshold component başına
tek maksimum, matching tolerance çalışma kenarının %4'ü. Bu threshold kalibre
edilmiş olasılık değildir; bu ek teşhis model seçiminde kullanılmıyor.

## Değerlendirme kapsamı

Seçilmiş checkpoint ile 50 insan çiziminin tamamı kendi train/validation/test
rolüyle kaydedilir. Train sonucu eğitim uyumudur. Eski test planları önceki
deneylerde incelendiğinden **yeni kör test veya yeni-yazar genellemesi değildir**.
Bilinen yazar örtüşmesi saklanır. İnsan referansları yaklaşık; exact topology
başarısı ve kullanıcı düzeltme süresi bu deneyde ölçülmüyor.

Karşılaştırmada eski U-Net ve DINO aynı `refined-full` profili, native 512 kare
kanıt ve sabit canonical decoder frame'i kullanır. İnsan fotoğraf normalizasyonu
her ikisinde açık. Sentetik 60 kontrol iki modelde de bu profille ölçülür; önceki
256 girişli sentetik raporun sayılarıyla doğrudan aynı deney değildir.

Yeni bir çıktı dizininde eğitim ve sabit seçimden sonra değerlendirme:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.dino_experiment train --output Saved/ShapeFirst/dinov2/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.dino_experiment evaluate --output Saved/ShapeFirst/dinov2/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.dino_keypoints --output Saved/ShapeFirst/dinov2/reproduction
```

Sonuçlara bakılarak aynı test üzerinde checkpoint/eşik yeniden seçilmez. Kaynak
snapshot'ları ve protocol/cache/model hash'leri her deneyde tutulur.

## Ölçülen sonuç

40 epoch tamamlandı; validation objective ile **epoch 20** seçildi. Üç checkpoint'in
hiçbiri sentetik validation korumasını geçmedi. Bu yüzden seçilen ağırlık bir
araştırma adayı, kabul edilmiş ürün modeli değil. Seçim sonrası retrospective
sonuçlara göre yeni eğitim veya eşik değişikliği yapılmadı.

| Küme / model | Bölge: doğru / öneri / referans | Opening konumu: doğru / öneri / referans | Doğru bağlı opening / owner referansı |
| --- | ---: | ---: | ---: |
| Train 35 plan, eski model | 44 / 60 / 99 | 14 / 14 / 85 | 14 / 78 |
| Train 35 plan, DINO | 78 / 85 / 99 | 32 / 32 / 85 | 31 / 78 |
| Validation 5 plan, eski model | 3 / 6 / 19 | 0 / 0 / 14 | 0 / 14 |
| Validation 5 plan, DINO | 15 / 17 / 19 | 9 / 9 / 14 | 9 / 14 |
| Eski test 10 plan, eski model | 7 / 11 / 26 | 1 / 1 / 20 | 1 / 19 |
| Eski test 10 plan, DINO | 19 / 21 / 26 | 4 / 4 / 20 | 4 / 19 |
| Sentetik 60 kontrol, eski model | 172 / 172 / 180 | 147 / 147 / 160 | 146 / 160 |
| Sentetik 60 kontrol, DINO | 151 / 181 / 180 | 91 / 91 / 160 | 91 / 160 |

İnsan region referansı olan plan sayısı train 29/35, validation 5/5, eski test 8/10.
Referans region bulunmayan planlar region skoruna girmez. Opening konum paydası
ile doğru owner paydası farklı: owner referansı olmayan açıklıklar ikinci metrikten
çıkarılıyor. Train'de bu tür bir model önerisi var; konumda 32, doğrulanabilen owner
skorunda 31 doğru sayılıyor. İnsan owner referansları hâlâ yaklaşık polygon
sınırlarına yakınlıkla atanıyor; bağımsız elle doğrulanmış exact topology değil.

Eski test grubunda region recall **%26.9 → %73.1**, region precision
**%63.6 → %90.5**. Opening konum recall **%5 → %20**; dört bulunan opening'in
dördü de doğru bölgelere bağlı. Sekiz open passage'ın hiçbiri önerilmedi;
12 door'un 4'ü bulundu. Bu nedenle yeni encoder'ın oda başarısı, tamamlanmış
bir plan graph'ı başarısı anlamına gelmiyor.

Sentetik kontrolde doğru bağlı opening recall **%91.25 → %56.88**, exact topology
**52/60 → 20/60**. Yeni modelde sentetik false/duplicate connection sayısı sıfır;
eski modelde bir. Eski modele göre daha az bağlantı önermek tek başına başarı değil.
Önceki decoder raporunun 256 girdili 142/160 sayısıyla bu yeni 512 girdili 147/160
baseline sayısı farklı deneylerdir; encoder kazanımı diye birleştirilmemeli.

CPU çıkarım süresi (aynı makine, torch 4 thread): insan girdilerinde DINO medyanı
yaklaşık **0.8 saniye**, eski model yaklaşık **0.43 saniye**. Bunlar local deney
süreleri; başka donanım için hız taahhüdü değildir.

## Keypoint ve kalan bağlantı sorunu

Kapı ucu başlığının bölge/graph sonucundan bağımsız teşhisi:

| Küme | Doğru / önerilen / referans endpoint | Precision | Recall |
| --- | ---: | ---: | ---: |
| Train | 79 / 79 / 90 | %100 | %87.8 |
| Validation | 18 / 19 / 20 | %94.7 | %90 |
| Eski test | 20 / 21 / 24 | %95.2 | %83.3 |

IoU ile eşleşen bölgelerin room/corridor türü train 78/78, validation 15/15,
eski test 19/19 doğru. Bu koşullu bir tür skoru; eksik ve fazla bölgeler bu
paydada yok. Ana region skoru geometriyi ölçüyor, türü ayrıca kontrol ettik.

`opening-audit.json` sonradan yapılan kanıt envanteri. Validation'da kaçan 5 ve
eski testte kaçan 15 opening'in en az bir referans komşu bölgesi decoded planda
eşleşmiyor. Eski testte kalan bir opening'in owner referansı bilinmiyor. Bu bir
kesin neden ispatı değil: modelin bölge maskesini üretmemesi ile vector decoder'ın
bölgeyi elemesi ayrıca ayrıştırılmalı. Özellikle bir corridor düğümünün eksikliği
birden çok bağlantıyı aynı anda kaybettiriyor. Sadece endpoint başlığına daha çok
eğitim vermek ana sorunu çözmeyebilir.

Data 47 before/after görselinde eski model 0/6, DINO 5/6 referans bölge buluyor.
DINO'nun fazladan bir bölgesi ve eksik corridor'u da görünüyor. Görsel yalnızca
başarı gösterimi değil, kalan hataları da içeriyor; tüm 50 çizim galeride saklı.

## Kullanılabilir aday ve kontrol kanıtı

Paketlenen deneysel decoder:
`SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt`.
SHA-256: `e2376f20f05d54701ee2b796b46a1ac8798cdf0746a680237052d414d3353201`.
`dinov2-candidate.lock.json` profil, normalizasyon, encoder lock ve başarısız
kabul kapılarını kaydediyor. `models.lock.json` hâlâ eski U-Net'i gösteriyor.

**129 benzersiz test geçti:** ana suite 127, sonradan eklenen endpoint testi 1,
loopback HTTP/token testi 1. Son DINO suite'inin 10 testi ayrıca yeniden geçti;
bu tekrar toplam sayıya eklenmiyor. Bilinmeyen piksellerin sıfır gradient'i,
frozen encoder, letterbox tam kapsamı, logical boundary/physical wall ayrımı,
incidental negatifler, çevrimdışı gerçek backbone, checksum reddi ve model
ayarlarının restart/retry ile korunması test edildi.

Gerçek seçilmiş checkpoint, port açmadan `ShapeJobs` worker'ında Data 18 ile
çalıştırıldı; sözleşme, model SHA, OCR kapalı ve acceptance pending kontrolleri
`worker-smoke.json` dosyasında. Bu bir browser testi değildir.

Deneme sunucusu ayrı portta başlatıldı:

```sh
OMP_NUM_THREADS=4 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.server --output Saved/ShapeFirst/dinov2/v1/interactive-jobs --port 8768 --profile refined-full --checkpoint SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt --expected-sha256 e2376f20f05d54701ee2b796b46a1ac8798cdf0746a680237052d414d3353201 --normalize-ink
```

Adres: http://127.0.0.1:8768/ . Browser açma işlemi, otomatik onay hizmetinin
kullanım sınırı nedeniyle reddedildi. Browser etkileşimi veya ekran görüntüsüyle
doğrulama yapıldığı iddia edilmiyor; bu engel başka browser/HTTP erişimiyle aşılmadı.
Port açmayan worker testi ve dosyaya kaydedilmiş model sonuçları tamamlandı.

Ana çıktı dizini `Saved/ShapeFirst/dinov2/v1/`:

- `protocol.json`, `source-freeze.json`, `source_snapshot/`, `integration-freeze*.json`:
  eğitim, değişmeyen kaynaklar ve sonradan eklenen entegrasyon/teşhis kaydı.
- `cache/manifest.json`, `label-inventory.json`, `training_report.json`, `train.log`:
  veri kapsamı, hash'ler, eğitim ve validation ile seçim.
- `report.json`, `evaluation/gallery.html`: 50 insan çiziminin iki kolu ve 60
  sentetik planın karşılaştırması. Her tahmin referans okunmadan önce kaydedildi.
- `keypoint-report.json`, `opening-audit.json`: sonradan teşhis; model yeniden seçilmedi.
- `Data47-before-after.png`: kaynak üstünde gerçek model önerileri.
- `verification.json`, `tests.log`, `final-dino-tests.log`, `http-tests.log`,
  `worker-smoke.json`: bütünlük ve test kanıtı.

İnsan algılamasında yararlı bir aday elde edildi. Sonraki deneyin oda/corridor
instance çıkarımı ve region'ın vector decoder'da kaybolması üzerine odaklanması
gerekiyor; yeni plan/yazar gruplarındaki kör test de hâlâ açık iş.

**Aşama teşhisi güncellemesi:** Kaydedilmiş maskelerle 110 decoder replay'i
birebir doğrulandı. Validation + eski testteki 11 eksik bölgenin 4'ü son overlap,
3'ü alan, 2'si doluluk filtresinde kayboluyor; 2'si Data 8'de model bölge hatası.
Bazı filtreye takılan maskeler de zayıf; filtreleri topluca kapatmak çözüm diye
sunulmuyor. [Kanıtlar ve düzeltme önceliği](dinov2_region_loss_audit_2026_11_04.md).
