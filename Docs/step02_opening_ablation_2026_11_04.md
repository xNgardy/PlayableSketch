# Sabit maskelerle dört kollu kapı decoder deneyi

Tarih: 4 Kasım 2026. Deney tamamlandı. Üretim decoder kodu, varsayılan model ve deneysel aday manifesti değiştirilmedi. Yeni eğitim veya model çıkarımı yapılmadı.

**Ana sonuç:** Yerel duvar takibi eski testte açıklık konumunu 8/20 → 13/20, owner referansıyla doğrulanabilen doğru bağlantıyı 7/19 → 12/19 yükseltti. Yalnızca endpoint-pair adayları eklemek sonuçları değiştirmedi; birleşik kol yalnızca takiple geometri bakımından da aynı sonucu verdi.

## Deney tasarımı

- Kontrol: mevcut decoder 2.4.
- A: mevcut öneriler + öğrenilmiş endpoint haritasından komşu uç çiftleri. Fiziksel kanıt mevcut sabit eksende örneklenir.
- B: mevcut öneriler + sınırlı yerel duvar yoluyla bulunan boşluklardan kapı adayları.
- A+B: her iki ek aday kaynağı.
- Mevcut öneriler her kolda önceliklidir ve korunur. Dolayısıyla eski önerilerin kaybolmaması tasarımın bir özelliğidir; tek başına bağımsız başarı göstergesi değildir.
- Bölge kutuları ve kabul eşikleri sabit. Yeni yol yalnızca ek kapı önerir; açık geçişleri değiştirmez. İnceleme/kullanıcı onayı pending kalır.

Yerel yol, yönlü morfolojik structural maskede sabit eksene yakın gözlemleri bulur; 7 gözlemlik median, eksen çevresinde sınırlı arama ve piksel başına eğim sınırıyla ara değerler üretir. Ara değer yalnızca kanıt arama şeridinin konumudur; duvar mürekkebi veya kapı kanıtı üretmez. Her uçta mevcut raw tick kontrolü ve mevcut model/strong-raw kuralları çalışır.

## Ön kontrol ve protokol

Önce 5 validation + 6 sentetik wavy örnekte çalıştırıldı. Tüm kollar validation 11/14 doğru bağlantı, sentetik 15/16 doğru bağlantı ve sıfır yanlış sentetik bağlantı verdi. Daha sonra aynı kod/politikayla 50 insan + 60 sentetik tam karşılaştırma yapıldı. Tam sonuçlara bakılarak eşik veya algoritma ayarı yapılmadı.

İlk pilot klasöründeki süre ölçümü yalnızca kontrol kolunda eksik kapsam içeriyordu. Karşılaştırılabilir opening decode + authoring süresiyle pilot_final tekrarlandı; doğruluk sonuçları aynı kaldı. Full ile pilot_final kod hashleri ve politikaları aynı. Süreler model/region decode içermeyen cached-mask deney süreleridir.

## Eski test — 10 plan

| Kol | Doğru bölge | Açıklık konumu | Doğru owner bağlantısı | Konumla eşleşmeyen yeni öneri |
|---|---:|---:|---:|---:|
| control | 24/26 | 8/20 | 7/19 | 0 |
| A_endpoints | 24/26 | 8/20 | 7/19 | 0 |
| B_tracking | 24/26 | 13/20 | 12/19 | 0 |
| AB_combined | 24/26 | 13/20 | 12/19 | 0 |

Data 5 açıklığının owner referansı bilinmiyor; 13 konum eşleşmesinin tamamının bağlantısı doğrulandı denmiyor. Region skoru referansı olan 8/10 planı kapsıyor. Bölge önerileri tüm kollarda aynı: 28 önerinin 24’ü referansla eşleşiyor.

## Diğer kümeler

| Küme | Kontrol doğru bağlantı | B / A+B doğru bağlantı |
|---|---:|---:|
| Train (eğitim uyumu) | 58/78 | 64/78 |
| Validation | 11/14 | 11/14 |
| Sentetik 60 | 133/160 | 133/160 |

Sentetik exact topology tüm kollarda 30/60, yanlış bağlantı 1 olarak kaldı (önceden bulunan 2001_stray). Sentetik precision yaklaşık %99.25. Yeni yanlış sentetik bağlantı oluşmadı. İnsanlarda konumla eşleşmeyen öneriler train 2, validation/eski test 0 olarak kaldı; eşleşen ve owner referansı olanlarda yeni yanlış owner oluşmadı. Bu, yaklaşık insan referansları üzerinde ölçümdür; bağımsız exact-topology doğrulaması değildir.

## Somut kurtarılan örnekler

- Data 23: eski boşluk y=280–386 yerine yerel takipte 280–300. Uçlar y=279 ve 301, iki yönde duvar desteği 1.0. İkinci model endpoint yanıtı hâlâ zayıf; kapı mevcut strong paired-raw kuralıyla geçiyor. Bu nedenle bu kapıyı bulmak için ikinci ucu yeniden eğitmek zorunlu olmadı.
- Data 25: iki kapı da bulundu. Yerel boşluklar y=204–240 ve 278–306; iki uçta da gerçek tick ve duvar kanıtı mevcut.
- Data 31: iki kapı da bulundu. Yerel boşluklar y=227–249 ve 260–293. İlk kapıda bir tarafın duvar desteği 0.625; mevcut 0.6 koşulunu geçiyor, mevcut model-tick desteği de var.
- Eğitim grubunda Data 24, 35, 37, 40, 41, 50 için birer ek doğru bağlantı bulundu. Eğitim sonucu genelleme kanıtı değildir.

Yalnızca endpoint adayları, mevcut sabit fiziksel kanıt şeridinin hatasını gideremedi. Birleşik kolun B ile aynı olması bu uygulamada uç çiftlerinin ek kazanım getirmediğini gösterir; bütün endpoint-first yaklaşımlarının yararsız olduğunu göstermez.

## Kalan işler ve sınırlar

- Eski testte kaçan 7 açıklık açık geçişler: Data 47 cH nedeniyle 4, Data 48 cV1 nedeniyle 2, Data 48 g005 fiziksel boşluk izdüşümü nedeniyle 1.
- Validation’da Data 8’in iki bölge/bağlantı sorunu ve Data 43 g004 ortak sınır/open-interface sorunu sürüyor.
- Açık geçiş algılaması bu deneyde değiştirilmedi; bölgeler de kurtarılmadı.
- Bu veri geçmişte incelenmiş geliştirme koleksiyonu. Yeni yazar/kör test başarısı ve kullanıcı düzeltme süresi bilinmiyor.
- Mevcut çıktıları koruyarak aday ekleme, yanlış bir eski öneriyi düzeltmez; mevcut sentetik yanlış bağlantı korunuyor.

## Doğrulama

- 110 kontrol replay’i kayıtlı decoder 2.4 çıktısıyla aynı.
- 440 authoring çıktısı contract doğrulamasından geçti; bölgeler aynı ve acceptance pending.
- A kontrolle, A+B ise B ile 110 örneğin tamamında geometri bakımından eşit.
- 550 cached girdi ve korunan kaynak/config/model/manifest hashleri değişmedi.
- 26 benzersiz test geçti: 6 yeni kapı deneyi, 9 region recovery, 11 refined decoder testi. Negatiflerde işaretsiz kırık ve kesintisiz tickli duvar; pozitiflerde eğri duvar ve zayıf ikinci endpoint kontrol edildi.
- Browser veya yeni gerçek-model worker QA yapılmadı. Deney üretim worker’ına bağlanmadı.

## Çıktılar ve sonraki karar

Nihai sonuç: `Saved/ShapeFirst/dinov2/opening_ablation/v1/full/` altında report.json, freeze.json, verification.json, tests.log, gallery.html ve her örneğin dört kolu.

Öneri: B kolu, sonraki kontrollü entegrasyon için en sade aday. Bu çalışmada üretime alınmadı. Sonraki kalite çalışması eksik koridorlar ve açık geçişlere odaklanmalı; endpoint-first ek karmaşıklığı bu karşılaştırmada kazanım vermedi.

Tekrar çalıştırma (yeni bir çıktı dizini seçilmeli):

    PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.evaluate_opening_ablation --subset validation --output Saved/ShapeFirst/dinov2/opening_ablation/new-pilot
    PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.evaluate_opening_ablation --subset all --output Saved/ShapeFirst/dinov2/opening_ablation/new-full
