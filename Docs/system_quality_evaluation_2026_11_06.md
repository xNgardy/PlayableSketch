# PlayableSketch yeni sistem — kalite değerlendirmesi

## Sonuç

Sistem oda/bölge bulmada güçlü; darboğaz eksik koridorlar, kaçırılan kapılar ve açıklıkların doğru bölgelere bağlanması. Yeni 20 çizimde kapı türü/konum F1 %74,5 iken doğru bölgelere bağlı kapı F1 %66,7 ve doğru bağlantı F1 %63,8. Tam otomatik kullanım başarısı bu nesne oranlarından çıkarılamaz.

## Değerlendirme kapsamı

- 130 çizim: eski 50 insan çizimi, yeni 20 insan çizimi, 60 sentetik kontrol.
- Son sistem ve iki önceki yöntem için kaydedilmiş 390 tahmin belgesi yeniden puanlandı; önceki raporla birebir eşitlik doğrulandı. Yeni model çıkarımı veya eğitim yapılmadı.
- Model/kaynak/veri hash’leri doğrulandı. Aynı yazarın daha önce incelenmiş verileridir; yeni yazar veya bağımsız kör test sonucu değildir.
- Bunlar DINO + geometri + kapı/geçit kuralları içeren bütün sistemin sonuçlarıdır. Ham segmentasyon ağının piksel Dice/IoU başarısı veya model güveninin kalibrasyonu ölçülmemiştir.

## Metriklerin anlamı

Precision = doğru tahmin / bütün tahminler; recall = doğru tahmin / referanstaki bütün öğeler; F1 = 2PR/(P+R). Tablolarda mikro toplama kullanılır: önce çizimler arasındaki sayılar toplanır. Tanımsız 0/0 oranları sıfır veya %100 sayılmaz. Makro F1 ve kapsamı JSON’da ayrıca tutulur.

Bölge eşleşmesi: kutu IoU en az 0,5. Ana bölge metriği oda/koridor türünden bağımsızdır; tür doğruluğu ayrıca ölçülmüştür. Kapı/açıklık eşleşmesi doğru tür ve maksimum çalışma kenarının %4’ü kadar uç konum toleransı ister. Bu, santimetre veya kusursuz geometri testi değildir. Yeni çizimlerde bağlantı metriği, doğru yere eşleşen açıklık üzerinden bağlanan benzersiz bölge çiftidir. Eski insan ve sentetik bağlantı metriği açıklık başına doğru bağlantıdır; bu grupları tek genel bağlantı oranında birleştirmedik.

## Yeni 20 çizim — geliştirme bütünü

Bu grupta 12 train, 4 validation, 4 test çizimi vardır. Tüm grubun sonucu bağımsız test başarısı diye sunulmamalıdır.

| Ölçüm | Doğru / tahmin / referans | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Bölge konumu (türden bağımsız) | 73 / 84 / 82 | 86,9% | 89,0% | 88,0% |
| Kapı türü + konumu | 19 / 19 / 32 | 100,0% | 59,4% | 74,5% |
| Tüm açıklıkların türü + konumu | 33 / 36 / 58 | 91,7% | 56,9% | 70,2% |
| Doğru bölge bağlantısı | 30 / 36 / 58 | 83,3% | 51,7% | 63,8% |
| Bölge (doğru tür + konum) | 71 / 84 / 82 | 84,5% | 86,6% | 85,5% |
| Oda (doğru tür + konum) | 46 / 55 / 46 | 83,6% | 100,0% | 91,1% |
| Koridor parçası (doğru tür + konum) | 25 / 29 / 36 | 86,2% | 69,4% | 76,9% |
| Doğru bölgelere bağlı kapı | 17 / 19 / 32 | 89,5% | 53,1% | 66,7% |

19 kapının tamamı tür/konum ölçütünü geçiyor, ancak yalnızca 17’si doğru iki bölgeye bağlı. Bu nedenle %100 kapı precision değerini %100 işlevsel kapı başarısı olarak yorumlamamalıyız. 32 referans kapının 13’ü bulunamadı; doğru bağlantı sayısı 30/58, kaçırılan bağlantı 28, referansla eşleşmeyen bağlantı 6. Eşleşmeyen öğe, yaklaşık referans nedeniyle fiziksel olarak kesin yanlış demek değildir.

## Eğitim, doğrulama ve test ayrımı

| Yeni çizim bölümü | Çizim sayısı | Bölge F1 | Kapı F1 | Bağlantı F1 |
|---|---:|---:|---:|---:|
| train | 12 | 93,3% | 77,4% | 68,0% |
| validation | 4 | 77,8% | 75,0% | 40,0% |
| test | 4 | 85,0% | 50,0% | 75,0% |

Yeni test yalnızca 4 çizim ve 3 kapı içeriyor: kapı 1/3, bağlantı 9/14. Validation bağlantı F1 %40,0; tek başarılı test grubuna bakarak sistemin genel başarısının %75 olduğu söylenemez. Bu test çizimleri önceki geliştirmede incelendiği için artık el değmemiş bir holdout değildir.

## Eski insan testi ve sentetik kontrol

| Grup | Ölçüm | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| Eski insan testi (10 çizim) | Bölge konumu (türden bağımsız) | 86,7% | 100,0% | 92,9% |
| Eski insan testi (10 çizim) | Kapı türü + konumu | 100,0% | 100,0% | 100,0% |
| Eski insan testi (10 çizim) | Doğru bölge bağlantısı | 94,1% | 84,2% | 88,9% |
| Sentetik kontrol (60 çizim) | Bölge konumu (türden bağımsız) | 86,4% | 95,0% | 90,5% |
| Sentetik kontrol (60 çizim) | Kapı türü + konumu | 100,0% | 94,6% | 97,2% |
| Sentetik kontrol (60 çizim) | Doğru bölge bağlantısı | 99,3% | 88,1% | 93,4% |

Eski testte bölge referansı yalnızca 8/10 çizimde puanlanabilir; referansı olmayan iki çizim başarılı sayılmadı. Sentetik sonuçların insan çizimlerindeki sonuçlardan daha iyi olması, gerçek kullanımın yalnızca sentetik skorla temsil edilemeyeceğini gösteriyor.

## Önceki sistemlere göre ilerleme

Yeni 20 çizimde, aynı eşleştirme ölçütleriyle:

| Ölçüm | Eski temel F1 | Düzeltme öncesi geometri F1 | Son sistem F1 |
|---|---:|---:|---:|
| Bölge konumu (türden bağımsız) | 66,7% | 88,0% | 88,0% |
| Kapı türü + konumu | 43,9% | 69,4% | 74,5% |
| Doğru bölge bağlantısı | 23,7% | 59,6% | 63,8% |

Eski temel yönteme göre kapı F1 +30,6 yüzde puan, bağlantı F1 +40,1 yüzde puan. Son üç parçalı düzeltmenin önceki geometri adayına ek katkısı kapı F1 +5,1 ve bağlantı F1 +4,3 yüzde puan. Ağ ağırlıkları aynı; iyileşme sistemin geometri ve açıklık kararlarından geliyor. Sentetik bölge duyarlılığı eski temel yöntemde %96,7 iken son sistemde %95,0; bu küçük gerileme ayrıca korunuyor.

## Çizim bütünlüğü ve belirsizlik

Yeni 20 çizimin 8’i (%40), mevcut eşleştirme ölçütleri altında tüm bölge türleri, açıklıkları ve bağlantıları eksiksiz eşleştiriyor: Data_51, Data_52, Data_59, Data_62, Data_65, Data_67, Data_68, Data_70. Bu, ölçülü kusursuz plan veya metrik 3B doğruluk değildir. Sentetik 60 çizimin 32’si (%53,3) mevcut exact-topology ölçütünü geçiyor. Yüksek nesne F1, bütün çizimin hatasız çıkmasını garanti etmiyor.

5.000 çizim düzeyinde bootstrap tekrarında, yeni 20 grubunun F1 için %95 aralıkları:

| Ölçüm | F1 | Bootstrap %95 aralığı |
|---|---:|---:|
| Bölge konumu (türden bağımsız) | 88,0% | 78,7%–97,3% |
| Kapı türü + konumu | 74,5% | 52,4%–91,2% |
| Doğru bölge bağlantısı | 63,8% | 43,2%–82,1% |

Aralıklar bu veri kümesindeki çizim değişkenliğini gösterir; yeni yazara genelleme garantisi vermez. Özellikle yeni testin kapı örnek sayısı çok azdır. %100 precision için bootstrap’ın %100 çıkması da gerçek dünyada hata olmayacağı anlamına gelmez.

Uç konum toleransını %4’ten %2’ye sıkılaştırınca tüm açıklık F1 %70,2’den %66,0’a, doğru bağlanan açıklık F1 %63,8’den %59,6’ya düşüyor. Dolayısıyla eksikler yalnızca küçük uç konum kaymalarıyla açıklanmıyor. Eşleşen 33 açıklığın uç hatası medyanı çalışma kenarının %1,11’i, p95’i %2,03; kaçırılan açıklıklar bu konum hatası istatistiğine dahil değildir.

## Geliştirme yönü

1. **Koridorları ve doğru bölge bağlantılarını öncele.** Oda recall %100, koridor parçası recall %69,4. Data_63/64/66/69 toplam 16/28 kaçırılan bağlantıyı ve 9/13 kaçırılan kapıyı içeriyor. Bu örnekler geliştirmenin tanı kümesidir; düzeltmenin başarısı yeni çizimlerle sınanmalı.
2. **Kapı kaçırmayı azaltırken doğru bölgeye bağlanmayı izle.** Sadece kapı konumu precision/recall yeterli değil. Ana takip göstergeleri attached-door F1, bağlantı F1, kaçırılan bağlantı ve eşleşmeyen bağlantı sayısı olmalı. Eşiği düşürmenin tek başına çözüm olduğu bu değerlendirmeden çıkarılamaz.
3. **Bağımsız bir değerlendirme kümesi oluştur.** Farklı yazarlardan yeni çizimler toplanıp test grubu ayar sırasında açılmamalı; oda/koridor türü, kapı uçları ve iki tarafın bölge kimlikleri açık etiketlenmeli. Mevcut testte yalnızca 3 kapı olması güvenilir genelleme değerlendirmesi için yetersiz.
4. **Kullanıcı emeğini ölç.** Çizim başına düzeltme süresi, gereken düzenleme sayısı, tam doğru çizim oranı ve işlem süresi p50/p95 izlenmeli. Bu değerlendirmede kullanıcı düzeltme süresi, boyutsal/cm doğruluk ve uçtan uca 3B çıktı doğruluğu ölçülmedi.

Accuracy/specificity verilmedi: tespit probleminde bütün gerçek negatiflerin tanımlı bir evreni yok. 110 yazılım testinin geçmesi de tahmin doğruluğunun %100 olduğu anlamına gelmez.

## Çıktılar

- Sayısal rapor: `Saved/ShapeFirst/quality_evaluation/v2/report.json`
- Grup ve yöntem CSV: `Saved/ShapeFirst/quality_evaluation/v2/metrics.csv`
- Tekrar puanlama betiği: `Scripts/evaluate_shape_quality.py`
- Tahminlerin kaynağı: `Saved/ShapeFirst/opening_alignment/v2`

Tüm bootstrap tekrarları seed=20261106 ile deterministiktir. Özgün tahminler, model ağırlıkları ve etiketler değiştirilmemiştir.
