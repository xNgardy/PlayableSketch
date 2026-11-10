# Yeni koridor verisiyle eğitim sonucu

Yeni verilerle iki eğitim denemesi tamamlandı. **Yeni ağırlıklar genel kalite
ölçütlerini geçemedi; çalışan model korundu.** Bu bir eğitim yapılmadığı veya
etiketlerin kullanılmadığı anlamına gelmiyor: ağırlık dosyaları, kayıp geçmişi,
gerçek doğrulama tahminleri ve seçim kararı kaydedildi.

## Veri ve eğitim

Yeni paketin 104 eğitim görünümü kullanıldı; 4 doğrulama ve 4 test fotoğrafı
öğrenmeye girmedi. Eski eğitimdeki 35 insan çiziminin dört görünümü ve 96 sentetik
planın dört stili de korundu. Toplam 628 eğitim görünümünün sabit DINOv2 özellikleri
yerel olarak çıkarıldı. Bu sayı bağımsız özgün çizim sayısı değildir.

Her turda 160 örnek, önce kaynak plan seçilerek alındı: 120 eski, 32 yeni fotoğraf
ailesi, 8 karmaşık sentetik aile. Böylece türev sayısı bir planın eğitim ağırlığını
katlamadı. İnsan etiketlerinde bilinmeyen pikseller sıfır kayıp ağırlığında kaldı.
Sayısal ölçü/OCR kullanılmadı.

İlk deneme mevcut ağırlıklardan başlayıp 10 tur boyunca çözümleyiciyi güncelledi;
DINOv2 omurgası sabit tutuldu. Öğrenme oranı 0,0001; eski örneklerde önceki modelin
çıktısını koruyan ek kayıp uygulandı. Eğitim kaybı 0,2613'ten 0,0934'e düştü.

Doğrulamadaki gerilemeler üzerine ikinci, açıkça kaydedilmiş bir yaklaşım denendi:
5 tur yalnız tick, open_interface ve door_endpoint çıkış satırları eğitildi.
Diğer ağırlıkların birebir sabit kaldığı kontrol edildi. Bu denemenin aynı veri
üzerinde sıralı doğrulama geliştirmesi olduğu protokolde belirtiliyor; yeni bir
bağımsız deney veya kör test sayılmamalı.

## Doğrulama sonuçları

| Grup / ölçüm | Başlangıç | Tam çözümleyici / tur 10 | Sınırlı çıkış eğitimi / tur 5 |
|---|---:|---:|---:|
| Eski doğrulama / Bölge F1 | 0.8947 | 0.8649 | 0.8947 |
| Eski doğrulama / Kapı F1 | 0.9474 | 0.9474 | 0.9474 |
| Eski doğrulama / Doğru bölgelere bağlı açıklık F1 | 0.8800 | 0.7826 | 0.8800 |
| Yeni doğrulama / Bölge F1 | 0.6857 | 0.7500 | 0.6857 |
| Yeni doğrulama / Kapı F1 | 0.5714 | 0.4615 | 0.5714 |
| Yeni doğrulama / Doğru bölgelere bağlı açıklık F1 | 0.2222 | 0.3750 | 0.2222 |

Tam eğitim yeni geometrileri ve bazı bağlantıları daha iyi buldu; fakat yeni kapı
F1'i ve eski bağlantı başarısı düştü. 2. turda yeni bölge F1'i 0,7879'a kadar çıktı,
amacı oluşturan diğer sonuçlar birlikte iyileşmedi. Sınırlı yaklaşım son çıktı
ölçümlerinde başlangıçla aynı kaldı. Başlangıç ağırlığı da seçim adayıydı; eşitlikte
erken aday korundu. Sonuç: yeni model kullanıma alınmadı.

Ölçütler eğitimden önce sabitlendi: eski, yeni ve sentetik doğrulamada bölge F1'inde
0,03; kapı ve bağlantı F1'inde 0,04; bağlantı kesinliğinde 0,03'ten fazla düşüşe izin
verilmedi. Amaç eski ve yeni bölge/kapı/bağlantı F1'lerinin dengeli ortalamasıydı.
Sentetik grup ayrıca gerileme kontrolü olarak kullanıldı. Test sonuçları ağırlık
seçmek için kullanılmadı.

## Kapı uçlarında öğrenme var mı?

Seçimden sonra, yalnız doğrulama üzerinde ve mevcut sabit tepe/tolerans yöntemiyle
ham kapı ucu çıkışı incelendi. Yeni dört doğrulama çizimindeki 20 kapı ucundan:

- Başlangıç modeli 9'unu buldu: F1 0,6207; kesinlik 1,0; duyarlılık 0,45.
- Tam eğitimin 10. turu 12'sini buldu: F1 0,7500; kesinlik 1,0; duyarlılık 0,60.
- Sınırlı eğitimin 5. turu 10'unu buldu: F1 0,6667.

Bu sonuç modelin bazı kapı işaretlerini daha iyi öğrendiğini, ancak bu kazanımın
son kapı/bölge bağlantısına taşınmadığını gösteriyor. Bu tanı incelemesi model
seçimini değiştirmedi. Küçük, aynı çizerden ve yaklaşık etiketli bir doğrulama
üzerindeki artıştır; genel başarı garantisi değildir.

## Ayrılmış test

Seçim sabitlendikten sonra 10 eski test, 4 yeni test ve 60 sentetik kontrol örneği
çalıştırıldı. Seçilen ağ başlangıç ağı olduğundan aynı ağırlığı iki kez çalıştırmak
yerine aynı tahminin ölçümü iki sütunda yeniden kullanıldı. Reddedilen ağırlıklar
test sonuçlarına göre seçilmedi veya yeniden ayarlanmadı.

| Korunan model / grup | Bölge F1 | Kapı F1 | Doğru bölgelere bağlı açıklık F1 |
|---|---:|---:|---:|
| Eski test / 10 çizim | 0.9286 | 1.0000 | 0.9143 |
| Yeni test / 4 çizim | 0.5789 | 0.0000 | 0.1111 |
| Sentetik kontrol / 60 örnek | 0.9062 | 0.9388 | 0.9048 |

Yeni testte üç kapının hiçbiri tam kapı önerisi olarak bulunmadı. Bu dört çizim,
korunan model için de zor; yeni veriyle eğitimin sorunu bütünüyle çözdüğü
söylenemez. İnsan referansları yaklaşık ve aynı kullanıcıdan olduğu için bunlar
farklı çizer başarısı veya yeni kör test iddiası taşımaz.

## Çalıştırma sırasında düzeltilen hatalar

Test sırasında eski Data_47 üzerinde yeni bir koridorun duvarı üç bölgeye
atayabildiği görüldü. Kanonik dönüşümden sonra böyle bir eklemeyi reddeden sözleşme
kontrolü eklendi. Bu düzeltmede etiket veya test puanı kullanılmadı. Kayıtlı 105
doğrulama tahmini yeni kontrolle tekrar çözüldü; geometriler ve seçim değişmedi.
Çözücü tanı sürümü 2.7.1 oldu.

Data_66'nın eğik görüntüsünde dönüşüm zincirinin boyutları NumPy int64 olarak
kalıyordu ve JSON kaydı duruyordu. Bunlar yerel Python int türüne çevriliyor;
koordinatlar veya pikseller değişmiyor. Düzeltmelerden sonra test tamamlandı.

42 ilgili birim testi geçti. Altı bölgeli/beş geçişli önceki L örneği sözleşme
kontrolünden geçmeye devam ediyor. Tüm korunan veri dosyaları ve canlı model
özeti kontrol edildi; orijinaller, etiketler ve canlı ağırlık değişmedi.

## Sonraki somut iş

Yeni doğrulamadaki doğru kapı uçlarını, bölge çıkarımından bağımsız aday olarak
koruyup gerçek duvar ve uygun bölge çiftiyle eşleştiren aşamayı geliştirmek gerekiyor.
Ardından aynı sabit doğrulama ölçütleriyle yeniden değerlendirme yapılmalı. Bu
veriler üzerinde daha çok deneme yapmak bağımsız test ihtiyacını ortadan kaldırmaz.

## Kayıtlar

Tüm kayıtların kökü: Saved/ShapeFirst/dinov2/corridor_addon/v1/.

- [Karar ve kaynak özetleri](../Saved/ShapeFirst/dinov2/corridor_addon/v1/decision.json)
- [İlk eğitim raporu](../Saved/ShapeFirst/dinov2/corridor_addon/v1/training_report.json)
- [Sınırlı eğitim raporu](../Saved/ShapeFirst/dinov2/corridor_addon/v1/markers/training_report.json)
- [Son seçim](../Saved/ShapeFirst/dinov2/corridor_addon/v1/final_selection.json)
- [Test raporu](../Saved/ShapeFirst/dinov2/corridor_addon/v1/evaluation_report.json)
- [Kapı ucu tanısı](../Saved/ShapeFirst/dinov2/corridor_addon/v1/validation_endpoint_diagnostic.json)

Çalışan modeli değiştirmek veya önceki eğitimi ezmek için bir işlem yapılmadı.
Yeni eğitim önbelleği ve aday ağırlıklar sonraki inceleme için saklandı.
