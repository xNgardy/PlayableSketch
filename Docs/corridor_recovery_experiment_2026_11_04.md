# Koridor kurtarma deneyi — 4 Kasım 2026

## Sonuç

`deneme_1.png` üzerinde koridor geometrisi iyileşti: önceki 3 oda / 0 koridor yerine 3 oda / 3 koridor segmenti öneriliyor. Üst bağlantı tek, alt L bağlantısı iki dikdörtgen olarak bulunuyor. Bu sonuç görsel incelemeyle uyumlu; bu çizim için bağımsız etiket veya F1 ölçümü yok.

| Deney | Oda | Koridor segmenti | Kapı | Açık geçiş önerisi |
|---|---:|---:|---:|---:|
| Mevcut yöntem | 3 | 0 | 0 | 0 |
| Paralel duvar | 3 | 1 | 0 | 2 |
| Paralel duvar + L parçalama | 3 | 3 | 0 | 3 |
| Kırpımla model doğrulaması zorunlu | 3 | 0 | 0 | 0 |
| Geometrik adaylar + kırpım model kanıtı | 3 | 3 | 0 | 4 |

**Tam oynanabilir bağlantı çözülmedi.** Üstteki iki kapı işareti hâlâ `door` olarak tanınmıyor; `open_passage` önerileri kapı başarısı sayılmamalı. Alt L'nin iki parçası geometrik olarak temas ediyor fakat mevcut açıklık çözücüsü dönüş noktasında geçiş üretmiyor. Dört açık geçiş, tüm odalar arasında kesintisiz rota olduğunu göstermiyor.

## Uygulanan yöntemler

1. Yerel kontrasttan gerçek çizgi maskesi çıkarılıyor. OpenCV Hough çizgileri yatay/dikey ayrılıyor; paralel çiftlerin duvar desteği, iç boşluğu ve genişliği kontrol ediliyor. Mevcut odaların açık yüzleri arasında bir yol oluşturmayan adaylar eleniyor. Modelin koridor olasılığı bu geometrik adayları veto etmiyor.
2. Birbirine dik koridor adayları L dönüşünde iki parçaya ayrılıyor. Parçalar örtüşmeden ortak kenara oturtuluyor; bağlantı grafiği çizgideki fiziksel boşluğu kontrol ediyor. Aday üretiminin bağlantı kontrolü ile son açıklık çözücüsü farklı aşamalar; ikincisindeki eksik geçiş yukarıda belirtilmiştir.
3. Tutulan adayların çevresi özgün fotoğraf piksellerinden kırpılıyor, koordinat dönüşümüyle 512×512 hazırlanıyor ve mevcut DINOv2 modeline yeniden veriliyor. Model eğitilmedi. Üç aday için üç gerçek model çağrısı yapıldı; kırpımlar ve olasılık maskeleri kaydedildi.

### Kırpma gerçekten yardımcı oldu mu?

| Bölge | Tam görüntü ortalama koridor yanıtı | Kırpım ortalama yanıtı | Kırpımda yanıtı >0,5 olan alan |
|---|---:|---:|---:|
| Alt yatay | 0,0160 | 0,0525 | %5,03 |
| Alt dikey | 0,000296 | 0,000050 | %0 |
| Üst dikey | 0,0707 | 0,0392 | %3,77 |

Bunlar doğruluk veya kalibre edilmiş güven yüzdeleri değildir. Kırpım doğrulaması için sabit alan eşiği %20 idi; hiçbir aday bunu geçmedi. Alt yatay yanıt arttı, diğer iki yanıt düştü. **Kırpma tek başına bu örnekte koridor tanımayı düzeltmedi.** Birleşik deneyde açıklık önerisi 3'ten 4'e çıktı; bölge kazanımı ilk iki yöntemden geliyor.

## Önceki örneklerde kontrol

50 insan çizimi ve 60 sentetik kontrol üzerinde beş deney kolu çalıştırıldı. Tahminler etiketler okunmadan önce dosyalara yazıldı. Yeni kırpım çıkarımı yalnızca yeni geometrik aday bulunan çizimlerde çalışıyor; diğer örneklerin mevcut model maskeleri yeniden kullanıldı.

| Ölçüm | Önce | Birleşik deney |
|---|---:|---:|
| Eski insan test grubunda bölge F1 | 0,9286 | 0,9286 |
| Eski insan test grubunda doğru bölgeye bağlı açıklık F1 | 0,9143 | 0,9143 |
| Sentetik bölge F1 | 0,9063 | 0,9063 |
| Sentetik tam topoloji | 30/60 | 30/60 |
| Sentetik yanlış bağlantı | 1 | 1 |

Referansı bulunan bölge/bağlantı ölçümlerinde artış veya düşüş yok. Yalnızca `Data_7` çizimine bir koridor ve iki açıklık önerisi eklendi. Görsel olarak iki oda arasındaki dar bağlantıya denk geliyor; ancak bölge etiketi yok ve iki açıklığın yalnızca biri mevcut açıklık referansıyla eşleşiyor. Bunu doğrulanmış genel başarı artışı saymıyoruz. Diğer 109 örnekte bölge/açıklık sayıları değişmedi.

Bu değerlendirme geçmişte incelenmiş geliştirme verisi üzerindedir; yeni, kör veya farklı çizerlerden bağımsız bir test değildir. `deneme_1` yöntem geliştirme sırasında kullanıldı. Dolayısıyla genel accuracy/F1 artışı iddiası yapılamaz.

## Testler ve kullanım

30 birim testi geçti: yeni aday üretimi, mevcut koridor/açıklık, bölge kurtarma ve ayrıntılı çözücü testleri. Yeni testler açık/kapalı uçları, boş görüntüyü, tek uca bağlı çizgileri ve L dönüşünde örtüşmeyen iki segmenti kapsıyor. Üretilen deney belgeleri mevcut sözleşme doğrulamasından geçti.

Kod ayrı ve isteğe bağlı bir deney olarak eklendi. Çalışan web sunucusu, varsayılan çözücü, model ağırlıkları, kabul edilmiş işler ve Unreal paketi değiştirilmedi. Yeni öneriler kullanıcı onayı gerektiriyor.

Proje kökünden hedef örneği yeniden çalıştırma:

```sh
OMP_NUM_THREADS=4 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.experiment_corridor_recovery \
  --input Saved/ShapeFirst/workspace/jobs/shape_779182569a3946428d87b3caca4d8f31/attempt_1 \
  --output Saved/ShapeFirst/corridor_recovery_experiment/replay_deneme_1 --zoom
```

- Deney sonuçları: `Saved/ShapeFirst/corridor_recovery_experiment/v1/deneme_1/`
- 110 örnek raporu: `Saved/ShapeFirst/corridor_recovery_experiment/v1/regression/report.json`
- Model ve deney kaynaklarının dondurulan özetleri: aynı klasörde `freeze.json`; kullanılan kaynak kopyaları `source_snapshot/` içinde. Çalışma sonrası kod biçimlendirildi; değerlendirmede kullanılan biçimlendirme öncesi kopyalar korunuyor.

Önerilen sonraki iş: bu üç segmenti inceleme ekranında öneri olarak göstermek; ardından kapı işaretlerini ve L dönüşündeki açık geçişi ayrı bir düzeltme olarak ele almak. Mevcut deney tamamlanmış otomatik oynanabilir çözüm olarak varsayılan yapılmamalı.
