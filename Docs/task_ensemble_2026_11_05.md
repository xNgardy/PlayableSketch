# Göreve göre ensemble deneyi — 5 Kasım 2026

## Sonuç

Görevleri ayıran deneysel akış uygulandı ve mevcut yöntem dahil 13 yapılandırma, 70 gerçek çizim ve 60 sentetik örnek üzerinde karşılaştırıldı. Doğrulama kümesinde tamamlanmış doğru kapı ve doğru bağlantı sayısı artmadı; seçim kuralı mevcut yöntemi korudu. Canlı servis, aktif ağırlıklar ve veri etiketleri değiştirilmedi. Yeni eğitim yapılmadı.

## Uygulanan akış

1. Bölge geometrisi mevcut DINO modeli, önceki U-Net modeli veya bunların sınırlı birleşiminden çıkarılıyor. Kapı aşamasında bu geometri sabit tutuluyor.
2. Ayrı ağırlıklara sahip DINO devam eğitiminin 10. epoch çıktısından yalnız kapı ucu kanalı kullanılıyor. Bu checkpoint önceki bütün-model denemesinde yayına alınmamıştı; burada oda tahminleri kullanılmıyor. İki DINO modeli aynı donmuş omurgayı paylaşır; bütünüyle bağımsız mimariler değiller. U-Net farklı mimaridir.
3. Yeni bağlantı için iki bölgenin ortak sınırı, iki uçta fiziksel dik çizgi desteği, duvar devamlılığı ve arada gerçek açıklık aranıyor. Eksik ikinci bölgeyi kapı dedektörü kendiliğinden oluşturmuyor. Mevcut kabul edilmemiş öneriler korunuyor; otomatik kullanıcı onayı yok.
4. Ek denemelerde U-Net hem 512 hem eğitim ölçeği olan 256 pikselde çalıştırıldı; iki ölçeğin ortalaması da denendi. DINO/U-Net bölge haritaları %75/%25 oranında birleştirildi. İkinci modelin görüntü desteğiyle CV kaynaklı koridorları veto eden alternatif de ölçüldü.
5. Tahmin edilen ortak duvarların çevresinden en fazla sekiz adet 256×256 yerel görünüm kapı dedektörüne verildi. Bunlar 512 piksellik kanıt görüntüsünden kırpılır; özgün fotoğrafın tam çözünürlüğü değildir. Kırpım seçimi etiketlere bakmaz. Son olarak iki modelin kapı ucu haritalarının maksimum birleşimi denendi.

## Doğrulama sonuçları

Kapı sayısı, referansla eşleşen tamamlanmış kapıdır; yalnız bulunan uç sayısı değildir. Bağlantı sayısı, açıklığın doğru bölge çiftine bağlandığı eşleşme sayısıdır.

| Yapılandırma | Doğru kapı | Doğru bağlantı | Koruma eşiklerini geçti mi? |
|---|---:|---:|---|
| baseline | 26 | 28 | Evet |
| dino_specialist | 26 | 28 | Evet |
| unet_dino | 17 | 20 | Hayır |
| unet_specialist | 17 | 20 | Hayır |
| fused_specialist | 26 | 28 | Evet |
| supported_dino | 26 | 28 | Evet |
| supported_dino_specialist | 26 | 28 | Evet |
| unet256_specialist | 7 | 7 | Hayır |
| unet_multiscale_specialist | 10 | 13 | Hayır |
| dino_roi_specialist | 26 | 28 | Evet |
| dino_endpoint_union | 26 | 28 | Evet |
| dino_roi_union | 26 | 28 | Evet |
| unet256_endpoint_union | 7 | 7 | Hayır |

Doğrulama: eski gerçek çizimlerden 5, yeni gerçek çizimlerden 4 ve önceden belirlenmiş 6 sentetik örnek. Eski/yeni/sentetik grupların bölge, kapı ve bağlantı F1 değerleri ile bağlantı hassasiyeti ayrı korunur; 0,02’den fazla kayba izin verilmez. Sentetik yanlış bağlantı sayısı artamaz. Eşit amaç puanında mevcut yöntem seçilir. Test sonuçları bu seçime katılmadı.

## Seçim sonrası sonuç denetimi

| Küme / yöntem | Doğru kapı / referans | Doğru bağlantı / referans | Üretilen bağlantı |
|---|---:|---:|---:|
| Eski gerçek test (10 çizim) — Mevcut | 12/12 | 16/19 | 16 |
| Eski gerçek test (10 çizim) — DINO + ayrı kapı modeli + yerel görünüm | 12/12 | 16/19 | 16 |
| Yeni gerçek test (4 çizim) — Mevcut | 0/3 | 1/14 | 4 |
| Yeni gerçek test (4 çizim) — DINO + ayrı kapı modeli + yerel görünüm | 0/3 | 1/14 | 4 |
| Sentetik kontrol (60 çizim) — Mevcut | 123/130 | 141/160 | 142 |
| Sentetik kontrol (60 çizim) — DINO + ayrı kapı modeli + yerel görünüm | 125/130 | 143/160 | 144 |

Sentetik kümede yerel görünüm kullanan seçenek 123/130 yerine 125/130 kapı, 141/160 yerine 143/160 doğru bağlantı sağladı. Yanlış bağlantı sayısı her ikisinde de 1 kaldı. Bu kazanım doğrulamada ve gerçek test çizimlerinde tekrarlanmadığı için aktif yöntemi değiştirmek için yeterli görülmedi. Uç haritalarını birleştiren yerel görünüm seçeneği sentetikte 124 kapı/142 doğru bağlantıda kaldı.

Gerçek çizimler için tam topoloji ve yanlış bağlantı sayacı yeterince tanımlı değil; JSON’daki genel false_connections=0 alanı gerçek çizimlerde sıfır hata kanıtı değildir. Yukarıdaki doğru/üretilen bağlantı sayıları esas alınmalıdır.

## Sınırlar ve yorum

- Bu veri geçmiş geliştirmelerde görülmüştür; bağımsız çizer veya kör test sonucu değildir. İnsan etiketleri yaklaşık geometrik referanslardır. Bölgeler IoU ≥0,5 ile eşleştirilir; bu skor tek başına oda/koridor tür doğruluğunu kanıtlamaz.
- İkinci ve üçüncü deney turunda ilk turdaki bazı yardımcı olasılık haritaları float16 önbellekten float32’ye döndürülerek kullanıldı. Eşik çevresinde nicemleme farkı oluşabilir. Aktif DINO haritaları float32’dir. İleride bir aday seçilirse tam hassasiyetle uçtan uca tekrar doğrulanmalıdır.
- Raporlardaki arm elapsed_seconds çoğunlukla önbellek sonrası geometri/kapı işlemini ölçer. Bunlar toplam model çalışma süresi veya servis gecikmesi olarak okunmamalıdır. İki model ve yerel görünümler ek çıkarım maliyeti getirir.
- Bu deneme mevcut modeller arasındaki birleşimi ölçer; bütün olası ensemble yöntemlerinin başarısız olduğunu göstermez. Eksik bölge/ortak sınır olduğunda iyi kapı uçları tek başına bağlantı kuramaz. Gözlenen insan çizimi sorunları bölge geometrisi ve kapı yorumunun birlikte iyileştirilmesini gerektiriyor.

## Kontroller ve tekrar çalıştırma

56 ilgili test geçti; bunların 6’sı yeni ensemble akışını denetler. Fiziksel açıklık gerekliliği, boş görüntüde kapı üretmeme, eksik ikinci bölgeye bağlamama, geometriyi koruma, mevcut kapıyı çoğaltmama ve yerel koordinat dönüşümü kontrol edildi. Aktif iki ağırlık, deneysel checkpoint ve servis giriş dosyalarının hash değerleri korundu.

Kod: `SketchPipeline/shape_authoring/task_ensemble.py`. İlk iki tur değerlendiricisi `evaluate_task_ensemble.py`; son birleşim turu `evaluate_endpoint_union.py`. Modülün etkin üretim yoluna bağlanması bu sonuçlar nedeniyle yapılmadı.

Ham çıktılar: `Saved/ShapeFirst/task_ensemble/v1`, `v2`, `v3`. Son toplu sayılar `v3/report.json`, seçim `v3/selection.json`, kontroller `v3/verification.json`. Her örneğin tahmini ve tanı kayıtları saklandı. Scriptler var olan çıktı klasörünü ezmez; yeni bir deney için farklı OUT yolu kullanılmalıdır.
