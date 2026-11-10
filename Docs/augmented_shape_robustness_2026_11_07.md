# Artırılmış görüntülerde son sistemin dayanıklılığı — 7 Kasım 2026

## Kapsam ve yöntem

Son DINO refined-full sistemiyle 600 artırılmış görüntü ve bunların 120 kaynak görüntüsü üzerinde toplam 720 taze çıkarım yapıldı. Her görüntüde üretim girişinin üç alternatifi oluşturuldu; puanlama önceden sabit birincil alternatiften yapıldı. Model ağırlıkları ve üretim kararları değişmedi; yeniden eğitim veya test sonuçlarından eşik seçimi yapılmadı.

Kaynaklar 50 insan çizimi ve 70 sentetik görüntüdür. 250 insan türevi ve 350 sentetik türev vardır. Sentetik görüntüler 60 adet önceki kontrol setinden farklı bir kümedir. Data_51–70 bu artırılmış sette yoktur. Bu nedenle önceki 130 örnekle birleştirilmiş genel başarı oranı verilmez.

Tüm tahminler kaydedildikten sonra referanslar okunarak puanlandı. Kaynak poligonları ve açıklık uçları, kayıtlı kaynak→artırılmış dönüşüm ve görüntünün gerçek ön işleme matrisiyle çalışma koordinatlarına taşındı. Kaynak bölge sahipleri dönüşüm sırasında korunur. Referans homografileri modele veya geometri çıkarımına verilmedi.

Bölge kutu IoU eşiği 0,5; açıklık için doğru tür ve en fazla çalışma kenarının %4’ü kadar uç hatası. Kapı türü/konum metriği doğru bölge bağlantısı gerektirmez; doğru bağlı kapı ve doğru bağlantı ayrıca raporlanır. Bağlantı, açıklık başına doğru tür, konum ve eşleşmiş iki kaynak bölge sahibini gerektirir. İnsan sahiplik referansları yaklaşık kaynak poligon yakınlığına dayanır; sentetik sahiplikler açık üretici bağlantılarından alınır.

## İnsan çizimleri

Her dönüşüm satırı aynı 50 çizimin birer türevidir. 250 türev 250 bağımsız plan değildir. F1 değerleri öğe sayıları toplanarak mikro hesaplanmıştır.

| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Doğru bağlantı F1 | Doğru bağlı kapı F1 |
|---|---:|---:|---:|---:|---:|---:|
| Özgün kaynak | 50 | 94,3% | 93,9% | 89,7% | 91,2% | 92,3% |
| Döndürme | 50 | 92,0% | 87,8% | 81,3% | 80,6% | 82,6% |
| Perspektif | 50 | 91,4% | 91,2% | 84,4% | 81,8% | 84,6% |
| Işık | 50 | 92,9% | 93,0% | 84,0% | 83,3% | 89,8% |
| Çekim etkisi | 50 | 91,9% | 93,0% | 87,2% | 84,8% | 89,8% |
| Birleşik | 50 | 90,3% | 83,3% | 71,1% | 71,0% | 81,4% |
| Bütün türevler | 250 | 91,7% | 89,8% | 81,8% | 80,5% | 85,7% |

## Sentetik çizimler

70 kaynak görüntü, birden çok çizim stilini de içerir; bağımsızlık birimi görüntü yerine temel plan grubudur.

| Koşul | Görüntü | Bölge F1 | Kapı F1 | Açıklık F1 | Doğru bağlantı F1 | Doğru bağlı kapı F1 |
|---|---:|---:|---:|---:|---:|---:|
| Özgün kaynak | 70 | 94,6% | 69,3% | 67,8% | 64,8% | 67,0% |
| Döndürme | 70 | 91,9% | 54,0% | 49,8% | 48,9% | 52,8% |
| Perspektif | 70 | 90,2% | 52,8% | 53,9% | 52,3% | 50,6% |
| Işık | 70 | 93,4% | 69,2% | 65,3% | 62,4% | 66,3% |
| Çekim etkisi | 70 | 93,2% | 70,3% | 67,4% | 65,9% | 68,9% |
| Birleşik | 70 | 90,8% | 49,6% | 50,3% | 49,0% | 48,4% |
| Bütün türevler | 350 | 91,9% | 60,0% | 58,0% | 56,3% | 58,2% |

## Precision, recall ve F1

| Grup | Koşul | Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |
|---|---|---|---:|---:|---:|---:|
| İnsan | Özgün kaynak | Bölge konumu | 140 / 153 / 144 | 91,5% | 97,2% | 94,3% |
| İnsan | Özgün kaynak | Kapı türü + konumu | 62 / 65 / 67 | 95,4% | 92,5% | 93,9% |
| İnsan | Özgün kaynak | Tüm açıklıklar | 100 / 104 / 119 | 96,2% | 84,0% | 89,7% |
| İnsan | Özgün kaynak | Doğru bağlantı | 98 / 104 / 111 | 94,2% | 88,3% | 91,2% |
| İnsan | Özgün kaynak | Doğru bağlı kapı | 60 / 65 / 65 | 92,3% | 92,3% | 92,3% |
| İnsan | Bütün türevler | Bölge konumu | 664 / 728 / 720 | 91,2% | 92,2% | 91,7% |
| İnsan | Bütün türevler | Kapı türü + konumu | 281 / 291 / 335 | 96,6% | 83,9% | 89,8% |
| İnsan | Bütün türevler | Tüm açıklıklar | 427 / 449 / 595 | 95,1% | 71,8% | 81,8% |
| İnsan | Bütün türevler | Doğru bağlantı | 404 / 449 / 555 | 90,0% | 72,8% | 80,5% |
| İnsan | Bütün türevler | Doğru bağlı kapı | 264 / 291 / 325 | 90,7% | 81,2% | 85,7% |
| Sentetik | Özgün kaynak | Bölge konumu | 344 / 365 / 362 | 94,2% | 95,0% | 94,6% |
| Sentetik | Özgün kaynak | Kapı türü + konumu | 147 / 176 / 248 | 83,5% | 59,3% | 69,3% |
| Sentetik | Özgün kaynak | Tüm açıklıklar | 186 / 217 / 332 | 85,7% | 56,0% | 67,8% |
| Sentetik | Özgün kaynak | Doğru bağlantı | 178 / 217 / 332 | 82,0% | 53,6% | 64,8% |
| Sentetik | Özgün kaynak | Doğru bağlı kapı | 142 / 176 / 248 | 80,7% | 57,3% | 67,0% |
| Sentetik | Bütün türevler | Bölge konumu | 1675 / 1835 / 1810 | 91,3% | 92,5% | 91,9% |
| Sentetik | Bütün türevler | Kapı türü + konumu | 567 / 650 / 1240 | 87,2% | 45,7% | 60,0% |
| Sentetik | Bütün türevler | Tüm açıklıklar | 719 / 821 / 1660 | 87,6% | 43,3% | 58,0% |
| Sentetik | Bütün türevler | Doğru bağlantı | 698 / 821 / 1660 | 85,0% | 42,0% | 56,3% |
| Sentetik | Bütün türevler | Doğru bağlı kapı | 550 / 650 / 1240 | 84,6% | 44,4% | 58,2% |

## Kaynak çizimin train / validation / test ayrımı

Türevler kaynak insan çiziminin önceki grup ayrımını devralır. Bu, yeni bağımsız test verisi oluşturmaz.

| Kaynak grubu | Koşul | Görüntü | Kapı F1 | Bağlantı F1 |
|---|---|---:|---:|---:|
| train | Özgün kaynak | 35 | 92,1% | 92,2% |
| train | Bütün türevler | 175 | 89,6% | 83,8% |
| validation | Özgün kaynak | 5 | 94,7% | 88,0% |
| validation | Bütün türevler | 25 | 98,0% | 83,5% |
| test | Özgün kaynak | 10 | 100,0% | 88,9% |
| test | Bütün türevler | 50 | 83,0% | 62,3% |

## Aynı kaynakla eşleştirilmiş farklar

Farklar yüzde puandır. %95 aralıklar 5.000 temel plan grubu düzeyinde bootstrap ile hesaplanır; aynı planın stilleri ve özgün/türev çiftleri birlikte tutulur. Yeni yazara genelleme aralığı değildir.

| Grup | Dönüşüm | Bağlantı F1 farkı | Eşleştirilmiş %95 aralık |
|---|---|---:|---:|
| human | Döndürme | -10,6 | -20,3 … -2,9 |
| human | Perspektif | -9,4 | -15,6 … -3,8 |
| human | Işık | -7,8 | -13,9 … -2,3 |
| human | Çekim etkisi | -6,4 | -12,4 … -1,7 |
| human | Birleşik | -20,2 | -29,0 … -12,1 |
| synthetic | Döndürme | -15,9 | -22,2 … -9,9 |
| synthetic | Perspektif | -12,6 | -20,5 … -4,3 |
| synthetic | Işık | -2,5 | -7,3 … +1,7 |
| synthetic | Çekim etkisi | +1,1 | -2,0 … +4,0 |
| synthetic | Birleşik | -15,8 | -24,9 … -6,9 |

## Yorum ve kalan sınırlar

- İnsan çizimleri: bağlantı açısından en düşük koşul **Birleşik**, F1 91,2% → 71,0%. Bu koşul sonraki geliştirme ve hata incelemesinde öncelikli adaydır.
- Sentetik çizimler: bağlantı açısından en düşük koşul **Döndürme**, F1 64,8% → 48,9%. Bu koşul sonraki geliştirme ve hata incelemesinde öncelikli adaydır.
- Dönüşümler şekil veya çekim dayanıklılığını ölçer; yeni bir mimari planı anlama ve yeni yazara genelleme başarısını ölçmez.
- İnsanlarda 50 kaynağın 42’sinde bölge referansı vardır: bölge metriği özgünlerde 42, türevlerde 210 görüntü üzerinden hesaplanır. Boş/eksik referans %100 başarı sayılmaz. Doğru bağlı kapı recall paydasında sahipliği belirli 65 kaynak kapı kullanılır; konum metriğinde 67 kapı vardır.
- Maskeler ayrı çizim örnekleri değildir. Mevcut maskeler duvar, söve ve metin renderer katmanlarıdır; tam model çıktısı için altı kanallı yoğun referans oluşturmaz. Bu çalışmada piksel Dice/IoU iddiası yoktur.
- Referansla eşleşmeyen bağlantı fiziksel olarak kesin yanlış demek değildir; insan referansları yaklaşık ve yeni manuel kontrol yapılmamıştır.
- Perspektif altında kutu IoU’nun sınırlılığı vardır; metrik santimetre veya kusursuz poligon geometrisi testi değildir.
- Çalışma süreleri CPU üzerinde seri ve ısınmış modelle ölçülmüştür; canlı servis yük testi değildir.
- Bozulmalara özel parametre veya model değişikliği yapılmadı. Bu rapor teşhis amaçlıdır; iyileştirme etkisi ayrı bir deneyle ölçülmelidir.

## Doğrulama ve çıktılar

720 tahmin arşivi ve 2.160 öneri belgesi doğrulandı; tamamı kullanıcı onayı bekliyor. Çalıştırma hatası yok. 5.782 korunan dosya değişmedi. Kaynak/model/veri hash kontrolleri ve örnek sayıları `verification.json` ve `analysis_verification.json` içindedir. Dönüşüm ve yanlış sahiplik kontrolleri için 3 otomatik değerlendirme testi geçti.

- `report.json`: tüm örnekler ve grup sonuçları
- `metrics.csv`: precision / recall / F1
- `paired.csv`: örnek başına özgün–türev farkları
- `gallery.html`: en büyük 20 bağlantı kaybının görüntü karşılaştırması
- `paired_intervals.json`: temel plan grubu bootstrap farkları
- `protocol.json`, `source_snapshot/`: sabitlenen protokol ve kaynaklar
- `predictions/`: sıkıştırılmış üretim önerileri, birincil authoring belgesi ve görüntü ön izlemeleri
