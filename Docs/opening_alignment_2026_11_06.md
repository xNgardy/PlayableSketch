# Kapı sınırı ve geçit türü düzeltmesi — 6 Kasım 2026

Üç parçalı düzeltme tamamlandı ve DINO refined öneri girişine bağlandı. Model ağırlıkları ve eğitim etiketleri değişmedi. Öneriler kullanıcı incelemesi gerektirir. Çalışmakta olan yerel servis bu işlem sırasında yeniden başlatılmadı; kaynak değişiklikleri yeni süreçte yüklenir.

## Uygulanan değişiklikler

1. İki taraflı çizim kanıtı ve fiziksel kontrolleri geçen kapı uçları, ortak duvar desteğine en fazla 2 kanıt pikseli taşmada hizalanır. Aralığın en az %85’i korunur; farklı sahipli rakip ortak duvar varsa hizalama reddedilir. Bölge sahipleri değiştirilmez.
2. Güçlü çift söve kanıtı varken çözülemeyen açıklık `needs_attention` olarak kaydedilir. Öğrenilmiş geçit ve koridor kurtarma yolları bunu sessizce açık geçide dönüştüremez. Geometri geri dönüşü de eski geçidi yeniden getiremez.
3. Aynı 130 örnekte dört kol yeniden ölçüldü; eski davranışın 130 örnekte ve 15 doğrulama tekrarında topolojisi birebir korundu. 580 öneri belgesi şema kontrolünden geçti. 82 korunan veri/model dosyasının hash’i değişmedi.

## Sonuçlar

Yeni 20 çizimde doğru bulunan öğeler / referans sayısı:

| Ölçüt | Eski temel yöntem | Önceki geometri adayı | Düzeltme sonrası |
|---|---:|---:|---:|
| Bölge | 54/82 | 73/82 | 73/82 |
| Kapı | 9/32 | 17/32 | 19/32 |
| Doğru bölge bağlantısı | 9/58 | 28/58 | 30/58 |
| Eşleşmeyen bağlantı | 9 | 8 | 6 |

Düzeltme sonrasında kapı kesinliği %100, duyarlılığı %59,4; bağlantı kesinliği %83,3, duyarlılığı %51,7. Bu değerler daha önce incelenmiş aynı yazara ait verilerde geriye dönük ölçümdür; kör veya yeni yazar testi değildir.

| Yeni çizim bölümü | Bölge doğru/öneri/ref. | Kapı doğru/öneri/ref. | Bağlantı doğru/öneri/ref. | Eşleşmeyen bağlantı |
|---|---:|---:|---:|---:|
| train | 42/45/45 | 12/12/19 | 17/19/31 | 2 |
| validation | 14/18/18 | 6/6/10 | 4/7/13 | 3 |
| test | 17/21/19 | 1/1/3 | 9/10/14 | 1 |
| all | 73/84/82 | 19/19/32 | 30/36/58 | 6 |

Eski insan testinde 12/12 kapı ve 16/19 doğru bağlantı korundu. Sentetik kontrolde 123/130 kapı ve 141/160 doğru bağlantı korundu. Geometri adayının önceki sentetik bölge kaybı devam ediyor: temel yöntemde 174/180, geometri öncesi ve sonrasında 171/180. Tüm bölge sonuçlarının değişmeden kaldığı iddia edilmez.

Doğrulama seçimi: eski/yeni/sentetik her grupta bölge, kapı ve bağlantı F1 düşüşü en fazla 0,02; eşleşmeyen bölge ve bağlantı artışı yok. Düzeltilmiş geometri tüm koşulları geçti ve ağırlıklı amaç değeri 0,79225 ile seçildi. Önceki geometri adayı yeni doğrulama grubunda eşleşmeyen bağlantıyı 3’ten 4’e artırdığı için eleniyordu; düzeltme sonrasında 3. Test grubu seçim için kullanılmadı.

## Giriş ve negatif kontroller

81 geometri/decoder/kapı ve regresyon testi ile 29 öneri/iş/boyutlandırma testi geçti: toplam 110. Sandbox içinde localhost portu açamadığı için çalışmayan üç HTTP testi, ağ izniyle tekrar çalıştırıldı ve geçti. Sonuç `tests.json` içinde tutulur. Negatifler: kapalı duvar, tek söve, tek bölge sahibi, büyük taşma, dar açıklıkta aşırı kırpma, rakip ortak duvar sahibi, yanlış duvardaki kanıt ve gerçek işaretsiz açık geçit.

Data_58 gerçek yerel modelle yeniden çalıştırıldı: iki kapı, üç geçerli alternatif, `failure=null`, kullanıcı onayı bekleniyor. L koridorunun iç birleşimindeki üçüncü bağlantı halen eksik; çizimin tamamı çözülmüş sayılmaz. Data_63/64/66/69 gibi geometri geri dönüşü gerektiren örnekler için genel çözüm iddiası yok.

## Artefaktlar

- Son değerlendirme: `Saved/ShapeFirst/opening_alignment/v2/report.json`
- Dondurulmuş protokol ve kod: `protocol.json`, `source_snapshot/`
- Doğrulama seçimi: `selection.json`
- 20 çizim karşılaştırması: `gallery.html`
- Tekrar ve veri bütünlüğü: `verification.json`
- Gerçek model girişi: `Saved/ShapeFirst/opening_alignment/integration_actual_Data_58/proposals.json`

Etiket denetimindeki mevcut Data_63 uç düzeltmesi yalnızca değerlendirme referansına uygulanmıştır; özgün eğitim dosyaları değiştirilmemiştir.
