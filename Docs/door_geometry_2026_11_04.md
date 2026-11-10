# Görüntüdeki kapı çizgilerinden kapı önerisi

Kullanıcının tarif ettiği kural DINO refined analiz akışına eklendi. Model ağırlıkları
değişmedi. Çözücü sürümü 2.8, kapı politikası observed-door-jambs/1.5.

## Kural

- Odanın yerel duvar doğrultusuna dik iki çizgi aranır.
- İşaretler duvar eksenini iki yönde de kesmelidir. Çizgi kalınlığına göre gerçek bir
  uzama gerekir; sıradan koridor köşesi veya kalın duvar kenarı yeterli değildir.
- İki işaretin arasında çizgiyle kapatılmamış bir açıklık bulunmalıdır.
- Açıklığın iki yanında aynı duvarın devamı görünmelidir. Hafif eğri duvarın iki
  tarafındaki yerel eksen ayrı örneklenir; tek bir ideal doğruya zorlanmaz.
- Bulunan kapı adayı yalnız konumu uyumlu, iki bölgeye ait ortak duvara atanır.
  Birden fazla bölge çifti aynı derecede uygunsa otomatik atama yapılmaz.
- Mevcut kapı korunur. Güçlü işaret kanıtı varsa açık geçiş kapı olarak düzeltilebilir.
  Uygun ortak duvar bulunamayan aday tanı kayıtlarında unattached olarak saklanır;
  hayalî bölge veya bağlantı oluşturulmaz. Bu adaylar henüz ayrı bir kullanıcı
  arayüzü katmanı olarak gösterilmiyor.

Bütün sonuçlar öneridir; kullanıcı onayı ve mevcut metrik/oynanabilirlik kontrolleri
korunuyor. Bu kural modelin kapı tahminini zorunlu tutmaz; gerçek çizgi kanıtıyla
çalışır. Fiziksel boyut uydurmaz.

## Hedef çizimin sonucu

İlk deneme_1 çizimi, saklanan orijinal kaynak dosyasından canlı 8772 servisine tekrar
yüklendi. Kaynağın özeti önceki dosyayla aynı. Gerçek model çıkarımı ve tüm normal
analiz akışı çalıştı; elle düzeltme yapılmadı.

**3 oda, 3 koridor parçası, 2 kapı, 3 açık geçiş.** Üst koridorun iki ucundaki
işaretler artık kapı. Alttaki L'nin oda girişleri ve dönüşü açık geçiş olarak kaldı.
Belge sözleşmesi geçerli; bunun kendisi metrik ölçek veya oyun oynanabilirliği onayı
değildir.

[Yeni inceleme sonucunu aç](http://127.0.0.1:8772/?job=shape_213f42b2c3c04e45930f9d05829646ee)

Yeni iş önceki planı ezmedi ve otomatik onaylanmadı. Servis güncel kodla yeniden
başlatıldı, mevcut iş dosyalarının değişmediği doğrulandı. Yeni önbellek kimliği,
kapı ve koridor kontrol kodlarının özetlerini de içeriyor.

## Karşılaştırma

Aynı model maskeleri ve aynı oda/koridor geometrisiyle 70 insan çizimi ve 60 sentetik
kontrol örneği karşılaştırıldı. İki kolun tahminleri kaydedildikten sonra referanslar
okundu. Algoritma geliştirilirken bu retrospektif örnekler ve köşe/duvar birim testleri
yeniden incelendi; bu bağımsız kör test değildir. İlk geniş kurallar yanlış kapılar
ürettiği için etkinleştirilmedi. Nihai sürüm duvarı gerçekten kesen işareti çizgi
kalınlığına göre kontrol ediyor.

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Eski insan çizimleri eğitim grubunda doğru kapı | 39/45 | 41/45 |
| Aynı grupta önerilen kapı | 41 | 43 |
| Eski insan doğrulama kapı F1 | 0,9474 | 0,9474 |
| Eski insan test kapı F1 | 1,0000 | 1,0000 |
| Sentetik doğru kapı | 115/130 | 123/130 |
| Sentetik önerilen kapı | 115 | 123 |
| Sentetik kapı F1 | 0,9388 | 0,9723 |
| Sentetik doğru bölgelere bağlı açıklık F1 | 0,9048 | 0,9338 |
| Sentetik yanlış bağlantı | 1 | 1 |

Yeni Data_51..70 fotoğraflarındaki son kapı ve bağlantı ölçümleri bu değişiklikle
artmadı. Bazı görüntü adayları için uyumlu iki bölgeli duvar yok; bazı işaretler de
yeterli çizgi kanıtı vermiyor. Dolayısıyla bu güncelleme tüm yeni çizimleri çözmüş
sayılmamalı. Görsel olarak belirgin hedef çizimdeki iki kapıyı ise doğru türde
oluşturuyor. Bölgeler iki kol arasında aynı kaldı.

## Doğrulama ve dosyalar

69 farklı ilgili test geçti. Bunlar kapalı açıklık, tek işaret, paralel raylar,
açık koridor köşesi, belirsiz bölge sahipliği, ölçekli koordinat dönüşümü, mevcut
kapıların korunması, iş kimliği, HTTP oturumu ve metrik inceleme akışını kapsıyor.
HTTP testleri geçici localhost portları kullanılarak ayrıca çalıştırıldı.

- [130 örnek raporu](../Saved/ShapeFirst/door_geometry/v5/full/report.json)
- [Canlı aktivasyon ve hedef çizim kontrolü](../Saved/ShapeFirst/door_geometry/v5/activation.json)
- [Entegrasyon ve kaynak özetleri](../Saved/ShapeFirst/door_geometry/v5/integration.json)
- [Canlı akışın tam model çıktısı](../Saved/ShapeFirst/door_geometry/v5/integration_deneme_1/proposals.json)

Model eğitimi veya yeni ağırlık yayını yapılmadı. Değişiklik görüntü kanıtının
kapı türüne ve doğru ortak duvara bağlanması aşamasındadır.
