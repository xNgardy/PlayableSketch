# Tek alan türü ve ortak açıklık deneyi

Kullanıcı önerisi: koridoru ayrı bir sınıf olarak aramak yerine bütün dikdörtgen/
kare parçaları aynı oda türü saymak; komşu parçaların ortak sınırında kapı veya açık
bağlantı aramak. Kapı tek bir açıklık olarak iki odaya da ait olmalı.

Bu mantık ayrı deney modülünde uygulandı. Çalışan analiz, kabul edilmiş işler,
model ağırlıkları ve orijinal etiketler değiştirilmedi. Yeni bir model eğitilmedi.

## Kesin bağlantı kuralları

- Dikdörtgenlerin temas etmesi veya kesişmesi yalnızca bir komşuluk adayıdır.
- Ortak sınırda gerçek açıklık ve iki dik kapı işareti varsa kapı önerilir.
- Gerçek açıklık var, kapı işareti yoksa açık geçiş önerilir.
- Duvar devam ediyorsa iki alan bağlanmaz. İşaretin yokluğu tek başına boşluk kanıtı
  değildir; belirsiz durumda kullanıcı incelemesi gerekir.
- L veya T biçimli açık alan tek bir büyük dikdörtgene zorlanmaz; ayrı, örtüşmeyen
  dikdörtgen parçalar halinde temsil edilir. Bu parçaların türü aynı odadır.
- Çakışan iki ham kutuyu olduğu gibi iki kat zemin yapmak yerine, bölge geometrisi
  ortak kenara oturtulur veya çözülemeyen çakışma reddedilir.

Kapı kaydı bir kez tutulur ve entity_ids ile iki odaya bağlanır. Aynı destek duvarı
her iki odanın wall_ids listesinde yer alır. Böylece iki odada da aynı açıklık
kullanılır; iki ayrı kapı veya çift oyuk oluşturulmaz. Bu ortak sahiplik mevcut
belge sözleşmesinde de vardır ve yeni deneyde birim testiyle doğrulandı.

## Karşılaştırılan beş kol

1. Mevcut DINO + koridor ve kapı kontrolleri.
2. Yalnız koridor etiketlerini oda yapma; geometri/açıklıklar aynı.
3. Oda ve koridor model iç-alan haritalarının maksimumunu tek alan kabul etme;
   bağlı bileşenleri dikdörtgen parçalara ayırma.
4. Aynı başlıkların yanıtlarını toplayıp [0,1]'e kırparak birleştirme; böylece
   sınıflar arasında dağılmış kararsız yanıtın etkisini de sınama.
5. Modelin oda/koridor başlıklarını kullanmadan gözlenen çizgilerden kapalı serbest
   alan çıkarma ve bunları dikdörtgenlere bölme. Kapı işaretleri yalnız analiz
   maskesinde mantıksal kesim oluşturur; kaynak fotoğrafa duvar çizilmez.

Her iki sınıfsız çıkarımda da duvar/kapı delilleri kaynak görüntüde kontrol edilir.
Büyük iç boşluklar korunur; küçük kâğıt dokusu delikleri ayrı oda sayılmaz.

## Sonuç

50 eski insan çizimi, 20 yeni fotoğraf ve 60 sentetik örnek üzerinde beş kolun
çıktıları kaydedildi; sonra referanslar okunup puanlandı. Bu, daha önce incelenmiş
geliştirme verisinde yöntem geliştirme deneyi; bağımsız kör test değildir.

Yeni 20 fotoğrafta:

| Yöntem | Bölge F1 | Kapı F1 | Kaplanan alan IoU |
|---|---:|---:|---:|
| Mevcut yöntem | 0.667 | 0.439 | 0.712 |
| Yalnız bütün parçaları oda adlandırma | 0.667 | 0.439 | 0.712 |
| Tek alan / en yüksek sınıf yanıtı | 0.404 | 0.222 | 0.548 |
| Tek alan / iki sınıf yanıtını toplama | 0.404 | 0.222 | 0.547 |
| Doğrudan çizgilerden dikdörtgenler | 0.539 | 0.171 | 0.627 |

Sadece isim değişikliği doğal olarak konum veya bağlantı başarısını artırmadı.
İki haritayı birleştirmek de mevcut modelin kaçırdığı çizgi ve alanları yeterince
geri getirmedi; yeni parçalama bazı doğru sınırları bozdu.

Salt çizgi yöntemi Data_68'de doğru biçimde iki bağımsız oda üretti; mevcut yöntem
orada iki oda ve altı yanlış ek koridorla sekiz bölge üretiyordu. Ancak çizgi yöntemi
başka çizimlerde açık/kesik dış sınırdan dolayı iç alanı kaybetti veya fazla parça
üretti. İlk deneme_1 fotoğrafında dış sınır tam kapanmadığı için hiç kapalı alan
çıkaramadı. Bu sonuç çalışan sürümdeki iki kapıyı ve üç açık geçişi değiştirmedi.

Referans bölünmesinden farklı ama geçerli dikdörtgen parçalamalar olabileceği için
bölge F1'i tek ölçüt yapılmadı; toplam kaplanan alan IoU ve kapı sonucu da incelendi.
Bu ölçümler de genel olarak geriledi. Sentetik referans bölge çiftlerine göre uyumsuz
bağlantılar mevcut kolda 1, tek model haritası kollarında 2, saf çizgi kolunda 15 oldu.
Farklı parçalamalar bu eşleştirme sayısını etkileyebilir; yine de mevcut sonuç yeni
sürümü varsayılan yapmak için yeterli değil.

## Bunun öneri açısından anlamı

Önerilen çıktı temsili uygulanabilir: aynı tür alanlar ve aralarındaki kapı/açık
geçişler. Deney bunu belge düzeyinde kurabiliyor. Ancak mevcut sinir ağı oda ve
koridoru ayrı öğrenmiş durumda. Bu başlıkları sonradan birleştirme, tek alan türüyle
baştan/uyarlamalı eğitim yapmakla aynı deney değil. Tek sınıf eğitim hedefinin faydası
bu çalışmada ölçülmedi; iyileştireceği de garanti edilemez.

Bir sonraki karşılaştırma tek birleşik iç-alan hedefi, ayrı duvar ve kapı/açıklık
hedefleriyle eğitim olabilir. L/T ayrıştırma ve ortak sınırın geometrik doğruluğu
ayrıca değerlendirilmelidir. Şu anki zayıf prototip çalışan sisteme alınmadı.

## Kontroller ve dosyalar

57 ilgili test geçti. Yeni testler L alanını iki örtüşmeyen dikdörtgene bölme,
kapalı duvarı geçiş saymama, açık ortak kenar, tek kapının iki oda tarafından
paylaşılması, bağlantısız odalar ve büyük iç boşlukları korumayı kapsıyor.

- [130 örnek raporu](../Saved/ShapeFirst/unified_areas/v3/full/report.json)
- [Karar ve kaynak özetleri](../Saved/ShapeFirst/unified_areas/v3/decision.json)
- [Tek tür ve ortak kapı etiketleme kuralları](../Saved/ShapeFirst/unified_areas/v3/label_mapping.json)
- Kod: SketchPipeline/shape_authoring/unified_areas.py

Çalışan kapı çözümleyicisinin kaynak özetleri ve canlı model dosyası kontrol edildi;
önceki sürüm korunuyor.
