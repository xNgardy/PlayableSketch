# Koridor geometrisi geliştirmesi — 6 Kasım 2026

İlk geometri geliştirmesi kodlandı ve ölçüldü. Yeni 20 gerçek çizimde çevrili alan adayı bölge eşleşmesini 54/82'den 73/82'ye, tamamlanmış doğru kapıyı 9/32'den 17/32'ye, tür/konum/sahiplik birlikte doğru bağlantıyı 9/58'den 28/58'e çıkarıyor. Bunlar referans bilgisi tahmine verilmeden, aynı donmuş model olasılıkları ve mevcut kapı kabul kurallarıyla elde edildi. Yeni eğitim yok.

**Üretime alınmadı.** Doğrulamadaki eşleşmeyen bağlantı sayısı 3→4 arttığından önceden kaydedilen koruma kuralı adayı reddetti, `baseline` seçildi. Daha iyi toplam puan bu sınırı geçersiz kılmadı. Data_63 ve Data_69 çözülmüş değildir. Bu sonuçlar aynı kullanıcının önceden görülmüş geliştirme verisindedir; bağımsız çizer/kör test/genelleme başarısı değildir.

## Uygulanan değişiklik

Kod `SketchPipeline/shape_authoring/corridor_geometry.py` içinde ayrı bir deney modülüdür. `propose.py`, servis, varsayılan decoder, aktif ağırlıklar ve Unreal akışı değişmedi.

1. Ham fotoğraf kontrastındaki küçük kâğıt dokusu bileşenleri ayıklanır. Gerçek çizginin çevrelediği iç alanlar çıkarılır. Sınırlı çevre kapatma seçenekleri görüntü ve mevcut tahmin odalarının merkez desteğiyle seçilir; referans etiket okunmaz. Büyük açık çevrede tahminden vazgeçilebilir.
2. İç alanın mesafe dönüşümündeki geniş çekirdekler oda adayları verir. Kesişen ışınlardan oda kenarları bulunur. Desteklenen model odaları da çapa olarak korunabilir.
3. Odalar çıkarıldıktan sonra kalan dar şeritler yatay/dikey parçalara ayrılır. Uzun morfolojik filtre yönü bulur; tam kesitler eğik çizginin kırpılmasını azaltır. Mürekkep duvarla ayrılmayan paralel bantlar birleştirilebilir.
4. L dirsekleri örtüşmeyen ayrı dikdörtgenlere bölünür. Şeritler oda yüzlerine oturtulur. İki oda arasında rota oluşturmayan dallar elenir. Bu, Data_68'de dış boşluğa eklenen altı koridoru kaldırdı.
5. Kapı/açık geçiş kanıtları mevcut üretim fonksiyonlarıyla yeniden çalıştırılır. Yeni koridorlar mevcut `add_observed_passages` fiziksel ek kontrolünden geçer; yeni kabul eşiği eklenmedi, kapı modeli eğitilmedi. Önceki kapı/açıklık kaybolursa veya yüksek model yanıtlı, dört kenarı görüntüyle desteklenen bir oda kaybolursa tüm eski belge korunur. Bu kontrol referans kullanmaz; yanlış baseline önerilerinin bir bölümünü de koruyabildiği için sınırlıdır.
6. Ayrı `hybrid` kolu eksik çevrelerde mevcut paralel-duvar kurtarmasını ekler. Son turda ana ölçümler `enclosure` ile aynı kaldı; ek karmaşıklık lehine ölçülmüş kazanım yok.

Çalışma görüntüsü/512 kanıt dönüşümü kayıtlı matrisle yapılır. Aynı kanıt görüntüsü, aynı aktif DINO checkpoint'i ve float32 önbellekler kullanıldı. Özgün fotoğrafın daha yüksek çözünürlüğünde yeni model çağrısı yapılmadı; mevcut modele çıkarım/eğitim yaptırılmadı.

## Deney ve seçim

50 eski gerçek + 20 yeni gerçek + 60 sentetik = 130 örnek, üç yöntem. Her aday `validate_authoring` kontrolünden geçti. Önce 5 eski gerçek, 4 yeni gerçek ve önceden atanmış 6 sentetik doğrulama örneğinin tahminleri kaydedildi, ardından etiketler yalnız skorlama için okundu. Seçim kaydedildikten sonra tam denetim çalıştırıldı. Eğitim/validation/test toplamları ayrı tutuldu.

Geliştirme geçmişi açıkça kaydedildi: ilk algoritma yeni 12 train çiziminde geliştirildi. v1 doğrulamasındaki hatalar sonrasında v2'de mevcut açıklık/oda kaybı kontrolü ve tam kesit yerleştirmesi eklendi. Dolayısıyla doğrulama tekrar kullanılmış bir geliştirme kümesidir. v2 denetim/test skorlarından sonra geometri politikası değiştirilmedi; v3 yalnız yanlış görsel başlığını düzeltip aynı sonuçları ve kaynakları yeniden kaydeder. Test skorları seçim sıralamasına katılmadı; önceki çalışmalarda görülmüş veriyi bağımsız test gibi sunmuyoruz.

Koruma koşulları her eski/yeni/sentetik doğrulama grubunda bölge, kapı ve bağlantı F1 kaybı ≤0.02; eşleşmeyen bölge/bağlantı sayısı artamaz. Amaç puanı kapı ve bağlantı F1 ortalamasının eski/yeni/sentetik için 0.4/0.4/0.2 ağırlıklı toplamı; eşitlik baseline'da kalır. Amaç 0.720978→0.755581 artsa da yeni gerçek doğrulamadaki ek eşleşmeyen bağlantı nedeniyle seçim baseline.

## Metriklerin sınırı

Bölge bounding-box IoU ≥0.5; eşleme türden bağımsızdır, dolayısıyla doğru oda/koridor türünün tek başına kanıtı değildir. Açıklık eşlemesi aynı tür ve iki uçta en büyük hata ≤çalışma kenarının %4'ü; yeni 20 çizimde tolerans 10.24 çalışma pikseli. Doğru bağlantı ayrıca doğru referans sahipliği gerektirir. Yeni gerçeklerde tekil bölge çiftleri; eski gerçek/sentetikte önceki değerlendirmeyle uyumlu açıklık bazlı bağlı bağlantılar kullanılır. Gruplar ayrı raporlanır, karışık bir genel bağlantı accuracy'si verilmez. Bölge referansı bulunmayan eski çizimler bölge paydasına katılmaz.

Eşleşmeyen bağlantı = üretilen−tür/konum/sahiplik birlikte eşleşen. **Fiziksel olarak yanlış bağlantı kanıtı değildir.** Yeni gerçek referans sahipliği yapısal etiketlerin açık entity_ids alanından, eski gerçek referansı önceki yaklaşık yakınlık politikasından gelir. Eski false_connections=0 sayacı kullanılmadı. Bu çalışmada `Data_63 g003` için önceki fotoğraf denetimindeki tek uç düzeltmesi yalnız skorlama referansında kullanıldı; geometriye veya kapı adayına hiçbir referans verilmedi. Etiketler ve eğitim hedefleri değiştirilmedi.

## Yeni gerçek train — 12 çizim

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 31/44/45 | 0.705/0.689/0.697 | 5/19 | 6/9/31 | 0.667/0.194/0.300 | 3 |
| Çevrili alan adayı | 42/45/45 | 0.933/0.933/0.933 | 11/19 | 16/19/31 | 0.842/0.516/0.640 | 3 |
| Aday + paralel duvar kurtarma | 42/45/45 | 0.933/0.933/0.933 | 11/19 | 16/19/31 | 0.842/0.516/0.640 | 3 |

## Yeni gerçek validation — 4 çizim

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 12/17/18 | 0.706/0.667/0.686 | 4/10 | 2/5/13 | 0.400/0.154/0.222 | 3 |
| Çevrili alan adayı | 14/18/18 | 0.778/0.778/0.778 | 5/10 | 3/7/13 | 0.429/0.231/0.300 | 4 |
| Aday + paralel duvar kurtarma | 14/18/18 | 0.778/0.778/0.778 | 5/10 | 3/7/13 | 0.429/0.231/0.300 | 4 |

## Yeni gerçek test — 4 çizim

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 11/19/19 | 0.579/0.579/0.579 | 0/3 | 1/4/14 | 0.250/0.071/0.111 | 3 |
| Çevrili alan adayı | 17/21/19 | 0.810/0.895/0.850 | 1/3 | 9/10/14 | 0.900/0.643/0.750 | 1 |
| Aday + paralel duvar kurtarma | 17/21/19 | 0.810/0.895/0.850 | 1/3 | 9/10/14 | 0.900/0.643/0.750 | 1 |

## Yeni gerçek toplam — betimleyici

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 54/80/82 | 0.675/0.659/0.667 | 9/32 | 9/18/58 | 0.500/0.155/0.237 | 9 |
| Çevrili alan adayı | 73/84/82 | 0.869/0.890/0.880 | 17/32 | 28/36/58 | 0.778/0.483/0.596 | 8 |
| Aday + paralel duvar kurtarma | 73/84/82 | 0.869/0.890/0.880 | 17/32 | 28/36/58 | 0.778/0.483/0.596 | 8 |

Toplam eşleşmeyen bölge 26→11, eşleşmeyen bağlantı 9→8 düşüyor. Ancak validation bağlantıları özelinde 3→4 artış var; toplam kazanım bunu örtmüyor. Kaçan bağlantılar toplamda 49→30. Bölge sayısı 80→84 artmasına rağmen doğru eşleşme 54→73 arttığı için artan her bölge yanlış sayılmamalı. Kapı precision bütün kollarda 1.0, enclosure recall 0.281→0.531, F1 0.439→0.694; aynı veri/tolerans sınırlamaları geçerli.

## Eski gerçek test koruması

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 26/30/26 | 0.867/1.000/0.929 | 12/12 | 16/17/19 | 0.941/0.842/0.889 | 1 |
| Çevrili alan adayı | 26/30/26 | 0.867/1.000/0.929 | 12/12 | 16/17/19 | 0.941/0.842/0.889 | 1 |
| Aday + paralel duvar kurtarma | 26/30/26 | 0.867/1.000/0.929 | 12/12 | 16/17/19 | 0.941/0.842/0.889 | 1 |

12/12 kapı ve 16/19 sahipliği doğru açıklık korundu. Üretilen 17 açıklık, 16 doğru sahiplikli açıklık ve 16 tekil bağlantı farklı sayım birimleridir; önceki rapordaki tekil bağlantı sayısıyla çelişki gibi okunmamalıdır. Eski gerçeklerde yaklaşık sahiplik/eksik etiket sınırlaması sürer.

## Sentetik kontrol — 60 örnek

| Yöntem | Bölge doğru/üretilen/ref. | Bölge P/R/F1 | Kapı doğru/ref. | Bağlantı doğru/üretilen/ref. | Bağlantı P/R/F1 | Eşleşmeyen bağlantı |
|---|---:|---|---:|---:|---|---:|
| Mevcut | 174/204/180 | 0.853/0.967/0.906 | 123/130 | 141/142/160 | 0.993/0.881/0.934 | 1 |
| Çevrili alan adayı | 171/198/180 | 0.864/0.950/0.905 | 123/130 | 141/142/160 | 0.993/0.881/0.934 | 1 |
| Aday + paralel duvar kurtarma | 171/198/180 | 0.864/0.950/0.905 | 123/130 | 141/142/160 | 0.993/0.881/0.934 | 1 |

123/130 kapı, 141/160 doğru bağlı açıklık ve 1 eşleşmeyen bağlantı korundu. Bölge referans eşleşmesi 174→171 düştü; üretilen bölge 204→198, F1 0.90625→0.90476. Sentetikte bölge recall'ının tamamen korunduğu iddia edilmez. Doğrulama koruma toleransını geçse de bu kalan risk kayda alındı.

## Çizim bazında görsel denetim

20 son karşılaştırma görseli açılıp incelendi. Mavi oda, kahve koridor, yeşil kapı, mor açık geçiştir. Sağ panel deneysel adayı gösterir; seçilmediği halde üretim çıktısı gibi etiketlenmez.

| Çizim | Doğru bölge önce→sonra | Doğru kapı önce→sonra | Doğru bağlantı önce→sonra | Not |
|---|---:|---:|---:|---|
| Data_51 | 3→3 | 1→2 | 1→2 | Üst kapı tamamlandı; 2/2 kapı. |
| Data_52 | 2→3 | 0→1 | 0→2 | Eksik düz koridor bulundu; kapı ve açık bağlantı eşleşti. |
| Data_53 | 2→3 | 0→0 | 0→0 | İnce uzun koridor bulundu. Kapılar hâlâ tamamlanmıyor; geometri kazanımı kapı başarısı diye sayılmadı. |
| Data_54 | 3→3 | 2→2 | 2→2 | Mevcut açıklık kaybı kontrolü nedeniyle baseline korundu. |
| Data_55 | 2→4 | 0→0 | 0→1 | L iki parçaya ayrıldı; iki yanlış oda kaldırıldı. Referans geometrisinde dört bölge eşleşiyor; açık bağlantıların yalnız biri eşleşiyor. |
| Data_56 | 3→4 | 0→0 | 0→1 | L parçaları bulundu; fiziksel/semantik kapı reddi sürüyor. |
| Data_57 | 2→4 | 0→1 | 0→1 | L parçaları ve alt kapı bulundu; fazladan oda kaldırıldı. |
| Data_58 | 2→4 | 0→1 | 0→1 | İki koridor bölgesi de eşleşiyor. Üst bağlantı doğru çiftte fakat kapı yerine açık geçiş; ek eşleşmeyen doğrulama kaydı bu. |
| Data_59 | 4→4 | 2→2 | 3→3 | İki kapı ve üç bağlantı korundu; fazladan oda kaldırıldı. |
| Data_60 | 2→4 | 0→0 | 0→2 | L geometrisi bulundu; üç açık bağlantının ikisi eşleşti. |
| Data_61 | 2→4 | 0→0 | 0→1 | Üç koridor parçası çıkarıldı fakat yatay parça fazla geniş. Bölge eşleşmesi 4/5; yalnız bir tür/sahiplikli bağlantı eşleşti. |
| Data_62 | 3→5 | 0→0 | 1→4 | U yolu üç parçayla bulundu; dört açık bağlantı eşleşti. |
| Data_63 | 3→3 | 0→0 | 0→0 | T yapısı çözülmedi; desteklenen mevcut oda kaybı kontrolü baseline döndürdü. |
| Data_64 | 4→4 | 2→2 | 0→0 | Mevcut kapı/açıklık kaybı kontrolü baseline döndürdü. Merkez geometri sorunu sürüyor. |
| Data_65 | 3→5 | 1→4 | 1→4 | Orta oda ve iki koridor bulundu; dört kapı ve dört bağlantı eşleşti. |
| Data_66 | 3→3 | 0→0 | 0→0 | Desteklenen mevcut oda kaybı kontrolü baseline döndürdü. Bu örnek için iyileşme yok. |
| Data_67 | 3→3 | 1→1 | 1→1 | Üst kapı korundu; kapalı alt sınırda geçiş üretilmedi. |
| Data_68 | 2→2 | 0→0 | 0→0 | Altı yanlış CV koridoru kaldırıldı; iki oda kaldı ve bağlantı üretilmedi. |
| Data_69 | 3→3 | 0→0 | 0→0 | Eksik çevre kapatma ve oda kaybı nedeniyle baseline korundu; L sorunu sürüyor. |
| Data_70 | 3→5 | 0→1 | 0→3 | Gerçek L yolu bulundu; sağ üst bağımsız oda ayrı kaldı. Bir kapı ve üç bağlantı eşleşti. |

## Yayına geçişi durduran somut örnek

Data_58'de dört bölgenin tamamı artık referansla eşleşiyor. Üst oda–dik koridor çifti doğru, açıklığın konumu tolerans içinde, fakat çıktı `open_passage`; referans `door`. Alt kapı doğru. Bu nedenle ana metrik 1 doğru/2 üretilen bağlantı, 1 eşleşmeyen bağlantı sayıyor. Türden bağımsız yalnız bölge-çifti grafiğinde iki bağlantı da doğru; bu ek kontrol `type_agnostic_graph_audit.json` içinde bulunur. **Ana seçim metriği veya eşiği sonucu geçirtmek için değiştirilmedi.**

Bu bulgu, geometri ilerlemesinin kapı/açık geçiş yorumunu otomatik çözmediğini gösteriyor. Yeni bir hayali fiziksel geçiş bulduğumuz iddiası yok; açıklık türü hatası halen gerçek bir kabul hatasıdır. Sonraki dar iş, bu üst kapı ve Data_61'deki tür/öncelik çakışmasının mevcut fiziksel kanıtla çözülmesidir. Ardından aynı koruma koşulları tekrar uygulanmalıdır.

Data_63, Data_64, Data_66 ve Data_69'da korumalar baseline'a dönüyor; bu örnekler çözüldü sayılmaz. Eğik duvarları tek dikdörtgene yansıtmak, eksik dış çevre ve T kolunu ayırmak kalan geometri sınırlarıdır. Data_53'te koridor bulundu ama iki kapı hâlâ başarısız. Data_61'in yatay koridoru fazla geniş; yüksek bölge toplamı bunu gizlememeli.

## Kontroller ve teslim

- 58 ilgili test geçti; 8'i yeni geometri testi. Boş görüntüde çekimser kalma, ayrık kapalı odalara koridor eklememe, ince uzun koridor, L dirseğinin örtüşmeyen iki parçası, tek odaya bağlı dalı eleme, dış boşluğu reddetme, mevcut açıklığı kaybetmeme ve kabulün pending kalması kontrol edildi.
- 130×3 tam denetim + 15×3 doğrulama = 435 geçerli sözleşme belgesi. 155 korunan dosya hash'i değişmedi. Aktif model, eski kaynaklar, 20 fotoğraf/etiket ve servis dosyaları korundu. Yeni test/kod/rapor dosyaları bu çalışmanın ekleridir.
- `protocol.json`, `source_snapshot`, `verification.json`: model/önbellek/kaynak sürümleri ve seçim kaydı. `selection.json` her koruma koşulunu gösterir. `report.json`, `metrics.csv` bütün ölçümleri içerir. `image_review.json` görsel notlar; `unmatched_openings.json` eşleşmeyen açıklıkların tür/konum/sahiplik ayrımıdır.
- `gallery.html`: 20 karşılaştırma; her çizimde enclosure ve hybrid PNG/JSON'ları ve aday maskeleri bulunur. v1/v2 korunmuş ara deneyler, nihai teslim v3'tür.
- Süre alanları önbellek sonrası işlemleri ölçer; model çıkarım veya servis gecikmesi değildir. Ağırlık yükleme, yeni eğitim ve servis uçtan uca testleri bu çalışmanın parçası değildir.
- Her belge öneridir; otomatik kullanıcı onayı yok. Üretime entegrasyon, servis yeniden başlatma, aktif model değişimi yapılmadı.

Yeniden çalıştırma (proje kökünden, yeni çıktı klasörü seçerek):

```sh
PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python \
  -m SketchPipeline.shape_authoring.evaluate_corridor_geometry \
  --output Saved/ShapeFirst/corridor_geometry/NEW_RUN
```

Deney modülü: `SketchPipeline/shape_authoring/corridor_geometry.py`.
Değerlendirici: `SketchPipeline/shape_authoring/evaluate_corridor_geometry.py`.
Testler: `SketchPipeline/tests/test_corridor_geometry.py`.
