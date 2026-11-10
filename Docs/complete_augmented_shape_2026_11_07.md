# Tüm 70 insan çizimi ve türevleri — son sistem değerlendirmesi

## Kapsam

Data_51–70 için önceki deneyle aynı döndürme, perspektif, ışık, çekim etkisi ve birleşik profilleri kullanılarak 100 yeni görüntü oluşturuldu. Kaynak görüntüler, orijinal etiketler ve model ağırlıkları değiştirilmedi. İnsan çizimleri için yoğun piksel maskesi uydurulmadı; bölge poligonları ve açıklık uçları aynı homografiyle aktarıldı. Bölge sahipleri ve açıklık türleri korundu. 100 görüntüde sınır ve koordinat ileri–geri kontrolleri geçti.

Tam kapsam: **70 insan + 70 sentetik kaynak = 140 özgün görüntü; 350 insan + 350 sentetik türev = 700 artırılmış görüntü; toplam 840 tahmin**. Önceki 720 tahmin, model/kaynak kodu ve arşiv hash eşitliği doğrulanarak yeniden kullanıldı. Yeni 20 özgün + 100 türev için 120 taze çıkarım yapıldı. Model yeniden eğitilmedi ve eşikler ayarlanmadı.

Her görüntüde aynı DINO refined-full üretim girişi, normalizasyon ve üç alternatif kullanıldı. Puanlar sabit birincil alternatiften; toplam 2.520 öneri belgesi şema geçerli ve kullanıcı onayı bekliyor. Önceki 60 sentetik kontrol bu 70 sentetik kaynak setinden farklıdır; önceki 130 örnek değerlendirmesi ayrı kontrol raporu olarak korunmaktadır.

## Metrikler ve referans sınırları

Precision = doğru / tahmin; recall = doğru / referans; F1 = 2PR/(P+R). Tablolar mikro toplamadır; train/validation/test karışık toplamlar bağımsız test skoru değildir. Bölge metriği kutu IoU ≥ 0,5 ile türden bağımsız konum eşleşmesidir. Açıklık/kapı doğru tür ve uç hatası çalışma kenarının en fazla %4’ü olmalıdır. Doğru bağlı kapı ve bağlantı ayrıca iki doğru bölge sahibini gerektirir.

Bütün grupları karşılaştırabilmek için birleşik bağlantı metriği açıklık başına aynı eşleştirme kuralıyla hesaplandı. Data_51–70 için benzersiz bölge çifti metrikleri de her örneğin `unique_pair_metrics` alanında korunur. Bunlar doğrudan aynı metrikmiş gibi toplanmaz. Eski 50 insan çiziminde sahiplik yaklaşık poligon yakınlığıyla, yeni 20’de açık yapısal bölge kimlikleriyle belirlenir; bu referans kalitesi farkı nedeniyle gruplar ayrıca gösterilir.

Data_63 g003 için önceki denetimde sabitlenen uç düzeltmesi yalnızca değerlendirme referansına, bütün türevlere aynı homografiyle uygulanır. Özgün eğitim etiketleri ve oluşturulan ham kaynak-etiket aktarımları değiştirilmedi. Kullanılan değerlendirme referansları `evaluation_references/` altında saklanır. Yeni kör test veya yeni yazar genellemesi iddiası yoktur.

Bölge referansı 70 insan kaynağının 62’sinde vardır; bölge oranları özgünlerde 62, türevlerde 310 görüntüden hesaplanır. Referansı eksik 8 kaynak başarı sayılmaz. Sahipliği belirsiz iki eski kaynak kapısı, doğru bağlı kapı recall paydasına alınmaz; bütün insan kaynaklarında kapı konumu referansı 99, sahipliği belirli kapı referansı 97’dir.

## Bütün insan çizimleri — dönüşüm bazında

Her dönüşüm aynı 70 insan çiziminin bir görünümüdür. 350 türev bağımsız 350 plan değildir.

| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Bağlantı F1 | Doğru bağlı kapı F1 |
|---|---:|---:|---:|---:|---:|---:|
| Özgün kaynak | 70 | 92,0% | 88,5% | 83,9% | 82,8% | 85,1% |
| Döndürme | 70 | 86,5% | 79,8% | 72,7% | 71,2% | 74,7% |
| Perspektif | 70 | 84,9% | 81,7% | 74,5% | 69,5% | 75,4% |
| Işık | 70 | 92,6% | 88,4% | 81,0% | 79,2% | 83,8% |
| Çekim etkisi | 70 | 91,5% | 87,8% | 82,2% | 79,1% | 83,1% |
| Birleşik | 70 | 87,3% | 78,6% | 67,4% | 65,7% | 74,7% |
| Bütün türevler | 350 | 88,6% | 83,4% | 75,8% | 73,2% | 78,5% |

## Önceki 50, yeni 20 ve sentetik set ayrımı

| Grup | Koşul | Görüntü | Bölge F1 | Kapı F1 | Bağlantı F1 |
|---|---|---:|---:|---:|---:|
| Data_1–50 | Özgün kaynak | 50 | 94,3% | 93,9% | 91,2% |
| Data_1–50 | Bütün türevler | 250 | 91,7% | 89,8% | 80,5% |
| Data_51–70 | Özgün kaynak | 20 | 88,0% | 74,5% | 63,8% |
| Data_51–70 | Bütün türevler | 100 | 83,0% | 66,7% | 56,5% |
| Sentetik kaynaklar | Özgün kaynak | 70 | 94,6% | 69,3% | 64,8% |
| Sentetik kaynaklar | Bütün türevler | 350 | 91,9% | 60,0% | 56,3% |

## Precision / recall / F1

| Grup | Koşul | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |
|---|---|---|---:|---:|---:|---:|
| Bütün 70 insan çizimi | Özgün kaynak | Bölge konumu | 213 / 237 / 226 | 89,9% | 94,2% | 92,0% |
| Bütün 70 insan çizimi | Özgün kaynak | Kapı türü + konumu | 81 / 84 / 99 | 96,4% | 81,8% | 88,5% |
| Bütün 70 insan çizimi | Özgün kaynak | Tüm açıklıklar | 133 / 140 / 177 | 95,0% | 75,1% | 83,9% |
| Bütün 70 insan çizimi | Özgün kaynak | Doğru bağlantı | 128 / 140 / 169 | 91,4% | 75,7% | 82,8% |
| Bütün 70 insan çizimi | Özgün kaynak | Doğru bağlı kapı | 77 / 84 / 97 | 91,7% | 79,4% | 85,1% |
| Bütün 70 insan çizimi | Bütün türevler | Bölge konumu | 996 / 1118 / 1130 | 89,1% | 88,1% | 88,6% |
| Bütün 70 insan çizimi | Bütün türevler | Kapı türü + konumu | 361 / 371 / 495 | 97,3% | 72,9% | 83,4% |
| Bütün 70 insan çizimi | Bütün türevler | Tüm açıklıklar | 562 / 598 / 885 | 94,0% | 63,5% | 75,8% |
| Bütün 70 insan çizimi | Bütün türevler | Doğru bağlantı | 528 / 598 / 845 | 88,3% | 62,5% | 73,2% |
| Bütün 70 insan çizimi | Bütün türevler | Doğru bağlı kapı | 336 / 371 / 485 | 90,6% | 69,3% | 78,5% |
| Data_51–70 | Özgün kaynak | Bölge konumu | 73 / 84 / 82 | 86,9% | 89,0% | 88,0% |
| Data_51–70 | Özgün kaynak | Kapı türü + konumu | 19 / 19 / 32 | 100,0% | 59,4% | 74,5% |
| Data_51–70 | Özgün kaynak | Tüm açıklıklar | 33 / 36 / 58 | 91,7% | 56,9% | 70,2% |
| Data_51–70 | Özgün kaynak | Doğru bağlantı | 30 / 36 / 58 | 83,3% | 51,7% | 63,8% |
| Data_51–70 | Özgün kaynak | Doğru bağlı kapı | 17 / 19 / 32 | 89,5% | 53,1% | 66,7% |
| Data_51–70 | Bütün türevler | Bölge konumu | 332 / 390 / 410 | 85,1% | 81,0% | 83,0% |
| Data_51–70 | Bütün türevler | Kapı türü + konumu | 80 / 80 / 160 | 100,0% | 50,0% | 66,7% |
| Data_51–70 | Bütün türevler | Tüm açıklıklar | 135 / 149 / 290 | 90,6% | 46,6% | 61,5% |
| Data_51–70 | Bütün türevler | Doğru bağlantı | 124 / 149 / 290 | 83,2% | 42,8% | 56,5% |
| Data_51–70 | Bütün türevler | Doğru bağlı kapı | 72 / 80 / 160 | 90,0% | 45,0% | 60,0% |
| Sentetik kaynaklar | Özgün kaynak | Bölge konumu | 344 / 365 / 362 | 94,2% | 95,0% | 94,6% |
| Sentetik kaynaklar | Özgün kaynak | Kapı türü + konumu | 147 / 176 / 248 | 83,5% | 59,3% | 69,3% |
| Sentetik kaynaklar | Özgün kaynak | Tüm açıklıklar | 186 / 217 / 332 | 85,7% | 56,0% | 67,8% |
| Sentetik kaynaklar | Özgün kaynak | Doğru bağlantı | 178 / 217 / 332 | 82,0% | 53,6% | 64,8% |
| Sentetik kaynaklar | Özgün kaynak | Doğru bağlı kapı | 142 / 176 / 248 | 80,7% | 57,3% | 67,0% |
| Sentetik kaynaklar | Bütün türevler | Bölge konumu | 1675 / 1835 / 1810 | 91,3% | 92,5% | 91,9% |
| Sentetik kaynaklar | Bütün türevler | Kapı türü + konumu | 567 / 650 / 1240 | 87,2% | 45,7% | 60,0% |
| Sentetik kaynaklar | Bütün türevler | Tüm açıklıklar | 719 / 821 / 1660 | 87,6% | 43,3% | 58,0% |
| Sentetik kaynaklar | Bütün türevler | Doğru bağlantı | 698 / 821 / 1660 | 85,0% | 42,0% | 56,3% |
| Sentetik kaynaklar | Bütün türevler | Doğru bağlı kapı | 550 / 650 / 1240 | 84,6% | 44,4% | 58,2% |

## Yeni 20 çizimde hangi dönüşüm etkili?

| Koşul | Bölge F1 | Kapı F1 | Bağlantı F1 |
|---|---:|---:|---:|
| Özgün kaynak | 88,0% | 74,5% | 63,8% |
| Döndürme | 76,4% | 57,8% | 47,5% |
| Perspektif | 72,7% | 54,5% | 38,0% |
| Işık | 92,0% | 76,9% | 70,7% |
| Çekim etkisi | 90,9% | 74,5% | 66,7% |
| Birleşik | 82,0% | 66,7% | 54,1% |
| Bütün türevler | 83,0% | 66,7% | 56,5% |

## Kaynakların eğitim / doğrulama / test ayrımı

Türevler kaynaklarının ayrımını devralır. Önceden incelenmiş test kaynaklarının türevleri yeni bağımsız holdout değildir.

| Grup | Bölüm | Koşul | Görüntü | Kapı F1 | Bağlantı F1 |
|---|---|---|---:|---:|---:|
| Bütün 70 insan çizimi | train | Özgün kaynak | 47 | 88,3% | 86,3% |
| Bütün 70 insan çizimi | train | Bütün türevler | 235 | 84,5% | 76,7% |
| Bütün 70 insan çizimi | validation | Özgün kaynak | 9 | 85,7% | 66,7% |
| Bütün 70 insan çizimi | validation | Bütün türevler | 45 | 81,7% | 63,6% |
| Bütün 70 insan çizimi | test | Özgün kaynak | 14 | 92,9% | 83,3% |
| Bütün 70 insan çizimi | test | Bütün türevler | 70 | 80,6% | 68,6% |
| Data_1–50 | train | Özgün kaynak | 35 | 92,1% | 92,2% |
| Data_1–50 | train | Bütün türevler | 175 | 89,6% | 83,8% |
| Data_1–50 | validation | Özgün kaynak | 5 | 94,7% | 88,0% |
| Data_1–50 | validation | Bütün türevler | 25 | 98,0% | 83,5% |
| Data_1–50 | test | Özgün kaynak | 10 | 100,0% | 88,9% |
| Data_1–50 | test | Bütün türevler | 50 | 83,0% | 62,3% |
| Data_51–70 | train | Özgün kaynak | 12 | 77,4% | 68,0% |
| Data_51–70 | train | Bütün türevler | 60 | 69,9% | 54,1% |
| Data_51–70 | validation | Özgün kaynak | 4 | 75,0% | 40,0% |
| Data_51–70 | validation | Bütün türevler | 20 | 59,2% | 35,6% |
| Data_51–70 | test | Özgün kaynak | 4 | 50,0% | 75,0% |
| Data_51–70 | test | Bütün türevler | 20 | 69,6% | 76,7% |

## Yorum

- Bütün 70 insan çizimi: en düşük bağlantı F1 **Birleşik**, 82,8% → 65,7%.
- Data_51–70: en düşük bağlantı F1 **Perspektif**, 63,8% → 38,0%.
- Sentetik kaynaklar: en düşük bağlantı F1 **Döndürme**, 64,8% → 48,9%.

Özgün Data_51–70 zaten önceki 50’den daha düşük başarıya sahiptir; bu farkı yalnızca görüntü bozulmasına bağlayamayız. İlgili türevlerin başarısı aynı kaynakların özgün haliyle karşılaştırılmalıdır. Oda/koridor türü, kusursuz geometri ve cm/3B çıktı doğruluğu ana bölge F1 ile ölçülmez. Maskeler ayrı çizim veya ağ girdisi değildir; bu çalışma piksel Dice/IoU ölçümü yapmaz.

Plan grubu düzeyinde 5.000 eşleştirilmiş bootstrap tekrarı `paired_intervals.json` içindedir. Aynı planın özgün ve farklı stilleri birlikte örneklenir. Bu aralıklar mevcut verideki değişkenlik içindir; yeni yazar başarısı garantisi değildir.

## Veri bütünlüğü ve çıktılar

- Data_1–70 kaynaklarının tümü ve her biri için beş profil kapsanmıştır.
- 840 tahmin, 2.520 şema geçerli belge; tümü onay bekliyor.
- 120 yeni çıkarım; önceki 720 arşiv aynı model, kod ve içerik hash’leriyle doğrulandı.
- 6085 korunan dosya değişmedi.
- Ham etiketler ve Data_63 eğitim etiketleri değiştirilmedi; sayısal OCR veya fiziksel ölçü eğitimi yok.

- `report.json`: bütün 840 örnek ve grup sonuçları
- `metrics.csv`: grup/dönüşüm bazında precision / recall / F1
- `paired.csv`: aynı kaynakla F1 farkları
- `paired_intervals.json`: plan grubu bootstrap aralıkları
- `gallery.html`: yeni 20 çizimin özgün ve beş türevi; en büyük kayıplar
- `protocol.json`, `verification.json`: kaynak, veri, model ve sayım doğrulamaları
- Yeni görüntüler: `Data/augmented/new20_v1`
- Önceki 720 arşiv: `Saved/ShapeFirst/augmented_robustness/v1/predictions`
- Yeni 120 arşiv: `Saved/ShapeFirst/augmented_robustness/v2/predictions`

Dört değerlendirme testi geçti: proje dönüşümü ve ileri–geri kontrol, kaynak etiketleri değiştirmeme, tür/sahiplik koruma ve doğru konumdaki kapının yanlış sahiplerle başarı sayılmaması.
