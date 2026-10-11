# PlayableSketch — 4. gün: düzenleme, kayıt ve validation

Bu paket 3. günün sonunda projende bulunan kodlara göre hazırlandı. Implementasyonu sen yapacaksın. Asıl projenin Source dosyaları değiştirilmedi. Aşağıdaki dosyaların her biri tam dosya içeriğidir; bir fonksiyonu başka bir parçadan tamamlaman gerekmiyor. Teslim edilen C++ ve Build.cs kodlarında yorum satırı yok.

## Bugünün hedefi

Room ekleyebilmek, silebilmek, taşıyabilmek ve boyutunu değiştirebilmek; Connection kurabilmek; kapının duvarını ve duvar boyunca konumunu düzenleyebilmek; geçersiz tasarımda kod, ilgili ID ve marker görmek. Kaynak veri kaydedilmeli. Undo/Redo sonrasında önizleme kaynakla aynı hale gelmeli.

Bugün local rebuild eklemiyoruz. Rebuild Geometry (Full) bütün generated meshleri yeniler. Room yerleşimini yeniden aramaz. Local rebuild 5. günün işidir.

## 1. Dosyaları yerleştir

Önce Unreal Editor'ı kapat. Paketteki Source/PlayableSketch yolları projenin aynı yollarına karşılık gelir. DEĞİŞTİR dosyalarında mevcut içeriğin tamamını yeni içerikle değiştir. EKLE dosyalarında klasörü/dosyayı oluşturup tamamını yapıştır. Aynı dosyanın eski ve yeni sürümünü iki ayrı .cpp halinde Source altında bırakma.

Dosyaları şu sırayla uygula: FloorPlan.h → Room.h → Connection.h → GraphAsset.h/.cpp → LayoutGenerator.cpp → DoorGenerator.cpp → Validation.h/.cpp → Day4Tests.h/.cpp → Actor.h/.cpp → Build.cs. Hepsi yerleşmeden build alma.

generated.h dosyaları UnrealHeaderTool tarafından üretilecek. Onları elle oluşturma. Header'larda generated.h son include olarak kalmalı.

### Dosya listesi

| İşlem | Dosya |
|---|---|
| DEĞİŞTİR | `Source/PlayableSketch/Public/Layout/PlayableSketchFloorPlan.h` |
| DEĞİŞTİR | `Source/PlayableSketch/Public/SpatialGraph/PlayableSketchRoom.h` |
| DEĞİŞTİR | `Source/PlayableSketch/Public/SpatialGraph/PlayableSketchConnection.h` |
| DEĞİŞTİR | `Source/PlayableSketch/Public/SpatialGraph/PlayableSketchGraphAsset.h` |
| EKLE | `Source/PlayableSketch/Private/SpatialGraph/PlayableSketchGraphAsset.cpp` |
| DEĞİŞTİR | `Source/PlayableSketch/Private/Layout/PlayableSketchLayoutGenerator.cpp` |
| DEĞİŞTİR | `Source/PlayableSketch/Private/Layout/PlayableSketchDoorGenerator.cpp` |
| DEĞİŞTİR | `Source/PlayableSketch/PlayableSketch.Build.cs` |
| EKLE | `Source/PlayableSketch/Public/Validation/PlayableSketchValidation.h` |
| EKLE | `Source/PlayableSketch/Private/Validation/PlayableSketchValidation.cpp` |
| DEĞİŞTİR | `Source/PlayableSketch/PlayableSketchLevelActor.h` |
| DEĞİŞTİR | `Source/PlayableSketch/PlayableSketchLevelActor.cpp` |
| EKLE | `Source/PlayableSketch/Public/Validation/Tests/PlayableSketchDay4Tests.h` |
| EKLE | `Source/PlayableSketch/Private/Validation/Tests/PlayableSketchDay4Tests.cpp` |

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

Editor build: Succeeded. Unreal automation: Success. PASS kontrol sayısı: 21. Engine: UE 5.7.4. Gerçek projenin Source ve Content dosyaları değiştirilmedi. Save/reopen ve gerçek level üzerindeki UI/PIE testleri henüz yapılmadı.

## 13. Bütün kodlar — dosyaların tam son halleri

Aşağıdaki her blok dosyanın TAM içeriğidir. Dosya yolları projenin köküne göredir. Aynı tam dosyalar paketin Source klasöründe ayrı ayrı bulunur.

### Source/PlayableSketch/Public/Layout/PlayableSketchFloorPlan.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchRect.h"
#include "PlayableSketchFloorPlan.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchWallSide : uint8
{
    North,
    East,
    South,
    West
};

struct PLAYABLESKETCH_API FPlayableSketchPlacedRoom
{
    FGuid RoomId;
    FPlayableSketchRect Bounds;
};

struct PLAYABLESKETCH_API FPlayableSketchDoorEndpoint
{
    FGuid RoomId;
    EPlayableSketchWallSide WallSide = EPlayableSketchWallSide::North;

    FVector2D PositionCm = FVector2D::ZeroVector;
    double WidthCm = 150.0;
};

struct PLAYABLESKETCH_API FPlayableSketchCorridor
{
    FGuid ConnectionId;

    FPlayableSketchDoorEndpoint DoorA;
    FPlayableSketchDoorEndpoint DoorB;

    TArray<FPlayableSketchRect> Footprints;
};

struct PLAYABLESKETCH_API FPlayableSketchFloorPlan
{
    TArray<FPlayableSketchPlacedRoom> Rooms;
    TArray<FPlayableSketchCorridor> Corridors;
};
```

### Source/PlayableSketch/Public/SpatialGraph/PlayableSketchRoom.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "PlayableSketchRoom.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchRoomType : uint8
{
    Generic,
    Hub
};

UENUM(BlueprintType)
enum class EPlayableSketchRoomRole : uint8
{
    None,
    Start,
    Goal
};

UENUM(BlueprintType)
enum class EPlayableSketchPositionMode : uint8
{
    Auto,
    Locked
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchRoom
{
    GENERATED_BODY()

public:
    FPlayableSketchRoom()
        : RoomId(FGuid::NewGuid())
    {
    }
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Identity", meta = (IgnoreForMemberInitializationTest))
    FGuid RoomId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    FString DisplayName = TEXT("Room");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    EPlayableSketchRoomType RoomType = EPlayableSketchRoomType::Generic;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    EPlayableSketchRoomRole RoomRole = EPlayableSketchRoomRole::None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement")
    EPlayableSketchPositionMode PositionMode = EPlayableSketchPositionMode::Auto;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement", meta = (EditCondition = "PositionMode == EPlayableSketchPositionMode::Locked"))
    FVector2D PositionCm = FVector2D::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))
    int32 WidthCm = 600;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))
    int32 DepthCm = 600;
};
```

### Source/PlayableSketch/Public/SpatialGraph/PlayableSketchConnection.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "PlayableSketchConnection.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchDoorOverride
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
    bool bManual = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door", meta = (EditCondition = "bManual"))
    EPlayableSketchWallSide WallSide = EPlayableSketchWallSide::East;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door", meta = (EditCondition = "bManual"))
    double OffsetCm = 300.0;
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchConnection
{
    GENERATED_BODY()

public:
    FPlayableSketchConnection() : ConnectionId(FGuid::NewGuid())
    {
    }

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Identity", meta = (IgnoreForMemberInitializationTest))
    FGuid ConnectionId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomAId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomBId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 CorridorWidthCm = 200;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 DoorWidthCm = 150;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Doors")
    FPlayableSketchDoorOverride DoorASettings;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Doors")
    FPlayableSketchDoorOverride DoorBSettings;
};
```

### Source/PlayableSketch/Public/SpatialGraph/PlayableSketchGraphAsset.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "PlayableSketchGraphAsset.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedPlacement
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FGuid RoomId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FVector2D MinCm = FVector2D::ZeroVector;
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedLayout
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    TArray<FPlayableSketchSavedPlacement> Rooms;
};

UCLASS(BlueprintType)
class PLAYABLESKETCH_API UPlayableSketchGraphAsset : public UDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Graph")
    FPlayableSketchGraph Graph;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FPlayableSketchSavedLayout SavedLayout;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomAId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomBId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid RoomToRemoveId;

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddRoom();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddConnection();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void RemoveRoom();

    FString GetSourceText() const;

#if WITH_EDITOR
    virtual void PreEditChange(FProperty* PropertyAboutToChange) override;
    virtual void PreEditChange(FEditPropertyChain& PropertyAboutToChange) override;
    virtual void PostEditChangeChainProperty(FPropertyChangedChainEvent& PropertyChangedEvent) override;
#endif

private:
    TSet<FGuid> RoomsBeforeEdit;
    void CaptureRoomIds();
    void RemoveDeletedRoomConnections();
    void AssignUniqueIds();
};
```

### Source/PlayableSketch/Private/SpatialGraph/PlayableSketchGraphAsset.cpp

```cpp
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "UObject/UnrealType.h"

#if WITH_EDITOR
#include "ScopedTransaction.h"
#endif

FString UPlayableSketchGraphAsset::GetSourceText() const
{
    FString GraphText;
    FString LayoutText;
    FPlayableSketchGraph::StaticStruct()->ExportText(GraphText, &Graph, nullptr, nullptr, PPF_None, nullptr);
    FPlayableSketchSavedLayout::StaticStruct()->ExportText(LayoutText, &SavedLayout, nullptr, nullptr, PPF_None, nullptr);
    return GraphText + TEXT("|Layout|") + LayoutText;
}

void UPlayableSketchGraphAsset::CaptureRoomIds()
{
    RoomsBeforeEdit.Reset();

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        RoomsBeforeEdit.Add(Room.RoomId);
    }
}

void UPlayableSketchGraphAsset::RemoveDeletedRoomConnections()
{
    TSet<FGuid> CurrentIds;

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        CurrentIds.Add(Room.RoomId);
    }

    TSet<FGuid> DeletedIds;

    for (const FGuid& Id : RoomsBeforeEdit)
    {
        if (!CurrentIds.Contains(Id))
        {
            DeletedIds.Add(Id);
        }
    }

    Graph.Connections.RemoveAll([&](const FPlayableSketchConnection& Connection)
    {
        return DeletedIds.Contains(Connection.RoomAId) || DeletedIds.Contains(Connection.RoomBId);
    });

    SavedLayout.Rooms.RemoveAll([&](const FPlayableSketchSavedPlacement& Placement)
    {
        return DeletedIds.Contains(Placement.RoomId);
    });
}

void UPlayableSketchGraphAsset::AssignUniqueIds()
{
    TSet<FGuid> RoomIds;
    TSet<FGuid> ConnectionIds;

    for (FPlayableSketchRoom& Room : Graph.Rooms)
    {
        while (!Room.RoomId.IsValid() || RoomIds.Contains(Room.RoomId))
        {
            Room.RoomId = FGuid::NewGuid();
        }

        RoomIds.Add(Room.RoomId);
    }

    for (FPlayableSketchConnection& Connection : Graph.Connections)
    {
        while (!Connection.ConnectionId.IsValid() || ConnectionIds.Contains(Connection.ConnectionId))
        {
            Connection.ConnectionId = FGuid::NewGuid();
        }

        ConnectionIds.Add(Connection.ConnectionId);
    }
}

void UPlayableSketchGraphAsset::AddRoom()
{
#if WITH_EDITOR
    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "AddRoom", "Add PlayableSketch Room"));
    Modify();

    FPlayableSketchRoom Room;
    Room.DisplayName = FString::Printf(TEXT("Room_%d"), Graph.Rooms.Num() + 1);
    Graph.Rooms.Add(Room);
    MarkPackageDirty();
#endif
}

void UPlayableSketchGraphAsset::AddConnection()
{
#if WITH_EDITOR
    auto Exists = [&](const FGuid& Id)
    {
        return Graph.Rooms.ContainsByPredicate([&](const FPlayableSketchRoom& Room)
        {
            return Room.RoomId == Id;
        });
    };

    const bool bDuplicate = Graph.Connections.ContainsByPredicate([&](const FPlayableSketchConnection& Connection)
    {
        return (Connection.RoomAId == NewConnectionRoomAId && Connection.RoomBId == NewConnectionRoomBId)
            || (Connection.RoomAId == NewConnectionRoomBId && Connection.RoomBId == NewConnectionRoomAId);
    });

    if (!Exists(NewConnectionRoomAId) || !Exists(NewConnectionRoomBId)
        || NewConnectionRoomAId == NewConnectionRoomBId || bDuplicate)
    {
        UE_LOG(LogTemp, Error, TEXT("PS-I001: Select two existing, different Rooms without an existing Connection."));
        return;
    }

    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "AddConnection", "Add PlayableSketch Connection"));
    Modify();

    FPlayableSketchConnection Connection;
    Connection.RoomAId = NewConnectionRoomAId;
    Connection.RoomBId = NewConnectionRoomBId;
    Graph.Connections.Add(Connection);
    MarkPackageDirty();
#endif
}

void UPlayableSketchGraphAsset::RemoveRoom()
{
#if WITH_EDITOR
    if (!Graph.Rooms.ContainsByPredicate([&](const FPlayableSketchRoom& Room)
        {
            return Room.RoomId == RoomToRemoveId;
        }))
    {
        UE_LOG(LogTemp, Error, TEXT("PS-I001: RoomToRemoveId does not identify an existing Room."));
        return;
    }

    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "RemoveRoom", "Remove PlayableSketch Room"));
    Modify();
    CaptureRoomIds();

    Graph.Rooms.RemoveAll([&](const FPlayableSketchRoom& Room)
    {
        return Room.RoomId == RoomToRemoveId;
    });

    RemoveDeletedRoomConnections();
    MarkPackageDirty();
#endif
}

#if WITH_EDITOR
void UPlayableSketchGraphAsset::PreEditChange(FProperty* PropertyAboutToChange)
{
    CaptureRoomIds();
    Super::PreEditChange(PropertyAboutToChange);
}

void UPlayableSketchGraphAsset::PreEditChange(FEditPropertyChain& PropertyAboutToChange)
{
    CaptureRoomIds();
    Super::PreEditChange(PropertyAboutToChange);
}

void UPlayableSketchGraphAsset::PostEditChangeChainProperty(FPropertyChangedChainEvent& Event)
{
    if ((Event.ChangeType & EPropertyChangeType::Duplicate) != 0)
    {
        const int32 RoomIndex = Event.GetArrayIndex(TEXT("Rooms"));
        const int32 ConnectionIndex = Event.GetArrayIndex(TEXT("Connections"));
        if (Graph.Rooms.IsValidIndex(RoomIndex)) Graph.Rooms[RoomIndex].RoomId = FGuid::NewGuid();
        if (Graph.Connections.IsValidIndex(ConnectionIndex)) Graph.Connections[ConnectionIndex].ConnectionId = FGuid::NewGuid();
    }

    if ((Event.ChangeType & (EPropertyChangeType::ArrayAdd | EPropertyChangeType::Duplicate)) != 0)
    {
        AssignUniqueIds();
    }

    if ((Event.ChangeType & (EPropertyChangeType::ArrayRemove | EPropertyChangeType::ArrayClear)) != 0)
    {
        RemoveDeletedRoomConnections();
    }

    MarkPackageDirty();
    Super::PostEditChangeChainProperty(Event);
}
#endif
```

### Source/PlayableSketch/Private/Layout/PlayableSketchLayoutGenerator.cpp

```cpp
#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchPlacementSearch.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

bool FPlayableSketchLayoutGenerator::Generate(const FPlayableSketchGraph& Graph, int32 GridStepCm, int32 RoomGapCm, FPlayableSketchFloorPlan& OutFloorPlan, FString& OutError, int32 MaxPlacementAttempts)
{
    OutFloorPlan = FPlayableSketchFloorPlan();
    OutError.Reset();

    if (GridStepCm <= 0 || RoomGapCm < 0 || MaxPlacementAttempts <= 0)
    {
        OutError = TEXT("GridStepCm and MaxPlacementAttempts must be positive. RoomGapCm cannot be negative.");
        return false;
    }

    const TArray<FString> ValidationErrors = FPlayableSketchGraphValidator::Validate(Graph);

    if (!ValidationErrors.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Graph validation failed: %s"), *ValidationErrors[0]);
        return false;
    }

    TArray<FGuid> Queue;
    TSet<FGuid> DiscoveredRoomIds;

    Queue.Add(Graph.StartRoomId);
    DiscoveredRoomIds.Add(Graph.StartRoomId);

    for (int32 QueueIndex = 0; QueueIndex < Queue.Num(); ++QueueIndex)
    {
        const FGuid CurrentRoomId = Queue[QueueIndex];

        TArray<FGuid> NeighborIds;

        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (Connection.RoomAId == CurrentRoomId)
            {
                NeighborIds.Add(Connection.RoomBId);
            }
            else if (Connection.RoomBId == CurrentRoomId)
            {
                NeighborIds.Add(Connection.RoomAId);
            }
        }

        NeighborIds.Sort([](const FGuid& A, const FGuid& B)
            {
                return A.ToString() < B.ToString();
            });

        for (const FGuid& NeighborId : NeighborIds)
        {
            if (!DiscoveredRoomIds.Contains(NeighborId))
            {
                DiscoveredRoomIds.Add(NeighborId);
                Queue.Add(NeighborId);
            }
        }
    }

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (!DiscoveredRoomIds.Contains(Room.RoomId))
        {
            OutError = FString::Printf(TEXT("Placement failed: Room %s is not reachable from Start."), *Room.RoomId.ToString());
            return false;
        }
    }

    FPlayableSketchFloorPlan Result;

    TArray<FPlayableSketchPlacedRoom> Occupied;

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (Room.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        FPlayableSketchPlacedRoom LockedRoom;
        LockedRoom.RoomId = Room.RoomId;
        LockedRoom.Bounds = FPlayableSketchRect(Room.PositionCm, Room.PositionCm + FVector2D(Room.WidthCm, Room.DepthCm));

        if (!LockedRoom.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid Locked position: Room %s."), *Room.RoomId.ToString());
            return false;
        }

        for (const FPlayableSketchPlacedRoom& Existing : Occupied)
        {
            if (!LockedRoom.Bounds.HasRequiredGap(Existing.Bounds, RoomGapCm))
            {
                OutError = FString::Printf(TEXT("Locked Rooms overlap or violate RoomGapCm: %s and %s."), *Room.RoomId.ToString(), *Existing.RoomId.ToString());
                return false;
            }
        }

        Occupied.Add(LockedRoom);
    }

    double NextX = 0.0;

    for (const FGuid& RoomId : Queue)
    {
        const FPlayableSketchRoom* SourceRoom = Graph.Rooms.FindByPredicate([&RoomId](const FPlayableSketchRoom& Room)
            {
                return Room.RoomId == RoomId;
            });

        if (!SourceRoom)
        {
            OutError = FString::Printf(TEXT("Placement failed: Room %s was not found."), *RoomId.ToString());
            return false;
        }

        const FVector2D SizeCm(SourceRoom->WidthCm, SourceRoom->DepthCm);
        const FVector2D PreferredMinCm(NextX, 0.0);

        FPlayableSketchPlacedRoom PlacedRoom;

        if (SourceRoom->PositionMode == EPlayableSketchPositionMode::Locked)
        {
            PlacedRoom.RoomId = RoomId;
            PlacedRoom.Bounds = FPlayableSketchRect(SourceRoom->PositionCm, SourceRoom->PositionCm + SizeCm);
        }
        else
        {
            if (!FPlayableSketchPlacementSearch::FindPlacement(RoomId, SizeCm, PreferredMinCm, Occupied, GridStepCm, RoomGapCm, MaxPlacementAttempts, PlacedRoom, OutError))
            {
                return false;
            }

            Occupied.Add(PlacedRoom);
        }

        Result.Rooms.Add(PlacedRoom);

        NextX = PlacedRoom.Bounds.Max.X + RoomGapCm;
    }

    OutFloorPlan = MoveTemp(Result);

    return true;
}
```

### Source/PlayableSketch/Private/Layout/PlayableSketchDoorGenerator.cpp

```cpp
#include "Layout/PlayableSketchDoorGenerator.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

namespace
{
    bool ApplyDoorOverride(
        const FPlayableSketchPlacedRoom& Room,
        const FPlayableSketchDoorOverride& Override,
        int32 CornerMarginCm,
        FPlayableSketchDoorEndpoint& Door,
        FString& OutError)
    {
        if (!Override.bManual)
        {
            return true;
        }

        if (!FPlayableSketchDoorGenerator::CreateEndpoint(Room, Override.WallSide, Door.WidthCm, CornerMarginCm, Door, OutError))
        {
            return false;
        }

        const bool bHorizontal = Override.WallSide == EPlayableSketchWallSide::North || Override.WallSide == EPlayableSketchWallSide::South;
        const double LengthCm = bHorizontal ? Room.Bounds.Max.X - Room.Bounds.Min.X : Room.Bounds.Max.Y - Room.Bounds.Min.Y;

        if (!FMath::IsFinite(Override.OffsetCm)
            || Override.OffsetCm - Door.WidthCm * 0.5 < CornerMarginCm
            || Override.OffsetCm + Door.WidthCm * 0.5 > LengthCm - CornerMarginCm)
        {
            OutError = FString::Printf(TEXT("PS-V002: Manual Door offset does not fit Room %s."), *Room.RoomId.ToString());
            return false;
        }

        if (bHorizontal)
        {
            Door.PositionCm.X = Room.Bounds.Min.X + Override.OffsetCm;
        }
        else
        {
            Door.PositionCm.Y = Room.Bounds.Min.Y + Override.OffsetCm;
        }

        return true;
    }
}


bool FPlayableSketchDoorGenerator::CreateEndpoint(const FPlayableSketchPlacedRoom& Room, EPlayableSketchWallSide WallSide, double DoorWidthCm,
        int32 CornerMarginCm, FPlayableSketchDoorEndpoint& OutDoor, FString& OutError)
{
    OutDoor = FPlayableSketchDoorEndpoint();
    OutError.Reset();

    if (!Room.RoomId.IsValid() || !Room.Bounds.IsValid() || !FMath::IsFinite(DoorWidthCm) || DoorWidthCm <= 0.0 || CornerMarginCm < 0)
    {
        OutError = FString::Printf(TEXT("Invalid Door input for Room %s."), *Room.RoomId.ToString());
        return false;
    }

    const FVector2D SizeCm = Room.Bounds.Max - Room.Bounds.Min;
    const FVector2D CenterCm = Room.Bounds.Min + SizeCm * 0.5;

    double WallLengthCm = 0.0;
    FVector2D PositionCm = FVector2D::ZeroVector;

    switch (WallSide)
    {
    case EPlayableSketchWallSide::North:
        WallLengthCm = SizeCm.X;
        PositionCm = FVector2D(CenterCm.X, Room.Bounds.Max.Y);
        break;

    case EPlayableSketchWallSide::East:
        WallLengthCm = SizeCm.Y;
        PositionCm = FVector2D(Room.Bounds.Max.X, CenterCm.Y);
        break;

    case EPlayableSketchWallSide::South:
        WallLengthCm = SizeCm.X;
        PositionCm = FVector2D(CenterCm.X, Room.Bounds.Min.Y);
        break;

    case EPlayableSketchWallSide::West:
        WallLengthCm = SizeCm.Y;
        PositionCm = FVector2D(Room.Bounds.Min.X, CenterCm.Y);
        break;

    default:
        OutError = TEXT("Invalid Door wall side.");
        return false;
    }

    const double RequiredLengthCm = DoorWidthCm + 2.0 * static_cast<double>(CornerMarginCm);

    if (RequiredLengthCm > WallLengthCm)
    {
        OutError = FString::Printf(TEXT("Door does not fit: Room %s, wall length=%.0f, Door width=%.0f, corner margin=%d."), *Room.RoomId.ToString(), WallLengthCm, DoorWidthCm, CornerMarginCm);
        return false;
    }

    OutDoor.RoomId = Room.RoomId;
    OutDoor.WallSide = WallSide;
    OutDoor.PositionCm = PositionCm;
    OutDoor.WidthCm = DoorWidthCm;

    return true;
}

bool FPlayableSketchDoorGenerator::Generate(const FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& FloorPlan, int32 CornerMarginCm, FString& OutError)
{
    FloorPlan.Corridors.Reset();
    OutError.Reset();

    if (CornerMarginCm < 0)
    {
        OutError = TEXT("CornerMarginCm cannot be negative.");
        return false;
    }

    const TArray<FString> ValidationErrors = FPlayableSketchGraphValidator::Validate(Graph);

    if (!ValidationErrors.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Graph validation failed: %s"), *ValidationErrors[0]);
        return false;
    }

    TArray<int32> ConnectionOrder;

    for (int32 Index = 0; Index < Graph.Connections.Num(); ++Index)
    {
        ConnectionOrder.Add(Index);
    }

    ConnectionOrder.Sort([&Graph](int32 A, int32 B)
        {
            return Graph.Connections[A].ConnectionId.ToString() < Graph.Connections[B].ConnectionId.ToString();
        });

    TArray<FPlayableSketchCorridor> Result;

    for (int32 ConnectionIndex : ConnectionOrder)
    {
        const FPlayableSketchConnection& Connection = Graph.Connections[ConnectionIndex];

        const FPlayableSketchPlacedRoom* RoomA = FloorPlan.Rooms.FindByPredicate([&Connection](const FPlayableSketchPlacedRoom& Room)
            {
                return Room.RoomId == Connection.RoomAId;
            });

        const FPlayableSketchPlacedRoom* RoomB = FloorPlan.Rooms.FindByPredicate([&Connection](const FPlayableSketchPlacedRoom& Room)
            {
                return Room.RoomId == Connection.RoomBId;
            });

        if (!RoomA || !RoomB)
        {
            OutError = FString::Printf(TEXT("Door generation failed: missing placed Room for Connection %s."), *Connection.ConnectionId.ToString());
            return false;
        }

        if (!RoomA->Bounds.IsValid() || !RoomB->Bounds.IsValid() || RoomA->Bounds.OverlapsInterior(RoomB->Bounds))
        {
            OutError = FString::Printf(TEXT("Door generation failed: invalid or overlapping Rooms for Connection %s."), *Connection.ConnectionId.ToString());
            return false;
        }

        const FVector2D CenterA = RoomA->Bounds.Min + (RoomA->Bounds.Max - RoomA->Bounds.Min) * 0.5;
        const FVector2D CenterB = RoomB->Bounds.Min + (RoomB->Bounds.Max - RoomB->Bounds.Min) * 0.5;
        const FVector2D Direction = CenterB - CenterA;

        EPlayableSketchWallSide SideA;
        EPlayableSketchWallSide SideB;

        if (FMath::Abs(Direction.X) >= FMath::Abs(Direction.Y))
        {
            SideA = Direction.X >= 0.0 ? EPlayableSketchWallSide::East : EPlayableSketchWallSide::West;
            SideB = Direction.X >= 0.0 ? EPlayableSketchWallSide::West : EPlayableSketchWallSide::East;
        }
        else
        {
            SideA = Direction.Y >= 0.0 ? EPlayableSketchWallSide::North : EPlayableSketchWallSide::South;
            SideB = Direction.Y >= 0.0 ? EPlayableSketchWallSide::South : EPlayableSketchWallSide::North;
        }

        FPlayableSketchCorridor Corridor;
        Corridor.ConnectionId = Connection.ConnectionId;

        if (!CreateEndpoint(*RoomA, Connection.DoorASettings.bManual ? Connection.DoorASettings.WallSide : SideA, Connection.DoorWidthCm, CornerMarginCm, Corridor.DoorA, OutError))
        {
            OutError = FString::Printf(TEXT("Connection %s: %s"), *Connection.ConnectionId.ToString(), *OutError);
            return false;
        }

        if (!CreateEndpoint(*RoomB, Connection.DoorBSettings.bManual ? Connection.DoorBSettings.WallSide : SideB, Connection.DoorWidthCm, CornerMarginCm, Corridor.DoorB, OutError))
        {
            OutError = FString::Printf(TEXT("Connection %s: %s"), *Connection.ConnectionId.ToString(), *OutError);
            return false;
        }

        if (!ApplyDoorOverride(*RoomA, Connection.DoorASettings, CornerMarginCm, Corridor.DoorA, OutError)
            || !ApplyDoorOverride(*RoomB, Connection.DoorBSettings, CornerMarginCm, Corridor.DoorB, OutError))
        {
            return false;
        }

        for (const FPlayableSketchCorridor& Existing : Result)
        {
            const bool bDoorAOverlap = OpeningsOverlap(Corridor.DoorA, Existing.DoorA) || OpeningsOverlap(Corridor.DoorA, Existing.DoorB);
            const bool bDoorBOverlap = OpeningsOverlap(Corridor.DoorB, Existing.DoorA) || OpeningsOverlap(Corridor.DoorB, Existing.DoorB);

            if (bDoorAOverlap || bDoorBOverlap)
            {
                OutError = FString::Printf(TEXT("Door overlap: Connections %s and %s."), *Corridor.ConnectionId.ToString(), *Existing.ConnectionId.ToString());
                return false;
            }
        }

        Result.Add(Corridor);
    }

    FloorPlan.Corridors = MoveTemp(Result);

    return true;
}

bool FPlayableSketchDoorGenerator::OpeningsOverlap(const FPlayableSketchDoorEndpoint& A, const FPlayableSketchDoorEndpoint& B)
{
    if (A.RoomId != B.RoomId || A.WallSide != B.WallSide)
    {
        return false;
    }

    const bool bHorizontalWall = A.WallSide == EPlayableSketchWallSide::North || A.WallSide == EPlayableSketchWallSide::South;

    const double CenterA = bHorizontalWall ? A.PositionCm.X : A.PositionCm.Y;
    const double CenterB = bHorizontalWall ? B.PositionCm.X : B.PositionCm.Y;

    return FMath::Abs(CenterA - CenterB) < (A.WidthCm + B.WidthCm) * 0.5;
}
```

### Source/PlayableSketch/PlayableSketch.Build.cs

```csharp
using UnrealBuildTool;

public class PlayableSketch : ModuleRules
{
    public PlayableSketch(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore" });

        if (Target.bBuildEditor)
        {
            PrivateDependencyModuleNames.Add("UnrealEd");
        }
    }
}
```

### Source/PlayableSketch/Public/Validation/PlayableSketchValidation.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Geometry/PlayableSketchWallGeometry.h"
#include "PlayableSketchValidation.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchIssueSeverity : uint8
{
    Info,
    Warning,
    Error
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchValidationIssue
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FName Code;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    TArray<FGuid> ElementIds;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    EPlayableSketchIssueSeverity Severity = EPlayableSketchIssueSeverity::Error;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FString Message;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    bool bHasPosition = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector PositionCm = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector ExtentCm = FVector(25.0, 25.0, 25.0);
};

struct PLAYABLESKETCH_API FPlayableSketchValidationSettings
{
    FPlayableSketchWallSettings Walls;
    int32 GridStepCm = 50;
    double MinCorridorWidthCm = 100.0;
    double PawnRadiusCm = 40.0;
    double PawnHeightCm = 180.0;
    double ClearanceCm = 10.0;

    double RequiredWidthCm() const
    {
        return FMath::Max(MinCorridorWidthCm, 2.0 * (PawnRadiusCm + ClearanceCm));
    }
};

class PLAYABLESKETCH_API FPlayableSketchValidation
{
public:
    static bool HasErrors(const TArray<FPlayableSketchValidationIssue>& Issues);

    static TArray<FPlayableSketchValidationIssue> ValidateInput(
        const FPlayableSketchGraph& Graph,
        const FPlayableSketchValidationSettings& Settings);

    static TArray<FPlayableSketchValidationIssue> ValidatePlan(
        const FPlayableSketchGraph& Graph,
        const FPlayableSketchFloorPlan& Plan,
        const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
        const FPlayableSketchValidationSettings& Settings);
};
```

### Source/PlayableSketch/Private/Validation/PlayableSketchValidation.cpp

```cpp
#include "Validation/PlayableSketchValidation.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

namespace
{
    const double ToleranceCm = 0.01;

    void AddIssue(
        TArray<FPlayableSketchValidationIssue>& Issues,
        const TCHAR* Code,
        const FString& Message,
        const TArray<FGuid>& Ids,
        const FVector& Position,
        const FVector& Extent = FVector(25.0, 25.0, 25.0))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = FName(Code);
        Issue.Message = Message;
        Issue.ElementIds = Ids;
        Issue.bHasPosition = !Position.ContainsNaN();
        Issue.PositionCm = Issue.bHasPosition ? Position : FVector::ZeroVector;
        Issue.ExtentCm = Extent;
        Issues.Add(Issue);
    }

    FVector RoomCenter(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Center = (Room.Bounds.Min + Room.Bounds.Max) * 0.5;
        return FVector(Center.X, Center.Y, 25.0);
    }

    FVector RoomExtent(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Half = (Room.Bounds.Max - Room.Bounds.Min) * 0.5;
        return FVector(Half.X, Half.Y, 25.0);
    }

    bool GetWallFrame(
        const FPlayableSketchPlacedRoom& Room,
        EPlayableSketchWallSide Side,
        FVector2D& Origin,
        FVector2D& Tangent,
        FVector2D& Normal,
        double& Length)
    {
        const FVector2D Size = Room.Bounds.Max - Room.Bounds.Min;

        switch (Side)
        {
        case EPlayableSketchWallSide::North:
            Origin = FVector2D(Room.Bounds.Min.X, Room.Bounds.Max.Y);
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, 1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::South:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, -1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::East:
            Origin = FVector2D(Room.Bounds.Max.X, Room.Bounds.Min.Y);
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(1.0, 0.0);
            Length = Size.Y;
            return true;

        case EPlayableSketchWallSide::West:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(-1.0, 0.0);
            Length = Size.Y;
            return true;
        }

        return false;
    }

    bool FootprintsConnected(const TArray<FPlayableSketchRect>& Rects)
    {
        if (Rects.IsEmpty())
        {
            return false;
        }

        TSet<int32> Visited;
        TArray<int32> Queue;
        Queue.Add(0);
        Visited.Add(0);

        for (int32 Head = 0; Head < Queue.Num(); ++Head)
        {
            const FPlayableSketchRect& A = Rects[Queue[Head]];

            for (int32 Index = 0; Index < Rects.Num(); ++Index)
            {
                if (Visited.Contains(Index))
                {
                    continue;
                }

                const FPlayableSketchRect& B = Rects[Index];
                const double OverlapX = FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X);
                const double OverlapY = FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y);
                const bool bConnected = (OverlapX > ToleranceCm && OverlapY >= -ToleranceCm)
                    || (OverlapY > ToleranceCm && OverlapX >= -ToleranceCm);

                if (bConnected)
                {
                    Visited.Add(Index);
                    Queue.Add(Index);
                }
            }
        }

        return Visited.Num() == Rects.Num();
    }

    bool CoversDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FVector2D& Origin,
        const FVector2D& Tangent,
        const FVector2D& Normal,
        const TArray<FPlayableSketchRect>& Rects)
    {
        const double Center = FVector2D::DotProduct(Door.PositionCm - Origin, Tangent);
        const double Start = Center - Door.WidthCm * 0.5;
        const double End = Center + Door.WidthCm * 0.5;
        TArray<FVector2D> Intervals;

        for (const FPlayableSketchRect& Rect : Rects)
        {
            bool bContact = false;

            if (Normal.X > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.X, Origin.X, ToleranceCm);
            }
            else if (Normal.X < 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.X, Origin.X, ToleranceCm);
            }
            else if (Normal.Y > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.Y, Origin.Y, ToleranceCm);
            }
            else
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.Y, Origin.Y, ToleranceCm);
            }

            if (bContact)
            {
                const double Min = FVector2D::DotProduct(Rect.Min - Origin, Tangent);
                const double Max = FVector2D::DotProduct(Rect.Max - Origin, Tangent);
                Intervals.Add(FVector2D(Min, Max));
            }
        }

        Intervals.Sort([](const FVector2D& A, const FVector2D& B)
        {
            return A.X < B.X;
        });

        double Cursor = Start;

        for (const FVector2D& Interval : Intervals)
        {
            if (Interval.Y < Cursor - ToleranceCm)
            {
                continue;
            }

            if (Interval.X > Cursor + ToleranceCm)
            {
                return false;
            }

            Cursor = FMath::Max(Cursor, Interval.Y);

            if (Cursor >= End - ToleranceCm)
            {
                return true;
            }
        }

        return false;
    }

    bool BoxesOverlap(const FBox& A, const FBox& B)
    {
        return FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X) > ToleranceCm
            && FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y) > ToleranceCm
            && FMath::Min(A.Max.Z, B.Max.Z) - FMath::Max(A.Min.Z, B.Min.Z) > ToleranceCm;
    }

    bool CheckDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FGuid& ExpectedRoomId,
        const FPlayableSketchConnection& Connection,
        const FPlayableSketchFloorPlan& Plan,
        const TArray<FPlayableSketchRect>& Rects,
        const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
        const FPlayableSketchValidationSettings& Settings,
        TArray<FPlayableSketchValidationIssue>& Issues)
    {
        const FVector Position(Door.PositionCm.X, Door.PositionCm.Y, 40.0);
        const TArray<FGuid> Ids = { Connection.ConnectionId, ExpectedRoomId };
        const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item)
        {
            return Item.RoomId == ExpectedRoomId;
        });

        FVector2D Origin;
        FVector2D Tangent;
        FVector2D Normal;
        double Length = 0.0;

        if (!Room || Door.RoomId != ExpectedRoomId
            || !Room->Bounds.IsValid()
            || !FMath::IsFinite(Door.PositionCm.X) || !FMath::IsFinite(Door.PositionCm.Y)
            || !FMath::IsFinite(Door.WidthCm) || Door.WidthCm <= 0.0
            || !GetWallFrame(*Room, Door.WallSide, Origin, Tangent, Normal, Length))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door ownership, side or coordinates are invalid."), Ids, Position);
            return false;
        }

        const FVector2D Delta = Door.PositionCm - Origin;
        const double Offset = FVector2D::DotProduct(Delta, Tangent);

        if (!FMath::IsNearlyZero(FVector2D::DotProduct(Delta, Normal), ToleranceCm)
            || Offset - Door.WidthCm * 0.5 < Settings.Walls.CornerMarginCm
            || Offset + Door.WidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm
            || !FMath::IsNearlyEqual(Door.WidthCm, static_cast<double>(Connection.DoorWidthCm), ToleranceCm))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door must lie on its wall, respect corner margin and match DoorWidthCm."), Ids, Position);
            return false;
        }

        if (Door.WidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door is too narrow for the configured Pawn and clearance."), Ids, Position);
            return false;
        }

        if (!CoversDoor(Door, Origin, Tangent, Normal, Rects))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor does not cover the full Door opening."), Ids, Position);
            return false;
        }

        const FVector2D Center2D = Door.PositionCm + Normal * (Settings.Walls.ThicknessCm * 0.5);
        const FVector OpeningCenter(Center2D.X, Center2D.Y, Settings.Walls.DoorHeightCm * 0.5);
        const FVector OpeningSize = Tangent.X != 0.0
            ? FVector(Door.WidthCm, Settings.Walls.ThicknessCm, Settings.Walls.DoorHeightCm)
            : FVector(Settings.Walls.ThicknessCm, Door.WidthCm, Settings.Walls.DoorHeightCm);
        const FBox OpeningBox(OpeningCenter - OpeningSize * 0.5, OpeningCenter + OpeningSize * 0.5);

        bool bBlocked = false;
        bool bHasLintel = Settings.Walls.DoorHeightCm == Settings.Walls.HeightCm;

        for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
        {
            if (Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN())
            {
                continue;
            }

            const FBox Box(Piece.CenterCm - Piece.SizeCm * 0.5, Piece.CenterCm + Piece.SizeCm * 0.5);

            if (BoxesOverlap(OpeningBox, Box))
            {
                bBlocked = true;
                AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated wall or lintel blocks the Door opening."), { Connection.ConnectionId, ExpectedRoomId, Piece.SourceId }, Position);
            }

            if (Piece.bRoom && Piece.SourceId == ExpectedRoomId && Piece.Role == EPlayableSketchGeometryRole::Lintel
                && Box.Min.X <= OpeningBox.Min.X + ToleranceCm && Box.Max.X >= OpeningBox.Max.X - ToleranceCm
                && Box.Min.Y <= OpeningBox.Min.Y + ToleranceCm && Box.Max.Y >= OpeningBox.Max.Y - ToleranceCm
                && FMath::IsNearlyEqual(Box.Min.Z, Settings.Walls.DoorHeightCm, ToleranceCm)
                && FMath::IsNearlyEqual(Box.Max.Z, Settings.Walls.HeightCm, ToleranceCm))
            {
                bHasLintel = true;
            }
        }

        if (!bHasLintel)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Expected Door lintel is missing or has incorrect dimensions."), Ids, Position);
        }

        return !bBlocked && bHasLintel;
    }
}

bool FPlayableSketchValidation::HasErrors(const TArray<FPlayableSketchValidationIssue>& Issues)
{
    return Issues.ContainsByPredicate([](const FPlayableSketchValidationIssue& Issue)
    {
        return Issue.Severity == EPlayableSketchIssueSeverity::Error;
    });
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidateInput(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues;

    for (const FString& Error : FPlayableSketchGraphValidator::Validate(Graph))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = Error;
        for (const FPlayableSketchRoom& Room : Graph.Rooms)
        {
            if (Error.Contains(Room.RoomId.ToString()))
            {
                Issue.ElementIds.AddUnique(Room.RoomId);
            }
        }
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (Error.Contains(Connection.ConnectionId.ToString()))
            {
                Issue.ElementIds.AddUnique(Connection.ConnectionId);
            }
        }
        if (Error.StartsWith(TEXT("Invalid Start")))
        {
            Issue.ElementIds.AddUnique(Graph.StartRoomId);
        }
        if (Error.StartsWith(TEXT("Invalid Goal")))
        {
            Issue.ElementIds.AddUnique(Graph.GoalRoomId);
        }
        Issues.Add(Issue);
    }

    const bool bSettingsValid = Settings.GridStepCm > 0
        && FMath::IsFinite(Settings.MinCorridorWidthCm) && Settings.MinCorridorWidthCm > 0.0
        && FMath::IsFinite(Settings.PawnRadiusCm) && Settings.PawnRadiusCm > 0.0
        && FMath::IsFinite(Settings.PawnHeightCm) && Settings.PawnHeightCm > 0.0
        && FMath::IsFinite(Settings.ClearanceCm) && Settings.ClearanceCm >= 0.0
        && FMath::IsFinite(Settings.Walls.HeightCm) && Settings.Walls.HeightCm > 0.0
        && FMath::IsFinite(Settings.Walls.ThicknessCm) && Settings.Walls.ThicknessCm > 0.0
        && FMath::IsFinite(Settings.Walls.DoorHeightCm) && Settings.Walls.DoorHeightCm > 0.0
        && Settings.Walls.DoorHeightCm <= Settings.Walls.HeightCm
        && FMath::IsFinite(Settings.Walls.CornerMarginCm) && Settings.Walls.CornerMarginCm >= 0.0;

    if (!bSettingsValid)
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = TEXT("Invalid validation or wall settings.");
        Issues.Add(Issue);
        return Issues;
    }

    if (Settings.Walls.DoorHeightCm < Settings.PawnHeightCm + Settings.ClearanceCm)
    {
        AddIssue(Issues, TEXT("PS-V002"), TEXT("Door height is too low for the configured Pawn and clearance."), {}, FVector::ZeroVector);
    }

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        if (Connection.CorridorWidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V003"), FString::Printf(TEXT("Corridor width %d cm is below required %.1f cm."), Connection.CorridorWidthCm, Settings.RequiredWidthCm()), { Connection.ConnectionId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        if (Connection.DoorWidthCm < Settings.RequiredWidthCm() || Connection.DoorWidthCm > Connection.CorridorWidthCm)
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door width must fit the Corridor and the configured Pawn."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        const FPlayableSketchDoorOverride* Overrides[] = { &Connection.DoorASettings, &Connection.DoorBSettings };
        const FGuid RoomIds[] = { Connection.RoomAId, Connection.RoomBId };

        for (int32 Index = 0; Index < 2; ++Index)
        {
            if (!Overrides[Index]->bManual)
            {
                continue;
            }

            const FPlayableSketchRoom* Room = Graph.Rooms.FindByPredicate([&](const FPlayableSketchRoom& Item)
            {
                return Item.RoomId == RoomIds[Index];
            });

            const EPlayableSketchWallSide Side = Overrides[Index]->WallSide;
            const bool bValidSide = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South
                || Side == EPlayableSketchWallSide::East || Side == EPlayableSketchWallSide::West;
            const bool bHorizontal = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South;
            double Length = Room ? (bHorizontal ? Room->WidthCm : Room->DepthCm) : 0.0;
            if (Room && Room->PositionMode == EPlayableSketchPositionMode::Auto)
            {
                Length = FMath::CeilToDouble(Length / Settings.GridStepCm) * Settings.GridStepCm;
            }
            const double Offset = Overrides[Index]->OffsetCm;

            if (!Room || !bValidSide || !FMath::IsFinite(Offset)
                || Offset - Connection.DoorWidthCm * 0.5 < Settings.Walls.CornerMarginCm
                || Offset + Connection.DoorWidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm)
            {
                AddIssue(Issues, TEXT("PS-V002"), TEXT("Manual Door side or offset is invalid."), { Connection.ConnectionId, RoomIds[Index] }, FVector::ZeroVector);
                Issues.Last().bHasPosition = false;
            }
        }
    }

    for (int32 A = 0; A < Graph.Rooms.Num(); ++A)
    {
        const FPlayableSketchRoom& RoomA = Graph.Rooms[A];

        if (RoomA.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        const FPlayableSketchRect BoundsA(RoomA.PositionCm, RoomA.PositionCm + FVector2D(RoomA.WidthCm, RoomA.DepthCm));

        if (!BoundsA.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Locked Room coordinates are invalid."), { RoomA.RoomId }, FVector::ZeroVector);
            continue;
        }

        for (int32 B = A + 1; B < Graph.Rooms.Num(); ++B)
        {
            const FPlayableSketchRoom& RoomB = Graph.Rooms[B];
            const FPlayableSketchRect BoundsB(RoomB.PositionCm, RoomB.PositionCm + FVector2D(RoomB.WidthCm, RoomB.DepthCm));

            if (RoomB.PositionMode == EPlayableSketchPositionMode::Locked && BoundsA.OverlapsInterior(BoundsB))
            {
                const FVector2D Center = (BoundsA.Min + BoundsA.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Locked Rooms overlap."), { RoomA.RoomId, RoomB.RoomId }, FVector(Center.X, Center.Y, 25.0), FVector(RoomA.WidthCm * 0.5, RoomA.DepthCm * 0.5, 25.0));
            }
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Queue.Add(Graph.StartRoomId);
    Reachable.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room is disconnected from Start in the Graph."), { Room.RoomId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }
    }

    return Issues;
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidatePlan(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues = ValidateInput(Graph, Settings);

    for (int32 A = 0; A < Plan.Rooms.Num(); ++A)
    {
        const FPlayableSketchPlacedRoom& Room = Plan.Rooms[A];
        if (!Room.Bounds.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Invalid placed Room bounds."), { Room.RoomId }, FVector::ZeroVector);
            return Issues;
        }
        for (int32 B = A + 1; B < Plan.Rooms.Num(); ++B)
        {
            if (Room.Bounds.OverlapsInterior(Plan.Rooms[B].Bounds))
            {
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Placed Rooms overlap."), { Room.RoomId, Plan.Rooms[B].RoomId }, RoomCenter(Room), RoomExtent(Room));
            }
        }
    }

    TSet<FGuid> ValidConnections;

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item)
        {
            return Item.ConnectionId == Connection.ConnectionId;
        });

        if (!Corridor)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Connection has no routed Corridor."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
            continue;
        }

        bool bValidRects = !Corridor->Footprints.IsEmpty();
        for (const FPlayableSketchRect& Rect : Corridor->Footprints)
        {
            bValidRects &= Rect.IsValid();
            if (Rect.IsValid()
                && (!FMath::IsNearlyEqual(Rect.Max.X - Rect.Min.X, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)
                    && !FMath::IsNearlyEqual(Rect.Max.Y - Rect.Min.Y, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)))
            {
                const FVector2D Center = (Rect.Min + Rect.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V003"), TEXT("Corridor footprint width does not match its declared CorridorWidthCm."), { Connection.ConnectionId }, FVector(Center.X, Center.Y, 25.0));
            }
        }

        const FVector Position(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
        const bool bConnected = bValidRects && FootprintsConnected(Corridor->Footprints);

        if (!bConnected)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor footprints are invalid or physically disconnected."), { Connection.ConnectionId }, Position);
        }

        const bool bDoorAValid = CheckDoor(Corridor->DoorA, Connection.RoomAId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);
        const bool bDoorBValid = CheckDoor(Corridor->DoorB, Connection.RoomBId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);

        if (bConnected && bDoorAValid && bDoorBValid && Connection.CorridorWidthCm >= Settings.RequiredWidthCm())
        {
            ValidConnections.Add(Connection.ConnectionId);
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Reachable.Add(Graph.StartRoomId);
    Queue.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (!ValidConnections.Contains(Connection.ConnectionId)) continue;
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room has no validated physical route from Start."), { Room.RoomId }, RoomCenter(Room), RoomExtent(Room));
        }
    }

    for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
    {
        if (!Piece.SourceId.IsValid() || Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN()
            || Piece.SizeCm.X <= 0.0 || Piece.SizeCm.Y <= 0.0 || Piece.SizeCm.Z <= 0.0)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated geometry descriptor is invalid."), { Piece.SourceId }, FVector::ZeroVector);
            continue;
        }

        if (Piece.CenterCm.Z - Piece.SizeCm.Z * 0.5 >= Settings.PawnHeightCm)
        {
            continue;
        }

        const FPlayableSketchRect WallRect(
            FVector2D(Piece.CenterCm.X - Piece.SizeCm.X * 0.5, Piece.CenterCm.Y - Piece.SizeCm.Y * 0.5),
            FVector2D(Piece.CenterCm.X + Piece.SizeCm.X * 0.5, Piece.CenterCm.Y + Piece.SizeCm.Y * 0.5));

        for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
        {
            if (WallRect.OverlapsInterior(Room.Bounds))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Room interior."), { Piece.SourceId, Room.RoomId }, Piece.CenterCm);
            }
        }

        for (const FPlayableSketchCorridor& Corridor : Plan.Corridors)
        {
            if (Piece.bRoom && (Corridor.DoorA.RoomId == Piece.SourceId || Corridor.DoorB.RoomId == Piece.SourceId))
            {
                continue;
            }

            if (Corridor.Footprints.ContainsByPredicate([&](const FPlayableSketchRect& Rect)
                {
                    return WallRect.OverlapsInterior(Rect);
                }))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Corridor interior."), { Piece.SourceId, Corridor.ConnectionId }, Piece.CenterCm);
            }
        }
    }

    for (FPlayableSketchValidationIssue& Issue : Issues)
    {
        if (Issue.bHasPosition) continue;
        for (const FGuid& Id : Issue.ElementIds)
        {
            const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item) { return Item.RoomId == Id; });
            if (Room)
            {
                Issue.PositionCm = RoomCenter(*Room);
                Issue.ExtentCm = RoomExtent(*Room);
                Issue.bHasPosition = true;
                break;
            }
            const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item) { return Item.ConnectionId == Id; });
            if (Corridor)
            {
                Issue.PositionCm = FVector(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
                Issue.bHasPosition = true;
                break;
            }
        }
    }

    return Issues;
}
```

### Source/PlayableSketch/PlayableSketchLevelActor.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "Validation/PlayableSketchValidation.h"
#include "PlayableSketchLevelActor.generated.h"

class UMaterialInterface;

UCLASS()
class PLAYABLESKETCH_API APlayableSketchLevelActor : public AActor
{
    GENERATED_BODY()

public:
    APlayableSketchLevelActor();

    UPROPERTY()
    TArray<FPlayableSketchRoom> Rooms;

    UPROPERTY()
    TArray<FPlayableSketchConnection> Connections;

    UPROPERTY()
    FPlayableSketchGraph Graph;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
    TObjectPtr<UPlayableSketchGraphAsset> GraphAsset = nullptr;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateGraph();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestLayoutRect();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestFloorPlan();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestRoomPlacement();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestPlacementSearch();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestDoors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestCorridorCandidates();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestCorridorRouting();
    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1"))
    int32 GridStepCm = 50;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "0"))
    int32 RoomGapCm = 400;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "0"))
    int32 DoorCornerMarginCm = 50;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1"))
    int32 MaxPlacementAttempts = 128;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1.0"))
    float FloorThicknessCm = 20.0f;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Generation")
    void GenerateFloors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Generation")
    void ClearFloors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestFloorPath();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float WallHeightCm = 300.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float WallThicknessCm = 20.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float DoorHeightCm = 220.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry")
    bool bGenerateOnBeginPlay = true;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> WallMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> DefaultFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> HubFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> StartFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> GoalFloorMaterial = nullptr;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestWallSegments();



    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void GenerateLayout();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring", meta = (DisplayName = "Rebuild Geometry (Full)"))
    void RebuildGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateCurrentDesign();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestDay4Validation();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Authoring")
    bool bAutoRebuildGeometry = true;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float MinCorridorWidthCm = 100.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnRadiusCm = 40.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnHeightCm = 180.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "0.0"))
    float ClearanceCm = 10.0f;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    FString PreviewStatus = TEXT("Generate Layout to create the first saved placement.");

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    bool bPreviewStale = false;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Validation")
    TArray<FPlayableSketchValidationIssue> LastIssues;

    virtual void OnConstruction(const FTransform& Transform) override;

#if WITH_EDITOR
    virtual void PostEditUndo() override;
#endif

protected:
    virtual void BeginPlay() override;

public:
    virtual void Tick(float DeltaTime) override;

    TArray<FVector2D> PreviewPathPoints;

    void ApplyFloorMaterials();
    void DrawFloorPathPreview();

    #if WITH_EDITOR
        virtual bool ShouldTickIfViewportsOnly() const override;
    #endif

private:

    FPlayableSketchFloorPlan GeneratedFloorPlan;
    FString LastAttemptSignature;
    FString PublishedSignature;

    FString GetSourceSignature() const;
    FPlayableSketchValidationSettings GetValidationSettings() const;
    bool ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const;
    bool BuildCandidate(FPlayableSketchFloorPlan& Plan, TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void InvalidatePreview(const TArray<FPlayableSketchValidationIssue>& Issues, const FString& Status);
    void FailStage(const TCHAR* Code, const FString& Message);
    void AnnotateIssues();
    void LogIssues() const;
    void DrawValidationIssues();
};
```

### Source/PlayableSketch/PlayableSketchLevelActor.cpp

```cpp
#include "PlayableSketchLevelActor.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"
#include "Validation/Tests/PlayableSketchRectTests.h"
#include "Validation/Tests/PlayableSketchFloorPlanTests.h"
#include "Validation/Tests/PlayableSketchRoomPlacementTests.h"
#include "Validation/Tests/PlayableSketchPlacementSearchTests.h"
#include "Validation/Tests/PlayableSketchDoorTests.h"
#include "Validation/Tests/PlayableSketchCorridorCandidateTests.h"
#include "Validation/Tests/PlayableSketchCorridorRoutingTests.h"
#include "Components/SceneComponent.h"
#include "Geometry/PlayableSketchFloorBuilder.h"
#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchCorridorRouting.h"
#include "Validation/Tests/PlayableSketchGridNavigationTests.h"
#include "DrawDebugHelpers.h"
#include "Geometry/PlayableSketchWallGeometry.h"
#include "Geometry/PlayableSketchWallBuilder.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Validation/Tests/PlayableSketchDay4Tests.h"

#if WITH_EDITOR
#include "ScopedTransaction.h"
#endif

APlayableSketchLevelActor::APlayableSketchLevelActor()
{
    PrimaryActorTick.bCanEverTick = true;

    USceneComponent* SketchRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SketchRoot"));
    SketchRoot->SetMobility(EComponentMobility::Movable);

    SetRootComponent(SketchRoot);
}

void APlayableSketchLevelActor::BeginPlay()
{
    Super::BeginPlay();

    if (bGenerateOnBeginPlay)
    {
        RebuildGeometry();
    }
}

void APlayableSketchLevelActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

#if WITH_EDITOR
    if (GetWorld() && !GetWorld()->IsGameWorld())
    {
        const FString Signature = GetSourceSignature();

        if (Signature != LastAttemptSignature)
        {
            PreviewPathPoints.Reset();
            bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty();
            PreviewStatus = TEXT("Source changed. Preview needs Rebuild Geometry.");
            LastAttemptSignature = Signature;

            if (bAutoRebuildGeometry)
            {
                RebuildGeometry();
            }
        }
    }
#endif

    DrawFloorPathPreview();
    DrawValidationIssues();
}

void APlayableSketchLevelActor::ValidateGraph()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    const TArray<FString> Errors = FPlayableSketchGraphValidator::Validate(GraphAsset->Graph);

    if (Errors.IsEmpty())
    {
        UE_LOG(LogTemp, Display, TEXT("Graph validation passed."));
        return;
    }

    UE_LOG(LogTemp, Error, TEXT("Graph validation failed: %d error(s)."), Errors.Num());

    for (const FString& Error : Errors)
    {
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
    }
}

void APlayableSketchLevelActor::TestLayoutRect()
{
    FPlayableSketchRectTests::Run();
}

void APlayableSketchLevelActor::TestFloorPlan()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchFloorPlanTests::Run(GraphAsset->Graph);
}

void APlayableSketchLevelActor::TestRoomPlacement()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchRoomPlacementTests::Run(GraphAsset->Graph);
}

void APlayableSketchLevelActor::TestPlacementSearch()
{
    FPlayableSketchPlacementSearchTests::Run();
}

void APlayableSketchLevelActor::TestDoors()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchDoorTests::Run(GraphAsset->Graph);
}

void APlayableSketchLevelActor::TestCorridorCandidates()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchCorridorCandidateTests::Run(GraphAsset->Graph);
}

void APlayableSketchLevelActor::TestCorridorRouting()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchCorridorRoutingTests::Run(GraphAsset->Graph);
}

void APlayableSketchLevelActor::GenerateFloors()
{
    if (GetWorld() && GetWorld()->IsGameWorld())
    {
        RebuildGeometry();
    }
    else
    {
        GenerateLayout();
    }
}

void APlayableSketchLevelActor::ClearFloors()
{
    FPlayableSketchWallBuilder::Clear(*this);
    FPlayableSketchFloorBuilder::Clear(*this);
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    LastIssues.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");
}

void APlayableSketchLevelActor::TestFloorPath()
{
    PreviewPathPoints.Reset();

    if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty() || bPreviewStale || PublishedSignature != GetSourceSignature())
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("Generate Layout or Rebuild Geometry successfully before testing the current path."));

        return;
    }

    FPlayableSketchGridPath Path;

    if (!FPlayableSketchGridNavigationTests::Run(
        GeneratedFloorPlan,
        GraphAsset->Graph.StartRoomId,
        GraphAsset->Graph.GoalRoomId,
        GridStepCm,
        Path))
    {
        return;
    }

    PreviewPathPoints = MoveTemp(Path.Points);
}
void APlayableSketchLevelActor::DrawFloorPathPreview()
{
    if (!GetWorld() || PreviewPathPoints.Num() < 2 || bPreviewStale || PublishedSignature != GetSourceSignature())
    {
        return;
    }

    const FTransform ActorTransform = GetActorTransform();

    for (int32 Index = 0; Index + 1 < PreviewPathPoints.Num(); ++Index)
    {
        const FVector2D& PointA = PreviewPathPoints[Index];
        const FVector2D& PointB = PreviewPathPoints[Index + 1];

        const FVector A = ActorTransform.TransformPosition(
            FVector(PointA.X, PointA.Y, 10.0));

        const FVector B = ActorTransform.TransformPosition(
            FVector(PointB.X, PointB.Y, 10.0));

        DrawDebugLine(GetWorld(), A, B, FColor::Green, false, -1.0f, 0, 5.0f);
    }
}

#if WITH_EDITOR
bool APlayableSketchLevelActor::ShouldTickIfViewportsOnly() const
{
    return true;
}
#endif

void APlayableSketchLevelActor::ApplyFloorMaterials()
{
    if (!GraphAsset)
    {
        return;
    }

    const FName GeneratedFloorTag(TEXT("PlayableSketch.GeneratedFloor"));
    const FName RoomFloorTag(TEXT("PlayableSketch.RoomFloor"));

    TArray<UStaticMeshComponent*> Components;
    GetComponents<UStaticMeshComponent>(Components);

    for (UStaticMeshComponent* Component : Components)
    {
        if (!IsValid(Component) || !Component->ComponentHasTag(GeneratedFloorTag))
        {
            continue;
        }

        UMaterialInterface* Material = DefaultFloorMaterial.Get();

        if (Component->ComponentHasTag(RoomFloorTag))
        {
            const FPlayableSketchRoom* Room = GraphAsset->Graph.Rooms.FindByPredicate(
                [Component](const FPlayableSketchRoom& Item)
                {
                    const FName RoomTag(*FString::Printf(
                        TEXT("RoomId=%s"),
                        *Item.RoomId.ToString()));

                    return Component->ComponentHasTag(RoomTag);
                });

            if (Room)
            {
                if (Room->RoomRole == EPlayableSketchRoomRole::Start && StartFloorMaterial)
                {
                    Material = StartFloorMaterial.Get();
                }
                else if (Room->RoomRole == EPlayableSketchRoomRole::Goal && GoalFloorMaterial)
                {
                    Material = GoalFloorMaterial.Get();
                }
                else if (Room->RoomType == EPlayableSketchRoomType::Hub && HubFloorMaterial)
                {
                    Material = HubFloorMaterial.Get();
                }
            }
        }

        if (Material)
        {
            Component->SetMaterial(0, Material);
        }
    }
}

void APlayableSketchLevelActor::TestWallSegments()
{
    FPlayableSketchWallSettings Settings;

    FPlayableSketchWallSegment Wall;
    Wall.LengthCm = 600.0;

    const FGuid SourceId = FGuid::NewGuid();

    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    FString Error;
    int32 Failures = 0;

    auto Check = [&](bool bPassed, const TCHAR* Name)
        {
            if (bPassed)
            {
                UE_LOG(LogTemp, Display, TEXT("PASS: %s"), Name);
            }
            else
            {
                ++Failures;
                UE_LOG(LogTemp, Error, TEXT("FAIL: %s"), Name);
            }
        };

    const bool bSolidSuccess = FPlayableSketchWallGeometry::SplitWall(
        Wall,
        TArray<FPlayableSketchWallOpening>(),
        Settings,
        SourceId,
        true,
        Pieces,
        Error);

    Check(
        bSolidSuccess
        && Pieces.Num() == 1
        && Pieces[0].CenterCm.Equals(FVector(300.0, 10.0, 150.0), 0.01)
        && Pieces[0].SizeCm.Equals(FVector(600.0, 20.0, 300.0), 0.01),
        TEXT("Solid wall dimensions"));

    FPlayableSketchWallOpening Opening;
    Opening.StartCm = 200.0;
    Opening.EndCm = 400.0;

    TArray<FPlayableSketchWallOpening> Openings;
    Openings.Add(Opening);

    const bool bDoorSuccess = FPlayableSketchWallGeometry::SplitWall(
        Wall,
        Openings,
        Settings,
        SourceId,
        true,
        Pieces,
        Error);

    Check(
        bDoorSuccess
        && Pieces.Num() == 3
        && Pieces[0].CenterCm.Equals(FVector(100.0, 10.0, 150.0), 0.01)
        && Pieces[0].SizeCm.Equals(FVector(200.0, 20.0, 300.0), 0.01)
        && Pieces[1].Role == EPlayableSketchGeometryRole::Lintel
        && Pieces[1].CenterCm.Equals(FVector(300.0, 10.0, 260.0), 0.01)
        && Pieces[1].SizeCm.Equals(FVector(200.0, 20.0, 80.0), 0.01)
        && Pieces[2].CenterCm.Equals(FVector(500.0, 10.0, 150.0), 0.01),
        TEXT("Door segments and lintel dimensions"));

    FPlayableSketchWallOpening SecondOpening;
    SecondOpening.StartCm = 100.0;
    SecondOpening.EndCm = 150.0;

    Openings.Add(SecondOpening);

    const bool bMultipleSuccess = FPlayableSketchWallGeometry::SplitWall(
        Wall,
        Openings,
        Settings,
        SourceId,
        true,
        Pieces,
        Error);

    Check(
        bMultipleSuccess && Pieces.Num() == 5,
        TEXT("Multiple unsorted openings"));

    Openings[1].StartCm = 300.0;
    Openings[1].EndCm = 450.0;

    Check(
        !FPlayableSketchWallGeometry::SplitWall(
            Wall,
            Openings,
            Settings,
            SourceId,
            true,
            Pieces,
            Error)
        && Pieces.IsEmpty(),
        TEXT("Overlapping openings rejected"));

    Openings.SetNum(1);
    Openings[0].StartCm = -20.0;
    Openings[0].EndCm = 100.0;

    Check(
        !FPlayableSketchWallGeometry::SplitWall(
            Wall,
            Openings,
            Settings,
            SourceId,
            true,
            Pieces,
            Error)
        && Pieces.IsEmpty(),
        TEXT("Outside opening rejected"));

    UE_LOG(
        LogTemp,
        Display,
        TEXT("Wall segment tests finished: Failures=%d"),
        Failures);
}

FString APlayableSketchLevelActor::GetSourceSignature() const
{
    if (!GraphAsset)
    {
        return TEXT("NoGraphAsset");
    }

    return GraphAsset->GetPathName() + GraphAsset->GetSourceText()
        + FString::Printf(TEXT("|%d|%d|%d|%d|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g"),
            GridStepCm, RoomGapCm, DoorCornerMarginCm, MaxPlacementAttempts,
            FloorThicknessCm, WallHeightCm, WallThicknessCm, DoorHeightCm,
            MinCorridorWidthCm, PawnRadiusCm, PawnHeightCm, ClearanceCm)
        + GetPathNameSafe(WallMaterial.Get()) + GetPathNameSafe(DefaultFloorMaterial.Get())
        + GetPathNameSafe(HubFloorMaterial.Get()) + GetPathNameSafe(StartFloorMaterial.Get())
        + GetPathNameSafe(GoalFloorMaterial.Get());
}

FPlayableSketchValidationSettings APlayableSketchLevelActor::GetValidationSettings() const
{
    FPlayableSketchValidationSettings Settings;
    Settings.GridStepCm = GridStepCm;
    Settings.Walls.HeightCm = WallHeightCm;
    Settings.Walls.ThicknessCm = WallThicknessCm;
    Settings.Walls.DoorHeightCm = DoorHeightCm;
    Settings.Walls.CornerMarginCm = DoorCornerMarginCm;
    Settings.MinCorridorWidthCm = MinCorridorWidthCm;
    Settings.PawnRadiusCm = PawnRadiusCm;
    Settings.PawnHeightCm = PawnHeightCm;
    Settings.ClearanceCm = ClearanceCm;
    return Settings;
}

bool APlayableSketchLevelActor::ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const
{
    OutPlan = FPlayableSketchFloorPlan();
    OutError.Reset();

    if (!GraphAsset)
    {
        OutError = TEXT("GraphAsset is not assigned.");
        return false;
    }

    if (GridStepCm <= 0)
    {
        OutError = TEXT("GridStepCm must be positive.");
        return false;
    }

    for (const FPlayableSketchRoom& Room : GraphAsset->Graph.Rooms)
    {
        FVector2D MinCm = Room.PositionCm;

        if (Room.PositionMode == EPlayableSketchPositionMode::Auto)
        {
            const FPlayableSketchSavedPlacement* Saved = GraphAsset->SavedLayout.Rooms.FindByPredicate(
                [&](const FPlayableSketchSavedPlacement& Placement)
                {
                    return Placement.RoomId == Room.RoomId;
                });

            if (!Saved)
            {
                OutError = FString::Printf(TEXT("Room %s has no saved placement. Run Generate Layout."), *Room.RoomId.ToString());
                return false;
            }

            MinCm = Saved->MinCm;
        }

        FPlayableSketchPlacedRoom Placed;
        Placed.RoomId = Room.RoomId;
        FVector2D SizeCm(Room.WidthCm, Room.DepthCm);
        if (Room.PositionMode == EPlayableSketchPositionMode::Auto)
        {
            SizeCm.X = FMath::CeilToDouble(SizeCm.X / GridStepCm) * GridStepCm;
            SizeCm.Y = FMath::CeilToDouble(SizeCm.Y / GridStepCm) * GridStepCm;
        }
        Placed.Bounds = FPlayableSketchRect(MinCm, MinCm + SizeCm);

        if (!Placed.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid position or dimensions for Room %s."), *Room.RoomId.ToString());
            return false;
        }

        OutPlan.Rooms.Add(Placed);
    }

    return true;
}

bool APlayableSketchLevelActor::BuildCandidate(
    FPlayableSketchFloorPlan& Plan,
    TArray<FPlayableSketchGeometryDescriptor>& Pieces)
{
    for (int32 A = 0; A < Plan.Rooms.Num(); ++A)
    {
        for (int32 B = A + 1; B < Plan.Rooms.Num(); ++B)
        {
            if (Plan.Rooms[A].Bounds.OverlapsInterior(Plan.Rooms[B].Bounds))
            {
                FPlayableSketchValidationIssue Issue;
                Issue.Code = TEXT("PS-V001");
                Issue.ElementIds = { Plan.Rooms[A].RoomId, Plan.Rooms[B].RoomId };
                Issue.Message = TEXT("Room interiors overlap. Move or resize a Room.");
                const FVector2D Center = (Plan.Rooms[A].Bounds.Min + Plan.Rooms[A].Bounds.Max) * 0.5;
                const FVector2D Half = (Plan.Rooms[A].Bounds.Max - Plan.Rooms[A].Bounds.Min) * 0.5;
                Issue.PositionCm = FVector(Center.X, Center.Y, 25.0);
                Issue.ExtentCm = FVector(Half.X, Half.Y, 25.0);
                Issue.bHasPosition = true;
                LastIssues.Add(Issue);
            }
        }
    }

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid Room placement. Preview cleared."));
        return false;
    }

    FString Error;

    if (!FPlayableSketchDoorGenerator::Generate(GraphAsset->Graph, Plan, DoorCornerMarginCm, Error))
    {
        FailStage(TEXT("PS-V002"), Error);
        return false;
    }

    if (!FPlayableSketchCorridorRouting::Generate(GraphAsset->Graph, Plan, GridStepCm, Error))
    {
        FailStage(TEXT("PS-G002"), Error);
        return false;
    }

    if (!FPlayableSketchWallGeometry::Generate(Plan, GetValidationSettings().Walls, Pieces, Error))
    {
        FailStage(TEXT("PS-V005"), Error);
        return false;
    }

    LastIssues = FPlayableSketchValidation::ValidatePlan(GraphAsset->Graph, Plan, Pieces, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Validation failed. Preview cleared."));
        return false;
    }

    return true;
}

void APlayableSketchLevelActor::GenerateLayout()
{
    LastAttemptSignature = GetSourceSignature();

    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    if (GetWorld() && GetWorld()->IsGameWorld())
    {
        UE_LOG(LogTemp, Warning, TEXT("Generate Layout is an Editor authoring action. Use Rebuild Geometry during PIE."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid input. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;

    if (!FPlayableSketchLayoutGenerator::Generate(GraphAsset->Graph, GridStepCm, RoomGapCm, Candidate, Error, MaxPlacementAttempts))
    {
        FailStage(TEXT("PS-G001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;

    if (!BuildCandidate(Candidate, Pieces))
    {
        return;
    }

#if WITH_EDITOR
    {
        const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "GenerateLayout", "Generate PlayableSketch Layout"));
        GraphAsset->Modify();
        GraphAsset->SavedLayout.Rooms.Reset();

        for (const FPlayableSketchPlacedRoom& Room : Candidate.Rooms)
        {
            FPlayableSketchSavedPlacement Saved;
            Saved.RoomId = Room.RoomId;
            Saved.MinCm = Room.Bounds.Min;
            GraphAsset->SavedLayout.Rooms.Add(Saved);
        }

        GraphAsset->MarkPackageDirty();
    }
#endif

    PublishCandidate(Candidate, Pieces);
}

void APlayableSketchLevelActor::RebuildGeometry()
{
    LastAttemptSignature = GetSourceSignature();

    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid input. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;

    if (!ReadSavedRooms(Candidate, Error))
    {
        FailStage(TEXT("PS-L001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;

    if (BuildCandidate(Candidate, Pieces))
    {
        PublishCandidate(Candidate, Pieces);
    }
}

void APlayableSketchLevelActor::PublishCandidate(
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces)
{
    FString Error;

    if (!FPlayableSketchFloorBuilder::Build(*this, Plan, FloorThicknessCm, Error)
        || !FPlayableSketchWallBuilder::Build(*this, Pieces, WallMaterial.Get(), Error))
    {
        FailStage(TEXT("PS-G003"), Error);
        return;
    }

    GeneratedFloorPlan = Plan;
    PreviewPathPoints.Reset();
    PublishedSignature = GetSourceSignature();
    LastAttemptSignature = PublishedSignature;
    bPreviewStale = false;
    PreviewStatus = TEXT("Current valid preview. Full geometry rebuild completed.");
    ApplyFloorMaterials();
    LogIssues();
}

void APlayableSketchLevelActor::InvalidatePreview(
    const TArray<FPlayableSketchValidationIssue>& Issues,
    const FString& Status)
{
    LastIssues = Issues;
    AnnotateIssues();
    FPlayableSketchWallBuilder::Clear(*this);
    FPlayableSketchFloorBuilder::Clear(*this);
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = Status;
    LogIssues();
}

void APlayableSketchLevelActor::FailStage(const TCHAR* Code, const FString& Message)
{
    FPlayableSketchValidationIssue Issue;
    Issue.Code = FName(Code);
    Issue.Message = Message;

    if (GraphAsset)
    {
        for (const FPlayableSketchRoom& Room : GraphAsset->Graph.Rooms)
        {
            if (Message.Contains(Room.RoomId.ToString())) Issue.ElementIds.AddUnique(Room.RoomId);
        }
        for (const FPlayableSketchConnection& Connection : GraphAsset->Graph.Connections)
        {
            if (Message.Contains(Connection.ConnectionId.ToString())) Issue.ElementIds.AddUnique(Connection.ConnectionId);
        }
    }

    InvalidatePreview({ Issue }, TEXT("Generation failed. Preview cleared; see Last Issues."));
}

void APlayableSketchLevelActor::AnnotateIssues()
{
    if (!GraphAsset) return;

    for (FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        if (Issue.bHasPosition) continue;

        for (const FGuid& Id : Issue.ElementIds)
        {
            const FPlayableSketchConnection* Connection = GraphAsset->Graph.Connections.FindByPredicate(
                [&](const FPlayableSketchConnection& Item) { return Item.ConnectionId == Id; });
            const FGuid RoomId = Connection ? Connection->RoomAId : Id;
            const FPlayableSketchRoom* Source = GraphAsset->Graph.Rooms.FindByPredicate(
                [&](const FPlayableSketchRoom& Item) { return Item.RoomId == RoomId; });
            const FPlayableSketchSavedPlacement* Saved = GraphAsset->SavedLayout.Rooms.FindByPredicate(
                [&](const FPlayableSketchSavedPlacement& Item) { return Item.RoomId == RoomId; });

            if (Source && (Source->PositionMode == EPlayableSketchPositionMode::Locked || Saved))
            {
                const FVector2D Min = Source->PositionMode == EPlayableSketchPositionMode::Locked ? Source->PositionCm : Saved->MinCm;
                Issue.PositionCm = FVector(Min.X + Source->WidthCm * 0.5, Min.Y + Source->DepthCm * 0.5, 25.0);
                Issue.ExtentCm = FVector(Source->WidthCm * 0.5, Source->DepthCm * 0.5, 25.0);
                Issue.bHasPosition = !Issue.PositionCm.ContainsNaN();
                break;
            }

            const FPlayableSketchPlacedRoom* Previous = GeneratedFloorPlan.Rooms.FindByPredicate(
                [&](const FPlayableSketchPlacedRoom& Item) { return Item.RoomId == RoomId; });
            if (Previous)
            {
                const FVector2D Center = (Previous->Bounds.Min + Previous->Bounds.Max) * 0.5;
                Issue.PositionCm = FVector(Center.X, Center.Y, 25.0);
                Issue.bHasPosition = true;
                break;
            }
        }
    }
}

void APlayableSketchLevelActor::LogIssues() const
{
    for (const FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        FString Ids;
        for (const FGuid& Id : Issue.ElementIds) Ids += Id.ToString() + TEXT(" ");
        UE_LOG(LogTemp, Warning, TEXT("[%s] Severity=%d IDs=%s Position=%s Message=%s"),
            *Issue.Code.ToString(), static_cast<int32>(Issue.Severity), *Ids,
            Issue.bHasPosition ? *Issue.PositionCm.ToString() : TEXT("Unknown"), *Issue.Message);
    }
}

void APlayableSketchLevelActor::DrawValidationIssues()
{
    if (!GetWorld()) return;
    const FTransform Transform = GetActorTransform();
    const FVector Scale = Transform.GetScale3D().GetAbs();

    for (const FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        if (!Issue.bHasPosition) continue;
        const FVector Position = Transform.TransformPosition(Issue.PositionCm);
        const FColor Color = Issue.Severity == EPlayableSketchIssueSeverity::Error ? FColor::Red : FColor::Yellow;
        DrawDebugBox(GetWorld(), Position, Issue.ExtentCm * Scale, Transform.GetRotation(), Color, false, -1.0f, 0, 3.0f);
    }
}

void APlayableSketchLevelActor::ValidateCurrentDesign()
{
    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());
    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Validation failed. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;
    if (!ReadSavedRooms(Candidate, Error))
    {
        FailStage(TEXT("PS-L001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    if (BuildCandidate(Candidate, Pieces))
    {
        bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty() && PublishedSignature != GetSourceSignature();
        PreviewStatus = bPreviewStale
            ? TEXT("Design is valid, but displayed preview is stale. Rebuild Geometry.")
            : TEXT("Design validation passed. Validation did not publish new geometry.");
        UE_LOG(LogTemp, Display, TEXT("Current design validation passed."));
    }
}

void APlayableSketchLevelActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);

    if (GraphAsset && GetWorld() && !GetWorld()->IsGameWorld() && bAutoRebuildGeometry)
    {
        RebuildGeometry();
    }
}

#if WITH_EDITOR
void APlayableSketchLevelActor::PostEditUndo()
{
    Super::PostEditUndo();
    LastAttemptSignature.Reset();
    if (bAutoRebuildGeometry) RebuildGeometry();
}
#endif

void APlayableSketchLevelActor::TestDay4Validation()
{
    FPlayableSketchDay4Tests::Run();
}
```

### Source/PlayableSketch/Public/Validation/Tests/PlayableSketchDay4Tests.h

```cpp
#pragma once

#include "CoreMinimal.h"

class PLAYABLESKETCH_API FPlayableSketchDay4Tests
{
public:
    static bool Run();
};
```

### Source/PlayableSketch/Private/Validation/Tests/PlayableSketchDay4Tests.cpp

```cpp
#include "Validation/Tests/PlayableSketchDay4Tests.h"
#include "Validation/PlayableSketchValidation.h"
#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Misc/AutomationTest.h"

#if WITH_EDITOR
#include "Editor.h"
#include "ScopedTransaction.h"
#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#endif

namespace
{
    void MakeFixture(FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& Plan)
    {
        for (int32 Index = 0; Index < 3; ++Index)
        {
            FPlayableSketchRoom Room;
            Room.RoomId = FGuid(0, 0, 0, Index + 1);
            Room.DisplayName = FString::Printf(TEXT("FixtureRoom%d"), Index);
            Graph.Rooms.Add(Room);

            FPlayableSketchPlacedRoom Placed;
            Placed.RoomId = Room.RoomId;
            Placed.Bounds = FPlayableSketchRect(FVector2D(Index * 1000.0, 0.0), FVector2D(Index * 1000.0 + 600.0, 600.0));
            Plan.Rooms.Add(Placed);
        }

        Graph.StartRoomId = Graph.Rooms[0].RoomId;
        Graph.GoalRoomId = Graph.Rooms[2].RoomId;

        for (int32 Index = 0; Index < 2; ++Index)
        {
            FPlayableSketchConnection Connection;
            Connection.ConnectionId = FGuid(0, 0, 0, 100 + Index);
            Connection.RoomAId = Graph.Rooms[Index].RoomId;
            Connection.RoomBId = Graph.Rooms[Index + 1].RoomId;
            Graph.Connections.Add(Connection);

            FPlayableSketchCorridor Corridor;
            Corridor.ConnectionId = Connection.ConnectionId;
            Corridor.DoorA.RoomId = Connection.RoomAId;
            Corridor.DoorA.WallSide = EPlayableSketchWallSide::East;
            Corridor.DoorA.PositionCm = FVector2D(Index * 1000.0 + 600.0, 300.0);
            Corridor.DoorB.RoomId = Connection.RoomBId;
            Corridor.DoorB.WallSide = EPlayableSketchWallSide::West;
            Corridor.DoorB.PositionCm = FVector2D((Index + 1) * 1000.0, 300.0);
            Corridor.Footprints.Add(FPlayableSketchRect(
                FVector2D(Index * 1000.0 + 600.0, 200.0),
                FVector2D((Index + 1) * 1000.0, 400.0)));
            Plan.Corridors.Add(Corridor);
        }
    }

    bool HasIssue(const TArray<FPlayableSketchValidationIssue>& Issues, const TCHAR* Code, const FGuid& Id)
    {
        return Issues.ContainsByPredicate([&](const FPlayableSketchValidationIssue& Issue)
        {
            return Issue.Code == FName(Code) && Issue.ElementIds.Contains(Id)
                && Issue.Severity == EPlayableSketchIssueSeverity::Error
                && Issue.bHasPosition && !Issue.PositionCm.ContainsNaN() && !Issue.Message.IsEmpty();
        });
    }
}

bool FPlayableSketchDay4Tests::Run()
{
    int32 Failures = 0;
    auto Check = [&](bool bPassed, const TCHAR* Name)
    {
        if (bPassed)
        {
            UE_LOG(LogTemp, Display, TEXT("PASS: %s"), Name);
        }
        else
        {
            ++Failures;
            UE_LOG(LogTemp, Error, TEXT("FAIL: %s"), Name);
        }
    };

    FPlayableSketchGraph Graph;
    FPlayableSketchFloorPlan Plan;
    MakeFixture(Graph, Plan);
    FPlayableSketchValidationSettings Settings;
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    FString Error;

    const bool bGenerated = FPlayableSketchWallGeometry::Generate(Plan, Settings.Walls, Pieces, Error);
    Check(bGenerated, TEXT("Valid fixture wall generation"));
    Check(!FPlayableSketchValidation::HasErrors(FPlayableSketchValidation::ValidatePlan(Graph, Plan, Pieces, Settings)), TEXT("Valid fixture passes independent validation"));

    FPlayableSketchFloorPlan BadPlan = Plan;
    BadPlan.Rooms[1].Bounds = FPlayableSketchRect(FVector2D(400.0, 0.0), FVector2D(1000.0, 600.0));
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V001"), Graph.Rooms[1].RoomId), TEXT("PS-V001 overlap with ID, position, severity and message"));

    BadPlan = Plan;
    BadPlan.Corridors[0].DoorA.PositionCm.X -= 10.0;
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V002"), Graph.Connections[0].ConnectionId), TEXT("PS-V002 invalid Door with metadata"));

    FPlayableSketchGraph BadGraph = Graph;
    BadGraph.Connections[0].CorridorWidthCm = 60;
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(BadGraph, Plan, Pieces, Settings), TEXT("PS-V003"), Graph.Connections[0].ConnectionId), TEXT("PS-V003 narrow Corridor with metadata"));

    BadPlan = Plan;
    BadPlan.Corridors[0].Footprints.Reset();
    BadPlan.Corridors[0].Footprints.Add(FPlayableSketchRect(FVector2D(600.0, 200.0), FVector2D(700.0, 400.0)));
    BadPlan.Corridors[0].Footprints.Add(FPlayableSketchRect(FVector2D(900.0, 200.0), FVector2D(1000.0, 400.0)));
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V004"), Graph.Rooms[1].RoomId), TEXT("PS-V004 physical disconnection with metadata"));

    TArray<FPlayableSketchGeometryDescriptor> BadPieces = Pieces;
    FPlayableSketchGeometryDescriptor BlockingWall;
    BlockingWall.SourceId = Graph.Rooms[0].RoomId;
    BlockingWall.bRoom = true;
    BlockingWall.CenterCm = FVector(610.0, 300.0, 100.0);
    BlockingWall.SizeCm = FVector(20.0, 150.0, 200.0);
    BadPieces.Add(BlockingWall);
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, Plan, BadPieces, Settings), TEXT("PS-V005"), Graph.Connections[0].ConnectionId), TEXT("PS-V005 Door blocked by Wall with metadata"));

    BadPieces = Pieces;
    BadPieces.RemoveAll([](const FPlayableSketchGeometryDescriptor& Piece)
    {
        return Piece.Role == EPlayableSketchGeometryRole::Lintel;
    });
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, Plan, BadPieces, Settings), TEXT("PS-V005"), Graph.Connections[0].ConnectionId), TEXT("Missing lintel rejected"));

    BadGraph = Graph;
    BadGraph.Rooms[1].PositionMode = EPlayableSketchPositionMode::Locked;
    BadGraph.Rooms[1].PositionCm = FVector2D(1400.0, 1000.0);
    FPlayableSketchFloorPlan LockedPlan;
    const bool bLockedGenerated = FPlayableSketchLayoutGenerator::Generate(BadGraph, 50, 400, LockedPlan, Error);
    const FPlayableSketchPlacedRoom* LockedRoom = LockedPlan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Room)
    {
        return Room.RoomId == BadGraph.Rooms[1].RoomId;
    });
    Check(bLockedGenerated && LockedRoom && LockedRoom->Bounds.Min == BadGraph.Rooms[1].PositionCm, TEXT("Generate Layout preserves Locked position"));

    BadGraph = Graph;
    BadGraph.Connections[0].DoorASettings.bManual = true;
    BadGraph.Connections[0].DoorASettings.WallSide = EPlayableSketchWallSide::East;
    BadGraph.Connections[0].DoorASettings.OffsetCm = 160.0;
    FPlayableSketchFloorPlan DoorPlan = Plan;
    const bool bDoorGenerated = FPlayableSketchDoorGenerator::Generate(BadGraph, DoorPlan, 50, Error);
    const FPlayableSketchCorridor* ManualCorridor = DoorPlan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Corridor)
    {
        return Corridor.ConnectionId == BadGraph.Connections[0].ConnectionId;
    });
    Check(bDoorGenerated && ManualCorridor && ManualCorridor->DoorA.PositionCm == FVector2D(600.0, 160.0), TEXT("Manual Door offset applied"));

#if WITH_EDITOR
    UPlayableSketchGraphAsset* Asset = NewObject<UPlayableSketchGraphAsset>(GetTransientPackage(), NAME_None, RF_Transactional);
    Asset->Graph = Graph;
    Asset->RoomToRemoveId = Graph.Rooms[1].RoomId;
    Asset->RemoveRoom();
    Check(Asset->Graph.Rooms.Num() == 2 && Asset->Graph.Connections.IsEmpty(), TEXT("Deleting a Room removes its Connections"));
    Check(Asset->Graph.StartRoomId == Graph.StartRoomId && Asset->Graph.GoalRoomId == Graph.GoalRoomId, TEXT("Deleting a Room does not silently reassign Start or Goal"));
    Asset->RoomToRemoveId = Graph.StartRoomId;
    Asset->RemoveRoom();
    Check(FPlayableSketchValidation::HasErrors(FPlayableSketchValidation::ValidateInput(Asset->Graph, Settings)), TEXT("Deleting Start leaves an explicit validation error"));

    UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
    APlayableSketchLevelActor* Actor = World ? World->SpawnActor<APlayableSketchLevelActor>() : nullptr;
    Check(Actor != nullptr, TEXT("Editor integration fixture created"));

    if (Actor)
    {
        UPlayableSketchGraphAsset* PreviewAsset = NewObject<UPlayableSketchGraphAsset>(GetTransientPackage(), NAME_None, RF_Transactional);
        PreviewAsset->Graph = Graph;
        Actor->GraphAsset = PreviewAsset;
        Actor->GenerateLayout();
        Check(PreviewAsset->SavedLayout.Rooms.Num() == 3 && Actor->LastIssues.IsEmpty(), TEXT("Generate Layout saves valid Room placements"));

        auto GeneratedCount = [&]()
        {
            TArray<UStaticMeshComponent*> Components;
            Actor->GetComponents<UStaticMeshComponent>(Components);
            int32 Count = 0;
            for (UStaticMeshComponent* Component : Components)
            {
                if (Component->ComponentHasTag(TEXT("PlayableSketch.GeneratedFloor"))
                    || Component->ComponentHasTag(TEXT("PlayableSketch.GeneratedWall"))) ++Count;
            }
            return Count;
        };

        const int32 BaselineCount = GeneratedCount();
        const FPlayableSketchSavedLayout Saved = PreviewAsset->SavedLayout;
        Actor->RebuildGeometry();
        Check(BaselineCount > 0 && GeneratedCount() == BaselineCount, TEXT("Repeated full rebuild does not accumulate components"));

        {
            const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "TestResize", "Day 4 test resize"));
            PreviewAsset->Modify();
            PreviewAsset->Graph.Rooms[0].WidthCm = 625;
        }
        Actor->RebuildGeometry();
        Check(Actor->LastIssues.IsEmpty() && PreviewAsset->SavedLayout.Rooms[1].MinCm == Saved.Rooms[1].MinCm, TEXT("Resize and rebuild preserve other Room positions"));

        TArray<UStaticMeshComponent*> Components;
        Actor->GetComponents<UStaticMeshComponent>(Components);
        const FName StartTag(*FString::Printf(TEXT("RoomId=%s"), *Graph.StartRoomId.ToString()));
        UStaticMeshComponent* StartFloor = nullptr;
        for (UStaticMeshComponent* Component : Components)
        {
            if (Component->ComponentHasTag(TEXT("PlayableSketch.RoomFloor")) && Component->ComponentHasTag(StartTag)) StartFloor = Component;
        }
        Check(StartFloor && FMath::IsNearlyEqual(StartFloor->GetRelativeScale3D().X * 100.0, 650.0, 0.01), TEXT("Auto Room dimensions retain grid rounding during rebuild"));

        GEditor->UndoTransaction();
        Actor->Tick(0.016f);
        Check(PreviewAsset->Graph.Rooms[0].WidthCm == 600 && Actor->LastIssues.IsEmpty(), TEXT("Undo restores source and automatically rebuilds preview"));

        GEditor->RedoTransaction();
        Actor->Tick(0.016f);
        Check(PreviewAsset->Graph.Rooms[0].WidthCm == 625 && Actor->LastIssues.IsEmpty(), TEXT("Redo restores edit and automatically rebuilds preview"));

        PreviewAsset->Graph.Rooms[0].WidthCm = 6000;
        Actor->RebuildGeometry();
        Check(GeneratedCount() == 0 && Actor->PreviewPathPoints.IsEmpty()
            && Actor->LastIssues.ContainsByPredicate([](const FPlayableSketchValidationIssue& Issue) { return Issue.Code == FName(TEXT("PS-V001")); }),
            TEXT("Invalid edit clears geometry and old navigation preview"));
        Actor->Destroy();
    }
#endif

    UE_LOG(LogTemp, Display, TEXT("Day 4 tests finished: Failures=%d"), Failures);
    return Failures == 0;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchDay4AutomationTest, "PlayableSketch.Day4.Validation", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPlayableSketchDay4AutomationTest::RunTest(const FString& Parameters)
{
    return FPlayableSketchDay4Tests::Run();
}
#endif
```

