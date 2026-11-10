# Bağlantı kaybı incelemesi — 4 Kasım 2026

Model ve üretim decoder kodu değiştirilmeden kayıtlı maskeler yeniden oynatıldı. Bu bir düzeltme veya yeni başarı değerlendirmesi değildir. Yaklaşık referanslar yalnızca tüm replay işlemleri bittikten sonra açıldı.

## Doğrulama

- 50 insan + 60 sentetik örnekte normal, gözlemli ve önceki kayıtlı decoder çıktıları eşleşti.
- Genişlik kontrolünü geçen her boşluk için tam bir karar kaydı bulundu; 110 örnekte bu kapsama kontrolü geçti.
- 455 cached dosyanın hash kontrolünde değişiklik yok. Üretim decoder kaynakları, ilgili configler, DINO decoder checkpoint ve varsayılan model manifesti korundu.
- Yeni model çıkarımı, eğitim, oracle injection veya eşik ayarı yapılmadı.

## Bulgular

| Plan / açıklık | Aşama ve kesin gözlem |
|---|---|
|Data_23 g001|Ortak sınır var. Boşluk adayları: [[280, 386]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_25 g001|Ortak sınır var. Boşluk adayları: [[152, 240], [278, 378]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_25 g002|Ortak sınır var. Boşluk adayları: [[152, 240], [278, 378]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_31 g001|Ortak sınır var. Boşluk adayları: [[260, 315]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_31 g002|Ortak sınır var. Boşluk adayları: [[217, 249]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_43 g004|Ortak sınır var. Boşluk adayları: [[303, 314]]. Her adayda duvar desteği başarısız; ayrıntılı kontrol sonuçları JSON dosyasında.|
|Data_47 g002|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cH. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_47 g003|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cH. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_47 g004|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cH. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_47 g005|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cH. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_48 g002|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cV1. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_48 g003|Gerekli referans bölge decoded çıktıyla eşleşmiyor: cV1. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_48 g005|Ortak sınır var. Boşluk adayları: [[310, 313], [333, 337]]. Aday genişlikleri [3, 4] px; minimum 6.144 px. İkisi de fiziksel kanıt kontrolüne ulaşmadan eleniyor.|
|Data_8 g001|Gerekli referans bölge decoded çıktıyla eşleşmiyor: c0. Açıklık kanıtı henüz değerlendirilemiyor.|
|Data_8 g002|Gerekli referans bölge decoded çıktıyla eşleşmiyor: c0, rB. Açıklık kanıtı henüz değerlendirilemiyor.|

## Data 25 ve 31: artık açıklanabilen kayıp

Her iki plandaki dört uç bağımsız endpoint teşhisinde bulunuyor. Bununla birlikte decoder önce boşluk arıyor, sonra uçları yalnızca çıkarılmış boşluk kenarlarının yakınında örnekliyor. Modelin bulduğu uç çiftlerinden bağımsız kapı adayı üretmiyor.

- Data 25: gerçek açıklık aralıkları yaklaşık y=207–239 ve 280–308. Sabit eksen x=273.5, yarıçap 4. Çıkarılan boşluklar y=152–240 ve 278–378. Birincisi ortak sınırın başına, ikincisi sonuna kadar uzuyor. Gerçek birer uç eksenden yaklaşık 9.3 ve 7.0 px uzakta. Adayların bir yanında duvar desteği sıfır; yanlış yerde örneklenen model yanıtı da düşük.
- Data 31 g001: gerçek aralık y=257–295; bulunan boşluk 260–315 ve sınır sonuna uzuyor. Alt uç eksenden yaklaşık 7.1 px uzakta. Alt duvar desteği ve alt tick kontrolü başarısız.
- Data 31 g002: gerçek aralık y=226–248; aday 217–249 ile ortak sınırın başından başlıyor. Üst uç eksenden yaklaşık 4.3 px uzakta (yarıçap 4). Üst duvar desteği ve üst tick kontrolü başarısız.

Bu kayıplar aday yerleşimi/yerel duvar izleme çalışmasını gerekçelendiriyor. Tek başına şeridi genişletmenin veya endpoint-first yaklaşımının kapıları güvenle kurtaracağı kanıtlanmadı.

## Data 23

Önceki teşhis doğrulandı: gerçek y≈278–302 yerine 280–386 boşluğu çıkıyor. Sabit eksen x=250, yarıçap 4; alt referans uç x≈260.3. Alt tarafta duvar desteği sıfır. Ayrıca ikinci gerçek endpoint model yanıtı zayıf; bu karma hata olarak kalıyor.

## Açık geçişler

- Data 48 g005: gerçek açıklık yaklaşık x=308–339, y≈170–173. Arama ekseni y=172.5. Mürekkep izdüşümü açıklığı 3 ve 4 px genişlikte boşluklara bölüyor; minimum 6.144 px. Açık-geçiş model yanıtının kontrol edildiği aşamaya ulaşılmıyor. Mürekkebin yazı/gerçek sınır olup olmadığı ve yanlış izdüşümün tam katkısı ayrıca doğrulanmalı.
- Data 43 g004 (validation): referans geçiş yaklaşık x=300–343, fakat mevcut ortak sınır x=303–314 ile sınırlı. Bu dar sınırda open-interface yanıtı yaklaşık 0.000588 (eşik 0.45); adayın bir yanında duvar desteği de yok. Burada yalnızca kapı ucu mantığını değiştirmek yeterli bir çözüm olarak görülemez.

## Sonraki deney önerisi

Önce model ve maskeler sabitken endpoint çiftlerinden aday üretimini ve yerel duvar takibini ayrı kollar halinde ölçmek. Kapı için boşluk + iki tick kuralını korumak. Data 48 açık geçişinde fiziksel izdüşümün parçalanmasını ve Data 43 ortak sınır daralmasını ayrı çalışmak. Eksik koridorların etkisi bu deneyin kazancı sayılmamalı.

## Çıktılar

- `gallery.html`: 7 problemli planın görseli ve ayrıntılı kayıtları; 15 validation/eski-test planının ham trace dosyaları da saklanıyor.
- `report.json`: 15 eksik açıklığın envanteri (eski test 12, validation 3).
- `Data_*/trace.json`: tüm ortak sınırlar, occupied izdüşümleri, genişlikte elenenler dahil boşluklar ve her karar dalı.
- `Data_*/missed-openings.json`: referansın teşhis amaçlı eşleştirmesi; tüm adaylar sunulur, en yakın adayın gerçek kapı olduğu varsayılmaz.
- `verification.json`: hash ve replay eşitlik kayıtları.

v1 teşhis çalışması galeri JSON serileştirme hatasıyla durdu; v2/v3 ara çıktıları silinmedi. Nihai çalışma v4. Bu araç üretim decoder tarafından import edilmez.
