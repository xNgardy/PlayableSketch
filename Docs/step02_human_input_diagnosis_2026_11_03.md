# Step 2 — İnsan çizimleri: görüntü hazırlama ve model/decoder teşhisi

> **4 Kasım 2026 ölçüm düzeltmesi:** Önceki insan opening paydası incidental bir kırığı da içeriyordu. Aynı altılıda 18 yerine 17 gerçek geçiş var. Eski deney kayıtları korunuyor; [düzeltme notunu](shape_opening_metric_correction_2026_11_04.md) esas al.

Tarih: 3 Kasım 2026. Kapsam: kararlaştırılan **1. görüntü hazırlama** ve
**2. model ile decoder'ı ayrı sınama** çalışmaları. Yeniden eğitim yapılmadı.

**Sonuç:** Aynı modelin insan çizimlerinde oda/bölge bulmasını görüntü hazırlama
belirgin biçimde etkiliyor. Mevcut girişte 0/15 olan eşleşme, deneysel otomatik
kırpma + 512 piksel kare dolgulama ile 12/15'e çıktı. Kapı/geçiş algılaması ise
hâlâ yetersiz; tick yanıtları ve decoder'ın ölçeğe bağlı işlemleri ayrıca ele
alınmalı. Bu sonuç, aynı küçük geliştirme setindeki teşhistir; bağımsız insan
çizimi başarısı veya ürünün hazır olduğu anlamına gelmez.

## Deneyin sınırları

- Önceki pilotun aynı altı insan çizimi: Data 3, 8, 18, 31, 41, 45.
- Bölge çizgileri bulunan dört çizimde toplam 15 referans bölge var. Data 3/8
  bölge skoruna dahil değil. Altı çizimin tamamında 18 opening var: 16 door,
  2 open passage. Bu iki payda birbirine karıştırılmamalı.
- Aynı paketlenmiş U-Net, aynı ağırlıklar ve aynı decoder eşikleri kullanıldı.
  Model SHA-256: `e8f6637b5be5f2b399f43f1417944e41105a4afbe58008331330d088b8affbde`.
- 7 giriş seçeneği × 6 çizim = 42 normal tahmin. Çözünürlük dışında kırpma ve
  kare dolgulama da ayrı seçenekler olarak karşılaştırıldı; model seçimi/eğitimi yok.
- Oda eşleşmesi IoU≥0.5; opening eşleşmesi aynı tür ve uç nokta hatası≤görselin
  uzun kenarının %4'ü. Bütün skorlar aynı 256 piksel çalışma koordinatında hesaplandı.
- İnsan etiketleri yaklaşık çizgilerdir. Bunlardan piksel düzeyinde background
  ground truth üretilmedi. İnsan exact topology ve correction time hâlâ bilinmiyor.
- Sayısal OCR, boyut okuma veya dimension association çağrılmadı. Referans etiketleri
  normal tahmin kaydedildikten sonra yalnızca skor/teşhis için yüklendi.

## 1. Görüntü hazırlama

Orijinal giriş bazı fotoğrafları 256×91 veya 256×116 piksele indiriyor. Model ise
256×256 sentetik girdilerle eğitilmiş. Deneyde germe yapılmadı; kare seçeneklerde
oran korunarak beyaz kenar dolgusu eklendi. Kırpma adayı, yalnızca görüntüdeki uzun
çizgilerin zarfından ve güvenlik payından hesaplandı; etiket veya OCR kullanılmadı.
Bu kırpıcı bir deneysel adaydır; bütün yeni çizimlerde doğru olacağı doğrulanmadı.

İlk karşılaştırmada yüksek çözünürlüklü model maskeleri mevcut decoder'ın sabit
koordinatına geri yansıtıldı. Böylece model girdisinin etkisi, decoder'ın çalışma
boyutunu değiştirmeden incelendi.

| Giriş | Eşleşen / önerilen bölge (15 referans) | Bölge precision / recall | Eşleşen / önerilen opening (18 referans) |
| --- | ---: | ---: | ---: |
| Mevcut 256, oran korunuyor | 0 / 4 | %0 / %0 | 0 / 0 |
| 256 kare dolgu | 0 / 4 | %0 / %0 | 0 / 0 |
| 512, oran korunuyor | 9 / 13 | %69,2 / %60 | 1 / 2 |
| 512 kare dolgu | 10 / 11 | %90,9 / %66,7 | 1 / 2 |
| 768 kare dolgu | 7 / 12 | %58,3 / %46,7 | 0 / 1 |
| Otomatik kırpma + 256 kare | 0 / 4 | %0 / %0 | 0 / 0 |
| Otomatik kırpma + 512 kare | 12 / 14 | %85,7 / %80 | 0 / 1 |

En yüksek bölge recall'ına sahip seçenek tüm ölçütlerde en iyi değil. Örneğin
12/15 bölge bulan seçenek doğru opening bulamadı; bir yanlış opening önerdi.
512 kare seçeneği daha yüksek bölge precision'ına sahip. Yüksek çözünürlük de
monoton biçimde iyileştirmiyor: 768 seçeneği 512'den daha kötü sonuç verdi.

Kırpma + 512 ile Data 18: 3/3, Data 31: 1/3, Data 41: 3/3, Data 45: 5/6 bölge
bulundu. Bu altı örnekte otomatik kırpma, denetlenen bütün pozitif referans
noktalarını korudu: 4.944 wall, 373 tick, 38 junction ve 375 bölge içi probe.
Bu, etiketlenmemiş bütün içeriğin veya yeni çizimlerin korunacağı garantisi değildir.

**Gözlem:** Kare dolgu tek başına sorunu çözmedi. Daha fazla yapısal detayın
modele ulaşması önemli. Bu küçük sette 512 çözünürlük belirgin yarar sağladı.

## 2. Model ve decoder ayrımı

### Model maskeleri

Yaklaşık wall/tick/junction çizgileri çevresinde pozitif probe'lar alındı. Bunlar
piksel precision/IoU veya kalibre edilmiş olasılık ölçümleri değildir; yalnızca
bilinen yapının yakınında model yanıtı olup olmadığını gösterir.

- Wall probe hit oranı: mevcut girişte %28,7 → kırpma + 512'de %98,5.
- Tick probe hit oranı: %36,2 → %52,0.
- Bölge içi pozitif noktalarında yanıt zaten yüksekti; fakat bu tek başına ayrı
  odalar üretmiyordu. Duvar ayrımı ve mantıksal kapı sınırları da gerekiyor.
- Maskelerin görsel incelemesinde yazıların da wall/tick yanıtı ürettiği görülüyor.
  Bunlar boyut olarak okunmuyor; yapısal işaretlerle karışan distractor ink.

Bu bulgular bütün sorunun model kapasitesi olduğunu desteklemiyor. Aynı ağırlıklar,
daha uygun girdide duvarları ve birçok bölgeyi çıkarabiliyor. Ancak kapı işaretleri
ve yazı ayrımı için model tarafında da eksik devam ediyor.

### Decoder çözünürlük etkisi

Aynı kaydedilmiş maskeler bu kez doğrudan kendi 512/768 çalışma boyutunda decoder'a
verildi; sonuç geometrisi karşılaştırma için yine ortak koordinata taşındı. Bu
ikinci denemede yeni inference veya eğitim yapılmadı.

| Aynı model girdisi | Sabit 256 decoder: eşleşen bölge | Native decoder: eşleşen bölge | Native doğru / önerilen opening |
| --- | ---: | ---: | ---: |
| 512, oran korunuyor | 9/15 | 6/15 | 0/0 |
| 512 kare | 10/15 | 5/15 | 0/0 |
| 768 kare | 7/15 | 8/15 | 0/0 |
| Kırpma + 512 kare | 12/15 | 8/15 | 1/1 |

Bu, `max_side` değerini değiştirmeyi tek başına bir ürün düzeltmesi olarak
uygulamamak gerektiğini gösteriyor. Decoder'da dört piksellik sınır payı, minimum
örnekleme mesafeleri ve morphology işlemleri gibi sabit piksel kararları var.
Maske yeniden örneklemesi de etkili. Bu deney hangilerinin ayrı ayrı ne kadar
hata verdiğini henüz kanıtlamıyor; toplam ölçek bağımlılığını ortaya koyuyor.

### Kapı kuralları

Ayrı, açıkça **referans konumu kullanılan teşhis** deneyinde bilinen kapı uçlarında
mevcut raw-tick ve model-tick kontrolleri ölçüldü. Bunlar otomatik bulunan kapı
sonuçları veya precision ölçümü değildir.

Kırpma + 512 native görünümde 16 referans kapının 16'sında raw dört-taraflı çizgi
kontrolü geçti; modelin aynı dört tarafta yeterli tick yanıtı yalnızca 1/16 kapıda
geçti. Tam görüntü 512 seçeneklerinde model kontrolü 0/16'da geçti. Yaklaşık
etiket konumu bu ölçümü etkileyebilir; sonuç tek başına marker head ile gate
geometrisinin katkısını bütünüyle ayırmaz. Yine de ham çizgi bilgisinin mevcut
olmasına rağmen learned-marker kapısının neden önemli bir tıkanma noktası olduğunu
gösteriyor. Eşiği düşürmek için bir precision kanıtı sağlamıyor.

### Kusursuz maske kontrolü

12 sentetik kontrol görselinde gerçek maskeler doğrudan decoder'a verildi.
Bu sonuçlar **AI başarısına dahil değil**. Exact topology 11/12 oldu. `2003_grid`
örneğinde bölgeler doğru olmasına rağmen üç opening'den biri,
`GAP_WITHOUT_PAIRED_TICKS_OR_INTERFACE` kontrolünde elendi. Böylece öğrenilmiş
maskeler kusursuz olduğunda bile raw görüntü/gate tarafında hata kalabildiği gösterildi.

Ayrıca referans bölge kutuları verilerek sadece opening aşaması sınandı. İnsan
poligonlarının yaklaşık kutulara dönüştürülmesi bazı bölgeleri düşürdüğü için bu
müdahale kusursuz bir insan-geometrisi oracle'ı sayılmadı; supplied/retained sayıları
ve kayıpları raporda ayrı tutuldu.

## Kod, kanıt ve tekrar çalıştırma

Yeni, opt-in modüller:

- `SketchPipeline/shape_authoring/diagnostic_preprocessing.py`: image-only crop,
  oran koruyan dolgulama, tersinir transform ve ortak koordinata maske taşıma.
- `SketchPipeline/shape_authoring/diagnose.py`: dondurulmuş giriş karşılaştırması,
  pozitif probe'lar, ayrı oracle kontrolleri ve karşılaştırma galerisi.
- `SketchPipeline/shape_authoring/diagnostic_decoder_audit.py`: kaydedilmiş native
  maskelerden decoder çözünürlük ve referans-konumu gate teşhisi.
- `SketchPipeline/tests/test_shape_diagnostics.py`: 9 yeni koordinat/veri ayrımı
  testi. Dolgu/crop transformları, dışarıdaki yanlış tahminleri skor için koruma,
  pozitif probe sınırı ve kusursuz sentetik decoder kontrolü dahil.

Son kanıtlar:

- `Saved/ShapeFirst/diagnostics/v2/protocol.json`, `report.json`, `gallery.html`.
- Her çizim/profil için model girdisi, temizlenmiş görüntü, raw ve ortak-frame
  maskeler, normal tahmin, metrik, ayrı oracle dosyası ve açıklamalı panel.
- `Saved/ShapeFirst/diagnostics/v2/Data_18_before_after.png`.
- `Saved/ShapeFirst/diagnostics/native-v2/report.json` ve native decoder kayıtları.
- İlk v1 teşhisi korunuyor. v2, kaynakları yeniden dondurulmuş doğrulama tekrarıdır:
  ölçülmeyen kontrol süreleri null yapıldı ve sentetik referans transformu açıkça
  uygulandı. Giriş profilleri/eşikler/model değişmedi; insan bölge ve opening
  sayıları v1 ile aynı kaldı.

Tekrar çalıştırırken yeni çıktı dizinleri kullan:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.diagnose \
  --output Saved/ShapeFirst/diagnostics/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.diagnostic_decoder_audit \
  --study Saved/ShapeFirst/diagnostics/reproduction \
  --output Saved/ShapeFirst/diagnostics/reproduction-native
```

Bu tur CPU'da PyTorch 2.9.1 / OpenCV 4.13.0 / NumPy 2.4.2 ile çalıştı. MPS,
bu yürütme ortamında kullanılamadı; inference CPU'da tamamlandı. Model initialization,
skorlama ve oracle denemeleri normal inference sürelerine dahil değil. Ölçülmeyen
sentetik kontrol süreleri null; insan correction time ölçülmedi.

69 ilgili test geçti: 68 test sandbox içinde, yerel HTTP testi ise sandbox'ın port
açma kısıtı nedeniyle yalnızca loopback sunucu izniyle ayrı çalıştırıldı. Bu toplamın
9'u yeni diagnostic testidir. Kaynak görseller/annotation/accepted dosyalarını
kapsayan 4.961 Data dosyası hash kontrolünde değişmedi. Model ağırlıkları, model
lock'u, decoder kodu, presetler ve varsayılan upload/inference ayarları değiştirilmedi.

## Sonraki düzeltme için karar

1. 512 giriş + dolgulama/kırpma adayını deneysel olarak koru; bütün ürün akışına
   varsayılan yapmadan opening ve ek bölge hatalarını düzelt.
2. Decoder'daki sabit piksel işlemlerini stroke/koordinat ölçeğiyle tutarlı hale
   getir; native ve ortak-frame sonuçlarını aynı testlerde karşılaştır.
3. Kapı uçlarını ve dört-taraflı tick kontrolünü, gerçek işaret boyu/konumuyla
   birlikte incele. Yazılardan false passage üretmeyi engelleyen koşulları koru.
4. Bu müdahalelerden sonra kalan marker/distractor hataları için hedefli insan
   etiketleri ve yeniden eğitim planla. Yeni writer verisi gelirse ayrı değerlendirme
   olarak sakla; bu altı örnekteki iyileşmeyi genelleme başarısı sayma.

Bu tur 1 ve 2 için teşhis altyapısını ve ölçülmüş sonucu teslim eder. İnsan
çizimlerinden güvenilir otomatik bağlantı çıkarma sorununun tamamı çözülmüş değildir.
