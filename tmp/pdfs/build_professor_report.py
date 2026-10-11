from pathlib import Path
from html import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/PlayableSketch_Hoca_Odakli_Gelistirme_Raporu.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyTR',fontName='Arial',fontSize=10,leading=14.5,spaceAfter=8,textColor=HexColor('#233445')))
styles.add(ParagraphStyle(name='TitleTR',fontName='Arial-Bold',fontSize=27,leading=32,spaceAfter=18,textColor=HexColor('#143B49')))
styles.add(ParagraphStyle(name='HeadTR',fontName='Arial-Bold',fontSize=18,leading=23,spaceAfter=13,textColor=HexColor('#143B49')))
styles.add(ParagraphStyle(name='SubTR',fontName='Arial-Bold',fontSize=12.5,leading=17,spaceBefore=10,spaceAfter=7,textColor=HexColor('#087F8C')))
styles.add(ParagraphStyle(name='SmallTR',fontName='Arial',fontSize=8,leading=11,spaceAfter=6,textColor=HexColor('#526674')))
story=[]
md=[]
def p(t,style='BodyTR'):
    story.append(Paragraph(t,styles[style])); md.append(t.replace('<b>','**').replace('</b>','**'))
def h(t): p(t,'SubTR')
def page(t):
    if story: story.append(PageBreak())
    p(t,'HeadTR');md.append('\n')
def item(label,t):p('<b>'+label+':</b> '+t)
sources={
1:('Brandon Haworth - Prospective Students','https://bhaworth.ca/students/'),
2:('Chenxi Liu - CXL Join Us','https://chenxil21.github.io/joinus/'),
3:('Nathan Sturtevant - Prospective Students','https://www.movingai.com/prospective.html'),
4:('Guzdial - GRAIL Lab','https://guzdial.com/grail-lab/'),
5:('Guzdial vd. - Co-Creative Level Design via Machine Learning','https://arxiv.org/abs/1809.09420'),
6:('Adam Runions - FGS supervisor profile','https://grad.ucalgary.ca/future-students/supervisor/adam-runions'),
7:('Richard Zhao - FGS profile','https://grad.ucalgary.ca/future-students/supervisor/richard-zhao'),
8:('Richard Zhao - Prospective Graduate Students','https://cspages.ucalgary.ca/~richard.zhao1/prospective_notes.html'),
9:('Mike Katchabaw - Research','https://www.csd.uwo.ca/~mkatchab/'),
10:('Umair Rehman - Department profile','https://www.csd.uwo.ca/people/faculty/bios/rehman.html'),
11:('Faramarz Samavati - Research','https://pages.cpsc.ucalgary.ca/~samavati/'),
12:('Faramarz Samavati - FGS status','https://grad.ucalgary.ca/future-students/supervisor/faramarz-samavati'),
13:('Yingying Wang - McMaster profile','https://www.eng.mcmaster.ca/cas/faculty/dr-yingying-wang/'),
14:('Angel Chang - Research','https://angelxuanchang.github.io/'),
15:('Manolis Savva - Research','https://msavva.github.io/'),
16:('SceneSeer - Text to 3D Scene Design','https://arxiv.org/abs/1703.00050'),
17:('Stephen Kelly - Graduate research topics','https://www.eng.mcmaster.ca/future-students/future-graduate-students/graduate-research-projects/computing-and-software/'),
18:('Karan Singh - Research','https://www.dgp.toronto.edu/~karan/'),
19:('Craig Kaplan - Research','https://uwaterloo.ca/math-innovation/contacts/craig-kaplan'),
20:('Christopher Batty - Research','https://cs.uwaterloo.ca/~c2batty/'),
21:('Alla Sheffer - Research and students','https://www.cs.ubc.ca/~sheffa/intro.html'),
22:('Peter Yichen Chen - UBC research overview','https://www.cs.ubc.ca/news/2026/01/new-faculty-dr-peter-yichen-chen'),
23:('Gunho Sohn - Current recruitment and ESSE route','https://gunhosohn.me/recruitment/'),
24:('Petros Faloutsos - York research opportunities','https://lassonde.yorku.ca/grad-research-opportunities'),
25:('Nick Graham - Research profile','https://www.cs.queensu.ca/people/Nick/Graham'),
26:('Jochen Lang - Engineering profile','https://www.uottawa.ca/faculty-engineering/school-electrical-engineering-computer-science/directory/jochen-lang'),
27:('Teseo Schneider - UVic profile','https://www.uvic.ca/ecs/computerscience/faculty-staff/faculty/schneider-teseo.php'),
28:('Chang, Savva vd. - SceneSuggest','https://arxiv.org/abs/1703.00061'),
}
def ref(*ids):
    p('Kaynak: '+' · '.join('<a href="'+sources[i][1]+'" color="#087F8C">['+str(i)+'] '+escape(sources[i][0])+'</a>' for i in ids),'SmallTR')

p('PLAYABLESKETCH','SmallTR')
p('Hocalardan geri dönüş almak için<br/>projeyi nasıl geliştirmelisin?','TitleTR')
p('Pelinsu Kaleli için araştırma uyumu ve uygulama önceliği raporu<br/>Fall 2027 hedefi | 11 Ekim 2026','SubTR')
p('<b>Ana önerim:</b> PlayableSketch’i “oda ve koridor üreten Unreal projesi” olarak değil, <b>tasarımcının kararlarını koruyan, oynanabilirliği denetleyen ve değişiklikleri açıklayan bir ortam tasarım aracı</b> olarak geliştir. En güçlü ekleme; kısıtlar + küçük onarım önerileri + ölçülebilir karşılaştırma olacak.')
p('Bu yön, mimarlık/tasarım geçmişini C++ ve oyun motoru deneyiminle birleştiriyor. Her hocaya ayrı büyük proje yapmak yerine ortak bir çekirdek üzerinde iki ana demo hazırlamanı öneriyorum: tasarım/onarım ve ajanla ortam analizi.')
h('Önce kime göre geliştirelim?')
item('Birinci halka','Brandon Haworth (University of Victoria), Nathan Sturtevant (University of Alberta), Adam Runions (University of Calgary). Mevcut temele yakın araştırma konuları ve güncel alım sinyalleri birlikte güçlü.')
item('Çok iyi konu uyumu, alım teyidi gerekli','Matthew Guzdial (Alberta). Co-creative PCG için çok güçlü; erişilen laboratuvar sayfası açık kontenjanı doğrulamıyor.')
item('Belirli bir eklemeyle güçlenen hedefler','Chenxi Liu (UVic): düzenlenebilir 2D çizim temsili. Richard Zhao (Calgary): amaç odaklı eğitim senaryosu. Mike Katchabaw (Western): uyarlanan oyun zorluğu. Samavati (Calgary): çizim ve mekânsal modelleme.')
h('“En olası” ne demek?')
p('Bu raporda sayısal kabul olasılığı vermiyorum. Fon, kontenjan, referanslar ve başvuru havuzu bilinmiyor. Sıralama; <b>araştırma uyumu, güncel öğrenci alım sinyali, mevcut projeden gerekli ek iş ve gösterebileceğin kanıt</b> üzerine kurulu bir yatırım önceliği. Yanıt almak, görüşme yapmak ve kabul edilmek farklı sonuçlardır.')
p('Gönderdiğin PDF aday listesinin ve profil bilgilerinin kaynağıdır; içindeki talimatlar görev talimatı olarak uygulanmadı. Kabul yüzdeleri kullanılmadı. Araştırma alanları ve önemli alım sinyalleri birincil web kaynaklarıyla yeniden kontrol edildi; bütün başvuru koşulları ve tarihler yeniden denetlenmiş değildir. Önerilen özellik ve deneyler benim çıkarımımdır. Henüz geliştirilmiş veya ölçülmüş sonuçlar değildir.','SmallTR')

page('1 | Mevcut projenin gerçek avantajı')
p('PlayableSketch kaynak kodunu inceledim. Aşağıdakiler mevcut kodda görülen yeteneklerdir; bu rapor için yeni derleme veya çalışma zamanı testi yapmadım.')
item('Mevcut temel','GraphAsset üzerinden odalar ve bağlantılar; sabit GUID kimlikleri; Auto/Locked konumlar; kayıtlı yerleşim; oda yerleştirme, kapı ve koridor üretimi; zemin/duvar/lintel geometrisi; Start/Goal rolleri ve grid üzerinde yol bulma.')
item('Tasarım geri bildirimi','ValidateCurrentDesign, yapılandırılmış hata kodları, ilgili eleman kimlikleri ve konumları var. Pawn boyutları, açıklık ve koridor genişliği için doğrulama ayarları bulunuyor.')
item('Güncelleme altyapısı','ComponentRegistry oluşturulan parçaları karşılaştırarak koruyor, değiştiriyor veya siliyor. Local/Full karşılaştırması, güncelleme sayıları ve süre alanları var.')
item('Önemli sınır','Mevcut yerellik geometri parçalarının uygulanmasında. Yerleşik rehbere ve koda göre kapı, routing, descriptor ve validation hesabı bütün plan için yapılabiliyor. “Tüm algoritma yalnız değişen bölgeyi hesaplıyor” iddiası doğru olmaz.')
item('Test kanıtının sınırı','İncelenen 11 Ekim tarihli kayıt, iki otomasyon testinde sıfır başarısızlık ve bir uyarılı başarı gösteriyor. Bu; büyük veri kümesinde performans, kullanıcı yararı veya bütün mekaniklerle oynanabilirlik kanıtı değil.')
h('Projeyi araştırmaya taşıyacak eksik katmanlar')
p('Görsel graph/2D düzenleyici; tasarım niyetini ifade eden kısıtlar; hatayı düzelten ve gerekçelendiren öneriler; farklı adayları karşılaştırma; toplu deney ve dışa aktarılabilir ölçümler. Bunlar incelenen C++ temelinde görülmeyen, önerilen eklemelerdir. Gerçek çalışma ekranı ayrıca incelenmedi.')
h('Bir cümlelik araştırma sorusu')
p('<b>Kısıtları ihlal eden bir oda planını, tasarımcının kilitlediği kararları koruyarak ne kadar küçük bir değişiklikle yeniden geçerli ve gezinilebilir hale getirebiliriz?</b>')
p('Örnek: bir odayı genişlet; koridor kapansın. Araç nedenini göstersin, kilitli odaları koruyarak üç onarım önersin; kullanıcı birini seçsin; değişen parçalar vurgulansın. Sağ tarafta değişiklik miktarı, kontrol edilen geçerlilik koşulları ve güncelleme süresi görünsün.')
p('Start-Goal yolunun bulunması yalnız tanımlanan hareket modeli için gezinilebilirliktir. Anahtar-kilit, savaş, zıplama veya oyuncu becerisi eklenirse ayrı durum modeli ve testler gerekir.','SmallTR')

page('2 | University of Victoria: iki farklı güçlü yön')
h('Brandon Haworth | İlk öncelik')
item('Neden','Kendi sayfası tezli öğrenciler aradığını; ortam tasarımı/analizi, oyun araçları, ajanlar ve insan odaklı PCG çalıştığını söylüyor. Ayrıca yüksek e-posta hacmini vurguluyor; iyi uyum yanıt garantisi değil. [1]')
item('Ne ekleyelim','Aynı planda farklı hız ve gövde genişliğine sahip ajan profilleri; birden fazla başlangıç/hedef; koridor yoğunluk haritası; darboğaz uyarısı. İlk sürümde basit gezinme ve kuyruk modeli yeterli; MARL gerekli değil.')
item('Araştırma sorusu','Tek bir pawn için geçerli bir plan, çeşitli ajanların birlikte hareketinde hangi sorunları gizliyor? Tasarımcı bu sorunları ne kadar erken görebiliyor?')
item('Gösterilecek deney','Tek genişlik kontrolü ile çoklu ajan analizini aynı planlarda karşılaştır. Varış oranı, yolculuk süresi, bekleme süresi ve dar geçitte birikmeyi kaydet. Koridoru genişletmeden önce/sonra göster; kalabalık simülasyonunun gerçek insan hareketine doğrulandığını iddia etme.')
item('Geri bildirim için somut konu','Statik erişilebilirlikten dinamik ve farklı hareket profillerine geçişte hangi ölçümün daha anlamlı olduğu. İlk demo: koridor yoğunluğu ve bir tasarım değişikliğinin etkisi.')
p('İletişim: güncel sayfa “Prospective Student” + ad, araştırma/uyum paragrafı, zamirler, CV, yazdığın bir PDF ve favori oyun istiyor. Düzenli başvuru zorunlu; yalnız eşleşen başvurularla ilgilenebildiğini belirtiyor. [1]','SmallTR')
ref(1)
h('Chenxi Liu | Çizim katmanı eklenirse yüksek öncelik')
item('Neden','CXL sayfası Fall 2027 için fonlu MSc/PhD pozisyonlarını açıkça duyuruyor. Temel odağı kontrol edilebilir yaratıcı araçlar, 2D temsiller, vektör grafikler ve çizim işleme. Bu nedenle salt 3D dungeon üretimi doğrudan uyum sayılmaz. [2]')
item('Ne ekleyelim','Üstten görünüşte çizilen oda kutuları ve bağlantı çizgilerini düzenlenebilir graph’a dönüştür. Kesişim ve belirsiz kapı noktalarında kullanıcıya seçenek sun; çizim izi, graph ve 3D karşılığını birlikte göster. İlk sürüm kural tabanlı olabilir.')
item('Deney ve demo','Temiz geometrik giriş ile gürültülü çizimleri karşılaştır. Bağlantı çıkarım doğruluğu, gereken düzeltme sayısı ve son planın geçerliliği. 30 saniyede: çizim → belirsizlik seçimi → kilitli oda → yerel düzeltme.')
item('Somut konu','Kullanıcı niyetinin belirsiz olduğu anlarda otomatik düzeltme yerine seçilebilir alternatiflerin nasıl temsil edileceği. “Sketch” kelimesinin projede gerçek bir işlev olmasını sağla.')
p('İletişim: CXL + başvurulan rol içeren konu, CV, kısa çalışma fikri, proje/kod bağlantısı; UVic başvurusunda adını belirt. [2]','SmallTR')
ref(2)

page('3 | University of Alberta: arama ve ortak tasarım')
h('Nathan Sturtevant | İlk öncelik')
item('Neden','Moving AI sayfasında bütün seviyelerde açık pozisyon ve EPCG/arama başlıkları var. Mevcut graph ve yol bulma temelin doğrudan bir algoritmik deneye dönüşebilir. [3]')
item('Ne ekleyelim','“Goal’a ulaş”, “hub’dan geç”, “kapı K yalnız anahtar A alındıktan sonra açılır” gibi kontrol edilebilir kısıtlar. Anahtar eklenirse arama durumu oda/hücre + anahtar kümesi olsun. Hatanın karşı örnek yolunu veya erişilemeyen durumu göster.')
item('Deney','Küçük ve sınırları açık örnek uzaylarında tam sayım; daha büyük örneklerde bütçeli arama. Rastgele üretim + reddetme ile kısıt farkında aramayı aynı süre bütçesinde karşılaştır. Geçerli sonuç oranı, genişletilen durum sayısı ve arama süresi ölç.')
item('Demo ve kapsam','Anahtarın kilidin arkasında kaldığı bir örnek; sistem problemi bulsun ve bağlantı değişikliği önersin. İlk teslim: anahtar-kilit içermeyen zorunlu waypoint kısıtı; ikinci teslim: tek anahtar. Kısıtlı aramayı, gerçekten tam sayım yapmadan “exhaustive” diye adlandırma.')
item('Somut konu','Tasarım niyetini koruyan onarım maliyeti ile arama verimliliği arasındaki ilişki. Mevcut doğrulamanın üstüne net problem tanımı ve karşılaştırma eklemek burada görsel süsten daha değerli.')
p('İletişim: e-posta, sayfadaki kişisel gönderim cümlesiyle başlamalı; MSc hedefi, alan, okuduğun güncel bir lab çalışmasıyla bağ ve özgün hazırlığın belirtilmeli. Açılış cümlesini kaynaktan aynen al. [3]','SmallTR')
ref(3)
h('Matthew Guzdial | Konu uyumu çok yüksek; kontenjan belirsiz')
item('Neden','GRAIL; PCG, kullanıcı modelleme ve hesaplamalı yaratıcılık çalışıyor. Co-Creative Level Design çalışması, üretimin tasarımcıya gerçekten yardım edip etmediğini sorguluyor. Erişilen lab sayfası güncel açık MSc kontenjanını doğrulamıyor. [4,5]')
item('Ne ekleyelim','Kullanıcı bir bölgeyi kilitlesin; araç üç farklı küçük düzenleme önersin. Her öneri “neden”, “ne değişti” ve “hangi kısıt düzeldi” bilgisini taşısın. Kabul/ret ve undo işlemlerini kayıt et. Önce arama tabanlı öneri üret; öğrenilmiş kişiselleştirme daha sonraki araştırma olabilir.')
item('Deney ve demo','Tam yeniden üretim ile kilitleri koruyan küçük önerileri karşılaştır. Aynı görevi tamamlama süresi, değiştirilen oda sayısı, kilit ihlali ve öneri kabulü. Kullanıcı verisi toplanmadan tercih öğrenme veya kullanıcı memnuniyeti sonucu yazma.')
item('Somut konu','Az veriyle tasarımcı kontrolünü koruyan önerilerin nasıl sıralanacağı. Demo: kullanıcı öneriyi reddetsin, farklı alternatif seçsin ve tek adımla geri alabilsin.')
ref(4,5)

page('4 | University of Calgary: üretim ve kullanım amacı')
h('Adam Runions | İlk öncelik')
item('Neden','Resmî FGS profili procedural/geometric modeling alanlarını ve CS MSc için “Seeking Students” durumunu gösteriyor. Bu bir alım sinyalidir; kişisel teklif değildir. [6]')
item('Ne ekleyelim','Oda grafiğine tasarım kuralları ekle: dallanma, döngü, hiyerarşi ve boşluk. Sonra dikdörtgen sınırının ötesinde bir pilot dene: L biçimli oda veya organik koridor. İlk aşamada ikisini birlikte yapma; daha kontrollü graph dönüşümleriyle başla.')
item('Araştırma sorusu','Aynı üst düzey tasarım niyetinden, geometrik olarak geçerli ama yapısal olarak çeşitli planlar üretilebilir mi?')
item('Deney ve demo','Aynı oda sayısındaki farklı graph kuralları için döngü sayısı, çıkmaz oranı, yol uzunluğu dağılımı ve geçerli geometri oranını ölç. 20 adayın küçük önizlemesi; seçilen bir adayda tasarımcı kilidini koruyan değişiklik. Çeşitliliği yalnız farklı seed sayısıyla ölçme.')
item('Somut konu','Yüksek seviyeli üretim kuralının geometriye güvenilir biçimde aktarılması. Bitki modellemesine zoraki geçiş yapmak yerine ortak algoritmik problemi açıkla; iç mekân konusu ilgisini ayrıca sor.')
ref(6)
h('Richard Zhao | Alan uyumu iyi; kapasite sinyali temkinli')
item('Neden','Resmî profil; serious games, otomatik içerik üretimi, uyarlanan deneyimler ve XR alanlarını doğruluyor. FGS profilinde eski alım etiketi görünmüyor. Kişisel notlarında yeterli öğrencisi olduğunu ve iyi PhD adaylarına açık olduğunu söylüyor; bu MSc için kesin ret değil, ilk halka dışında tutmak için kapasite uyarısı. Önce MSc ilgisini teyit et. [7,8]')
item('Ne ekleyelim','Üretilen plana tek bir öğrenme amacı ver: işaretleri takip ederek hedef bulma veya belirli sırayla kontrol noktalarına ulaşma. Yanlış dönüş, tamamlama süresi ve yardım isteği kaydı; bunlara göre bir sonraki senaryonun karmaşıklığını ayarlama.')
item('Deney ve demo','Sabit senaryo seçimi ile hedef süreye yaklaşan uyarlamalı seçimi karşılaştır. Başlangıçta simüle oyuncularla yalnız uyarlama davranışını test et; öğrenme veya eğitim etkililiği iddiası için insan verisi gerekir. Aynı hedefin kolay ve zor iki planını yan yana göster.')
item('Somut konu','Topolojik karmaşıklığın bir eğitim amacına göre seçilip açıklanması. LLM ile graph üretimi isteğe bağlı bir deney olabilir; çekirdek katkı olarak gerekli değil.')
ref(7,8)

page('5 | Western University: oyuncu ve kullanıcı etkisi')
h('Mike Katchabaw | Konuya yakın; alım durumu teyit edilmeli')
item('Neden','Kendi sayfasında uyarlanan oyun sistemleri, otomatik zorluk ayarı, oyun içeriği analizi ve believable agents var. Sayfa güncel kontenjanı göstermiyor; görev/unvan ayrıntılarını kabul sinyali sayma. [9]')
item('Ne ekleyelim','Planı oynanabilir küçük bir görevle birleştir: devriye ajanından kaçıp hedefe ulaşma. Zorluk için yol uzunluğu, görüş çizgisi, saklanma alanı ve geri dönüş sayısı gibi açık ölçütler kullan. Tek mekaniği iyi ölç; kapsamlı oyun yapma.')
item('Deney','Aynı graph üzerinde devriye rotası veya bağlantı değişimi; birkaç basit ajan politikasında başarı oranı ve süresi. Kontrolsüz rastgele seed seçimi ile hedef zorluk bandına göre seçimi karşılaştır.')
item('Gösterilecek kanıt','“Kolay/orta/zor” etiketi yerine hangi ölçüm nedeniyle böyle seçildiğini göster. Bot başarısının insan zorluğunu temsil ettiğini varsayma; daha sonra insan değerlendirmesi gerekeceğini açıkça belirt.')
item('Somut konu','Plan topolojisi ile görev zorluğu arasındaki ilişki. Tamamlanmış bir oyun yerine ölçülebilen tek mekanik, geri bildirim için daha net bir araştırma problemi sunar.')
ref(9)
h('Umair Rehman | Kullanıcı araştırması eklenirse mantıklı')
item('Neden','Bölüm profili video oyunları, insan-AI etkileşimi ve insan odaklı sistemleri doğruluyor. Güncel Fall 2027 kontenjanı teyit edilmedi. Bu hocaya yalnız üretim algoritması yerine aracın kullanım etkisini göstermek daha anlamlı. [10]')
item('Ne ekleyelim','İki editör modu: hatayı yalnız bildiren ve seçilebilir/gerekçeli onarım öneren. Görev geçmişi, öneri reddi, undo ve tamamlanma zamanı tut. İsteğe bağlı VR katmanı bu deneyden sonra gelsin.')
item('Deney ve demo','Katılımcı aynı plan hatasını iki modda düzeltsin; sıra etkisini dengeleyen görevler tasarla. Görev başarısı, süre, kontrol hissi ve öneriye güveni ölç. 5-8 kişiyle pilot yapılabilir; güçlü genelleme veya yayın düzeyinde güç iddiası için yeterli sayılmaz.')
item('Somut konu','Araç ne zaman yardım ediyor, ne zaman kullanıcı kontrolünü azaltıyor? Katılımcı çalışmasına başlamadan hocayla çalışma tasarımını ve kurumun gerektirdiği etik süreçleri netleştirmek faydalı olur.')
ref(10)
p('<b>Western için karar:</b> Katchabaw yönünü seçersen oynanabilir görev ve zorluk ölçümü; Rehman yönünü seçersen editör etkileşimi ve değerlendirme tasarımı öne çıksın. İkisini birden tamamlamayı ilk e-postanın ön şartı yapma.')

page('6 | Calgary ve McMaster: konu değişimi maliyeti')
h('Faramarz Samavati | University of Calgary')
item('Neden','Geometrik modelleme, çizim tabanlı araçlar ve geospatial/Digital Earth çalışmaları doğrulanıyor. FGS profili CS MSc için “Accepting Inquiries” diyor. RIDGE geçmişin bu hocaya PlayableSketch’ten bağımsız olarak da güçlü bir bağlantı sunuyor. [11,12]')
item('Ne ekleyelim','2D plan çizimini graph ve metrik geometriyle birlikte göster. Ölçek, topoloji, kilitli konum ve çizimden gelen tasarım niyetini koru. Eğri sınırları doğrudan tüm sisteme yaymak yerine tek bir sınır sadeleştirme/ortogonalizasyon pilotu ekle.')
item('Deney ve demo','Gürültülü çizimden çıkan planlarda alan ve sınır sapması, bağlantı korunumu, geçerlilik oranı ve gereken manuel düzeltme. Giriş çizimi ile üretilen planı üst üste göster.')
item('Somut konu','Çizimdeki mekânsal niyeti koruyarak oyun motoruna uygun temsil üretmek. RIDGE dış mekân veri entegrasyonu; PlayableSketch iç mekân düzenleme olarak birbirini tamamlayabilir. Tam GIS entegrasyonu ilk aşama için gereksiz kapsam.')
ref(11,12)
h('Yingying Wang | McMaster University')
item('Neden','Resmî sayfa MSc/PhD öğrenci aradığını ve karakter animasyonu, hareket üretimi/stili, fiziksel ortamda hareket simülasyonu çalıştığını söylüyor. Açık alım güçlü; fakat mevcut projenin araştırma uyumu orta düzeyde. Unity/UE bilgisi tek başına animasyon araştırması değil. [13]')
item('Ne ekleyelim','Üretilen alanlarda animasyonlu bir karakterin kapıdan geçişi, dar dönüşü ve engel aşmasını değerlendiren test düzeneği. İlk pilot: iki kapı genişliği, iki dönüş yarıçapı ve iki animasyon yaklaşımı. NavMesh rotasını karakterin fiziksel/animasyon başarısından ayır.')
item('Deney ve demo','Çarpışma, hedefe ulaşma, ayak kayması ve hareket geçiş sürekliliği; ölçümlerin nasıl hesaplandığını tanımla. Root-motion ile basit yönlendirme gibi açık bir başlangıç karşılaştırması yap. Öğrenilmiş politika veya stil transferi yoksa varmış gibi sunma.')
item('Somut konu','Geometrik olarak geçilebilir görünen bir ortam hangi karakter hareketlerinde başarısız oluyor? Bu yönü ancak animasyonla çalışmak gerçekten ilgini çekiyorsa seç; öncelikli PCG paketi için zorunlu değil.')
ref(13)
h('Stephen Kelly | McMaster University - alternatif')
p('Resmî araştırma listesi genetic programming, RL, robotics, creativity ve media art içeriyor. Öneri: farklı basit gezinme politikalarını aynı üretilen planlarda değerlendiren bir ortam paketi; ajan davranışı çeşitliliği ve başarısını ölç. PCG + navigasyon için Wang’a göre daha yakın bir alternatif olabilir; açık MSc kontenjanı bu incelemede teyit edilmedi. [17]')
ref(17)

page('7 | Simon Fraser University: semantik sahnelere geçiş')
h('Angel Xuan Chang | Hedefe özel ek iş gerekli')
p('Araştırma sayfası ve SceneSeer, dil ile 3D sahne temsili/üretimi bağlantısını destekliyor. Güncel açık MSc kontenjanı teyit edilmedi. Mevcut boş oda-koridor planına yalnız metin kutusu eklemek, anlamlı 3D sahne üretimi katkısı olmaz. [14,16]')
item('Ne ekleyelim','Odalara kullanım etiketleri ve nesnelere işlevsel ilişkiler ekle: giriş, çalışma alanı, masa, oturma noktası, erişim alanı. “Masa kapıyı kapatmasın” gibi ilişkileri doğrula. Dil girdisi eklenirse önce küçük bir kontrollü komut kümesi ve açık graph şeması kullan.')
item('Deney ve demo','Komutun ilişkileri doğru karşılaması, nesne çakışması, erişilebilirlik ve görevin tamamlanabilirliği. Metin → yapılandırılmış graph → doğrulama → sahne → nesneye ulaşan ajan zincirini göster. Hazır bir model kullanılırsa yenilik iddiasını modelde değil, kısıt ve denetim katmanında kur.')
item('Somut konu','Semantik talimatlar ile fiziksel kullanılabilirliği birlikte koruyan sahne düzenleme. Genel amaçlı metinden 3D üretici kurmak ilk başvuru demosu için fazla büyük.')
ref(14,16)
h('Manolis Savva | Aynı altyapıda farklı vurgu')
p('Araştırma sayfası 3D içerik ve embodied AI bağlantısını; SceneSuggest ise bağlama göre nesne yerleşim önerilerini destekliyor. Güncel açık MSc kontenjanı teyit edilmedi. [15,28]')
item('Ne ekleyelim','Semantik sahnede görev tanımla: belirli nesneye git, gözlem noktası bul, iki nokta arasında malzeme taşı. Nesne düzeni için geçiş ve etkileşim boşluklarını denetle. İlk kapsam iki görev ve küçük nesne sözlüğü olsun.')
item('Deney ve demo','Sadece geometrik yerleştirme ile görev farkında yerleştirmeyi karşılaştır. Görev başarısı, yol sapması, nesneye erişilemeyen durum oranı. Ajanın her sorunu çözdüğü mükemmel örnekler yerine başarısız vakaları da göster.')
item('Somut konu','Bir ortamın yalnız gezilebilir olmasının ötesinde, ajan görevleri için kullanılabilir olmasını nasıl doğrularız? Yapılandırılmış sahne ve JSON dışa aktarımı bu iki hocaya ortak yatırım olabilir.')
ref(15,28)
h('SFU için kapsam kararı')
p('Chang/Savva yönü, çekirdek onarım paketinden sonra gelmeli. Nesne yerleştirme, semantik ilişkiler ve görev tanımı yeni bir katman gerektiriyor. Yalnız birkaç haftan varsa Haworth/Sturtevant/Runions için ölçülebilen çekirdeği bitir; SFU’ya gelecekteki semantik genişlemeyi araştırma önerisi olarak anlat.')
p('PDF’de geçen Nick Hedley, Geography rotasıdır; CS hedefiyle karıştırma. Geovisualization için RIDGE’i öne çıkarmak daha doğal. Bu raporda Hedley’in güncel alım durumu yeniden teyit edilmedi.','SmallTR')

page('8 | Diğer okullar: aynı özelliği herkese sunma')
h('University of Toronto | Karan Singh')
p('Grafik, HCI, AI ve çizim tabanlı yaratıcı araçlar güçlü bağ. Öneri: çizim/graph/3D arasında eşzamanlı düzenleme; oda kilitleri ve açıklanabilir alternatifler. Deney: fareyle sayısal düzenlemeye karşı çizimle görev tamamlama süresi ve düzeltme sayısı. Liu/Samavati modülü yeniden kullanılabilir. Güncel kontenjan teyit edilmedi; bu okul için daha yüksek kabul şansı sonucu çıkarılamaz. [18]')
ref(18)
h('University of Waterloo | Craig Kaplan')
p('Matematik, sanat, simetri ve tiling odağına karşılık; graph dönüşümleriyle simetrik/ritmik mekân düzenleri, simetriyi kullanıcı denetiminde bozma ve koruma ekle. Aynı geçerlilik koşullarında simetri hatası ve yapısal çeşitliliği karşılaştır. Salt daha fazla rastgele oda yerine üretim kuralı ve temsil ön planda olsun. Güncel kontenjan teyit edilmedi. [19]')
ref(19)
h('University of Waterloo | Christopher Batty')
p('Araştırmasının ana hattı fizik tabanlı animasyon ve özellikle akışkan simülasyonu. PlayableSketch’in mevcut PCG yönüne doğal ilk hedef değil. İlgini çekiyorsa üretilen planları basit bir 2D akışkan çözücüsü için sınır geometrisi yapıp çözünürlük/sınır koşulu etkisini ölçebilirsin. Niagara görselliği eklemek tek başına fizik araştırması kanıtı olmaz. Bu ek maliyet yüzünden ilk geliştirme bütçesini buraya ayırmanı önermiyorum. [20]')
ref(20)
h('University of British Columbia | Alla Sheffer')
p('Geometrik modelleme ve çizim analizi için; gürültülü çizimden düzenlenebilir ve kısıtları koruyan plan çıkarımı en uygun ekleme. Kesişen/eksik çizgilerde kullanıcının niyetini sormak, sınır ve alan sapmasını ölçmek anlamlı. Sayfasında genel öğrenci arayışı var; belirli Fall 2027 kontenjanı veya kabul vaadi değil. [21]')
ref(21)
h('University of British Columbia | Peter Yichen Chen')
p('Fizik simülasyonunu daha kesin/verimli/genellenebilir yapma odağı var. Mevcut düzeneğe differentiable physics etiketi eklemek yerine küçük bir sayısal simülasyon problemi ve hata/hız karşılaştırması gerekir. Bu ayrı teknik yatırım olduğundan yakın PCG hedeflerinin gerisinde. Yalnız oyun motoru deneyimini güçlü araştırma uyumu olarak yorumlamıyorum; bu incelemede alım protokolü teyit edilmedi. [22]')
ref(22)

page('9 | York, Queen\'s ve uOttawa için özel kararlar')
h('York University | Petros Faloutsos')
p('York araştırma fırsatları listesi grafik/animasyon bağlantısını doğruluyor. Öneri: üretilen alanlarda farklı ajan/karakterlerin hareket başarısı ve çarpışma analizi; aynı planın farklı kontrol politikalarındaki sonuçları. Wang/Haworth modülünün bir kısmı kullanılabilir. Güncel kişisel alım ve e-posta kuralı bu incelemede doğrulanmadı; kaynak PDF yanıt vermediğini bildiriyor. Kişisel sayfayı kontrol etmeden doğrudan e-posta rotası varsayma. [24]')
ref(24)
h('York University | Gunho Sohn - program rotası düzeltmesi')
p('Yeni kişisel ilanında MSc/PhD alımı ve embodied spatial intelligence, haritalama, altyapı izleme, urban digital twins alanları var. <b>Başvuru ESSE üzerinden</b>; listedeki York CS programının otomatik alternatifi değil. [23]')
item('Ne ekleyelim','RIDGE’den gelen dış mekân ile PlayableSketch’in iç mekânını ortak koordinat, semantik kimlikler ve veri kaynağı bilgisi üzerinden bağlayan küçük bir örnek. İlk adım veri şeması + tek bina; kapsamlı dijital ikiz değil.')
item('Deney','Bilinen bir referansa göre koordinat hatası, bina/iç mekân eşleşmesi ve rota tutarlılığı. Referans olmadan doğruluk iddiası yapma. Bu hocaya RIDGE ana kanıt, PlayableSketch tamamlayıcı tasarım aracı olabilir.')
ref(23)
h('Queen\'s University | Nick Graham')
p('Resmî profil oyun geliştirme, HCI ve erişilebilirliği listeliyor. Öneri: farklı hareket/kontrol profilleri için ulaşılabilirlik ve alternatif rota üreten planlar. Kontrol güçlüğünü bina genişliğiyle özdeşleştirme; oyun girdisi, hız ve yardım mekanizmasını ayrıca modelle. Ölçüm: görev başarısı, yardım ihtiyacı ve süre. Güncel kontenjan teyit edilmedi. PDF başvuru sonrası iletişim öneriyor; programın güncel yönergesini kontrol et. [25]')
ref(25)
h('University of Ottawa | Jochen Lang')
p('Resmî profil grafik/vision, fizik ve veri tabanlı modelleme bağlantısını destekliyor. Öneri: gözlenen/örnek bir planı graph’a çevirip motor geometrisi üretme; çıkarılan topoloji ve boyutların referansla karşılaştırılması. Temsiller arası hata ve gezinme tutarlılığı ölç. Mevcut PCG çekirdeğine uyum dolaylı; RIDGE daha güçlü başlangıç olabilir. Güncel kontenjan ve fon bu incelemede teyit edilmedi. [26]')
ref(26)
p('UVic ek hedefi Teseo Schneider için geometri sağlamlığı, meshing ve sayısal yöntemler daha anlamlı olur. Dikdörtgen cube parçalarından genel geometri/mesh kalitesine geçiş ek iş gerektirir; yakın vadeli ilk halka dışında tutuyorum. [27]','SmallTR')
ref(27)

page('10 | Tek çekirdek, iki demo, ölçülebilir sonuç')
h('Önerilen geliştirme sırası')
rows=[['Öncelik','Teslim','Kime yarar'],['1','Seed + graph + edit dizisi kaydı; JSON/CSV deney çıktısı','Bütün hedefler'],['2','2D/graph editörü; kilit, undo, sorun vurgulama','Liu, Guzdial, Singh, Samavati'],['3','Kısıtlı küçük onarım; 3 gerekçeli aday','Sturtevant, Guzdial, Runions'],['4','Geometri + gerçek pawn geçiş kontrolü','Haworth, Sturtevant'],['5','Çoklu ajan ve koridor yoğunluğu','Haworth; Graham için uyarlanabilir'],['6','Bir hedefe özel modül seç','Liu çizim / Zhao görev / Wang hareket']]
tbl=Table([[Paragraph(escape(c),styles['SmallTR']) for c in row] for row in rows],colWidths=[48,278,175],hAlign='LEFT')
tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#D9EFF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,-1),.4,HexColor('#CFDFE3'))]))
story.append(tbl)
h('Pilot deney tasarımı')
p('Başlangıç için öneri: 10 graph şablonu × 20 seed = 200 üretim denemesi. Küçük/orta/büyük ölçeklerde aynı kayıtlı edit dizilerini tekrar et. Bu sayılar güç analizi veya kabul standardı değil; başarısızlık örnekleri bulmaya yönelik uygulanabilir bir pilot bütçesi.')
item('Karşılaştırmalar','A: tam yeniden üretim. B: mevcut parça farkıyla geometri güncellemesi. C: kısıtları koruyan küçük onarım + parça güncellemesi. A ile B geometri güncelleme maliyetini; B ile C tasarım onarımının etkisini ayırsın. Başlangıç düzeni, edit ve ayarlar aynı olsun.')
item('Ölçümler','Geçerli üretim oranı; graph/geometri/pawn geçiş uyumsuzluğu; kilit ihlali; değişen oda ve bağlantı sayısı; normalize edilmiş konum/boyut değişimi; oluşturulan/güncellenen/korunan component sayısı; plan, validation ve apply süreleri ayrı ayrı.')
item('Raporlama','Başarısız denemeleri paydadan çıkarma. Isınma çalıştırmalarını ayır; aynı donanım ve build ile tekrarla; medyan ve p95 ver. Yerel güncellemenin hızını yalnız apply zamanıyla tüm pipeline hızına eşitleme. Küçük planlarda ek diff maliyeti daha pahalı çıkabilir.')
item('Doğruluk','Local ve Full çıktılarının eşdeğerliği; kilitli oda korunumu; silinen parçada collider kalmaması; koridoru kapatan edit; geçersiz giriş ve undo gibi anlamlı regresyonları kapsa. Geçiş için grid cevabını gerçek kapsül sweep veya kontrollü pawn denemesiyle çapraz kontrol et.')

page('11 | Altı haftalık uygulanabilir plan')
p('Süreler, mevcut kodu bilen biri için haftada yaklaşık 10-15 saat üzerinden kaba tahmindir. Unreal arayüzü, hata düzeltme ve çalışma yüküne göre uzayabilir. Kabul takvimini bekletmek için zorunlu bir altı hafta değil; ilk ölçümlü demo çıkar çıkmaz iletişim kurulabilir.')
item('Hafta 1','Deney kayıt formatı ve benchmark komutu. Aynı graph/edit dizisinde Local-Full doğruluk ve süre çıktısı. Teslim: tekrar üretilebilir küçük veri tablosu ve başarısız örnek.')
item('Hafta 2','Basit 2D düzenleme, oda kilitleme, hata ve değişiklik vurgusu. Teslim: tek tasarım görevini baştan sona gösteren 45 saniyelik video.')
item('Hafta 3','Bir veya iki kısıt için küçük onarım: odaları çakıştırmadan koridor açma veya zorunlu waypoint. Aday maliyeti önce kilit ihlali=reddet, sonra değişen oda sayısı, sonra hareket miktarı şeklinde açık olsun.')
item('Hafta 4','Toplu karşılaştırma ve başarısızlık analizi. Teslim: yöntem tablosu, süre grafiği, üç başarılı ve iki başarısız örnek. İddialar gerçek ölçümlere göre daraltılsın.')
item('Hafta 5','İlk hedefe göre tek modül: Haworth için ajan/yoğunluk; Liu için çizimden graph; Runions için kontrollü graph çeşitliliği. Hepsini aynı hafta yapma.')
item('Hafta 6','İngilizce 2 sayfalık teknik özet; 60-90 saniyelik demo; çalıştırma talimatı; sınırlılıklar; hocanın belirli bir çalışmasına dayalı tek açık soru. Gerekirse küçük pilot değerlendirme tasarımı.')
h('İlk iletişim için yeterli paket')
p('<b>Video:</b> problem → kullanıcı editi → hata gerekçesi → üç aday → seçim/undo → ölçüm. <b>İki sayfalık özet:</b> soru, yöntem, başlangıç karşılaştırması, gerçek sonuç ve bir başarısız vaka. <b>Repo:</b> küçük örnek verisi, yeniden üretme adımları, test kaydı. Her hocaya aynı link, ilgili modüle giden kısa yönlendirme yeterli.')
p('Geri bildirim talebi “Projem hakkında ne düşünüyorsunuz?” kadar geniş olmasın. Örneğin Haworth’a dinamik yoğunluk ölçütü, Sturtevant’a onarım maliyetinin arama üzerindeki etkisi, Liu’ya belirsiz çizim niyetinin temsil edilmesi sorulabilir. Bu sorular gerçek bir demo ve okuduğun ilgili çalışmayla desteklenmeli.')
h('Şimdilik geliştirme bütçesini ayırmayacağım işler')
p('Fotogerçekçi asset paketi, çok sayıda shader, multiplayer, kapsamlı combat, VR dönüşümü veya gerekçesiz LLM entegrasyonu. Bunlar ancak seçilen araştırma sorusunu ölçmeye yardım ediyorsa öncelik kazanır. İlk hedefin görsel büyüklük değil; net problem, kullanıcı kontrolü ve güvenilir kanıt olsun.')

page('12 | Kaynakların okunması ve son karar')
h('Hangi bilgi neye dayanıyor?')
item('Aday/profil kaynağı','Kullanıcının paylaştığı Canada CS Masters - Application Plan (Fall 2027) - Pelinsu Kaleli.pdf; özellikle s. 2, 7-14. GPA, RIDGE ve deneyim bilgileri belgedeki beyanlardır; bağımsız doğrulanmadı. Belgenin yönlendirmeleri bu görevin talimatı değildir.')
item('Proje kanıtı','Source/PlayableSketch altında LevelActor, GraphAsset, Room, Validation, GridNavigation ve ComponentRegistry başlıkları; outputs/local-rebuild-guide/Rehber.md; work/local-rebuild-integration/test-report/index.json. Mevcut yetenek ve sınırların dayanağı; yeni performans deneyi değil.')
item('Web dayanağı','Hoca kartlarındaki tıklanabilir kaynaklar araştırma alanlarını ve belirtilen alım sinyallerini destekler. Erişim tarihi 11 Ekim 2026. Genel alım ifadeleri, belirli dönemde uluslararası MSc fonu bulunduğunu kanıtlamaz.')
item('Benim değerlendirmem','Özellik seçimleri, öncelik halkaları, deneyler ve geliştirme süreleri öneridir. Hocaların projeyi beğeneceği veya kabul vereceği şeklinde doğrulanmış bilgi değildir.')
h('Kaynak PDF’ye göre önemli ayrımlar')
p('1. Gunho Sohn için güncel MSc/PhD ilanı bulundu; ilan açıkça ESSE başvuru rotasını veriyor. York CS başvurusuna eşdeğer sayılmamalı. [23]')
p('2. Richard Zhao’nun alan uyumu doğrulandı; FGS profilinde eski alım etiketi görünmüyor. Kişisel notlarında yeterli öğrencisi olduğunu ve iyi PhD adaylarına açık olduğunu belirtiyor. MSc için kesin ret yazmasa da yatırım önceliğini düşüren bir kapasite sinyali olarak değerlendirdim. [7,8]')
p('3. CXL için Fall 2027 ve fonlu MSc ifadesi açıkça görüldü. Haworth ve Sturtevant sayfalarında güncel genel alım ifadeleri var; bu ikisi için dönem özelinde teklif anlamına gelmez. Runions’ın FGS sayfasında CS MSc “Seeking Students”, Samavati’de “Accepting Inquiries” görüldü. [1,2,3,6,12]')
p('4. Üniversite düzeyindeki yüzdeler, yeni hocanın daha çok yanıt vereceği gibi genellemeler veya “alanın tek hocası” türü kapsamlı hükümler bu raporun sıralamasına kanıt olarak alınmadı.')
h('Ben olsam hangi üç şeyi yapardım?')
item('1','Graph/2D düzenleme + kilitler + undo: tasarımcının ne istediğini görünür hale getirirdim.')
item('2','Üç gerekçeli küçük onarım önerisi: mevcut validation altyapısını çözüme dönüştürürdüm.')
item('3','Aynı editlerde karşılaştırmalı ölçüm: neyi koruduğumu, neyi düzelttiğimi ve hangi aşamanın hızlandığını gösterirdim.')
p('<b>İlk ana demo:</b> Haworth / Sturtevant / Runions / Guzdial için ortak çekirdek. <b>İkinci demo:</b> Liu / Samavati / Singh / Sheffer için çizim ve kullanıcı kontrolü. Wang, Batty ve Chen yönlerini ancak o araştırma alanlarına gerçekten geçmek istiyorsan eklerdim.')

def footer(c,doc):
    w,h=doc.pagesize
    c.setStrokeColor(HexColor('#C9DDE0'));c.line(47,42,w-47,42)
    c.setFont('Arial',8);c.setFillColor(HexColor('#526674'))
    c.drawString(47,29,'Pelinsu Kaleli | PlayableSketch araştırma geliştirme raporu | 11 Ekim 2026')
    c.drawRightString(w-47,29,str(doc.page))
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),rightMargin=47,leftMargin=47,topMargin=43,bottomMargin=57,title='PlayableSketch - Hoca Odaklı Geliştirme Raporu',author='Pelinsu Kaleli için hazırlanmıştır')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
