# PlayableSketch: 20 gerçek çizimde bileşen teşhisi — 6 Kasım 2026

Ana bulgu: önce bölge/koridor geometrisi ve ortak sınır çıkarımına odaklanmalıyız. Mevcut yöntemin 9/32 doğru kapısı referans sınırlarla 24/32'ye çıkıyor; yalnız kapı ucu müdahalesi 11/32'de kalıyor; ikisi birlikte 28/32. Bu sayılar yeni bir modelin gerçek kullanım başarısı değildir. Referanslı koşullar, aynı kullanıcıdan daha önce görülmüş çizimlerde yapılan teşhis müdahaleleridir.

## Doğrulanan mevcut durum

- Kaynak ve kayıtlı iş yapılandırmaları DINO ağırlığını ve `refined-full`, ink normalization, `shape-decoder/2.8`, `supported-corridors`, `corridor-passages`, `observed-jambs`, `observed-door-jambs/1.5` politikalarını doğruluyor. Decoder'ın çıplak varsayılan çağrısı bu servis seçimleriyle aynı değil.
- 8772 servisi `/api/bootstrap` isteğine yanıt verdi. `/api/health` kaynakta yok. İlk kısıtlı ağ isteğinin başarısız olması servis kapalı demek değildi. Yeni canlı model işi gönderilmedi; mevcut iş ayarları, dosya hash'leri ve önbelleklerden yeniden çalıştırılan decoder doğrulandı. Bellekte yüklü modelin yeni bir çağrıdaki davranışı ayrıca ölçülmedi.
- Yeni veri manifestinde 20 insan fotoğrafı, 60 türev, 12 rehber, 20 karmaşık sentetik kayıt: toplam 112. Veri denetimi bölümler arasında ebeveyn/hash sızıntısı bulmadı. Yeni 20 fotoğraf train/validation/test = 12/4/4; bu çalışma sentetikleri başarı toplamına katmıyor.
- Önceki ensemble seçimi dosyalarda baseline; doğrulamada 26 kapı/28 bağlantı. Eski test 12 kapı/16 bağlantı; yeni test 0 kapı/1 bağlantı; sentetik baseline 123 kapı/141 bağlantı. v3 mevcut kolların dosyalarını v2'den kullanıyor: v3 altında her kol için ayrı baseline dosyası yok. Bu beklenen dosya düzeni farkı kaydedildi.
- Kodda gece modu, düzenlenebilir otomatik bölge adları ve onaydan önce geometry/gameplay seçimi var. Unreal Pawn hareketi kameranın sağ/yukarı vektörlerinden hesaplanıyor. Ön işleme EXIF dönüşümü ve sınırlı küçük açı düzeltmesi içeriyor; yön koruması dönüşüm metadatasıyla izleniyor. Bu oturumda canlı Unreal/UI uçtan uca testi yapılmadığı için bunlar kaynak doğrulamasıdır.
- Korunan deneme_1 kaynağı ve önceki inceleme işi bulundu; SHA doğrulandı, önceki 3 oda/3 koridor/2 kapı/3 açık geçiş çıktısı dosyadan doğrulandı. Bu, yeni 20 çizimin sonucu olarak kullanılmadı.

## Deneyin tam tanımı

1. **Mevcut yöntem:** aktif DINO'nun float32 önbellekleri + bugünkü üretim decoder'ı. 20/20 topoloji önceki v2 baseline ile birebir aynı. Kapı aşamasının ayrı yeniden yürütümü de 20/20 aynı açıklıkları verdi.
2. **Referans sınırlar:** anotasyondaki gerçek poligonlar bölge yerine verildi. Ortak kenarlar yalnız bu poligonlardan çıkarıldı; kapı etiketleri/bağlantı sahipliği bu aşamaya verilmedi. Fiziksel kontrol yatay/dikey sınır istediği için fotoğraftaki ortak kenarlar baskın eksene izdüşürüldü. Bölge poligonları değiştirilmedi. En büyük normal izdüşüm hatası çalışma görüntüsünde 5.311 piksel (Data_64); her kenar için kayıt var. Dolayısıyla bu, kusursuz perspektifli geometri üst sınırı değildir.
3. **Referans kapı uçları:** sadece kapılara ait, eşleştirilmemiş nokta kümesi verildi. Nokta çiftleri, sahiplik, kabul sonucu, işaret uzunluğu veya açık geçiş uçları verilmedi. Tanı amaçlı bir adaptör bu noktalarda gerçek mürekkep uzanımlarını ölçüp mevcut `detect_pairs` fiziksel doğrulamasına sokuyor. Her iki eksen ve bütün olası çiftler yine deneniyor. Önceki üretim geçiş/kapı yolları korunuyor. Bu, head-6 haritasını değiştirmekle aynı değildir ve öğrenilmiş bir dedektörün üst sınırı diye okunamaz.
4. **İki referans birlikte:** 2 ve 3 aynı anda, aynı fiziksel/geometrik kabul kurallarıyla.

Üretim kapı yolu modelin **head 6 kapı ucu kanalını doğrudan kullanmıyor**. Head 3 işaret yanıtı, head 5 açık arayüz yanıtı, çizgi çiftleri ve fiziksel görüntü kontrolleri var. Head 6 atlaslarda gösteriliyor; zayıf head 6 yanıtını tek başına üretim hatasının nedeni saymadım. Bu çalışmada deneysel ensemble kodu kullanılmadı.

Ana referans-bölge koşullarında CV ile sonradan kurtarıldı geçmişi yok. Üretimdeki yalnız kurtarılmış koridorlara uygulanan ek fiziksel geçiş yolu böylece çalışmıyor. Bu kaynak/provenans farkının etkisini saklamamak için ayrıca iki duyarlılık koşulu çalıştırıldı: referans koridorların tamamı sonradan eklenmiş kabul edilip **mevcut** fiziksel ek kontrol çalıştırıldı; doğru açıklık ya da sahiplik verilmedi. Ana dört koşulun sonuçları bununla değiştirilmedi.

## Değerlendirme

Bütün koşullarda aynı maksimum eşleme: bölge bounding-box IoU ≥0.5 (türden bağımsız), açıklık türü aynı ve iki uçta en büyük hata ≤çalışma kenarının %4'ü. Bu görüntülerde tolerans 10.24 çalışma pikseli. Tür doğruluğu ayrıca JSON'da tutulur; IoU eşleşmesi doğru oda/koridor türü demek değildir. Noktalar özgün → 512 kanıt → çalışma dönüşüm matrisleriyle aktarılır. Özgün koordinata gidiş/dönüş sayısal hatası en çok 2.28e-13 piksel.

**Doğru kapı** konum ve tür eşleşmesidir. **Doğru bağlantı** ayrıca doğru referans bölge çifti gerektirir. Ana tabloda tekil bölge çiftleri sayılır; açıklık bazlı sahiplik metrikleri ayrıca `attached_openings` altında JSON/CSV'dedir. Bu kümede referans açıklık ve bağlantı paydaları aynıdır: 58. Aynı çiftin birden fazla açıklığı olursa bu iki metrik farklılaşabilir.

Sahiplik referansı eski değerlendiricideki en yakın poligondan türetme yerine yapısal referansın **açıkça kayıtlı entity_ids** alanıdır. Önceki değerlendirme çıktıları değiştirilmedi; eski skorlar her çizimde `legacy_baseline_metrics.json` içinde saklandı. Gerçek veride eski `false_connections=None` değerini toplarken 0'a dönüştürmek sıfır hata kanıtı değildi. Yeni tabloda üretilen−doğru sayısı **referansla eşleşmeyen** bağlantıdır; yaklaşık etiket ve bölge eşleme yüzünden bunu doğrudan fiziksel olarak yanlış kapı sayısı diye sunmuyoruz. Doğrulanmış gerçek dünya false-positive sayısı bu çalışma ile tam belirlenmedi.

P/R/F1 mikro toplamdır. Üretim yoksa precision tanımsız (—), sıfır başarılı sayılmaz. Kör test/bağımsız çizer/genelleme ve toplam model çıkarım süresi iddiası yok. Eğitim başlatılmadı.

## Train — 12 çizim

| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |
|---|---:|---|---:|---|---:|---:|
| Mevcut yöntem | 5/5/19 | 1.000/0.263/0.417 | 6/9/31 | 0.667/0.194/0.300 | 3 | 25 |
| Referans sınırlar | 12/12/19 | 1.000/0.632/0.774 | 15/18/31 | 0.833/0.484/0.612 | 3 | 16 |
| Referans kapı uçları | 7/7/19 | 1.000/0.368/0.538 | 8/9/31 | 0.889/0.258/0.400 | 1 | 23 |
| Referans sınırlar + uçlar | 16/16/19 | 1.000/0.842/0.914 | 19/20/31 | 0.950/0.613/0.745 | 1 | 12 |

## Validation — 4 çizim

| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |
|---|---:|---|---:|---|---:|---:|
| Mevcut yöntem | 4/4/10 | 1.000/0.400/0.571 | 2/5/13 | 0.400/0.154/0.222 | 3 | 11 |
| Referans sınırlar | 9/9/10 | 1.000/0.900/0.947 | 10/10/13 | 1.000/0.769/0.870 | 0 | 3 |
| Referans kapı uçları | 4/4/10 | 1.000/0.400/0.571 | 2/5/13 | 0.400/0.154/0.222 | 3 | 11 |
| Referans sınırlar + uçlar | 9/9/10 | 1.000/0.900/0.947 | 10/10/13 | 1.000/0.769/0.870 | 0 | 3 |

## Test — 4 çizim

| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |
|---|---:|---|---:|---|---:|---:|
| Mevcut yöntem | 0/0/3 | —/0.000/0.000 | 1/4/14 | 0.250/0.071/0.111 | 3 | 13 |
| Referans sınırlar | 3/3/3 | 1.000/1.000/1.000 | 10/10/14 | 1.000/0.714/0.833 | 0 | 4 |
| Referans kapı uçları | 0/0/3 | —/0.000/0.000 | 1/4/14 | 0.250/0.071/0.111 | 3 | 13 |
| Referans sınırlar + uçlar | 3/3/3 | 1.000/1.000/1.000 | 10/10/14 | 1.000/0.714/0.833 | 0 | 4 |

## Toplam — yalnız betimleyici

| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |
|---|---:|---|---:|---|---:|---:|
| Mevcut yöntem | 9/9/32 | 1.000/0.281/0.439 | 9/18/58 | 0.500/0.155/0.237 | 9 | 49 |
| Referans sınırlar | 24/24/32 | 1.000/0.750/0.857 | 35/38/58 | 0.921/0.603/0.729 | 3 | 23 |
| Referans kapı uçları | 11/11/32 | 1.000/0.344/0.512 | 11/18/58 | 0.611/0.190/0.289 | 7 | 47 |
| Referans sınırlar + uçlar | 28/28/32 | 1.000/0.875/0.933 | 39/40/58 | 0.975/0.672/0.796 | 1 | 19 |

## Koridor ek kontrolü duyarlılığı

Bu ek koşullar ana dört koşula dahil edilmedi. Train/validation/test ayrımları JSON/CSV'de ayrıca var.

| Koşul | Kapı doğru/üretilen/ref. | Kapı P/R/F1 | Bağlantı doğru/üretilen/ref. | Bağ. P/R/F1 | Eşleşmeyen | Kaçan |
|---|---:|---|---:|---|---:|---:|
| Referans sınırlar + fiziksel koridor ek kontrolü | 24/24/32 | 1.000/0.750/0.857 | 46/49/58 | 0.939/0.793/0.860 | 3 | 12 |
| İki referans + fiziksel koridor ek kontrolü | 28/28/32 | 1.000/0.875/0.933 | 50/51/58 | 0.980/0.862/0.917 | 1 | 8 |

Referans geometride ek kontrol açılınca bağlantı 35'ten 46'ya; iki referansta 39'dan 50'ye çıkıyor. Kapı sayıları değişmiyor. Açık geçişteki eksiğin bir bölümü fiziksel açıklık yokluğundan değil, öğrenilmiş arayüz yanıtı ve koridorun hangi yoldan geldiğine bağlı dallanmadan kaynaklanıyor. Bu, ek kontrolü bütün tahminlere koşulsuz açmanın güvenli olduğunu kanıtlamaz.

## Etiket denetimi ve görsel bulgular

20 fotoğrafın tamamı, referans bindirmeleri ve altı panelli atlaslar açılıp incelendi. Bir somut geometri etiket hatası bulundu: **Data_63 g003 alt ucu** [1121.9473,679.0028] yerine fotoğrafta ikinci kısa çizginin duvarla kesiştiği yaklaşık [1127,644] olmalı. Gözlemdeki l0038 çizgisi de alt duvara konmuş. Önce/sonra, kaynak SHA ve fotoğraf koordinat kanıtı `../label_audit_overrides_v1.json` içinde kayıtlı. Yalnız teşhis referansının bu ucu düzeltildi; **özgün etiketler ve eğitim hedefleri değiştirilmedi**. Tür, sahiplik ve bölgeler korunuyor. Seçim model tahmininden değil özgün fotoğraftan yapıldı. Özgün etiketlerle v4 korunuyor; v5 aynı dört koşulu düzeltilmiş referansla yeniden çalıştırıyor. Ana fark yalnız iki-referans koşulunda: kapı 27→28, bağlantı 38→39; diğer ana koşullar aynı. Eski etiketle bu kapının reddini salt fiziksel kontrol hatası diye yorumlamak yanlıştı. Bu, poligonların ve uçların piksel düzeyinde doğru olduğu anlamına gelmez. Kapı uçları yaklaşık duvar/işaret merkezlerini tarif ediyor; kesin geçiş kenarı ölçümü değil. Koridor dirseklerindeki iç bölme kesitleri çoğu zaman çizilmiş duvar değil mantıksal ayırımdır; kesin kesit konumları uzlaşımsal. Bunlar her açıklık için `label_audit` içinde işaretlendi; referans modele uydurulmadı ve belirsiz örnekler paydadan çıkarılmadı.

Data_64'te dört kapı; Data_67'nin alt sınırı kapalı; Data_68'de iki ayrık oda; Data_69'un dirseğinde kapalı ayırıcı; Data_70'te sağ üst odanın ayrıklığı fotoğrafla tutarlı bulundu. Tüm çizimlerin notları aşağıdadır.

| Çizim | Görsel inceleme |
|---|---|
| Data_51 | İki kapı ve düz koridor fotoğrafla tutarlı. Üst kapı açık geçiş olarak yorumlanmış; referans uç müdahalesi bunu kapıya çeviriyor. |
| Data_52 | Solda kapı, sağda işaretsiz açık geçiş var. Oda sınırları bulunmuş; aradaki koridor eksik. |
| Data_53 | İnce uzun koridor eksik. Alt kapının kalın, eğik uçlarında 512 kanıt çözünürlüğünde açıklık daralıyor. |
| Data_54 | İki kapı doğru tamamlanıyor. Koridorun oda diye sınıflandırılması tür hatası; konum eşleştirmesi türü zorlamıyor. |
| Data_55 | İki oda arasındaki L yol işaretsiz açık. Yanlış ek odalar ve eksik yatay koridor var; dirsekteki bölme çizgisi geometrik bir etiketleme uzlaşımı. |
| Data_56 | L yolun yatay kolu eksik, dik kol kısa. Üst kapı açık geçiş sayılıyor. Sol kapıda duvar desteği referanslı deneyde de sınır altında. |
| Data_57 | Üst bağlantı açık, altta kapı var. Her iki L kolu tahminde kayıp; ayrıca görüntü dışı fazladan oda önerisi var. |
| Data_58 | L yolu büyük bir oda dikdörtgeniyle temsil edilmiş. Referans geometri iki kapıyı kurtarıyor; dirsek açık arayüz yanıtı düşük. |
| Data_59 | İki kapı ve L geçişi mevcut yöntemde eşleşiyor; ayrıca fazladan oda var. Referans geometride CV-kurtarma geçmişi kaldırılınca iç geçiş kayboluyor; duyarlılık koşulu bunu geri getiriyor. |
| Data_60 | Üç açık geçiş; kapı işareti yok. Dik koridor kısmen bulunmuş, yatay kol eksik. Dirsek geçişi referanslarla da eşiklerde kalıyor. |
| Data_61 | Üstte tek kapı ve iki dirsekli yol var. Koridorlar kayıp. Referanslarla üst açıklık önce açık geçiş olarak tutuluyor; sonraki kapı kanıtı bunu değiştiremiyor. |
| Data_62 | U yol, iki oda ve kapısız açık girişler fotoğrafla tutarlı. İki kısa dik koridor tahmini bütün yolu temsil etmiyor. Koridor içi kesitlerin kesin konumu uzlaşımsal. |
| Data_63 | T yapısında üç kapı var. Koridorların yerinde/çevresinde yanlış oda dikdörtgenleri oluşmuş. g003 alt uç etiketi 35 piksel aşağıda duvara konmuş; fotoğrafa dayalı referans düzeltmesiyle iki referans koşulu üç kapıyı da buluyor. |
| Data_64 | Dört kapı fotoğrafta görünür; iki kapılı rehbere dönüştürülmedi. Merkez ve kollar yanlış bölündüğünden konumu doğru iki kapı bile referans bölge çiftine bağlanmıyor. |
| Data_65 | Üç oda, iki koridor ve dört kapı fotoğrafla tutarlı. Üst koridor oda sayılmış, orta oda ve alt koridor kaçmış. Referans bölgeler dört kapıyı da kurtarıyor. |
| Data_66 | Üç oda, iki kapı, iki açık bağlantı. Dik ve yatay koridor tahminleri parçalı; boş alanda fazladan bölgeler var. Referans geometri dört bağlantıyı da kurtarıyor. |
| Data_67 | Üstte kapı, altta kesintisiz kapalı sınır var. Alt sınırda geçiş referansı yok ve üretilmiyor. |
| Data_68 | İki ayrık kapalı oda var. Üretim CV kurtarma altı yanlış koridor bölgesi ekliyor; buna rağmen tamamlanmış kapı/bağlantı sayısı sıfır. |
| Data_69 | İki kapı var; dirsekte çizilmiş kapalı ayırıcı geçiş sayılmıyor. Dik kol eksik; yatay kol oda sayılmış. Sağ kapıda duvar desteği eşiğin altında. |
| Data_70 | Sol üst kapı ve L yol; sağ üst oda bağımsız. Model gerçek L yerine sağdaki iki oda arasına yanlış koridor koyuyor; tamamlanmış bağlantı üretmiyor. |

## Açıklık bazında engeller

Mevcut yöntem 58 referans açıklığın 9'unu doğru sahipliğe bağladı, 49'u eşleşmedi. Bunların 46'sında en az bir referans bölge IoU eşlemesinde yok; bu, bazen fiziksel yokluk, bazen aşırı kısa/yanlış birleşmiş geometri. Kalan üçünde de tek başına “uç modeli başarısız” denilemez. Neden etiketleri çoklu olabilir; yakındaki reddedilmiş aday başka bir aday da olabilir. Ham kayıt ve müdahale sonucu birlikte okunmalıdır.

Referans sınırlar baseline'ın kaçırdığı 27 bağlantıyı kurtarıyor; Data_59 g002 ise CV-kurtarma geçmişi kaldırıldığından kayboluyor (net +26). Yalnız uç müdahalesi Data_51 g001 ve Data_56 g001'i kurtarıyor. Data_63 g003 için bölge ve uç birlikte gerekli; etiket düzeltmesi bu ayrımı görünür kıldı. Sınır+uç müdahalesinde 19 bağlantı hâlâ kaçıyor: dördü kapı, on beşi açık geçiş. Bunların hepsinin “fiziksel duvar var” diye etiketlenmesi yanlış olur.

| İki referansa rağmen kaçan kapı | Ölçülen engel |
|---|---|
| Data_53 g002 | 512 kanıtta gap_clear=0.667; gereken ≥0.85. Kalın/eğik kısa kapı, yaklaşık uç konumu ve çözünürlük birlikte etkili olabilir. |
| Data_56 g002 | Duvar desteği min=0.636; gereken ≥0.65. |
| Data_61 g001 | Açık geçiş önce tutulmuş; takip yolu kapı için bütün testleri geçse de `overlap_baseline_or_earlier` ile bastırılmış. Son çizgi-çifti yolunda min duvar desteği 0.214. Tür/öncelik ve fiziksel örnekleme birlikte etkili. |
| Data_63 g003 — etiket denetimi | Eski referansta gap_clear=0.8125; alt uç etiket hatası. Fotoğraf temelli düzeltmeyle iki-referans koşulunda kapı eşleşiyor; artık kalan kapı hatası sayılmıyor. |
| Data_69 g002 | min duvar desteği 0.625; gereken ≥0.65. |

Örnek açık geçişler: Data_55 g002 clear=1.0 iken arayüz yanıtı 0.000242; Data_58 g003 clear=0.944 iken yanıt 0.00000170; Data_64 g005 clear=0.985 iken yanıt 0.4404 (<0.45). Data_64 örneği fiziksel açıklıktan çok semantik eşik tarafından engelleniyor. Bu değerler `failures.json → gate_audits` içinde kayıtlıdır. Ek kontrol duyarlılığı bazılarını kurtarıyor; bütün geçişlerde kurtarmıyor.

Ek negatif kontrol, fiziksel doğrulamanın başka bir sınırını gösterdi: kapalı ince duvara referans konumlarda aday sunulduğunda, geniş duvar desteği şeridi duvarı görürken dar açıklık şeridi duvarın biraz dışına kayıp boşluk bulabiliyor. Olağan üretim aday araması bu örnekte aday çıkarmıyor; referans-uç adaptörüyle aynı fiziksel doğrulayıcı bir kapı kabul ediyor. Kalın bariyer ve boş görüntü kontrolleri reddediliyor. Bu açık `physical_negative_control.json` ve bir regresyon testiyle kayda alındı; kapı fiziksel doğrulamasının tam güvenilir olduğu veya uç adaptörünün üretime hazır olduğu iddia edilmiyor. Üretim kuralı bu oturumda değiştirilmedi.

Data_68 özellikle önemlidir: 2 gerçek oda karşısında 6 yanlış CV koridor bölgesi ekleniyor ama tamamlanmış bağlantı üretilmiyor. “Yanlış bağlantı 0” bu bölge hatasını gizleyebilir. Bu nedenle bölge ve bağlantı ölçümleri birlikte tutuldu.

## Bir sonraki geliştirme önceliği

1. İnce/uzun ve L/T koridorların geometrisi, bölge türü ve ortak sınır üretimi. Referans geometri validation'da kapıyı 4→9, bağlantıyı 2→10; testte kapıyı 0→3, bağlantıyı 1→10 çıkarıyor. Bu çalışma kapsamındaki en güçlü teşhis kanıtı budur.
2. Açık geçiş kararının semantik başlık ve koridorun üretildiği yola bağımlılığını ele almak; tür/öncelik çakışmasını (Data_61) ve kaymış açıklık örnekleme negatif kontrolünü ayrı düzeltme hedefleri yapmak. Önce mevcut atlas negatifleriyle ölçmek; eşikleri körlemesine gevşetmemek.
3. Kapı ucu dedektörü bundan sonra: konum müdahalesi iki mevcut kapıyı kurtarıyor, fakat eksik bölgeyi tamamlamıyor. Tek başına yeni eğitim/ensemble önceliğini desteklemiyor.

Bu sonraki geliştirmeler başlatılmadı. Yeni veri istenmedi, eğitim yapılmadı, aktif ağırlık veya üretim kaynakları değiştirilmedi; hiçbir plan otomatik onaylanmadı.

## Teslim ve yeniden çalıştırma

- `gallery.html`: 20 adet altı panelli atlas, dört koşul görüntüleri ve açıklık bazında Türkçe neden tablosu. Her açıklık ID'si özgün fotoğraf/512 kanıt yakınlaştırmasına açılır.
- `report.json`, `metrics.csv`: dört ana koşul + iki ayrı duyarlılık koşulu, train/validation/test ayrımı ve precision/recall/F1.
- `failures.json`, `opening_failures.csv`: 58 açıklığın nedenleri, her koşuldaki aşama kayıtları; 32 kapı ayrı tür alanıyla seçilebilir.
- `label_audit.json`: 20 görsel inceleme notu, iç bölme belirsizlikleri ve teşhis yan referansındaki tek uç düzeltmesinin kaydı.
- Her çizimde `coordinates.json`, `reference.json`, koşul tahminleri ve `candidates.json` var. Reddedilen numaralar aday kayıtlarına karşılık gelir. Arama öncesinde elenen her olası çizgi çifti kaydedilmiyor; “kayıt yok” tek başına ret nedenini ispatlamaz.
- `protocol.json`: model, veri, önbellek ve kaynak SHA256 kayıtları; `source_snapshot`: kullanılan yerel kod/politikalar. `service_check.json`: anahtar içermeyen servis durum özeti.
- 155 model/veri/üretim/deney dosyası değişmedi; teslim raporu betiği hesaplama sonrasında güncellendi ve ayrıca sürümlendi; üç checkpoint SHA256 özetteki değerlerle eşleşti. 20 baseline topolojisi ve 20 kapı aşaması yeniden yürütümü eşit. Yeni 10 teşhis testi dahil ilgili 41 test geçti. Veri `--check` denetimi 112 kayıtta geçti. Ayrı `verification_final.json` çıktı envanterini ve son kontrolleri içerir.

```sh
PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python \
  -m SketchPipeline.shape_authoring.diagnose_new20 \
  --output Saved/ShapeFirst/new20_diagnosis/NEW_RUN \
  --label-overrides Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json
```

Mevcut çıktı klasörü üzerine yazılmaz. `review_new20_diagnosis.py` bu oturumdaki elle gözden geçirilmiş notları v5 paketine ekleyen teslim betiğidir. v1 tamamlanmamış yeniden-yürütüm kontrolünde durmuştur; v2/v3 ara çalışmalardır, **teslim sürümü v5**. v4 özgün etiketlerle dört ana koşul ve ek duyarlılıkları içerir; v5 fotoğraftan denetlenmiş tek uç düzeltmesiyle aynı deneyi tekrarlar. İki-referans koşulu 27/32 yerine 28/32 kapı bulur. v4 raporu etiket denetimiyle birlikte okunmalıdır; önceki kesin etiket-hatası-yok ifadesi bu yakın incelemeyle geçersiz kalmıştır.
