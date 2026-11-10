# Birleşik oda geometrisi — 9 Kasım 2026

Ayırıcı duvar veya kapı olmadan birleşen geniş ve dar alanlar tek oda sayılır. Bu kural otomatik önerilerde, gözlenen çizgiler ve kapı işaretleriyle ayrılan iç alanların bağlantılı bileşenleri üzerinden uygulanır. Geometri politikası `observed-room-geometry/1.1` oldu.

Yerel aydınlatma değişimlerine uyarlanan eşikleme, güçlü çizgilere bağlı soluk kalem izlerini geri kazanır. Küçük kopukluklar yalnızca iki yanında aynı yönde devam eden çizgi desteği varsa onarılır. Görüntünün karşılıklı kenarlarına uzanan çerçeve/masa bileşenleri ayrılır. Kapı işaretleri kapı olarak tutulur; açık, dar boyunlar bölünmez. Büyük eksik sınırlar güvenilir bir kapalı oda gibi tamamlanmaz.

Kontur sadeleştirmesi artık tüm çevre uzunluğuyla büyüyen tek tolerans yerine birden fazla sınırlı toleransı karşılaştırır. Köşe sınırı düzenleme API'siyle birlikte 64'e çıkarıldı. El çizgisindeki sapmalar yatay/dikey duvarlara düzenlenir. Bu, serbest açılı veya eğrisel mimari duvar desteği değildir.

İki özgün fotoğraf güncel model ve üretim profiliyle tekrar işlendi:

| Örnek | Mantıksal oda | Kapı | Oda köşeleri | Motor zemin parçaları |
| --- | ---: | ---: | --- | ---: |
| Önceki L fotoğrafı | 4 | 3 | 4, 6, 4, 4 | 5 |
| Yeni U fotoğrafı | 2 | 1 | 18, 4 | 8 |

U fotoğrafındaki soldaki geniş alan, kıvrımlı bağlantı ve sağ üstteki geniş alan tek odadır. Alttaki kapıyla ayrılan alan ikinci odadır. Her iki örnek ölçülendirmeden ve kanonik geometri doğrulamasından geçti. Motor için oluşturulan zemin parçalarının birleşiminin oda çokgenine eşit olduğu denetlendi; arayüzde tek oda sınırı korunur.

510 otomatik test geçti. Yeni kontroller: U biçimi ve 16'dan fazla köşe, ayırıcısız geniş uçlar, kısa duvar kopukluğu, soluk çizgi ve değişken aydınlatma, dar açık geçiş, büyük eksik dış sınır ve kapısız ayrı odalar. Tarayıcıda çizim ve plan görünümü doğrulandı.

Model ağırlıkları ve eğitim verisi değişmedi; genel precision/recall/F1 yeniden hesaplanmadı. Test sayısı model doğruluk oranı değildir. Fiziksel ölçüler önceki uygulama önerilerini kullanır; dar alanlarda oyuncu açıklığı için ölçüleri büyütmek gerekebilir. Unreal oynanışı bu çalışmada doğrulanmadı.

Eski kullanıcı kayıtları korunarak yeni U analizi `shape_64c015ebce2f4d98b4fdcde1be721272` kaydında açıldı. Kullanıcı adına onay veya dışa aktarım yapılmadı.

Kanıtlar: `Saved/ShapeFirst/unified_room_geometry_2026_11_09/verification.json`, `tests.log`, `l/`, `u/`, `sketch-preview.png`, `plan-preview.png`.
