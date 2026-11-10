# PlayableSketch: projeyi baştan sona anlama raporu

**Güncel durum: 4 Kasım 2026 | Teknik olmayan okur için**

## 1. Bu proje ne yapıyor?

PlayableSketch, elle çizilmiş bir kat planını düzenlenebilir bir tasarıma, ardından Unreal Engine içinde gezilebilen bir seviyeye dönüştüren yerel bir uygulama. Çizimdeki oda, koridor ve kapılar için öneriler üretir. Sen bu önerileri kontrol eder, ölçüleri düzenler ve planı onaylarsın. Onaylanan plan, oyun motorunda geometri ve çarpışma kontrollerinden geçerek açılır.

Bugünkü ürün yaklaşımı **AI önerir, kullanıcı düzeltir ve onaylar** şeklindedir. Hiç müdahale gerektirmeden her çizimi doğru çözen bir sistem olduğu gösterilmiş değil.

**Bir örnek:** Yan yana iki oda ve aralarındaki bir kapıyı çiziyorsun. Sistem iki oda ve kapı öneriyor. Bir odanın genişliğini 5 metre yapıyorsun. Başlangıcı bir odaya, hedefi diğerine koyup planı onaylıyorsun. Unreal, geçişi fiziksel olarak uygun bulursa oyuncu temsilcisi odalar arasında ilerleyebiliyor.

| Sıra | Ne oluyor? | Kim yapıyor? |
| --- | --- | --- |
| 1 | Çizim yükleniyor. | Sen |
| 2 | Görüntü hazırlanıyor; oda ve geçiş adayları bulunuyor. | Python ve AI |
| 3 | Eksikler düzeltiliyor, ölçüler seçiliyor. | Sen ve düzenleyici |
| 4 | Kaydedilmiş plan açıkça onaylanıyor. | Sen |
| 5 | Unreal için doğrulanmış paket oluşturuluyor. | Python |
| 6 | Zemin, duvar, açıklık ve çarpışmalar üretiliyor. | Unreal Engine |
| 7 | Geçiş kontrol edilip seviye oynanabilir hale geliyor. | Unreal Engine |

**Önemli ayrım:** Çizimdeki şekli anlamak, tasarıma metre cinsinden boyut vermek ve içinde yürünebilir bir seviye üretmek üç ayrı problemdir. Proje bu işleri ayrı aşamalarda çözer. [R1, R2]

<!-- pagebreak -->

## 2. Neyin ne olduğunu anlayalım

Sistem aynı bilgisayarda çalışan üç ana parçadan oluşur: **tarayıcı arayüzü, Python işlem katmanı ve Unreal uygulaması.** Tarayıcı senin çalışma masandır; Python çizimi yorumlar ve planı hesaplar; Unreal ise planı üç boyutlu olarak kurar ve hareketi denetler.

| Parça | Basit açıklaması |
| --- | --- |
| Web çalışma alanı | Resmi yüklediğin; oda, kapı ve ölçüleri düzenlediğin ekran. |
| Python işlem katmanı | Analiz işlerini yürütür, kayıt tutar, ölçüleri çözer ve paket oluşturur. |
| DINOv2 ve eğitilen ağ başlığı | Görüntüdeki yapısal izleri bulmaya yardımcı olan AI bölümü. |
| Geometri kuralları | AI yanıtlarını temiz oda, duvar ve bağlantı önerilerine dönüştürür. |
| Boyutlandırma çözücüsü | Oda, kapı ve koridor boyutlarını birlikte ve tutarlı hesaplar. |
| Unreal Engine | Zeminleri, duvarları ve çarpışmaları üretir; oyuncunun geçişini sınar. |

### AI kısmında iki farklı “decoder” anlamı var

DINOv2, başka bir kurumun önceden eğittiği görsel özellik çıkarıcısıdır. Projede bu ana ağ donduruldu; yani eğitim sırasında ağırlıkları değiştirilmedi. Üzerine bize ait küçük bir ağ başlığı eğitildi. Bu başlık, görüntüde duvar, oda içi, koridor, kapı işareti ve benzeri alanlar için haritalar üretir.

Ardından **kurallarla çalışan geometri çözümleyicisi** bu haritaları yorumlar. Belgelerde bu ikinci parçaya da decoder deniyor. Dolayısıyla model eğitimiyle yapılan bir iyileştirme ile kuralları değiştirerek elde edilen iyileştirme aynı şey değil.

### Klasörler ne işe yarıyor?

- **Source / Content / Config:** Unreal kodu, proje varlıkları ve ayarlar.
- **SketchPipeline:** Görüntü işleme, AI, plan düzenleme ve doğrulama kodları.
- **Scripts ve iki Start dosyası:** Sistemi açan ve kontrollü testleri çalıştıran araçlar.
- **Data:** Özgün çizimler, referanslar ve veri kayıtları.
- **Docs:** Kullanım, geliştirme ve deney raporları.
- **Saved:** Üretilen sonuçlar, işler, Python ortamları, bazı model bağımlılıkları ve paketli uygulama.

**Saved klasörü tamamen silinmemeli.** Bu projede yalnızca geçici dosyalar içermiyor; çalışan sistemin ihtiyaç duyduğu dosyalar da burada. [R1, R3]

<!-- pagebreak -->

## 3. Bir çizim içeride nasıl işleniyor?

### Önce görüntü hazırlanır

Yüklenen PNG/JPG dosyası korunur. Sistem çalışma için boyutu ve koordinatları düzenlenmiş bir kopya üretir. Soluk fotoğraflarda mürekkebi görünür kılmaya, uygun durumlarda kareli kâğıt çizgilerini bastırmaya çalışır. Bu işlemler her görüntüde kusursuz değil; özgün çizimin korunması bu yüzden önemli.

### AI yapısal alanlar önerir

Model görüntüyü gerçekten işler; önceden kaydedilmiş çizimleri arayıp sonucunu döndürmez. Oda içleri, koridorlar, duvarlar ve kapı uçları gibi izler için yanıt üretir. Aynı bilgisayardaki model dosyalarını kullanır; normal çalışma sırasında çizim buluta gönderilmez.

### Kurallar, izleri bir plana dönüştürür

AI çıktısı doğrudan duvar inşa etme komutu değildir. Geometri kuralları dikdörtgen bölgeleri, ortak sınırları ve açıklıkları kontrol eder. Komşu iki odanın paylaştığı duvar tek fiziksel duvar olarak temsil edilir. Bir kapının hangi iki bölgeyi bağladığı ayrıca kaydedilir.

**Kapı için yalnızca bir çizgi boşluğu yeterli değildir.** Boşluğun çevresindeki duvar ve kapı uç işaretleri de değerlendirilir. Böylece tesadüfi bir kalem kopması otomatik olarak kapı sayılmamaya çalışılır. Açık koridor geçişi ile kapı işaretleri ayrı ele alınır.

### Sen önerileri düzeltirsin

Çalışma alanında oda ve koridor ekleyebilir, taşıyabilir, büyütüp küçültebilir, türünü değiştirebilir ve bağlantıları düzenleyebilirsin. Bir bağlantı duvarından koparsa sistem bunu sorunsuzmuş gibi saklamak yerine dikkat gerektiren bir durum olarak gösterir.

Analiz boş dönerse, zaman aşımına uğrarsa veya model kullanılamazsa görüntü kaybolmaz. **Manuel araçlarla devam edilebilir.** Yapılan düzenlemeler geçmişte saklanır; Undo/Redo ile geri alınabilir.

### Sayı okumak güncel akışın parçası değil

Yeni yaklaşım “önce şekil” mantığıyla çalışır. Çizime ölçü yazman gerekmez. Eski sayı okuma hattı proje içinde korunuyor; fakat yeni açılış komutları sayısal OCR çağırmadan çalışıyor. Her yükleme veya onay işlemi modeli yeniden eğitmez. [R2, R3, R4]

<!-- pagebreak -->

## 4. Ölçüler, onay ve Unreal aktarımı

### Çizim oranı, gerçek ölçü değildir

Bir çizimde oda büyük görünüyorsa sistem bunu başlangıç tasarımı için kullanabilir. Bu, odanın gerçek dünyada kaç metre olduğunun bulunduğu anlamına gelmez.

Başlangıç politikası, en büyük yorumlanmış oda için 20 m² referans alanı; koridor için 2 metre, kapı için 1,20 metre genişlik gibi tercihler içerir. Bunlar düzenlenebilir tasarım önerileridir. Arayüzde uzunluklar metreyle gösterilir; Unreal'a giden ortak plan santimetre kullanır.

### Boyutlar birlikte çözülür

Bir odayı büyütmek komşu odayı, ortak duvarı ve kapının yerini etkileyebilir. Bu nedenle her ölçü bağımsız hesaplanmaz. Çözücü, bağlantıları ve çakışmama koşullarını birlikte korumaya çalışır.

- **Custom / kullanıcı değeri:** Senin seçtiğin ölçü; sessizce yeni öneriyle değiştirilmez.
- **Lock:** Seçilen değeri sabit tutar.
- **Reset:** Kullanıcı müdahalesini kaldırıp yeniden öneri politikasına döner.
- **Keep proportions:** Boyut değişirken şeklin oranını korur.

Seçimler çelişirse hata gösterilir. Son geçerli önizleme korunabilir; fakat yeni seçimlerin geçerli olduğu iddia edilmez. Kilitli ölçüler kendiliğinden değiştirilmez.

### Onay, belirli bir kayıt için geçerlidir

Confirm plan, o anda kaydedilmiş şekillerin, ölçülerin ve ayarların birlikte onayıdır. Daha sonra bunlardan biri değişirse yeniden onay gerekir. Eski veya değiştirilmiş bir kaydın güncel planmış gibi aktarılması reddedilir.

Export for Unreal bir ZIP indirir. İçindeki **validated-layout.json** Unreal'ın okuyacağı plandır. **authoring.json** tasarım kararlarını; **manifest.json** ise kaynak, sürüm ve bütünlük bilgilerini saklar. Dosya özetleri, içerik değişikliğini fark etmeye yarayan parmak izleri gibidir.

### Son söz Unreal'ın kontrollerindedir

Geometry only yalnızca geometri aktarımı ister. Playable level ise farklı Start ve Goal odaları seçilmesini ve geçiş kontrollerini gerektirir. Python bir ön kontrol yapar; Unreal gerçek geometri, çarpışma, zemin desteği ve hareketi ayrıca denetler. Paket indirilmiş olması, Unreal'ın Play izni verdiği anlamına gelmez. [R5, R6]

<!-- pagebreak -->

## 5. Geliştirme geçmişi: ilk yaklaşım ve öğrendiklerimiz

Projede iki yol haritası var. **Eski 14 aşamalı plan**, çizimdeki ölçüleri okuyarak seviye üretmeye odaklanıyordu. **Yeni 5 aşamalı plan**, önce şekli düzenlemeyi, sonra ölçüleri tasarım kararı olarak seçmeyi esas alıyor. “Step 5” ifadesi bu nedenle iki farklı belgede farklı işi anlatabilir.

### A. Önce Unreal'ın planı kurabilmesi sağlandı

İlk çekirdek, oda ve bağlantı verilerinden zemin, duvar, kapı ve koridor üretiyordu. Sonra hazır bir planı doğru biçimde kuran ortak JSON aktarımı eklendi. Böylece AI hatalarıyla oyun motorunun geometri hataları ayrı sınanabildi.

Yerel yeniden oluşturma, doğrulama, fiziksel geçiş, kayıt ve paketli Mac uygulaması geliştirildi. Bu altyapı yeni yaklaşımda yeniden kullanıldı; oyun motoru tarafı sıfırdan yazılmadı.

### B. Sayı okuma geliştirildi, fakat planı anlamaya yetmedi

Eski OCR deneyinde TrOCR'ın yazı tanıma kısmı eğitildi. On özgün insan test çiziminde sayı ve konumu birlikte değerlendiren F1, **%42,5'ten %59,0'a** çıktı. Doğru santimetre değerini yakalama oranı **%49,4'ten %69,7'ye** çıktı.

Bu, sayı tanıma için olumlu sonuçtu. Fakat doğru sayıyı okumak, bütün odaları ve bağlantıları doğru çıkarmayı sağlamadı. Bu skorlar bugünkü şekil tespitinin başarı oranı olarak kullanılmıyor.

### C. Klasik çizgi işleme ve kareli kâğıt temizliği denendi

Kâğıt ızgarası, ölçü çizgileri ve yazılar duvar/kapı gibi algılanabiliyordu. Kontrollü 19 görüntülük eski pilotta ızgara bastırma, açıklık F1'ini **%33,8'den %50,5'e** yükseltti. Bu küçük geliştirme çalışmasıydı; yeni kullanıcı başarısı olarak genellenmedi.

Daha sert açıklama çizgisi temizliği bazı yanlışları azalttı, ama gerçek geçişleri de kaybetti. Tek bir F1 artışı, bütün koşullarda daha güvenilir ürün anlamına gelmedi.

### D. Yerel görsel dil modeli denendi

Küçük Qwen görsel dil modeli, tek başına güvenilir geometri üretemedi. Hibrit denemede verilen adayları aynen koruyup yeni yararlı geometri eklemedi; işlem süresi arttı. Bu model güncel akışın temel çözümü seçilmedi. Sonuç, bütün görsel dil modellerinin başarısız olduğu anlamına gelmez. [R7, R8, R9]

<!-- pagebreak -->

## 6. Geliştirme geçmişi: şekil odaklı yaklaşım

### E. Küçük U-Net modeli: sentetikte iyi, insan çiziminde yetersiz

Projeye ait U-Net modeli sıfırdan eğitildi. Bilgisayarda üretilen çizimlerde geliştirme hedeflerini geçti; ilk altı insan çiziminde kullanılabilir oda/bağlantı yapısını çıkaramadı. Manuel düzenleme yolu çalışıyordu, fakat insan çizimi otomasyonu hedefi karşılanmadı.

### F. Sorunun yalnızca eğitim olmadığı görüldü

Aynı modelde görüntüyü hazırlama biçimi değiştirildi. Küçük teşhis kümesinde doğru bölge sayısı **0/15'ten 12/15'e** çıkabildi. Daha fazla çözünürlük her zaman daha iyi değildi; 768 piksel bazı seçeneklerde 512'den kötüydü. Kapılar ise hâlâ zayıftı.

Kurallı çözümleyicide ölçek ve ince kapı kanıtları düzeltildi. Altı çizimde gerçek açıklık sayısı sonradan **17** olarak düzeltildi: önce sayılan bir çizgi kırığı aslında kapı değildi. **6/18 yerine 6/17 yazılması bir model kazanımı değil, ölçüm düzeltmesidir.**

### G. İnsan çizimlerine yönelik yeniden eğitim tek başına çözmedi

Birkaç eğitim denemesinde bütün ağ, son katmanlar veya yalnızca işaret başlıkları güncellendi. Bazı kontrast işlemleri görüntüyü kötüleştirdi; bir deneme dosya yolu hatasıyla durdu. Son aday, aynı teşhis çizimlerinde daha iyi görünse de ayrı tutulan dokuz planda yalnızca **2/18 açıklık konumu** eşleştirdi. Sentetik kontrol de geriledi. Bu aday otomasyon için kabul edilmedi.

### H. DINOv2 ile görsel temsil güçlendirildi

Dondurulmuş DINOv2 üzerine bize ait küçük ağ başlığı eğitildi. Oda/bölge algılaması iyileşti, fakat ilk denemede bağlantı hedefleri karşılanmadı. Model çıktısını plana çeviren kurallar da iyileştirildi.

| Sonraki deneme | Ne öğrendik? |
| --- | --- |
| Bölge kurtarma | Ortak sınırları birlikte düzenlemek, eksik oda/koridorları geri getirdi. Eski testte doğru bölge 19/26'dan 24/26'ya çıktı. |
| A: yalnızca kapı uç çiftleri | Ek kazanım sağlamadı. Daha çok aday üretmek tek başına yeterli olmadı. |
| B: yerel duvar takibi | Dalgalı duvarın gerçek yolunu izlemek kapıları kurtardı; açıklık konumu 8/20'den 13/20'ye çıktı. |
| Koridor ve açık geçiş düzeltmeleri | Birleşik son sürümde doğru bölge 26/26, açıklık konumu 17/20 oldu. Üç açık geçiş hâlâ eksik. |

Güncel açılış komutları bu deneysel DINO adayını açıkça seçer. Kodun genel model varsayılanı ve eski U-Net yolu korunur. [R3, R4, R10, R11, R12]

<!-- pagebreak -->

## 7. Bugünkü doğruluk ne kadar?

**Tek bir genel accuracy sayısı henüz yok.** Oda bulmak, açıklığın yerini bulmak ve doğru odaları bağlamak ayrı ölçülüyor. Aşağıdaki sonuçlar otomatik önerilerindir; kullanıcı düzeltmesinden sonra elde edilen başarı değildir.

### Eski 10 çizimlik geliştirme test grubunun son sonucu

| Ölçüm | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Oda ve koridor bölgeleri | %86,7 | %100,0 | **%92,9** |
| Kapı/açık geçiş konumu | %100,0 | %85,0 | **%91,9** |
| Açıklığın doğru bölgelere bağlanması | %100,0 | %84,2 | **%91,4** |

**Bu sayılar nasıl okunur?** Bölge değerlendirmesinde 26 gerçek bölgenin tamamı bulundu; fakat toplam 30 öneri vardı. Dört fazla öneri bulunduğu için recall %100 olsa da F1 %100 değil. Açıklık konumlarında 20 referansın 17'si bulundu. Bağlantı değerlendirmesinde sahibi bilinen 19 referansın 16'sı doğru eşleşti.

Bölge referansı yalnızca 10 planın 8'inde mevcut. Sahibi bilinmeyen bir açıklık, bağlantı metriğinin paydasına alınmıyor. Etiketlerin bir kısmı yaklaşık olduğundan fazladan öneriler bağımsız inceleme gerektiriyor.

### Diğer kontroller

- Beş çizimlik validation grubunda bölge F1 **%89,5**, doğru bağlantı F1 **%88,0**.
- 60 sentetik kontrolde bölge F1 **%90,6**, doğru bağlantı F1 **%90,5**.
- Sentetikte bütün planın eksiksiz doğru çıkması **30/60, yani %50**.
- İnsan çizimlerinde bütün planın tamamen doğru çıkma oranı ve gerçek düzeltme süresi henüz ölçülmedi.

### Bu sonuçların sınırı

İnsan çizimleri 35 eğitim, 5 validation ve 10 eski test planı olarak ayrıldı. Ancak bu koleksiyon geliştirme boyunca incelendi; bazı iyileştirmeler sonuçlara bakılarak yapıldı. Aynı çizim sahibinin farklı planları da gruplarda bulunabiliyor. Bu nedenle “yeni bir kullanıcının çiziminde %93 başarı” denemez.

**Mevcut veride F1 yaklaşık %91-93; yeni ve bağımsız çizimlerde genel başarı henüz bilinmiyor.** Eski sayı okuma puanları, farklı küçük pilotlar ve bugünkü şekil puanları tek bir ortalamada birleştirilmemeli. [R12]

<!-- pagebreak -->

## 8. Ürün akışı ve güvenilirlik: neler tamamlandı?

Yeni beş aşamalı planın yerel çekirdek teslimi tamamlandı. Bu, otomatik algılamanın kusursuz olduğu veya ürünün herkese dağıtıma hazır olduğu anlamına gelmez.

| Aşama | Yapılan iş | Son durum |
| --- | --- | --- |
| Step 1 | Şekil, ölçü, kaynak ve kullanıcı kararını ayıran veri yapısı. | Uygulandı. |
| Step 2 | AI önerileri, geometri kuralları ve manuel düzeltme. | Çalışıyor; algılama hataları sürüyor. |
| Step 3 | Ortak boyutlandırma, kilitler ve tutarlı önizleme. | Uygulandı. |
| Step 4 | Tek çalışma alanı, görsel düzenleme, kayıt ve onay. | Çalışıyor; gerçek tarayıcı akışları sınandı. |
| Step 5 | İndirilebilir paket, Unreal aktarımı, kayıt ve uçtan uca testler. | Yerel çekirdek akış doğrulandı. |

### Gerçekte ne sınandı?

**135 Python testi ve 15 JavaScript durum kontrolü geçti.** Bunlar sözleşme, geometri, kayıt, eski onayın reddi, boyutlandırma ve API davranışını kontrol eder. AI'ın çizimleri %100 doğru bulduğunu söylemez.

Gerçek tarayıcıda hem hazır örnek hem dosyadan yüklenen sayısız kontrol çizimi denendi. Gerçek DINO analizi çalıştı. Arayüzde oda adı ve genişliği değiştirildi; plan onaylandı ve ZIP indirildi.

İndirilen planın aynı içeriği paketli Unreal uygulamasına aktarıldı. **Gerçek Pawn hedefe ulaştı.** Ayrı süreçte kayıt geri yüklendi; servis kapalıyken önceki hazır seviye korundu. Hatalı yeni import, mevcut geçerli seviyeyi yarım değiştirmedi.

### Olumsuz test de önemliydi

Tarayıcı kontrolünde 1,20 metrelik kapı Python ön kontrolünü geçti; fakat Unreal'ın çarpışma/grid kontrolü yürünebilirliği reddetti. Play açılmadı. Kapı arayüzde 1,60 metreye çıkarıldı, yeniden onaylanıp indirildi; aynı yeni paketle Pawn hedefe ulaştı.

Bu sonuç **1,60 metrenin her durumda garanti olduğu** anlamına gelmez. Öğrendiğimiz şey, ön kontrolün son motor kontrolünün yerine geçemediği ve yeniden düzenleme akışının çalıştığıdır.

Başka bir kontrollü uçtan uca testte AI analizinden sonra test amaçlı topoloji düzeltmeleri de yapıldı. Bunlar otomatik algılama başarısı olarak sayılmadı. Paketli uygulama testleri görüntüsüz yürütüldü; insanla etkileşimli oyun testi yapıldığı iddia edilmiyor. Tam erişilebilirlik ve tüm ekran boyutları doğrulaması da yapılmış değil. [R5, R6, R13]

<!-- pagebreak -->

## 9. Sistemi kullanma ve sonraki geliştirme adımı

### Günlük kullanım

1. Proje klasöründeki **Start Sketch Workspace.command** dosyasını aç. Terminal açık kalsın. Tarayıcıda **http://127.0.0.1:8772/** adresine git.
2. **Upload sketch** ile çizimini yükle veya **Use a sample** ile dene. Başlangıç için dikdörtgen odalar ve belirgin kapı işaretleri kullan.
3. **Sketch / Plan / Compare** görünümlerinde önerileri incele. Eksik şekil ve bağlantıları düzelt; şekil değişikliklerinde **Save changes** kullan.
4. Sağ panelden isim ve metre cinsinden ölçüleri ayarla. Çelişki varsa kilitleri, kapı yerini ve boyutları gözden geçir.
5. **Settings > Delivery > Playable level** seç. Farklı Start ve Goal odaları belirleyip **Apply settings** kullan.
6. **Review plan > Confirm plan > Export for Unreal** ile paketi indir.
7. **Start PlayableSketch.command** dosyasını aç. Son oynanabilir dışa aktarım seçilir. Uygulamada **Import**, Ready sonrasında **Play** kullan. Elle hareket için görüntü alanına tıklayıp WASD kullanabilirsin.

ZIP'i özel bir klasöre taşımak gerekmez. Hazır uygulama seçilen kaydı yerel servisten alır. Unreal Editor'a elle aktaracaksan ZIP içindeki **validated-layout.json** dosyasının yolunu Actor'ın **Import Layout Json Path** alanına verip **Import Canonical Layout Json** kullanırsın; bir Imported Layout Asset de atanmalıdır.

### Bakımda ne yapıldı?

Yeniden üretilebilir derleme kopyaları ve önbelleklerden **7,68 GiB** temizlendi. Kaynak kod, model dosyaları, çizimler, çalışma ortamları, onaylar ve değerlendirme kanıtları korundu. Sonraki Unreal derlemesi önbellekleri tekrar oluşturacağı için daha uzun sürebilir.

Ana kodlar İngilizce. Eski rapor üreticilerinin Türkçe içerikleri ayrı metin kaynaklarına taşındı. Aktif kodda yinelenen Undo/Redo, API ve hata akışları sadeleştirildi. Bu bakım AI doğruluğunu artıran bir eğitim deneyi değil. [R14]

### Şimdi en yararlı adım

Daha önce kullanılmamış, mümkünse farklı kişilerin çizdiği 10 planı önce bağımsız değerlendirme için ayırmak. Her planda yanlış/eksik oda ve geçişleri, gereken düzeltme sayısını ve oynanabilir seviyeye kadar geçen süreyi kaydetmek. Sonra en çok zaman kaybettiren sorunu iyileştirmek.

Bugünkü kapsam tek katlı, üstten görülen, dik açılı ve dikdörtgen bölümlü planlar. Çok kat, serbest biçimli odalar, genel kullanıma açık bulut hizmeti ve tek dosyayla kurulabilen dağıtım paketi henüz bu teslimin parçası değil.

<!-- pagebreak -->

## 10. Terimler ve raporun dayandığı kayıtlar

### Kısa sözlük

- **Topoloji:** Odaların nerede olduğundan önce, hangi odanın hangisine bağlandığı.
- **Inference / çıkarım:** Eğitilmiş modelin yeni görüntüyü işlemesi. Eğitimden farklıdır.
- **OCR:** Görseldeki yazıyı veya sayıyı okumak. Güncel şekil akışında kullanılmıyor.
- **Canonical JSON:** Python ile Unreal'ın aynı planı anlamasını sağlayan ortak veri dosyası.
- **Revision / snapshot:** Tasarımın belirli bir andaki kayıtlı sürümü.
- **Pawn:** Unreal içinde hareket eden oyuncu/ajan temsilcisi.
- **Precision:** Önerilen öğelerin ne kadarının doğru olduğu.
- **Recall:** Gerçek öğelerin ne kadarının bulunduğu.
- **F1:** Precision ve recall'ı birlikte özetleyen puan. Bütün planın kusursuz çıkma oranı değildir.

### Kaynaklar

Bu rapor, projedeki kod ve kayıtların açıklamasıdır; yeni bir model eğitimi veya bağımsız doğruluk deneyi değildir. Aşağıdaki belgeler **Docs** klasöründedir. Bazıları yazıldığı tarihin durumunu anlatır; güncel sonuç için son tarihli kayıt esas alınmıştır.

- **R1:** product_architecture.md - sistemin ana parçaları ve eski/yeni yaklaşım.
- **R2:** ShapeFirst_Implementation_Guide_TR.md - beş aşamalı yeni plan ve kapsam.
- **R3:** step02_dinov2_pilot_2026_11_04.md - DINO modeli, eğitim ve ilk deneyin sınırları.
- **R4:** step02_shape_proposals.md - U-Net ve ilk şekil önerisi pilotu.
- **R5:** step03_shape_sizing_2026_11_04.md - öneri ölçüler, kilitler ve çelişkiler.
- **R6:** step05_shape_delivery_2026_11_04.md - onay, paket, gerçek motor ve kayıt testleri.
- **R7:** data_training_evaluation_v1.md - eski OCR eğitimi ve sonuçları.
- **R8:** geometry_multimodal_pilot_results_2026_10_19.md - ızgara ve yerel görsel dil modeli.
- **R9:** step14_packaged_runtime.md - mevcut paketli Unreal altyapısı.
- **R10:** step02_human_input_diagnosis_2026_11_03.md ve step02_human_adaptation_2026_11_04.md - görüntü hazırlama ve başarısız eğitim adayları. İlk belgedeki eski açıklık paydası, sonraki düzeltmeyle birlikte okunmalı.
- **R11:** step02_decoder_recovery_2026_11_04.md ve step02_opening_ablation_2026_11_04.md - bölge kurtarma, A/B karşılaştırması.
- **R12:** step02_corridor_passage_2026_11_04.md - son bütünleşik algılama sonucu. Sayılar Saved/ShapeFirst/dinov2/corridor_passage/v2/full/report.json ile doğrulandı.
- **R13:** Saved/ShapeFirst/delivery/v1/acceptance-summary.json ve Saved/Maintenance/clean-code-2026-11-04 test kayıtları - gerçek aktarım ve son regresyon kontrolleri.
- **R14:** cleanup_2026_11_04.md ve Saved/Maintenance içindeki bakım kayıtları.

**Genel değerlendirme:** Yerel çizim düzenleme, boyutlandırma, onay ve Unreal aktarım zinciri çalışıyor. En büyük açık alan, yeni çizimlerde otomatik algılamanın güvenilirliği ve kullanıcıya gereken düzeltme yükü. Bir sonraki kararı bu iki şeyi ölçerek vermek gerekiyor.
