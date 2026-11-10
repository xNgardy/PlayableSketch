# Eksik koridorlar ve açık geçişler: toplu geliştirme ve sonuçlar

Tarih: 4 Kasım 2026. Kapsam Step 2 algılama/bağlantı kalitesi; yeni model eğitimi,
indirme, boyutlandırma veya Unreal ürün adımları bu çalışmaya dahil değil.

**Sonuç:** B sonrasındaki eski test başarısı region 24/26→26/26, opening konumu
13/20→17/20 ve doğru owner bağlantısı 12/19→16/19 oldu. Üç eski-test açık geçişi
hâlâ eksik. Validation ve eski testin tamamındaki hatalar çözülmüş değildir.

## Uygulanan düzeltmeler

1. **Odanın koridora taşan maskesi:** güçlü corridor yanıtı ve gözlenen iki
   paralel duvar ile desteklenen koridora taşan oda sınırı, odanın çoğunu
   koruyacak şekilde kısaltılıyor. Böylece ortak sınır uzlaştırmasında koridor
   silinmiyor. Büyük veya kanıtsız overlap bu kuralla giderilmiyor.
2. **Dar corridor sınır fit'i:** mevcut alan/doluluk koşullarını geçen ama duvar
   fit'i hatalı corridor adayları daha geniş fakat sınırlı bir pencerede yeniden
   gerçek duvarlara oturtuluyor. İki paralel duvar desteği, güçlü model yanıtı ve
   derin overlap reddi korunuyor. Küçük bitişik overlap mevcut joint solve'a
   bırakılıyor; odaya gömülü koridor eklenmiyor.
3. **Open-interface-first önerileri:** önce boşluk genişlik filtresini geçmeyi
   beklemek yerine, ortak sınırdaki öğrenilmiş interface yanıtı aday üretiyor.
   En az bir owner corridor olmalı; fiziksel açıklık ve coherent crossing-wall
   reddi gerekiyor. Kanıt yoksa sadece bitişiklik passage oluşturmuyor.
4. Önceki B yerel duvar takibi ve kapı kuralları korunuyor. Tick'siz kırık door
   haline getirilmedi. Açık passage, door'dan ayrı kanıtlarla değerlendiriliyor.

## Data 47 için düzeltilen teşhis

Önceki genel notun aksine cH component'i region-recovery koşullarını zaten geçiyor.
Asıl son kayıp, alt odanın sınırının koridor içine taşınması ve joint snap'in bunu
yanlış uzlaştırması ardından overlap reddinde oluşuyor. Yeni inceleme bu ayrımı
ortaya çıkardı. cH ve Data 48 cV1 artık korunuyor.

## Deney akışı

v1: beş validation + altı sentetik kontrol, ardından 110 örneğin dört kolu.
Eski testte doğru bağlantı 15/19 oldu. Data 48 cV1 fit'i doğru duvarları bulmasına
rağmen bir piksellik komşu overlap yüzünden joint solve öncesi eleniyordu.
v2 bu dar komşuluk engelini kaldırdı; tekrar küçük kontrol, sonra tam karşılaştırma
çalıştırıldı. Eski sonuçlar silinmedi. Bu geliştirme koleksiyonunda sonuca bakarak
bir düzeltme yapıldı; çalışma kör test olarak sunulmuyor.

## Dört kolun eski-test sonucu

| Kol | Doğru bölge | Opening konumu | Doğru owner bağlantısı |
|---|---:|---:|---:|
| Kontrol: B / 2.5 | 24/26 | 13/20 | 12/19 |
| Yalnızca corridor düzeltmesi | 26/26 | 15/20 | 14/19 |
| Yalnızca açık geçiş düzeltmesi | 24/26 | 14/20 | 13/19 |
| Birleşik | 26/26 | 17/20 | 16/19 |

Region referansı yalnızca 8/10 planda mevcut. Öneri sayısı 28→30; eşleşmeyen
region sayısı dört olarak kaldı. Data 5 opening owner referansı olmadığı için
17 konum eşleşmesinin yalnızca 16'sının doğru attachment'ı doğrulanabiliyor.

## Diğer kümeler ve yeni hatalar

- Validation: region 17/19 ve doğru bağlantı 11/14 değişmedi.
- Train: region 97/99 değişmedi, doğru bağlantı 64/78→69/78. Bu eğitim uyumu;
  genelleme kanıtı değil. Region önerisi 104→105; **bir yeni eşleşmeyen region**
  var. İnsan annotation'ları yaklaşık olduğundan bağımsız adjudication gerektirir.
- Sentetik 60: region 174/180, doğru bağlantı 133/160, exact topology 30/60,
  mevcut yanlış bağlantı 1 değişmedi. Yeni yanlış sentetik bağlantı oluşmadı.
- İnsanlarda yeni konumla eşleşmeyen opening veya bilinen owner'a yanlış attachment
  oluşmadı. Önceki iki train unmatched opening korunuyor.
- Referans bazında önceki doğru region/owner bağlantılarından hiçbiri kaybolmadı;
  `regression-inventory.json` bu kontrolü ve kalan açıklıkları saklıyor.

## Kalan somut hatalar

Eski test:
- Data 47 g004: interface yanıtı yaklaşık 0.227, aynı kanıt seçeneğinde ham
  açıklık oranı 0.5; gereken 0.45 interface / 0.8 clear koşulları geçilmiyor.
- Data 47 g005: ham çizgi açık olsa da interface yanıtı yaklaşık 0.142; semantik
  passage kanıtı zayıf. Yeni kurallar sırf boşluk var diye bağlantı üretmiyor.
- Data 48 g003: cV1 mevcut, ama interface yanıtı yaklaşık 0.150, ham açıklık
  yaklaşık 0.654. Kanıt koşullarını geçmiyor.

Validation:
- Data 43 g004: ortak sınır referans geçişinden kısa; interface yanıtı yaklaşık
  0.00095. Hem boundary extent hem model evidence sorunu açık.
- Data 8: c0 yanlış türde, rB birleşmiş model bölgesi. Door g001 ve passage g002
  eksik. Bu çalışma yeni model eğitmedi; güvenli decoder kuralları bu kanıtı
  kendiliğinden üretemedi.

Bu eşik yanıtları kalibre olasılık değildir. Bunları düşürerek kalan bağlantıları
zorlamak denenmedi. Sonraki model/veri işi için gerçek instance/type ve interface
etiketlerini doğrulamak, farklı yazarlardan veri toplamak ve yeni bağımsız
ayrımı baştan ayırmak gerekir. İnsan exact topology ve düzeltme süresi hâlâ yok.

## Entegrasyon ve doğrulama

- Birleşik yöntem DINO refined/refined-full yolunda decoder 2.6 olarak etkin.
  `propose` profile_configuration içinde region/opening policy sürümlerini saklar;
  config hash/revision değişir. Baseline, U-Net ve doğrudan legacy çağrılar korunur.
- 110 cached örnekte entegre kod frozen birleşik geometriyle aynı; B kontrol yolu
  frozen kontrolle aynı. Karşılaştırmada 550 cached dosya, entegrasyonda 440 dosya
  hash kontrolünden geçti. Model checkpoint'i ve global varsayılan model aynı.
- Gerçek worker: Data 8=0, 23=1, 25=2, 31=2, 43=4, 47=3, 48=4 opening.
  Yedi worker'ın geometrisi cached birleşik sonuçla aynı; her birinin eski native
  model maskelerine göre maksimum farkı 0.0. OCR kapalı ve acceptance pending.
- İlk worker denetiminde Data 8 için PNG varsayımı hatası düzeltildi; son araç
  gerçek source metadata yolunu kullanıyor. `integration_final` tamamlanmış kanıt.
- 60 benzersiz test geçti; altı yeni corridor/passage testi dahil. Coherent fiziksel
  duvarın sahte interface'i engellemesi, boş/kanıtsız görsel reddi, paralel duvarla
  fit ve derin overlap reddi test edildi. Loopback HTTP testi bu tur tekrarlanmadı.
- Browser QA yapılmadı. Eski jobs/accepted dosyalar kendiliğinden yeniden yazılmadı.
- DINO deneysel/review-required kalır; global model varsayılanına geçirilmedi.

## Çıktılar

`Saved/ShapeFirst/dinov2/corridor_passage/v2/full/`: report.json, gallery.html,
freeze.json, source_snapshot/, regression-inventory.json ve her örneğin dört kolu.
`v2/integration_final/`: verification.json, replay.json, worker-smoke.json,
jobs/, source_snapshot/, tests.log.

Bu çalışmayla kalan algılama işleri birlikte denenip güvenli kazanımlar entegre
edildi; bütün Step 2 sorunları veya Step 3–5 tamamlandı denmiyor.
