from pathlib import Path
import json
import zipfile
import shutil

root = Path.cwd()
out = root / 'outputs/day4'
manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))

guide = '''# PlayableSketch — 4. gün: düzenleme, kayıt ve validation

Bu paket 3. günün sonunda projende bulunan kodlara göre hazırlandı. Implementasyonu sen yapacaksın. Asıl projenin Source dosyaları değiştirilmedi. Aşağıdaki dosyaların her biri tam dosya içeriğidir; bir fonksiyonu başka bir parçadan tamamlaman gerekmiyor. Teslim edilen C++ ve Build.cs kodlarında yorum satırı yok.

## Bugünün hedefi

Room ekleyebilmek, silebilmek, taşıyabilmek ve boyutunu değiştirebilmek; Connection kurabilmek; kapının duvarını ve duvar boyunca konumunu düzenleyebilmek; geçersiz tasarımda kod, ilgili ID ve marker görmek. Kaynak veri kaydedilmeli. Undo/Redo sonrasında önizleme kaynakla aynı hale gelmeli.

Bugün local rebuild eklemiyoruz. Rebuild Geometry (Full) bütün generated meshleri yeniler. Room yerleşimini yeniden aramaz. Local rebuild 5. günün işidir.

## 1. Dosyaları yerleştir

Önce Unreal Editor'ı kapat. Paketteki Source/PlayableSketch yolları projenin aynı yollarına karşılık gelir. DEĞİŞTİR dosyalarında mevcut içeriğin tamamını yeni içerikle değiştir. EKLE dosyalarında klasörü/dosyayı oluşturup tamamını yapıştır. Aynı dosyanın eski ve yeni sürümünü iki ayrı .cpp halinde Source altında bırakma.

Dosyaları şu sırayla uygula: FloorPlan.h → Room.h → Connection.h → GraphAsset.h/.cpp → LayoutGenerator.cpp → DoorGenerator.cpp → Validation.h/.cpp → Day4Tests.h/.cpp → Actor.h/.cpp → Build.cs. Hepsi yerleşmeden build alma.

generated.h dosyaları UnrealHeaderTool tarafından üretilecek. Onları elle oluşturma. Header'larda generated.h son include olarak kalmalı.

### Dosya listesi

{inventory}

Diğer dosyalar mevcut halleriyle kalır: Graph.h, GraphValidator.h, PlacementSearch, CorridorRouter/Routing, FloorBuilder, WallGeometry, WallBuilder ve önceki testler. Yeni kod bu dosyalardaki API'leri kullanır.

## 2. Kaynak veri ve Actor görevlerini ayır

Kaynak, GraphAsset içindeki Graph'tır. Room adı, türü, rolü, boyutu, konum modu ve Connectionlar burada düzenlenir. Actor GraphAsset'i kullanır ve componentleri üretir.

Actor'daki eski Rooms/Connections/Graph alanları kayıt uyumluluğu için tutuldu fakat Details üzerinden gizlendi; üretimin kaynağı değiller. Aynı veriyi iki yerde düzenlemeyeceğiz.

Generated duvarı elle taşımak Graph'ı değiştirmez. Odayı taşımak için GraphAsset'teki ilgili Room'un PositionCm alanını değiştir.

## 3. Auto / Locked konumu ve saved layout

Room'a PositionMode ve PositionCm eklendi. PositionCm Actor-local cm cinsinden odanın sol alt köşesidir; odanın merkezi veya world position değildir.

Auto: Generate Layout konumu arar. Son bulunan sol alt köşe GraphAsset.SavedLayout.Rooms içinde Room ID ile kaydedilir. Rebuild Geometry bu kaydı okur ve Auto Room'u başka bir yere taşımaz.

Locked: PositionCm doğrudan kullanılır. Generate Layout bütün Locked odaları önce engel listesine koyar, sonra Auto odaları yerleştirir. Böylece Auto odanın sonradan yerleştirilecek bir Locked odanın yerini kapması engellenir. Locked konum sessizce yuvarlanmaz veya taşınmaz. Overlap/gap ihlalinde açık hata döner.

Mevcut 2. gün kodu Auto oda boyutlarını gridin bir sonraki katına yuvarlıyor. Aynı kural rebuild'de de uygulanır: GridStep=50 iken 625 cm Auto oda 650 cm üretilir. Locked oda boyutları kaynak değeriyle kullanılır. İlk denemelerde 600, 650, 700 gibi grid katlarını kullan.

Odayı bulunduğu yerde Locked yapmak için: Actor'ın Auto Rebuild Geometry alanını geçici olarak kapat; asset Saved Layout/Rooms listesinden ilgili Room ID'nin MinCm değerini not et; o Room'da Position Mode=Locked seç ve PositionCm'ye aynı MinCm'yi yaz; sonra Rebuild Geometry (Full) bas. Konumun bir bileşenini 100–200 cm değiştirerek taşıma testini yap. Düzenleme bittiğinde Auto Rebuild Geometry'yi tekrar açabilirsin.

Yeni bir Auto Room'un saved konumu yoktur. Connectionları tamamladıktan sonra Generate Layout kullan. Rebuild'in kendi kendine yerleşim aramaması bilinçli bir kuraldır; PS-L001 bu durumu açıklar.

## 4. Generate Layout ve Rebuild Geometry (Full)

| Action | Davranış |
|---|---|
| Generate Layout | Graph doğrulanır, Auto konumlar aranır, Locked konumlar korunur, kapılar/rotalar/duvarlar doğrulanır, başarılı konumlar assete kaydedilir ve geometri yayınlanır. |
| Rebuild Geometry (Full) | Auto konumlar saved layout'tan, Locked konumlar source Room'dan okunur. Güncel boyut/kapı ayarlarıyla corridor routing ve bütün meshler yeniden hesaplanır. Room yerleşimi aranmaz. |
| Validate Current Design | Kaydedilen Room konumlarıyla aynı kontrolleri çalıştırır. Başarılıysa yeni component yayınlamaz. Geçersizse eski önizlemeyi temizler. |
| Clear Floors | Duvar/zemin componentleri, yol çizgisi ve hata markerları temizlenir. Assetteki saved layout kalır. |

Eski Generate Floors düğmesi editor içinde Generate Layout'a yönlendirilir. Yeni çalışmalarında açık isimli düğmeleri kullan. PIE BeginPlay sırasında yalnız Rebuild Geometry çağrılır; oyun sırasında authoring assetine yeni layout yazılmaz.

Seed, RoomGap ve placement deneme sayısı gibi yerleşim ayarlarını değiştirmek tek başına Auto odaları taşımaz. Yeni yerleşim için Generate Layout gerekir. Actor ve bütün parçalarının transform ilişkisi 3. gündeki gibi korunur.

## 5. Room ekleme, Connection kurma ve silme

GraphAsset editöründe Details panelindeki Authoring alanında Add Room düğmesi var. Yeni Room stable ID alır. Name/Type/Role/Width/Depth alanlarını Graph/Rooms içinden düzenle. İlk ve son Room kimliği Graph.StartRoomId ve Graph.GoalRoomId ile ayrıca seçilir; RoomRole renk/etiket bilgisidir.

Connection için iki mevcut Room ID'yi New Connection Room A Id ve New Connection Room B Id alanlarına gir; Add Connection bas. Yeni Connection'ın CorridorWidthCm/DoorWidthCm değerlerini Graph/Connections üzerinden düzenle. Var olmayan uç, self connection veya aynı Room çifti tekrar eklenirse action reddedilir.

Oda silmek için Room To Remove Id girip Remove Room bas. Oda ve ona bağlı Connectionlar aynı transaction içinde kaldırılır; saved placement da kaldırılır. Details içindeki Rooms arrayinden Remove/Clear kullanıldığında da silinen Room ID'leri üzerinden bağlı Connectionlar temizlenir. Connection uçlarını düzenlerken yazdığın geçici yanlış ID sessizce silinmez; validation hatası olarak kalır.

Start veya Goal silinirse bu seçim kendiliğinden başka Room'a aktarılmaz. Eski ID kaynakta kalır ve PS-I001 çıkar; Graph'ta geçerli yeni StartRoomId/GoalRoomId'yi sen seçersin. Hub silinip Start/Goal bağlantısız kaldıysa PS-V004 de çıkabilir. Geçersiz editin görünür geometri bırakmaması beklenir.

Normal ad/boyut editinde ID değişmez. Duplicate işlemi yeni kopyaya yeni ID verir; var olan Connectionlar özgün Room'a bağlı kalır. Room listesinin sırasını değiştirmen bağlantı uçlarını değiştirmez.

## 6. Kapı yönünü ve offsetini düzenle

Her Connection'da Door A Settings ve Door B Settings var. A, RoomAId'ye; B, RoomBId'ye aittir.

bManual=false: mevcut otomatik yön ve merkez seçimi kullanılır.

bManual=true: WallSide ve OffsetCm kullanılır. Offset kapının merkezini belirtir. Kapının başlangıcını belirtmez.

| Side | Offset başlangıcı | Offset yönü |
|---|---|---|
| North | (Min.X, Max.Y) | +X |
| South | (Min.X, Min.Y) | +X |
| East | (Max.X, Min.Y) | +Y |
| West | (Min.X, Min.Y) | +Y |

Örnek: 600 cm East duvarı, DoorWidth=150, margin=50. Offset=200 ise açıklık 125–275 cm olur. İzin verilen merkez aralığı 125–475 cm'dir. Offset=20 ise PS-V002 çıkar.

Yan yana duran odalarda önce DoorA=East, DoorB=West ve her iki Offset=300 dene. Sonra ikisini birlikte 200 yap. Rebuild Geometry bas; açıklık ve corridor girişi hareket eder, Room konumları aynı kalır.

Geçerli bir Side/Offset seçimi mevcut sınırlı L routing aramasının mutlaka rota bulacağı anlamına gelmez. Rota bulunamazsa PS-G002 çıkar. Kapı verisi ile routing failure ayrı sorunlardır; bütün routing hatalarını invalid door olarak göstermiyoruz.

## 7. Bağımsız validator

Generator kendi kontrolünü yapar, fakat validator ayrıca Graph, FloorPlan ve GeometryDescriptor çıktısını inceler. Böylece generator'dan geçmiş olmayı doğruluğun tek kanıtı saymıyoruz. Testler validator'a doğrudan bozuk planlar verir.

| Code | Kontrol |
|---|---|
| PS-V001 | İki Room'un iç alanı üst üste geliyor. |
| PS-V002 | Door yanlış Room'a ait, yanlış duvar çizgisinde, köşeden taşıyor, yanlış genişlikte veya Pawn'a göre dar/alçak. |
| PS-V003 | Corridor minimum/Pawn genişliğinden dar veya footprint genişliği declared CorridorWidth ile uyuşmuyor. |
| PS-V004 | Graph'ta kopuk Room, eksik rota, birbirinden ayrılmış footprintler veya tam Door açıklığına ulaşmayan Corridor. |
| PS-V005 | Door açıklığını kesen duvar/lintel, eksik veya yanlış ölçülü lintel, geçersiz geometry descriptor. |
| PS-V006 | Yeni duvar kalınlığı Room ya da başka Corridor'un yürünebilen alanına taşıyor. |
| PS-I001 | Kaynak kimliği, uç, boyut, Start/Goal veya global ayar hatası. |
| PS-L001 | Saved Auto Room placement yok; Generate Layout gerekli. |
| PS-G001 | Sınırlı Room placement araması başarısız. |
| PS-G002 | Sınırlı corridor routing araması başarısız. |
| PS-G003 | Component/mesh üretimi başarısız. |

Bir edit birden fazla hata üretebilir. Örneğin dar koridor ayrıca fiziksel erişimi bozabilir. İlk hatayı bulmak, diğer kontrolleri saklamayı gerektirmez.

Minimum kullanılabilir genişlik = max(MinCorridorWidthCm, 2 × (PawnRadiusCm + ClearanceCm)). Varsayılan radius=40, clearance=10 ve minimum=100 ile sonuç 100 cm. Minimum Door height = PawnHeightCm + ClearanceCm; height=180, clearance=10 ile en az 190 cm. Bunları kendi Character capsule ölçülerine göre ayarla. PawnHeight tam yüksekliktir; Capsule Half Height değildir.

Fiziksel bağlantı kontrolü rectangle union'ın sürekliliğini ve kapı temasını doğrular. Bu, gerçek CharacterMovement yürüyüşünün veya 6. günün agent boyutuyla navigation hesabının yerine geçmez. 3. gündeki PIE geçiş testini düzenlemeden sonra tekrar yap.

Her Issue Code, ElementIds, Severity, Message, bHasPosition, PositionCm ve ExtentCm tutar. Position/Extent Actor-local cm'dir. Error olan yerde kırmızı debug box çizilir. Actor dönünce marker da döner. Code ve Message Details/Last Issues ve Output Log'da görülür; yalnız renk kullanmıyoruz. [Epic DrawDebugBox API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/DrawDebugBox)

Henüz hiç yerleştirilmemiş Auto Room veya global ayar hatası için gerçek konum bilinmeyebilir. bHasPosition=false olur ve logda Unknown yazar; uydurma bir konuma marker çizilmez. Beş bozuk plan testinde konumlar biliniyor ve metadata ayrıca kontrol ediliyor.

## 8. Geçersiz edit, stale preview ve navigation

Seçtiğimiz normal failure politikası clear'dır: geçersiz yeni inputta zeminler/duvarlar temizlenir, eski yol çizgisi kaldırılır, PreviewStatus hata durumunu açıklar. Hatalı tasarımın geometry'si yayınlanmaz.

Auto Rebuild Geometry açıkken Actor editor tick'inde kaynak değişimini algılar ve full rebuild yapar. Custom canvas veya büyük event altyapısı gerektirmeyen bu çözüm küçük graph için yeterlidir. Büyük graph performansı bu günün kapsamı değil.

Auto rebuild kapalıysa eski geometry geçici olarak kalabilir: bPreviewStale=true, PreviewStatus güncelleme gerektiğini gösterir ve path testi eski başarıyı yeni editin başarısı olarak kullanmaz. Explicit Generate/Rebuild başarısız olduğunda preview temizlenir. Test Floor Path ayrıca kaynağın başarılı üretimde kullanılan veriyle aynı olup olmadığını kontrol eder.

Editor viewport Realtime kapalıyken polling/marker çizimi durabilir. Realtime aç veya Rebuild Geometry düğmesini kullan. Kaynak asseti başka bir pencerede düzenliyorsan ana viewport'a dönerek değişikliği kontrol et.

## 9. Undo/Redo ve save

Add/Remove/Generate Layout gibi custom işlemler FScopedTransaction ile bir Undo işlemi halinde kaydedilir. Asset Modify() ile transaction'a alınır; MarkPackageDirty() ile kaydedilmesi gereken değişiklik UE'ye bildirilir. Details üzerinden yapılan property editleri de UE transaction sistemini kullanır. [Epic UObject::Modify API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/CoreUObject/UObject/Modify)

Türetilen componentlerin kendisini kalıcı kaynak kabul etmiyoruz. Undo/Redo sonrası kaynak/saved layout geri gelir; önizleme bundan yeniden üretilir. Auto rebuild kapalıysa explicit Rebuild kullan.

Save testi:

1. Generate Layout ile ilk SavedLayout'u oluştur.
2. Bir Room'un adını ve boyutunu değiştir; yeniden üretimi kontrol et.
3. Ctrl+Z yap; veri ve preview önceki hale dönmeli.
4. Ctrl+Y yap; edit tekrar gelmeli.
5. Asseti ve leveli Save et.
6. Editor'ı kapatıp yeniden aç.
7. Room/Connection ID'leri, Locked konum, manuel Door ayarları ve SavedLayout aynı olmalı.
8. Gerekirse Rebuild Geometry (Full) bas. Generate Layout'a basmadan önce konumların korunmasını doğrula.

Bu paket build ve headless testlerde doğrulandı. Senin gerçek assetinin diskten save/reopen testi ve görünür marker/PIE testi elle yapılacak; bu testleri otomatik yapılmış gibi sayma.

## 10. İlk çalıştırma sırası

1. Bütün 14 dosyayı uygula ve Editor kapalıyken Development Editor / Win64 build al.
2. Projeyi aç. Mevcut GraphAsset üç oda ve iki Connection ile kullanılabilir; yeni alanlar varsayılan Auto/otomatik kapı değerleriyle gelir.
3. Actor'da GraphAsset ata. İlk saved placement yoksa PS-L001 normaldir.
4. Min Corridor Width=100, Pawn Radius=40, Pawn Height=180, Clearance=10; Wall Height=300, Door Height=220, Wall Thickness=20 ayarla.
5. Test Day 4 Validation bas; Failures=0 bekle.
6. Generate Layout bas. Last Issues boş, PreviewStatus current valid preview olmalı.
7. Rebuild Geometry (Full) bas; oda konumları aynı kalmalı.
8. Assette bir Room boyutunu 600'den 650'ye değiştir. Önizleme full rebuild ile güncellenmeli; diğer Roomlar kaymamalı.
9. SavedLayout'taki konumdan başlayarak bir Room'u Locked yap ve taşı.
10. Manual Door side/offset değiştir. Geçişi PIE'da tekrar yürü.
11. Aşağıdaki kötü örnekleri ve save/undo testini tamamla.

Eski günlerin bazı test düğmeleri Start=(0,0) ve bütün odaların Auto/grid üzerinde olması gibi 2. gün varsayımları kullanıyor. Locked tasarım için Test Day 4 Validation ve bu günün edit testleri esas alınmalı.

## 11. Beş kötü örnek ve günlük bitiş ölçütü

Test Day 4 Validation gerçek kaynak assetini kullanmaz. Kendi küçük fixture'ını oluşturur; beş bozuk örneği doğrudan validator'a verir ve Code/ID/Severity/Position/Message kontrol eder. Ek olarak Locked yerleşim, manual Door, silme, gerçek Actor full rebuild, Undo/Redo ve invalid-preview davranışını test eder. Teste ait transient Actor temizlenir.

Elle yapacağın kötü örnekler:

| Örnek | İşlem | Beklenen |
|---|---|---|
| Overlap | İki Room'u Locked yapıp aynı PositionCm ver. | PS-V001, Room ID'leri, kırmızı box, preview clear. |
| Invalid Door | Manual=true ve OffsetCm=20 yap. | PS-V002, ilgili Room/Connection ID ve marker. |
| Narrow Corridor | CorridorWidthCm=60 yap. | PS-V003; DoorWidth nedeniyle PS-V002 de çıkabilir. |
| Disconnected Room | Connectionı silerek bir Room'u kopar. | PS-V004 ve Room markerı. |
| Door/Wall mismatch | Test fixture açıklığın içine ayrıca bir wall descriptor koyar. | PS-V005, Door/Connection ID ve konum. |

PS-V005'in bozuk geometry fixture'ı gerçek kaynak assetine yanlış duvar eklemez. Ayrıntı için test dosyasındaki BlockingWall örneğine bak. Validator descriptor'ları component oluşturmadan önce kontrol eder; marker için saklanan issue konumu Actor tarafında kullanılır.

Her kötü editten sonra Undo ile geçerli duruma dön. Preview geri gelmeli; eski collider/mesh birikmemeli.

4. gün tamamlandı demek için: Room ekleme/silme, Connection ekleme, Locked taşıma, boyut düzenleme, manuel kapı, iki action'ın farklı davranışı, beş hata kodu/marker, invalid preview temizliği, Undo/Redo ve Save/Reopen testleri geçmeli. Full rebuild olduğu açık kalmalı.

## 12. Doğrulama sonucu

{verification}

## 13. Bütün kodlar — dosyaların tam son halleri

Aşağıdaki her blok dosyanın TAM içeriğidir. Dosya yolları projenin köküne göredir. Aynı tam dosyalar paketin Source klasöründe ayrı ayrı bulunur.

'''

inventory = '| İşlem | Dosya |\n|---|---|\n' + '\n'.join(
    '| ' + ('DEĞİŞTİR' if item['action'] == 'replace' else 'EKLE') + ' | `' + item['path'] + '` |'
    for item in manifest)
verification_file = out / 'verification.json'
verification = json.loads(verification_file.read_text(encoding='utf-8')) if verification_file.exists() else {}
summary = f"Editor build: {verification.get('editor_build', 'Bekliyor')}. Unreal automation: {verification.get('automation_result', 'Bekliyor')}. PASS kontrol sayısı: {verification.get('pass_count', 'Bekliyor')}. Engine: UE 5.7.4. Gerçek projenin Source ve Content dosyaları değiştirilmedi. Save/reopen ve gerçek level üzerindeki UI/PIE testleri henüz yapılmadı."
guide = guide.replace('{inventory}', inventory).replace('{verification}', summary)
for item in manifest:
    text = (out / item['path']).read_text(encoding='utf-8')
    assert '//' not in text and '/*' not in text, item['path']
    language = 'csharp' if item['path'].endswith('.cs') else 'cpp'
    guide += f"### {item['path']}\n\n```{language}\n{text}```\n\n"

(out / 'Gun4_Tam_Rehber_ve_Kodlar.md').write_text(guide, encoding='utf-8')
archive = out / 'PlayableSketch_Gun4_Tam_Kod_Paketi.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for item in manifest:
        bundle.write(out / item['path'], item['path'])
    for name in ['Gun4_Tam_Rehber_ve_Kodlar.md', 'manifest.json', 'verification.json']:
        if (out / name).exists():
            bundle.write(out / name, name)
print(f'Packaged {len(manifest)} complete files. Guide size: {len(guide):,} characters.')
