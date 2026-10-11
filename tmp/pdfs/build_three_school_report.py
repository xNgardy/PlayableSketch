from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/PlayableSketch_UBC_UofT_Waterloo_Arastirma_Raporu.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
for name,file in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf')]:
    pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
styles=getSampleStyleSheet()
for name,size,lead,color,bold in [('BodyTR',10,14.5,'#253847',False),('TitleTR',27,33,'#173C50',True),('HeadTR',18,23,'#173C50',True),('SubTR',12.5,17,'#087E8B',True),('SmallTR',8,11,'#526674',False)]:
    styles.add(ParagraphStyle(name=name,fontName='Arial-Bold' if bold else 'Arial',fontSize=size,leading=lead,textColor=HexColor(color),spaceAfter=8,spaceBefore=8 if name=='SubTR' else 0))
story=[]
def p(t,style='BodyTR'):story.append(Paragraph(t,styles[style]))
def h(t):p(t,'SubTR')
def item(label,t):p('<b>'+label+':</b> '+t)
def page(t):
    if story:story.append(PageBreak())
    p(t,'HeadTR')
S={
1:('UofT - MSc eligibility','https://web.cs.toronto.edu/graduate/msc'),
2:('UofT - Direct-Entry PhD','https://web.cs.toronto.edu/graduate/phd'),
3:('UBC - Online application / supervisor contact','https://www.cs.ubc.ca/students/grad/admissions/application-components-required-documents/online-application'),
4:('Waterloo - Applying and admissions','https://cs.uwaterloo.ca/future-graduate-students/applying-admissions'),
5:('Alla Sheffer - Research / recruiting','https://www.cs.ubc.ca/~sheffa/intro.html'),
6:('Sheffer - Prospective students / group','https://www.cs.ubc.ca/~sheffa/Graduate.html'),
7:('Ma, Vining, Lefebvre, Sheffer - Game Level Layout (2014)','https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.12314'),
8:('LevelSyn - Authors\' code and data','https://github.com/chongyangma/LevelSyn'),
9:('Yin vd. - Intended Vector Sketch Connectivity (2022)','https://www.cs.ubc.ca/labs/imager/tr/2022/SketchConnectivity/'),
10:('Sheffer - Publications, including 2026','https://www.cs.ubc.ca/~sheffa/pap_list.html'),
11:('Xue Bin Peng - UBC move and research','https://xbpeng.github.io/'),
12:('Peng - Current prospective students instructions','https://xbpeng.github.io/prospective_students/index.html'),
13:('Peter Yichen Chen - PhysAI research','https://peterchencyc.com/'),
14:('UBC - Peter Chen research overview','https://www.cs.ubc.ca/news/2026/01/new-faculty-dr-peter-yichen-chen'),
15:('Karan Singh - Research','https://www.dgp.toronto.edu/~karan/'),
16:('Yu vd. - CASSIE (CHI 2021)','https://em-yu.github.io/research/cassie/'),
17:('Jacobson - Fall 2027 recruiting / publications / FAQ','https://www.cs.toronto.edu/~jacobson/'),
18:('Jacobson - Progressive Convex Hull Simplification (2026)','https://arxiv.org/abs/2604.14468'),
19:('Text-guided Controllable Mesh Refinement (2024)','https://text-mesh-refinement-project.github.io/'),
20:('Sanja Fidler - Research / general recruiting','https://www.cs.toronto.edu/~fidler/'),
21:('Ren vd. - GEN3C (2025)','https://arxiv.org/abs/2503.03751'),
22:('Aviad Levis - Research','https://www.aviadlevis.info/'),
23:('PI-Vision - Current research / publications','https://pi-vision.github.io/'),
24:('Craig Kaplan - Research and Fall 2026 group','https://cs.uwaterloo.ca/~csk/'),
25:('Kaplan - CS898 2025 project ideas','https://cs.uwaterloo.ca/~csk/teaching/cs898/s25/project.html'),
26:('Steinberg - Research and publications','https://ssteinberg.xyz/'),
27:('Steinberg, Pharr - Wave Tracing (2026)','https://ssteinberg.xyz/2025/08/28/generalizing_the_path_integral/'),
28:('Batty - Join the Computational Motion Group','https://cs.uwaterloo.ca/~c2batty/join.html'),
29:('Batty - Current research / simulation code','https://cs.uwaterloo.ca/~c2batty/'),
30:('van de Panne - Intake depends on funding','https://www.cs.ubc.ca/~van/opportunities.html'),
31:('Hachisuka - Capacity statement','https://cs.uwaterloo.ca/~thachisu/index.html'),
}
def ref(*ids):p('Kaynak: '+' · '.join('<a href="'+S[i][1]+'" color="#087E8B">['+str(i)+'] '+escape(S[i][0])+'</a>' for i in ids),'SmallTR')
def table(rows,widths):
    t=Table([[Paragraph(escape(c),styles['SmallTR']) for c in row] for row in rows],colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#DAEFF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-1),.4,HexColor('#CFDFE3'))]))
    story.append(t)

p('PELİNSU KALELİ | FALL 2027 | 11 EKİM 2026','SmallTR')
p('PlayableSketch<br/>UBC · UofT · Waterloo','TitleTR')
p('Hoca bazında araştırma uyumu, proje geliştirmeleri ve başvuruya dönük kanıt planı','SubTR')
p('<b>Benim önerim:</b> UBC’de <b>Alla Sheffer</b>, Waterloo’da <b>Craig Kaplan</b> için ortak bir tasarım/üretim çekirdeği geliştir. UofT’de <b>Karan Singh</b> ve <b>Alec Jacobson</b> araştırma açısından değerli hedefler; ancak senin uluslararası aday statün için program rotası değişiyor.')
h('Önceki raporu değiştiren kritik bulgu')
p('<b>UofT CS MSc uluslararası adayları değerlendirmiyor.</b> Güncel bölüm sayfası bunu açıkça yazıyor. Aynı bölüm, uygun lisans mezunları için Direct-Entry PhD rotası sunuyor; program sayfası 5 yıl ve 60 aylık garantili fon dönemi belirtiyor. Bu rota bir yüksek lisansın eşdeğeri değildir. Önceki raporum bu MSc kısıtını yakalamadı; buradaki değerlendirme onu düzeltiyor. [1,2]')
ref(1,2)
h('Tek proje, iki güçlü gösterim')
item('Demo A - ortak çekirdek','Tasarım grafiği → geçerli plan → kullanıcı editi → kilitleri koruyan küçük onarım → önce/sonra karşılaştırması. Sheffer için en doğrudan bağ; Jacobson için sağlam geometri ve hata analiziyle genişletilebilir.')
item('Demo B - hocaya özel görünüm','Singh için belirsiz çizimden düzenlenebilir yapıya geçiş; Kaplan için simetri/tiling ve kural denetimi. Aynı graph, kimlik, validation ve güncelleme altyapısı kullanılabilir.')
p('Bu rapor kabul olasılığı yüzdesi üretmez. Öncelik; araştırma uyumu, erişilen alım sinyali, programın sana açık olması ve mevcut projeden ek iş maliyetine dayanır. Özellik önerileri ve süreler benim değerlendirmem; hocaların talebi veya kabul vaadi değildir. Web kontrolü 11 Ekim 2026; bütün başvuru ayrıntıları yeniden denetlenmiş değildir.','SmallTR')

page('1 | Üç okulda hangi hocaya yatırım yapmalı?')
table([['Hoca / okul','Araştırma uyumu ve önerilen ek','Alım / rota kanıtı'],['Alla Sheffer / UBC','Çok yüksek: tasarım grafiği, çizim niyeti, kısıtlı plan onarımı','Genel graduate alım ifadesi; dönem özel kontenjan değil'],['Jason Peng / UBC hedefi','Koşullu: fizik tabanlı karakterler için kontrollü ortam ve görev paketi','UBC’ye 2027 geçişi; MSc/PhD için UBC başvurusu açıkça yazıyor'],['Peter Yichen Chen / UBC','Koşullu: sınır geometrisi ve sayısal fizik problemi','İncelenen güncel kişisel sayfada MSc alımı teyit edilmedi'],['Karan Singh / UofT','Çok yüksek: çizim, düzenlenebilir temsiller, yaratıcı araçlar','Fall 2027 kontenjanı teyit edilmedi; CS MSc uluslararasıya kapalı'],['Alec Jacobson / UofT','Yüksek: sağlam geometrik yöntem ve ölçülebilir hata','Fall 2027 graduate alımı açık; senin için MSc rotası kapalı'],['Sanja Fidler / UofT','Orta: semantik sahne, sentetik veri, 3D tutarlılık','Genel eski MSc/PhD ifadesi, program kuralını aşmaz'],['Aviad Levis / UofT','Mevcut projeye düşük; RIDGE ile daha anlamlı','Fall 2027 kontenjanı bu incelemede teyit edilmedi'],['Craig Kaplan / Waterloo','Yüksek: simetri, modüler kurallar, hesaplamalı tasarım','Aktif MMath öğrencileri var; açık 2027 kontenjanı teyit edilmedi'],['Shlomi Steinberg / Waterloo','Koşullu: geometri kontrollü ışık/dalga deney sahneleri','Fall 2027 kontenjanı teyit edilmedi'],['Christopher Batty / Waterloo','Koşullu: geometriyi kullanan sayısal fizik deneyleri','MMath thesis için açık genel başvuru çağrısı']], [112,220,169])
p('“Uyum yüksek” mevcut kodun araştırma sonucu olduğu anlamına gelmez. En az bir açık soru, makul başlangıç yöntemi ve tekrarlanabilir karşılaştırma gerekir. UofT satırları, Direct-Entry PhD veya ileride başka bir araştırma rotasına ilgin varsa anlamlıdır.','SmallTR')
ref(5,12,13,15,17,20,22,24,26,28)

page('2 | Mevcut temel ve gerçek araştırma boşluğu')
p('Güncel kaynakları tekrar kontrol ettim. Oda/bağlantı graph’ı, kalıcı GUID kimlikleri, Auto/Locked konumlar, kayıtlı yerleşim, kapı/koridor geometrisi, hata kodları ve parça farkıyla geometri güncelleme altyapısı mevcut. Bu raporda kaynak kodu değiştirmedim, yeni derleme veya çalışma zamanı testi yapmadım.')
h('Önceki incelemeye göre mevcut olan yeni navigation katmanı')
p('PlayableSketchNavigation, AgentRadius/Height/Clearance ayarlarıyla Analyze ve ExportJson arayüzlerini; erişilebilirlik, rota uzunluğu, çıkmaz sayısı, alternatif rota, erişilemeyen odalar, fiziksel/rota bağlantıları, grid hücreleri ve aşama sürelerini tanımlıyor. Actor’da AnalyzeNavigation, ExportNavigationReport ve örnek çalıştırma girişleri var. Bunları sıfırdan ekleme önerisi olarak tekrarlamıyorum.')
p('Bu alanların kodda bulunması, metriklerin her durumda doğru veya gerçek karakter hareketine doğrulanmış olduğunu kanıtlamaz. Özellikle “alternatif rota” ve “çıkmaz” tanımlarını raporda açıkla; gerçek dünya geometri/pawn testiyle çapraz kontrol et.')
h('Neden sadece graph’tan oda üretmek yetmez?')
p('<b>Game Level Layout from Design Specification (2014)</b> zaten tasarımcının bağlantı grafiğinden kullanıcı tanımlı blokları geçerli planlara yerleştiriyor. Dolayısıyla “graph → level” tek başına özgün araştırma iddiası olamaz. Bu çalışma Sheffer için doğrudan ilgili önceki iştir. [7]')
p('<b>Aday araştırma boşluğu:</b> Üretimden sonra gelen kullanıcı editlerinde, kilitli kararları ve mekânsal tasarım niyetini koruyarak planı az değişiklikle onarmak; planın graph ve ajan ölçütlerini birlikte açıklamak. Bu bir yenilik hipotezidir; literatür taraması tamamlanmadan ilk kez yapıldığı iddia edilmemeli.')
h('Somut demo senaryosu')
p('12 odalı bir planda kullanıcı hub’ı genişletsin. Bir koridor kapansın. Sistem problemi konumuyla göstersin; kilitli iki odayı koruyarak üç aday üretsin. Adaylarda hangi odaların oynadığı, bağlantıların korunup korunmadığı, rota uzunluğu ve toplam güncelleme süresi görünsün. Kullanıcı seçsin veya geri alsın.')
item('Henüz önerilen','Görsel 2D/graph düzenleme; tasarım kısıtları; küçük onarım araması; alternatif sıralama; çizim belirsizliği; simetri/tiling modu. İncelenen arayüzlerde bunların tamamlanmış kanıtı görülmedi.')
item('İddianın sınırı','Local rebuild parça uygulamasını azaltabilir; bütün routing/validation hesabının yerel olduğunu söyleme. Start-Goal grid yolu, fizik tabanlı karakter kontrolü veya tam oyun oynanabilirliği değildir.')
ref(7,8)

page('3 | UBC - Alla Sheffer: en doğrudan eşleşme')
item('Öncelik','Bu üç okulda mevcut PlayableSketch için ilk araştırma hedefim. Sayfası genel graduate öğrenci arayışını doğruluyor; özel Fall 2027 kontenjanı veya kişisel kabul olasılığı bilinmiyor. [5,6]')
h('Hangi çalışmaları gerçekten bağlayabiliriz?')
p('<b>Game Level Layout from Design Specification (2014):</b> tasarım graph’ını ve blok yerleşimini bağlayan doğrudan önceki iş. <b>Detecting Viewer-Perceived Intended Vector Sketch Connectivity (2022):</b> çizgilerin görünürdeki boşlukları ile amaçlanan bağlantıları ayıran algısal/bağlamsal yöntem. İlki plan üretimine, ikincisi çizimden graph çıkarımına gerekçe verir. [7,9]')
p('2026 yayın listesinde Sketch2Arti ve SharpEdge gibi güncel çizim/geometri işleri de var; 2014 makalesini bugünkü tek araştırma yönü gibi sunma. Güncel listeyi okuyup neden mevcut plan probleminin gruba hâlâ uygun olduğunu sor. [10]')
h('Ben ne eklerdim?')
item('Minimum sürüm','Tasarımcı bir odanın konumunu veya boyutunu değiştirince: oda kimlikleri, kilitli odalar ve istenen bağlantılar korunsun; sadece geçerli küçük değişiklik adayları önerilsin. Mevcut yerleşimi başlangıç çözümü olarak kullanan arama ekle.')
item('İkinci katman','Üstten görünüşte çizilen oda sınırları ve bağlantılardan graph çıkar. Yakın iki çizgi ucu için otomatik birleştirme yerine belirsizlik göster; kullanıcı seçimini kalıcı tasarım kararı olarak kaydet. Öğrenilmiş model ilk sürüm için şart değil.')
h('Araştırma sorusu ve karşılaştırma')
p('<b>Soru:</b> Yeni bir bağlantı veya oda boyutu editi sonrasında, tasarım niyeti ne kadar az geometrik değişiklikle korunabiliyor? A: mevcut üreticiyi yeniden çalıştırma. B: önceki plana dayanan onarım. C: onarım + kullanıcı kilitleri. B ve C arasındaki fark kilitlerin katkısını ayırsın.')
item('Ölçüm','Geçerli sonuç oranı; kilit ihlali; değişen oda sayısı; normalize edilmiş oda merkezi/boyut sapması; plan ve onarım süreleri; başarısız düzenleme türleri. Kilitleri delerek daha yüksek başarı elde etmek başarı sayılmasın.')
item('Hedefe özel demo','Graph, ilk yerleşim, kullanıcı editi ve üç onarım aynı ekranda. Video sonunda bir başarısız kısıt kombinasyonu ve bunun açıklaması yer alsın.')
item('Sorulacak somut konu','Onarım maliyetinde geometrik yakınlık ile tasarımcının algıladığı plan benzerliğinin nasıl dengelenebileceği. “Makalenizi Unreal’da yeniden yaptım” yerine hangi alt problemi değiştirdiğini açıkla.')
ref(5,6,7,9,10)

page('4 | UBC - Peng ve Chen: farklı teknik yatırımlar')
h('Xue Bin (Jason) Peng | hareket kontrolüne açıksan')
p('Kişisel sayfası 2027’de UBC’ye geçeceğini söylüyor. Güncel prospective sayfası MSc/PhD adaylarına UBC’ye başvurup adını belirtmelerini; e-posta için kabul sonrasını işaret ediyor. Önceki PDF’deki “önce mail at” önerisini bu güncel talimatın önüne koyma. [11,12]')
item('Çalışma bağlantısı','MaskedMimic (2024), CLoSD (2025) ve MimicKit çerçevesi; fiziksel karakter kontrolü ve hareket takibi yönünü gösteriyor. Bu raporda yöntemleri yeniden ürettiğimi veya ayrıntılı deney tablolarını denetlediğimi iddia etmiyorum. [11]')
item('Ek','Koridor genişliği, dönüş açısı, kapı eşiği ve engel konumu kontrollü değişen küçük bir test kümesi. JSON/mesh dışa aktarımıyla bir karakter kontrol deneyine bağla. Unreal önizleme olabilir; RL eğitimini Unreal içinde yapma şartı yok.')
item('Deney','Eğitim/geliştirme ve görülmemiş test planlarını ayır. Sabit kontrolcüde başarı, çarpışma, düşme, süre; mümkünse basit kontrolcü ile hazır öğrenilmiş kontrolcüyü karşılaştır. Temas/ayak kayması gibi ölçümleri yalnız tanımlayıp hesaplayabildiğinde ekle.')
item('İlk demo ve soru','Grid yolunun açık olduğu ama karakterin dar dönüşte başarısız olduğu örnek; ortam zorluğunun topolojiye mi geometriye mi bağlı olduğunu ayır. Öğrenilmiş kontrolcü kurulmadıysa bunu ilerideki genişleme olarak yaz.')
ref(11,12)
h('Peter Yichen Chen | sayısal fizik gerçekten ilgini çekiyorsa')
p('Güncel kişisel sayfa PhysAI’nin grafik/ML/bilimsel hesaplama/robotik kesişiminde fizik dünyasının simülatörlerini geliştirdiğini doğruluyor. Ancak erişilen sayfada açık MSc çağrısı veya eski “[Prospective Member]” başlık kuralı görünmüyor; bunları teyit edilmiş saymıyorum. [13,14]')
item('Ek','Üretilen ortamları, tek bir küçük sayısal fizik problemi için sınır geometrisi yap. Örneğin koridor ağında skaler difüzyon veya 2D dalga yayılımı. Başlangıçta analitik/referans çözümü bulunan basit geometriyle doğrula.')
item('Deney','Aynı problemde grid çözünürlüğü ve sınır temsilini değiştir; çözüm hatası, kararlılık ve süreyi karşılaştır. Bilimsel doğrulama olmadan gerçek hava akışı veya sensör doğruluğu iddiası kurma.')
item('Yatırım kararı','Sadece güzel fizik efekti yerine denklem, sınır koşulu ve hata ölçümü gerekir. Sayısal fizik hedefin yoksa Sheffer’a yatırım daha verimli. Bu öneri, hocanın doğrulanmış açık proje ilanı değil; araştırma alanından çıkarım.')
ref(13,14)

page('5 | UofT - Karan Singh: yaratıcı araç olarak güçlen')
p('<b>Program koşulu:</b> Bu bölüm araştırma uyumunu inceliyor. Uluslararası CS MSc hedefi için geçerli bir kabul rotası değil; Direct-Entry PhD’ye ilgi duyarsan değerlendirilir. Güncel Fall 2027 kişisel kontenjan teyit edilmedi. [1,2,15]')
h('Doğrudan bağlantı: CASSIE')
p('CASSIE (CHI 2021), serbest 3D çizimin tutarlı ve bağlı eğri ağlarına dönüşmesini destekleyen bir kavramsal modelleme aracı. Projenle ortak sorun, hızlı yaratıcı girdiyi sonraki aşamalarda kullanılabilen düzenli bir temsile çevirmek. PlayableSketch için bunun daha küçük bir 2D plan sürümü araştırılabilir. CASSIE’nin 3D/VR kapsamını senin 2D prototipinle eşdeğer sayma. [16]')
h('Ben ne eklerdim?')
item('Minimum sürüm','2D çizim katmanı: oda kutusu çiz, bağlantı çizgisi ekle, yaklaşık simetri belirt. Graph ve 3D plan aynı kimliklerle eşzamanlı güncellensin. Sayısal detay paneline gidip gelmeden bir tasarım görevi tamamlanabilsin.')
item('Özgün aday katkı','Sistem birden fazla yorum gördüğünde kullanıcıya görsel alternatifler sunsun. Seçilen yorumu ve kullanıcı kilitlerini koruyan düzeltme yapsın. Otomatik neatening, manuel düzenleme ve önerili düzenleme ayrılabilsin.')
item('Kontrol','Undo/redo; çizilen halin görünür kalması; önce/sonra farkı; belirli bir oda veya bağlantıyı koruma. Bu davranışlar, kullanıcı niyetini motor geometrisine taşıdığını gösterebilir.')
h('Araştırma sorusu ve değerlendirme')
p('<b>Soru:</b> Belirsiz bir plan çiziminde seçilebilir yorumlar sunmak, tam otomatik yorumlamaya kıyasla hatalı tasarım değişikliklerini azaltıyor mu?')
item('Karşılaştırma','A: en yakın uçları eşleştiren basit snapping. B: bağlam/kapanma kuralları. C: B + kullanıcıya alternatif yorum. Aynı çizimlerde graph bağlantı hatası ve manuel düzeltme sayısı ölç; sonra küçük görev pilotu planla.')
item('Kullanıcı deneyi','Görev süresi, başarı, undo sayısı ve kontrol hissi. Görev sırasını dengele; küçük pilotu güçlü genelleme gibi sunma. Pilot öncesi yalnız otomatik hata analizi de anlamlı ilk kanıt sağlar.')
item('Demo','Kasıtlı bir kapı boşluğu ile yanlışlıkla açık bırakılmış oda köşesinin farklı yorumlanması. Kullanıcı köşeyi kapatsın ama kapı açıklığı korunsun; 3D plandaki etkisi görünür olsun.')
item('Sorulacak konu','Çizim belirsizliğini kullanıcı kontrolünü azaltmadan ne zaman ve nasıl düzeltmek gerektiği. Tasarım geçmişin burada kişisel motivasyonunla teknik problemi birleştiriyor.')
ref(15,16)

page('6 | UofT - Alec Jacobson: geometri ve doğruluk')
p('Kendi sayfasında Fall 2027 graduate alımı açıkça var; 2026-27 sabbatical durumu bununla çelişmiyor. Ancak bu çağrı, bölümün uluslararası CS MSc kısıtını kaldırmıyor. FAQ başvuruyu, adını ve araştırma uyumunu belirtmeyi öne koyuyor; örnek FAQ sorusu PhD için. [1,17]')
h('İki olası bağ - birini seç')
item('Mevcut projeye yakın','Düzenlenebilir planı açık bir kısıtlı geometrik problem olarak formüle et. Kilitli merkezler, boyut alt sınırları, ayrık oda içleri ve kapı/koridor açıklıkları. Bir çözümün hangi koşullarda geçerli olduğunu ve başarısızlık biçimlerini göster.')
item('2026 çalışmasına daha doğrudan bağ','Progressive Convex Hull Simplification, karmaşık convex proxy’leri korumacı biçimde sadeleştiriyor. İleride genel oda/engel şekilleri eklersen collision proxy karmaşıklığı ile geçiş alanı kaybını inceleyebilirsin. Şu anki axis-aligned dikdörtgen odalarda bu algoritma için anlamlı karmaşıklık yok; sırf bağlantı kurmak için ekleme. [18]')
h('En uygulanabilir özellik paketi')
p('Küçük onarım çözücüsünde önce adayları geçerlilik filtresinden geçir; kalanları değişen oda sayısı, normalize edilmiş hareket ve boyut sapmasına göre sırala. Hangi değişkenin sabit kaldığını, hangi kısıtın aktif olduğunu ve neden çözüm bulunamadığını kaydet. Heuristik bir yöntemi global optimum veya matematiksel garanti diye sunma.')
item('Deney','Rastgele yeniden yerleştirme, warm-start onarım ve küçük örneklerde sınırları açık tam arama referansı. Ortak edit bütçesinde geçerlilik, en iyi bulunan maliyet, süre ve başarısızlık oranını karşılaştır. Büyük örneklerde optimum iddiası yerine bütçe içindeki en iyi sonuç yaz.')
item('Ek geometrik pilot','Genel şekillere geçersen: ayrıntılı referans collision ile sade proxy sonuçlarını karşılaştır. Korumacı proxy yanlış biçimde “geçilebilir” dememeli, fakat dar yolları gereksiz kapatabilir. Bu hız/güvenlik/kullanılabilirlik dengesini ölç. [18]')
item('Demo','Aynı editte farklı çözüm bütçelerinin plan değişimi ve süre eğrisi; bir çözülmeyen örnek. Daha sonra proxy pilotu yapılırsa referans ile sade geometri üst üste gösterilsin.')
item('Sorulacak konu','Tasarım değişikliklerinin küçük tutulması için hangi geometrik maliyetin anlamlı olduğu; geçerlilik kontrolünün ne kadarını garanti altına alabileceğin.')
p('Text-guided Controllable Mesh Refinement gibi başka interaktif modelleme çalışmaları da listesinde var. Bunlar genel yaklaşım için bağlam sağlar; PlayableSketch’in aynı yöntemi kullandığı veya bir devamı olduğu söylenmemeli. [19]','SmallTR')
ref(17,18,19)

page('7 | UofT - Fidler ve Levis: farklı sorular')
h('Sanja Fidler | yüksek ek iş, daha uzak ilk hedef')
p('Kişisel sayfası vision/graphics, 3D reconstruction/synthesis ve genel öğrenci arayışını belirtiyor. Sayfanın MSc ifadesi güncel bölüm kuralıyla çelişen bir istisna kanıtı değil. [1,20]')
item('Çalışma bağlantısı','GEN3C (CVPR 2025), kamera kontrolü ve 3D tutarlılık için 3D cache kullanan video üretim çalışması. Ortamındaki kamera, depth ve nesne kimliklerini doğru kaydetmek ilgili bir deney altyapısı olabilir; bu çalışmanın yöntemini yeniden yaptığın anlamına gelmez. [21]')
item('Ne ekleyelim','Semantik oda/nesne etiketleri, sabit instance ID, kamera yörüngesi, depth/segmentation çıktıları. Aynı planın geometri ve görünüş değişimlerini ayrı kontrol eden küçük bir sentetik veri paketi.')
item('Deney','Bir mevcut reconstruction/vision yöntemini görünüşü sabit-topolojisi farklı ve topolojisi sabit-görünüşü farklı setlerde değerlendir. Hold-out planlar, veri lisansları ve tam deney ayarları açık olsun. Salt veri dışa aktarımı araştırma sonucu değil; belirli bir hata hipotezi gerekir.')
item('Demo ve soru','Kapı ve oda kimliği editler arasında izlenirken bir vision yönteminin hangi değişimde hata verdiği. Çok-görünüş tutarlılığı veya mekânsal genelleme hatalarının hangi kontrollü örneklerle ölçülebileceği.')
ref(20,21)
h('Aviad Levis | PlayableSketch yerine RIDGE daha güçlü giriş')
p('PI-Vision; fizik bilgili görüntüleme, inverse problems, Earth/climate science ve astronomi çalışıyor. Güncel listede cloud tomography ve multi-angle imaging örnekleri var. Mevcut oda üretimiyle bağlantı dolaylı; Fall 2027 kişisel kontenjanı bu incelemede teyit edilmedi. [22,23]')
item('Ne ekleyelim','Yalnız bu yöne gerçekten dönmek istiyorsan: bilinen geometri/malzeme/ışık altında çoklu kamera ölçümleri üret; kontrollü gürültü ve eksik görünüşler ekle; basit inverse geometry/material problemi kur. RIDGE’nin ölçüm/veri tarafı ana hikâye olabilir.')
item('Deney','Referans geometri veya parametreye göre tahmin hatası; görünüş sayısı ve gürültü arttıkça hata. Görsel benzerlik ile fiziksel parametre doğruluğunu ayır. “Satellite-to-terrain” tek başına inverse imaging araştırması değildir.')
item('Yatırım kararı','Görüntüleme ve sayısal yöntemleri istemiyorsan bu hoca için PlayableSketch’i dönüştürme. Kısıtlı zamanın varsa Singh/Jacobson yönünde daha net bir katkı üret.')
ref(22,23)

page('8 | Waterloo - Craig Kaplan: matematik ve tasarım')
p('Kişisel sayfasında matematik-sanat, computational geometry, graph theory, simetri ve tiling odağı var. Fall 2026 listesinde MMath öğrencileri bulunuyor; bu açık Fall 2027 kontenjanını kanıtlamaz. [24]')
h('Güçlü kaynak: hocanın kendi proje fikirleri')
p('2025 CS898 proje sayfasında interaktif substitution tiling tasarımı, geçerlilik denetimi, Escherization, polyform checker ve Wang tile authoring önerileri yer alıyor. Bunlar ders projesi fikirleridir; MSc ilanı veya sana verilmiş görev değildir. Yine de hangi tasarım araçlarını ilginç bulduğuna doğrudan kanıt sağlar. [25]')
h('PlayableSketch’e nasıl çevrilebilir?')
item('Minimum sürüm','Oda/koridor modüllerinin kenarlarını kapı/duvar etiketleriyle tanımla; bitişik modüllerde eşleşme kurallarını doğrula. Üzerine bir simetri veya tekrar kuralı ekle. İlk çalışma sınırlı modül kümesi ve sonlu bölgeyle yapılsın.')
item('İkinci katman','Tasarımcı kuralı veya bir modülü değiştirince: komşulukların neden bozulduğunu görselleştir; sınırlı bölgeyi onarırken kilitli kararları koru. Global yeniden çözüm ile değişiklikten başlayan onarımı karşılaştır.')
item('Daha doğrudan alternatif','İç mekân araç akışından bağımsız, küçük bir substitution tiling editörü aynı projede ayrı görünüm olabilir. Fakat yalnız dekoratif zemin deseni üretmek, matematiksel ve algoritmik sorunu karşılamaz.')
h('Araştırma sorusu ve değerlendirme')
p('<b>Soru:</b> Sonlu bir modüler düzenin kuralı değiştiğinde, kenar eşleşmesini ve seçilmiş simetri ilişkilerini en az modül değişimiyle yeniden sağlayabilir miyiz?')
item('Deney','A: greedy eşleştirme. B: bütçeli backtracking. C: önceki çözümden başlayan onarım. Aynı sonlu örneklerde başarı, arama düğümü, süre, değişen modül sayısı ve simetri hatası. Çözüm bulunamamasını yalnız yöntem başarısızlığı olarak kaydet; kanıt yoksa döşenemezlik sonucu çıkarma.')
item('Demo','Bir kenar etiketi değişsin, ihlal zinciri görünür olsun, araç üç çözüm sunsun. Bir simetri kilidi devreye alındığında hangi seçeneklerin elendiği gösterilsin.')
item('Sorulacak konu','Hangi kural sınıfında yerel düzenleme yeterli kalıyor ve hangi durumda bütün sonlu bölgeyi çözmek gerekiyor? Kısıtları ve örnek uzayını açık tutmak burada özellikle değerli.')
p('Kaplan yönü, mimarlık/tasarım geçmişini matematiksel üretimle birleştirir. Ancak hocanın tiling odağını “her tür PCG” şeklinde genişletme. İç mekân yorumunun ilgisine uygunluğunu ayrıca sor.','SmallTR')
ref(24,25)

page('9 | Waterloo - Steinberg ve Batty')
h('Shlomi Steinberg | rendering değil, fiziksel ışık/dalga sorusu')
p('Sayfası wave optics ve karmaşık ortamlarda ışığın yayılımını/sensörlerle ilişkisini vurguluyor. Önceki oyun motoru deneyimi ilgi çekici ortak geçmiş; asıl araştırma bağının yerini tutmaz. Güncel 2027 kontenjanı teyit edilmedi. [26]')
item('Çalışma bağlantısı','Wave Tracing (2026), wave-optical transport ile uzun dalga boylarında yayılım/difraksiyon uygulamaları içeriyor. Oda/koridor düzenleri kontrollü sahne kümesi olabilir. [27]')
item('Ek','Genel sahne dışa aktarımı ve bir parametre taraması: kapı genişliği, koridor köşesi, kaynak/alıcı konumu. Malzeme, geometri ve birimleri açık kaydet. Hocanın araştırma yazılımına entegrasyon veya benzer bir hesaplama deneyi ayrı geliştirme gerektirir.')
item('Deney','Basit geometride referans/analitik çözümle doğrulama; yalnız line-of-sight modeli ile fiziksel wave/diffraction modelinin farkını kontrollü sahnelerde inceleme. Sonuç metriği fiziksel modeline uygun şiddet/hata ve süre olsun. Radar simülasyonu geçmişini ancak dalga fiziği gerçekten modelleniyorsa bağla.')
item('Karar','Zaten rendering/optik çalışmak istiyorsan değerli; genel bir shader, Lumen görünümü veya UE raycast eklemek bu hocaya güçlü araştırma kanıtı sayılmaz.')
ref(26,27)
h('Christopher Batty | açık çağrı var, fakat temel fizik olmalı')
p('Join sayfası güçlü matematik/programlama ile MMath thesis başvurusunu açıkça teşvik ediyor. Ana odağı fizik tabanlı animasyon; fluids, solids, yüzey temsilleri ve adaptive methods. Render/visualization ana araştırması olmadığını ayrıca söylüyor. [28,29]')
item('Ek','Başlangıçta küçük bir 2D incompressible fluid pilotu: üretilen oda/koridorları solid boundary yap; mevcut veya yeniden üretilen bir çözücüde sınır ve çözünürlük etkilerini ölç. Önce basit dikdörtgen örnekle doğrula.')
item('Deney','Divergence residual, hacim/kütle kayması, zaman adımı kararlılığı ve çözüm süresi. Kapı daralınca sadece güzel görünen su değil, sınır temsilinin sayısal etkisi gösterilsin. Referans ve fiziksel problem aynı olmalı.')
item('Karar','PDE/numerical methods öğrenmeye istekliysen alım çağrısı açısından mantıklı. Kısa sürede PCG demosunu bitirmek istiyorsan Kaplan yönü daha az konu değişimi ister. Açık çağrı + zayıf konu uyumunu otomatik “daha olası kabul” diye yorumlamıyorum.')
ref(28,29)

page('10 | Kodda ortak yatırım: neyi hangi sırayla ekle?')
table([['Sıra','Önerilen modül','Mevcut altyapı / hedef'],['1','EditScenario kaydı: graph, seed, önceki plan, edit, kilitler','Mevcut JSON/navigation ölçümleri genişletilir'],['2','ConstraintSet: sabit oda, boyut, bağlantı ve açıklık koşulları','Validation + stable GUID; Sheffer/Jacobson'],['3','RepairCandidate: plan değişimi, geçerlilik ve gerekçe','Mevcut saved layout + routing; ortak çekirdek'],['4','RepairSearch: önceki çözümden sınırlı aday arama','Zaman/iş bütçesi, başarısızlık nedeni'],['5','2D tasarım görünümü: fark, aday seçimi, undo','Singh/Sheffer; önce sade mouse arayüzü'],['6','Tek uzmanlık modülü','Kaplan: kenar kuralları; Singh: çizim belirsizliği']], [36,257,208])
p('Bu adlar önerilen tasarımdır; kodda var olan sınıf isimleri veya bu görevde yazılmış uygulamalar değildir. Mevcut navigation JSON dışa aktarımını kopyalamak yerine deney kaydıyla ilişkilendirmek daha az tekrar üretir. Çalışan kaynakları bu rapor için değiştirmedim.','SmallTR')
h('Onarım problemi nasıl tanımlanmalı?')
p('Önce geçerlilik: oda içleri çakışmasın; istenen bağlantılar üretilebilsin; seçilen ajan için açıklık koşulları sağlansın; kilitler ihlal edilmesin. Yumuşak amaç: değişen oda sayısı, önceki plana göre konum/boyut değişimi ve tercih edilen rota ölçütleri. Maliyetin birimleri ve ağırlıkları açıklansın; farklı ağırlıklarda duyarlılık analizi yapılsın.')
h('Karşılaştırmanın omurgası')
item('Üretim ve onarımı ayır','A: global yeniden yerleştirme. B: önceki planı başlangıç alan onarım. C: B + tasarımcı kilitleri. Aynı graph, seed, edit ve süre bütçesinde karşılaştır. Ayrı deneyde Full/Local geometry apply maliyetini ölç.')
item('Başarı ölçümü','Geçerli onarım oranı; korunan kilitler; değişen oda sayısı; geometrik sapma; navigation sonucu; hesaplanan aday ve genişletilen durum; toplam ve aşama süreleri. Başarısız girdiler paydada kalsın.')
item('Geçerlilik kanıtı','Kodun grid cevabını fiziksel kapsül sweep veya kontrollü pawn geçişleriyle çapraz kontrol et. CellSize duyarlılığını ölç. “Yol yok” ile MaxWork/MaxCells nedeniyle analiz tamamlanamadı durumlarını birleştirme.')
item('Yanlış hız iddiasını önle','Component apply, plan/routing, validation ve navigation sürelerini ayrı ver. Parçaları korumak, bütün pipeline’ın yerel veya daha hızlı olduğunu tek başına göstermez.')

page('11 | Altı hafta ve hocaya götürülecek paket')
p('Kaba plan: mevcut kodu bilen biri için haftada 10-15 saat. Süre bir taahhüt değil; arayüz, solver ve ders/iş yüküne göre değişir. İletişim için bütün planın tamamlanmasını beklemek gerekmez; ilk ölçümlü pilot yeterli bir konuşma başlangıcı olabilir.')
item('Hafta 1','Mevcut navigation sonuçlarını tanımla ve benchmark kaydına bağla. 10 graph × 20 seed pilotu; geometri, grid ve gerçek pawn ayrımlarını kontrol et. Bu örnek sayısı istatistiksel güç gerekçesi değil, başlangıç bütçesidir.')
item('Hafta 2','Kilit ve değişiklik maliyeti ekle. Mevcut yerleşimden başlayan basit onarım. Teslim: bir oda editinde doğru geçerli çözüm ve açık başarısız örnek.')
item('Hafta 3','Üç aday, gerekçe, fark vurgusu ve undo. Teslim: Sheffer odaklı 60-90 saniye demo ve başlangıç yöntemleriyle ilk tablo.')
item('Hafta 4','Kısıt/arama bütçesi duyarlılığı; büyük/küçük planlar; başarısızlık analizi. Basit örneklerde referansla doğruluk; değişen parça ve toplam süre ayrımı.')
item('Hafta 5','Tek yön seç: Kaplan için modül kenarı/simetri; Singh için çizimden graph ve belirsizlik. Jacobson için alternatif olarak genel geometri/proxy pilotu; bu daha yüksek ek iş ister.')
item('Hafta 6','İngilizce 2 sayfa teknik özet, tekrarlanabilir repo, bir kısa video. Soruyu, önceki işi, kendi katkını, gerçek ölçümleri ve sınırları açıkça ayır.')
h('İletişim sırası ve protokol')
item('UBC','Önce Sheffer: ilgili 2014/2022 çalışma bağını ve bir onarım deneyi sun. Program ön iletişimi zorunlu tutmuyor. Peng’in güncel sayfası başvuruda adını belirtip kabul sonrasında e-posta diyor; ona sırf yanıt almak için bu akışın tersini önermiyorum. [3,6,12]')
item('Waterloo','Önce Kaplan için konu/2027 kapasite sorusu ve küçük demo. Batty’ye ancak fizik/numerical problem önerisiyle git. Bölüm önceden supervisor bulmayı şart koşmuyor, ancak iletişim kurmayı tavsiye ediyor; kabul için supervisor gerekiyor. [4,24,28]')
item('UofT','Yalnız direct-entry PhD’ye gerçekten açıksan o rolü açıkça belirt. Singh’in yaratıcı araç ve Jacobson’ın geometrik yöntem yönünü ayrı anlat. “MSc Fall 2027” e-postasıyla mevcut bölüm kuralını görmezden gelme. [1,2,17]')
ref(3,4,12)

page('12 | Son karar ve kaynak sınırları')
h('Yalnız yüksek lisans istiyorsan')
p('<b>Birinci odak: UBC / Alla Sheffer.</b> Mevcut graph, oda ve doğrulama temelini doğrudan ilgili önceki işle karşılaştırabilirsin. <b>İkinci odak: Waterloo / Craig Kaplan.</b> Modüler kurallar ve simetri eklersen farklı ama ortak altyapıyla taşınabilen bir araştırma yönü oluşur. Kontenjanları kişisel olarak teyit edilmedi; sıralama kabul tahmini değil, geliştirme yatırım önerisi.')
p('<b>UofT CS MSc’yi bu statüyle başvuru hedefi sayma.</b> Direct-entry PhD beş yıllık ayrı bir tercih. UofT hocaları için geliştirilen çizim/geometri yönleri, yine de UBC ve Waterloo başvurularına da yarayan teknik kanıtlar üretebilir. [1,2]')
h('PhD’ye de açıksan')
p('<b>Singh:</b> çizimden düzenlenebilir temsile geçiş ve insan kontrolü. <b>Jacobson:</b> sağlam geometrik yöntem, açık problem tanımı ve referans karşılaştırması. Fall 2027 alım ifadesi Jacobson için açık; Singh için bu incelemede dönem özel ilan bulunmadı. Bu farkı, konu uyumu ile kontenjan kanıtının ayrı olması olarak değerlendir. [15,17]')
h('İlk aşamada kimi geriye koyardım?')
p('Peng: fizik tabanlı karakter kontrolü kurmaya hazırsan yükselir. Chen/Batty: sayısal fizik öğrenmeyi istiyorsan yükselir. Steinberg: ışık/dalga fiziğine dönmek istiyorsan yükselir. Fidler/Levis: mevcut projenin ötesinde veri, vision veya inverse-problem altyapısı gerekir. Bunlar kötü hedefler değil; mevcut projeden daha yüksek konu değişimi maliyeti var.')
p('UBC’de van de Panne’nin kendi sayfası fon durumuna bağlı alım ve sınırlı e-posta yanıtı belirtiyor. Waterloo’da Hachisuka, Fall 2026’dan itibaren kapasite sınırına ulaştığını yazıyor. Bu yüzden daha çok özellik ekleyerek bu kapasite sinyallerini aşabileceğini varsaymadım. [30,31]')
ref(30,31)
h('Bu rapor neyi doğruluyor?')
p('Birincil kaynaklar: resmî program sayfaları, hocaların kişisel/lab sayfaları, yazar proje sayfaları ve makale özetleri/yayın kayıtları. Araştırma bağlantıları bu kaynaklardan çıkarılmıştır; bütün makalelerin tam metin, kod ve sonuçlarını yeniden üretme çalışması yapılmadı. Önerilen özelliklerin yeni araştırma katkısı olup olmadığı ayrı literatür ve deney çalışması gerektirir.')
p('Proje kanıtı: güncel LevelActor.h, Room.h, ComponentRegistry.h ve yeni Navigation.h arayüzleri; navigation kaynak araması. Kodda bulunan yetenekler ile önerilen işler ayrıldı. Aday profilinin başlangıç kaynağı kullanıcı PDF’sidir; GPA/RIDGE beyanları bağımsız teyit edilmedi. Önceki raporun yüzdeleri veya e-posta talimatları güncel resmî kaynakların önüne konmadı.','SmallTR')
p('<b>Benim nihai önerim:</b> Önce Sheffer için tasarım niyetini koruyan onarım demosunu bitir; sonra aynı çekirdeği Kaplan için kural/simetri, Singh için çizim belirsizliği görünümüyle genişlet. Üç okul adına üç ayrı büyük proje yapma.')

def footer(c,doc):
    w,h=doc.pagesize
    c.setStrokeColor(HexColor('#CEDFE3'));c.line(47,42,w-47,42)
    c.setFont('Arial',8);c.setFillColor(HexColor('#526674'))
    c.drawString(47,29,'Pelinsu Kaleli | UBC / UofT / Waterloo | Araştırma ve geliştirme planı | 11 Ekim 2026')
    c.drawRightString(w-47,29,str(doc.page))
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),rightMargin=47,leftMargin=47,topMargin=43,bottomMargin=57,title='PlayableSketch - UBC, UofT ve Waterloo Odaklı Araştırma Raporu',author='Pelinsu Kaleli için hazırlanmıştır')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
