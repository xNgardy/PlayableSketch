# Tüm veriyle yeniden eğitim — 7 Kasım 2026

## Sonucun kapsamı

**Bütün raporlanan görüntüler eğitimde kullanıldı. Aşağıdaki precision, recall ve F1 değerleri eğitim verisindeki uyumu gösterir; bağımsız test veya yeni yazara genelleme başarısı değildir.** Önceki train/validation/test grupları bu deneyde eğitime dahil edildi.

Mevcut DINO çözücü ağırlığından başlanıp bütün çözücü parametreleri altı tam tur eğitildi. DINOv2 omurgası sabit kaldı. AdamW, öğrenme oranı 0,0001, batch 4, seed 71126. Her turda 1.376 örneğin tamamı bir kez görüldü: toplam 8.256 örnek sunumu. Son epoch 6, eğitim öncesinde sabitlendi; sonuçlardan checkpoint seçilmedi.

## Kullanılan veriler

| Veri grubu | Görüntü sunumu |
|---|---:|
| İlk 50 insan çizimi + beşer türev | 300 |
| 70 sentetik kaynak + beşer türev | 420 |
| Yeni 20 insan çizimi + beşer türev | 120 |
| Önceden oluşturulmuş ek insan türevleri | 60 |
| Rehber ve karmaşık koridor renderları | 32 |
| Önceki eğitim dağılımından basit sentetikler | 384 |
| Önceki 60 sentetik kontrol; artık eğitimde | 60 |
| **Toplam** | **1.376** |

Bu sayı bağımsız mimari plan sayısı değildir. Aynı kaynağın farklı görünümleri ve farklı setlerdeki olası tekrarları ayrı sunumlardır. Şema/ön izleme görselleri ve maskeler bağımsız çizim girdisi sayılmadı. Maskeler yalnızca tanımlı hedef kanallarında kullanıldı. Belirsiz insan pikselleri kayba sıfır ağırlıkla girer. Fiziksel ölçü veya sayısal OCR eğitimi yapılmadı.

Önceden denetlenmiş Data_63 uç ve söve çizgisi düzeltmesi hedef oluşturulurken bellekte uygulandı; kaynak fotoğraflar ve etiket dosyaları değiştirilmedi.

## Aynı görüntülerde eğitim öncesi / sonrası

Aşağıdaki özgün ve türevler sabit birincil öneriyle, aynı geometri ve açıklık kurallarıyla puanlandı. Bölge: türden bağımsız kutu IoU ≥ 0,5. Kapı: doğru tür ve çalışma kenarının %4’ü içinde uç konumu. Bağlantı: açıklığın doğru iki bölgeye bağlanması. Eski insan referanslarında sahiplik yaklaşık yakınlık hesabıdır; yeni 20’de açık bölge kimlikleri kullanılır.

| Grup | Görüntü | Bölge F1 önce → sonra | Kapı F1 önce → sonra | Bağlantı F1 önce → sonra |
|---|---:|---:|---:|---:|
| 70 özgün insan çizimi | 70 | 92,0% → 93,6% | 88,5% → 90,4% | 82,8% → 83,8% |
| 350 insan türevi | 350 | 88,6% → 93,2% | 83,4% → 87,8% | 73,2% → 82,0% |
| Yeni 20 özgün | 20 | 88,0% → 93,4% | 74,5% → 81,5% | 63,8% → 77,7% |
| Yeni 20’nin 100 türevi | 100 | 83,0% → 90,0% | 66,7% → 77,4% | 56,5% → 72,5% |
| 70 özgün sentetik | 70 | 94,6% → 96,4% | 69,3% → 70,1% | 64,8% → 76,1% |
| 350 sentetik türev | 350 | 91,9% → 95,5% | 60,0% → 61,0% | 56,3% → 69,2% |
| 32 ek yoğun etiketli örnek | 32 | 80,5% → 84,1% | 76,5% → 73,7% | 53,9% → 57,4% |
| Önceki 60 kontrol (eğitime dahil) | 60 | 90,5% → 100,0% | 97,2% → 100,0% | 93,4% → 100,0% |
| Bütün eğitim sunumları | 1376 | 90,0% → 95,5% | 78,9% → 80,9% | 72,0% → 81,3% |

## İnsan çizimlerinde precision / recall / F1

| Grup | Model | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |
|---|---|---|---:|---:|---:|---:|
| 70 özgün insan çizimi | Önce | Bölge konumu | 213 / 237 / 226 | 89,9% | 94,2% | 92,0% |
| 70 özgün insan çizimi | Önce | Kapı türü ve konumu | 81 / 84 / 99 | 96,4% | 81,8% | 88,5% |
| 70 özgün insan çizimi | Önce | Doğru bağlantı | 128 / 140 / 169 | 91,4% | 75,7% | 82,8% |
| 70 özgün insan çizimi | Önce | Doğru bağlı kapı | 77 / 84 / 97 | 91,7% | 79,4% | 85,1% |
| 70 özgün insan çizimi | Sonra | Bölge konumu | 218 / 240 / 226 | 90,8% | 96,5% | 93,6% |
| 70 özgün insan çizimi | Sonra | Kapı türü ve konumu | 85 / 89 / 99 | 95,5% | 85,9% | 90,4% |
| 70 özgün insan çizimi | Sonra | Doğru bağlantı | 137 / 158 / 169 | 86,7% | 81,1% | 83,8% |
| 70 özgün insan çizimi | Sonra | Doğru bağlı kapı | 83 / 89 / 97 | 93,3% | 85,6% | 89,2% |
| 350 insan türevi | Önce | Bölge konumu | 996 / 1118 / 1130 | 89,1% | 88,1% | 88,6% |
| 350 insan türevi | Önce | Kapı türü ve konumu | 361 / 371 / 495 | 97,3% | 72,9% | 83,4% |
| 350 insan türevi | Önce | Doğru bağlantı | 528 / 598 / 845 | 88,3% | 62,5% | 73,2% |
| 350 insan türevi | Önce | Doğru bağlı kapı | 336 / 371 / 485 | 90,6% | 69,3% | 78,5% |
| 350 insan türevi | Sonra | Bölge konumu | 1065 / 1156 / 1130 | 92,1% | 94,2% | 93,2% |
| 350 insan türevi | Sonra | Kapı türü ve konumu | 400 / 416 / 495 | 96,2% | 80,8% | 87,8% |
| 350 insan türevi | Sonra | Doğru bağlantı | 637 / 708 / 845 | 90,0% | 75,4% | 82,0% |
| 350 insan türevi | Sonra | Doğru bağlı kapı | 387 / 416 / 485 | 93,0% | 79,8% | 85,9% |
| Yeni 20 özgün | Önce | Bölge konumu | 73 / 84 / 82 | 86,9% | 89,0% | 88,0% |
| Yeni 20 özgün | Önce | Kapı türü ve konumu | 19 / 19 / 32 | 100,0% | 59,4% | 74,5% |
| Yeni 20 özgün | Önce | Doğru bağlantı | 30 / 36 / 58 | 83,3% | 51,7% | 63,8% |
| Yeni 20 özgün | Önce | Doğru bağlı kapı | 17 / 19 / 32 | 89,5% | 53,1% | 66,7% |
| Yeni 20 özgün | Sonra | Bölge konumu | 78 / 85 / 82 | 91,8% | 95,1% | 93,4% |
| Yeni 20 özgün | Sonra | Kapı türü ve konumu | 22 / 22 / 32 | 100,0% | 68,8% | 81,5% |
| Yeni 20 özgün | Sonra | Doğru bağlantı | 40 / 45 / 58 | 88,9% | 69,0% | 77,7% |
| Yeni 20 özgün | Sonra | Doğru bağlı kapı | 22 / 22 / 32 | 100,0% | 68,8% | 81,5% |
| Yeni 20’nin 100 türevi | Önce | Bölge konumu | 332 / 390 / 410 | 85,1% | 81,0% | 83,0% |
| Yeni 20’nin 100 türevi | Önce | Kapı türü ve konumu | 80 / 80 / 160 | 100,0% | 50,0% | 66,7% |
| Yeni 20’nin 100 türevi | Önce | Doğru bağlantı | 124 / 149 / 290 | 83,2% | 42,8% | 56,5% |
| Yeni 20’nin 100 türevi | Önce | Doğru bağlı kapı | 72 / 80 / 160 | 90,0% | 45,0% | 60,0% |
| Yeni 20’nin 100 türevi | Sonra | Bölge konumu | 369 / 410 / 410 | 90,0% | 90,0% | 90,0% |
| Yeni 20’nin 100 türevi | Sonra | Kapı türü ve konumu | 101 / 101 / 160 | 100,0% | 63,1% | 77,4% |
| Yeni 20’nin 100 türevi | Sonra | Doğru bağlantı | 173 / 187 / 290 | 92,5% | 59,7% | 72,5% |
| Yeni 20’nin 100 türevi | Sonra | Doğru bağlı kapı | 98 / 101 / 160 | 97,0% | 61,3% | 75,1% |

## Dönüşümlerde bağlantı başarısı

| Grup | Dönüşüm | Önce F1 | Sonra F1 |
|---|---|---:|---:|
| 70 insan kaynağı | rotate | 71,2% | 78,9% |
| 70 insan kaynağı | perspective | 69,5% | 82,1% |
| 70 insan kaynağı | lighting | 79,2% | 86,1% |
| 70 insan kaynağı | capture | 79,1% | 84,3% |
| 70 insan kaynağı | combined | 65,7% | 78,3% |
| Yeni 20 | rotate | 47,5% | 68,1% |
| Yeni 20 | perspective | 38,0% | 67,4% |
| Yeni 20 | lighting | 70,7% | 79,6% |
| Yeni 20 | capture | 66,7% | 77,7% |
| Yeni 20 | combined | 54,1% | 68,2% |

## Kayıp ve doğrulama

| Epoch | Ortalama eğitim kaybı | Görülen örnek |
|---|---:|---:|
| 1 | 0.30867 | 1376 |
| 2 | 0.17116 | 1376 |
| 3 | 0.13867 | 1376 |
| 4 | 0.11816 | 1376 |
| 5 | 0.10393 | 1376 |
| 6 | 0.09359 | 1376 |

Kayıp değeri precision/recall veya doğruluk yüzdesi değildir. Başarı yorumu yukarıdaki son sistem çıktılarının eşleşmesine dayanmalıdır. Eksik bölge referansları bölge puanından çıkarılır; boş referans başarı sayılmaz. Sahipliği belirsiz kapılar bağlı kapı recall paydasına girmez.

Sabit DINO omurgasının float32 özellikleri önbellekten okundu; mürekkep girdisi inference sırasında float32 yeniden kuruldu. Bu, aynı encoder hesaplamasını tekrar yapmamak içindir. Eğitim hedefleri inference girişine verilmedi. Önceki tam üretim girişinden 840 görüntüyle metrik eşitliği kontrolünde **840/840** görüntüde beş metriğin tamamı eşleşti. Tam giriş kontrol örnekleri ayrıca `integration/` içinde tutulur. Önbellek karşılaştırmasının süresi tam üretim gecikmesi olarak yorumlanamaz.

25 eğitim/veri sözleşmesi testi geçti. Adayın ağırlıkları başlangıç modelinden farklıdır; eğitim kaydı ve hash’ler saklandı. Eğitim kodu kaynak veriye ve aktif model dosyasına yazmadı; son kaynak hash kontrolünün sınırı aşağıda açıklanmıştır.

## Yorum

- 70 özgün insan çizimi: bağlantı F1 82,8% → 83,8% (+0.9 yüzde puan).
- 350 insan türevi: bağlantı F1 73,2% → 82,0% (+8.9 yüzde puan).
- Yeni 20 özgün: bağlantı F1 63,8% → 77,7% (+13.8 yüzde puan).
- Yeni 20’nin 100 türevi: bağlantı F1 56,5% → 72,5% (+16.0 yüzde puan).

Bunlar mevcut örnekleri öğrenme sonuçlarıdır. Tam veriyle eğitim sonrasında gerçek kullanım başarısını ölçmek için eğitimde ve ayarlarda görülmemiş yeni çizimler gerekir. Eğitimdeki iyi sonuç tek başına otomatik kullanıma hazır olma kanıtı değildir.

## Model ve çıktılar

- Yeni aday: `Saved/ShapeFirst/all_data_training/v1/training/epoch_6.pt`
- Yeni SHA256: `efe0b245734472c4198c2ab525e9175e7e0f4268d87c99ef2043582613344eb6`
- Başlangıç SHA256: `e2376f20f05d54701ee2b796b46a1ac8798cdf0746a680237052d414d3353201`
- Aktif model dosyası değiştirilmedi; yeni aday otomatik etkinleştirilmedi.
- `protocol.json`: sabit eğitim tarifi, kapsanan kayıtlar ve kaynak hash’leri
- `training/history.json`: altı turun kayıpları
- `evaluation/report.json`, `evaluation/metrics.csv`: önce/sonra tüm örnekler ve gruplar
- `evaluation/verification.json`: belge, veri bütünlüğü ve baseline eşitliği
- `evaluation/gallery.html`: en çok iyileşen ve gerileyen insan örnekleri

## Son kaynak doğrulamasının sınırı

Eğitim öncesinde tüm kaynak hash’leri doğrulandı. Son denetimde 6076 korunan dosya yeniden okunup değişmediği doğrulandı; 10 eski JPEG işletim sistemi tarafından okunamadı. Yetkili salt okunur deneme de bu dosyalara erişemedi. Eğitim ve ölçüm başlangıçta doğrulanmış önbellek üzerinden tamamlandı. Okunamayan JPEG’lerin son hash’i doğrulanmış gibi sunulmaz. Aktif model ve eğitim/evaluasyon kodu hash’leri doğrulandı. Dosya listesi `evaluation/verification.json` içindedir.
