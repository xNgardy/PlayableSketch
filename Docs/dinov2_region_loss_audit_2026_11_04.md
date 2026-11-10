# DINOv2: eksik bölgelerin kaybolduğu aşamalar

Tarih: 4 Kasım 2026. İnceleme tamamlandı. Yeni model çıkarımı/eğitim yapılmadı;
üretim decoder'ı ve model seçimi değiştirilmedi.

**Ana bulgu:** validation + eski test grubundaki 11 eksik referans bölgenin
**9'u decoder kapılarında eleniyor; 2'sinde model ayrı/doğru türde bir bölge
üretmiyor.** Bu, dokuz maskenin de kusursuz olduğu anlamına gelmiyor: üçünün
doğru sınıf yanıtı zayıf. Öncelik decoder'ın küçük koridorları ve yakın ortak
sınırları ele alışını düzeltmek; bütün eşikleri körlemesine gevşetmek değil.

## Nasıl kontrol edildi?

`dino_region_audit.py`, kaydedilmiş DINO maskelerini **değişmemiş**
`decoder.region_boxes` üzerinden çalıştırıyor. Dikdörtgen adayları, NMS sonrası,
sınır snap sonrası ve örtüşme reddi sonrası listeler yalnızca gözlemleniyor.
Üretim fonksiyonu dosyası düzenlenmiyor. Gözlem hook'ları aynı süreçte geçici;
başarı/hata durumunda geri kaldırılıyor.

50 insan + 60 sentetik örneğin **110'unda** gözlenen çıktı, hem hooksuz decoder'ın
çıktısıyla hem de önceki kaydedilmiş önerilerle birebir eşleşti. **550 kayıtlı
girdi dosyasının** hash'i değişmedi. Referans annotation'lar yalnızca normal
replay bittikten sonra neden eşleştirmesi ve maske probları için okunuyor.

Yaklaşık referans bölgeleriyle eşleşme IoU ≥0.5 ve bire bir. Filtre öncesi component
kutusu, mevcut decoder'ın kullanacağı sabit genişletmeyle teşhis ediliyor;
filtreyi bypass etmiş yeni bir öneri veya doğruluk artışı olarak sunulmuyor.
Maskenin referans içindeki yanıt yüzdesi de yaklaşık geometriye bağlı bir prob;
pixel-perfect insan ground truth metriği değil.

## Validation + eski testteki 11 eksik bölge

| Kaybolduğu aşama | Bölge sayısı | Örnekler | Somut kanıt |
| --- | ---: | --- | --- |
| Son örtüşme reddi | 4 | Data 18 rC; 23 rB; 25 rB; 39 rB | Doğru kutu adayları mevcut; komşuyla 3–10 px örtüşme yüzünden siliniyor |
| Minimum component alanı | 3 | Data 43 cH; 48 cV1, cV2 | 372, 152, 235 px; eşik 393.216 px |
| Dikdörtgen doluluğu | 2 | Data 31 rB; 47 cH | Doluluk 0.606 ve 0.564; eşik 0.65 |
| Modelin yanlış bölge türü | 1 | Data 8 c0 | Koridor içi doğru sınıf yanıtı %0; room yanıtı yaklaşık %66 |
| Modelin ayrı bölge üretememesi | 1 | Data 8 rB | Room yanıtı mevcut; bölge çevredeki yanlış pozitif alanlarla birleşiyor |
| **Toplam** | **11** | | |

Train grubundaki 21 eksik bölge de ayrıca kaydedildi: 14 minimum alan,
7 örtüşme reddi. Train sonucu genelleme kanıtı değildir. Ana 11 bölge tablosu
yalnızca validation ve geçmişte incelenmiş test grubudur; yeni kör test değil.

### 1. Modelin doğru bulduğu odalar sonradan siliniyor

`decoder.py` satır 131, kalan herhangi bir kutuyla IoU >0 olan kutuyu tamamen
atıyor. Dört örnekteki gerçek kutu kanıtı:

| Örnek | Snap sonrası adayın referansla IoU'su | Komşuyla örtüşen alanın boyutu | Komşuyla IoU |
| --- | ---: | --- | ---: |
| Data 18 rC | 0.940 | 3 × 70 px | 0.0119 |
| Data 23 rB | 0.977 | 5 × 112 px | 0.0299 |
| Data 25 rB | 0.948 | 10 × 113.5 px | 0.0477 |
| Data 39 rB | 0.956 | 6 × 75 px | 0.0461 |

Örneğin Data 23'te ham model maskesi iki odayı ayrı görüyor. Sağ odanın kutusu
referansla %97.7 IoU'ya sahip; buna rağmen sol kutuyla 5 px örtüşme yüzünden
final planda yok. Bu kayıp, o odayı modelin görememesiyle açıklanamaz.

Bu örneklerde snap toleransı yaklaşık 3.82 px. Data 18'de ilk iki sınır arasındaki
4 px fark toleransın dışında kalıyor; başka bir çiftin snap'i sonrasında 3 px
örtüşme kalıyor. Çiftler tek geçişte işlendiği için bütün ortak sınırlar birlikte
tutarlı hale getirilmiyor. Sabit kutu genişletmesi ve eksen fit'i de bu sınırlara
katkı sağlayabilir; dört örneğin tümünü tek bir nedene indirgeyen iddia yok.

### 2. Küçük koridorlar oda ölçeğindeki alan eşiğine takılıyor

`decoder.py` satır 40: minimum alan = `max_side² × 0.006`.
256 canonical frame'de bu **393.216 component pikseli**. Alan, genişletilmiş
son dikdörtgenin değil, eşiklenmiş model interior maskesinin alanı.

Eğitim interior sınırında bir marj bırakıyor. Bu nedenle dar ama geçerli bir
koridorun iç maskesi küçük kalabiliyor. Data 48 cV2'de 235 px'lik component'in
doluluk oranı 0.816 ve genişletilmiş kutunun referansla IoU'su 0.840; yine de
alan kontrolünden geçemiyor. Bu örnekte yeniden eğitimden önce filtre incelenmeli.

Data 43 cH ve Data 48 cV1'de ise ham doğru sınıf yanıtı yaklaşık %44 ve %49.
Dolayısıyla burada model zayıflığı da var. Alan filtresini kaldırmak, koridorun
tüm uçlarının doğru bulunduğunu veya geçişlerin otomatik düzeleceğini kanıtlamaz.

### 3. İyi sınır kutusuna rağmen parçalı maske reddediliyor

`decoder.py` satır 41: `component_area / bounding_box_area >= 0.65`.
Data 31 rB doluluğu 0.606; genişletilmiş component kutusu referansla 0.923 IoU.
Data 47 cH doluluğu 0.564; genişletilmiş kutu IoU'su 0.763. İkisi bu aşamada
eleniyor; kutu fit'i, NMS veya son örtüşme kontrolüne ulaşmıyor.

Data 47'de modelin corridor yanıtı da parçalı ve zayıf. Burada uygun yaklaşım,
yalnızca doluluk eşiğini düşürmek yerine gözlenen sınır/duvar kanıtı ve model
yanıtıyla adayın desteklenip desteklenmediğine bakmak. Aksi halde yazı ve
gürültüden yeni sahte bölgeler üretilebilir.

### 4. Data 8'de iki gerçek model hatası var

c0, corridor kanalında oluşmuyor; room kanalında yanıt var. rB ise çevredeki
yanlış pozitif room alanlarıyla birleşiyor. Birleşmiş component kutusunun rB ile
IoU'su yaklaşık 0.279; basitçe doluluk filtresini kapatmak doğru oda kutusunu
geri getirmiyor. Bu iki örnek için modelin bölge türü/ayırma davranışı geliştirilmesi
gerekiyor; decoder kapısını açmak tek başına yeterli değil.

## Bağlantılara etkisi

Önceki opening envanterindeki 20 komşu bölgesi eksik açıklığın bölge kayıpları:

- 6 açıklık: örtüşme reddinde kaybolan oda.
- 6 açıklık: alan filtresinde kaybolan koridor.
- 6 açıklık: doluluk filtresinde kaybolan bölge.
- 2 açıklık: Data 8'deki model bölge hataları.

Bunların dışında bir açıklığın owner referansı bilinmiyor. Sayılar aynı
validation + eski test grubuna ait. Bölgelerin korunması gerekli bir koşul;
bu açıklıkların hepsinin bulunacağına dair karşı-olgusal başarı skoru değil.
Kapı tick/gap kanıtı, ortak duvar ve doğru attachment yine kontrol edilmeli.

## Sonraki düzeltmenin önceliği

1. Küçük ortak sınır uyuşmazlığında doğru bölgeyi tamamen silmek yerine,
   görüntü/model desteğiyle ortak sınırları birlikte uzlaştırmak. Desteksiz veya
   büyük örtüşmeyi otomatik kapatmamak.
2. Küçük koridor adaylarını sabit tüm-görüntü alan eşiği yerine boyut, kalınlık
   ve yapısal destekle değerlendirmek; yazı/gürültü negatiflerini korumak.
3. Parçalı ama destekli dikdörtgen adayları için doluluk dışındaki kanıtları
   kullanmak. Sonra Data 8 gibi gerçek model hatalarına dönmek.

Bu tur düzeltme uygulanmadı. Eşik, model, seçili checkpoint ve önceki raporlar
korundu. Bir sonraki düzeltme aynı 50 insan + 60 sentetik kontrolde ölçülmeli;
bu development verisindeki kazanım yeni-yazar doğrulaması sayılmamalı.

## Çıktılar ve doğrulama

Yeni teşhis kodu: `SketchPipeline/shape_authoring/dino_region_audit.py`.
Çıktılar: `Saved/ShapeFirst/dinov2/region_audit/v2/`:

- `report.json`: her referans bölgenin kaybolduğu aşama ve opening ilişkisi.
- `Data_*/trace.json`: filtreler, gerçek fit/NMS/snap listeleri ve overlap kanıtı.
- `gallery.html`, `Data_*/stages.png`: ham room/corridor maskesi ve kayıp aşaması.
- `freeze.json`, `verification.json`, `source_snapshot/`, `tests.log`: bütünlük kanıtı.

110 replay birebir eşleşti; 550 cached input ve 4.961 Data dosyası değişmedi.
Varsayılan model, DINO checkpoint ve üretim decoder'ı aynı. Beş yeni teşhis testi
geçti: gözlemin çıktı/veriyi değiştirmemesi, küçük/düzensiz component kapıları,
NMS/overlap ayrımı, hata halinde hook restorasyonu ve bire bir eşleşme.

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.dino_region_audit --study Saved/ShapeFirst/dinov2/v1 --output Saved/ShapeFirst/dinov2/region_audit/new-run
Saved/Training/v1/python/bin/python -m unittest SketchPipeline.tests.test_shape_dino_region_audit -v
```

v1 teşhis çıktısı korunuyor; v2, profiler'ın hata çıkışını koruyan küçük bir teşhis
iyileştirmesiyle aynı sonuçları tekrar üretti. Bu değişiklik üretim decoder'ına
veya modelin tahminlerine uygulanmadı.

**Sonraki uygulama:** Bu teşhisten sonra decoder 2.4 ayrı olarak uygulandı;
9 decoder kaynaklı eksik bölgenin 7'si geri geldi. Teşhis çıktıları korunuyor.
[Yeni karşılaştırma ve kalan hatalar](step02_decoder_recovery_2026_11_04.md).
