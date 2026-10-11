# PlayableSketch — Local Rebuild uygulama rehberi

Bu rehber mevcut projenin 11 Ekim 2026 tarihindeki Source dosyalarına göre hazırlandı. Ana projenin Source dosyaları değiştirilmedi. Aşağıdaki kodları sen uygulayacaksın. Paket içindeki Source ağacı yalnız yeni/değişen altı dosyayı içerir; projenin Source klasörünü silme, dosyaları tek tek ekle veya karşılaştırarak değiştir.

Day 5 kapsamı, masaüstündeki PlayableSketch_7_Gunluk_Rehber_Sade_v2.pdf belgesinin 17–19. sayfalarındaki Local Rebuild bölümüdür. Belge bir kapsam kaynağı olarak kullanıldı; uygulamayı senin yapacağın talebin esas alındı.

## 1. Bugün neyi değiştireceksin?

Mevcut akışında `BuildCandidate` yeni kapıları, koridorları ve duvar descriptorlarını hesaplıyor. Ardından `PublishCandidate`, `FloorBuilder::Build` ve `WallBuilder::Build` çağırıyor. Bu iki builder `Clear` ile eski componentleri siliyor. Bu nedenle tek bir oda türünü değiştirmek bile bütün meshleri yeniden oluşturuyor.

Yeni akış:

```text
Graph + SavedLayout
    ↓ ReadSavedRooms
Aday Room bounds
    ↓ DoorGenerator + CorridorRouting + WallGeometry
Geçerli aday FloorPlan ve duvar descriptorları
    ↓ ValidatePlan
Floor + Wall + Lintel için ComponentSpec listesi
    ↓ canonical sıralama + AssignKeys
Eski registry ile yeni descriptorların karşılaştırılması
    ↓ DirtyRooms / DirtyConnections / değişen parça anahtarları
Yalnız değişen componentleri güncelle / ekle / sil
    ↓
Başarıdan sonra snapshot ve PublishedSignature güncellenir
```

**Bu sürümde geometri uygulaması yereldir.** Kapı seçimi, koridor routing, descriptor üretimi ve validation bütün plan için yeniden hesaplanır. Böylece henüz bir dependency arama optimizasyonuna güvenmek zorunda kalmazsın. CPU tarafında bütün planı hesaplamak, sahnedeki bütün componentleri yeniden oluşturmak anlamına gelmez.

Örneğin B büyüyünce B'nin flooru, duvarları, B'ye bağlı koridorlar ve komşuların kapı duvarları farklı descriptor verir. Registry bu farklılıkları bulur. Başka bir koridorun rotası da değişmişse onun parçaları da karşılaştırmada farklı çıkar. DirtySet bu sürümde **hesaplanan sonuç farkından** çıkarılır; graph üzerinde yalnız bir komşuluk adımıyla sınırlandırılmaz.

Bu seçim küçük proje için güvenilir bir ilk adımdır. Gerçekten yerel routing/validation optimizasyonunu daha sonra ekleyebilirsin. Bu uygulama için “yalnız dirty odaların algoritmalarını çalıştırıyorum” iddiasında bulunma.

## 2. Dosya listesi ve uygulama sırası

Paket içindeki yollar, projenin kök dizinine göre verilmiştir.

| İşlem | Dosya | Neden? |
|---|---|---|
| Yeni | `Source/PlayableSketch/Public/Geometry/PlayableSketchComponentRegistry.h` | Parça tanımı, registry ve update istatistikleri. |
| Yeni | `Source/PlayableSketch/Private/Geometry/PlayableSketchComponentRegistry.cpp` | Anahtar üretimi, fark hesabı, component lifecycle ve karşılaştırma. |
| Değiştir | `Source/PlayableSketch/Public/Geometry/PlayableSketchFloorBuilder.h` | Var olan koridor zeminini bölme algoritmasını public yapar. |
| Değiştir | `Source/PlayableSketch/PlayableSketchLevelActor.h` | Registry, snapshot, düğmeler ve süre alanları. |
| Değiştir | `Source/PlayableSketch/PlayableSketchLevelActor.cpp` | Builder'larla toplu silme yerine registry üzerinden yayınlama. |
| Yeni | `Source/PlayableSketch/Private/Validation/Tests/PlayableSketchLocalRebuildTests.cpp` | 10 edit, Local/Full eşitliği, pointer korunması, silme ve fallback kontrolleri. |

`Build.cs` değişmiyor: Core, CoreUObject, Engine ve Editor için UnrealEd zaten mevcut. `GraphAsset`, `Room`, `Connection`, `DoorGenerator`, `CorridorRouting`, `WallGeometry` ve validation dosyalarının mevcut kodlarını koru. Eski FloorBuilder/WallBuilder `.cpp` dosyalarını da silme; Actorun yeni yayınlama akışı onların toplu `Build` metodlarını çağırmayacak.

Editorü kapat. Önce registry dosyalarını ekle, FloorBuilder headerını değiştir, sonra Actor header/cpp değişikliklerini uygula, son olarak test dosyasını ekle. UFUNCTION/UPROPERTY değiştiği için ilk derlemeyi Live Coding yerine Editor kapalıyken yap. Paket sonunda altı dosyanın da TAM KODU var. Hazır Source dosyaları aynı kodları içerir.

## 3. Parça tanımı neden ayrı?

`FPlayableSketchComponentSpec` şu bilgileri tutar:

- `Key`: belirli bir generated parça için karşılaştırma anahtarı.
- `SourceId` ve `bRoom`: parçanın Rooma mı Connectiona mı ait olduğu.
- `Kind`: Floor, Wall veya Lintel.
- `CenterCm`, `SizeCm`: Actorun local uzayındaki ölçüler.
- `Material`: uygulanacak material; weak reference kullanılır.

Room ve Connection ID'lerini ayrı namespace içinde tutuyoruz. Tesadüfen aynı GUID kullanılsa bile anahtarlar çakışmaz. Componentleri Actorun instance component listesi sahiplenir. Registry weak pointer tutar; component dışarıdan silinirse dangling pointer ile işlem yapmaz.

Mevcut `FPlayableSketchGeometryDescriptor` yalnız Wall/Lintel için kullanılıyor. Onu değiştirmek yerine floorları da kapsayan yeni bir yayınlama tanımı oluşturuyoruz. Böylece mevcut wall ve validation testlerinin veri modelini bozmuyoruz.

## 4. ComponentKey nasıl üretiliyor?

Örnek anahtar:

```text
Room/<RoomGuid>/1/3
```

Burada kind `0=Floor`, `1=Wall`, `2=Lintel`; son sayı o owner ve kind grubundaki canonical sıradır. Bu sayı Room array indexi değildir. Önce owner türü, stable GUID, kind, center ve size ile sıralama yapılır; sonra numara verilir. Aynı çıktı, input array sırası değişse bile aynı anahtarları verir.

Bu anahtar tek bir duvar parçasının editler boyunca değişmez semantik kimliği değildir. Açıklık sayısı değişince aynı owner içindeki slotların karşılığı değişebilir. Registry yeni değerleri doğru slota yazar, fazlalığı siler ve eksiği ekler. Mevcut descriptorlarda wall side/segment ID bulunmadığı için bu projeye uyumlu, daha küçük bir çözümdür. Anahtarlar Local ile Full çıktısını karşılaştırmak için yeterlidir; isimleri diske kalıcı bir duvar kimliği olarak kaydetme.

## 5. Eski ve yeni konum, DirtySet ve dependencies

`GeneratedFloorPlan` son kabul edilmiş planı tutar. Yeni plan `Candidate` değişkeninde hazırlanır. Registry de eski yayınlanmış center/size/material değerlerini tutar. Başarılı uygulamaya kadar bunların üzerine yazılmaz. Dolayısıyla eski konum kaybolmaz.

`SameValue` anahtarı, ownerı, kindı, konumu, boyutu ve materialı karşılaştırır. Geometri değerlerinde exact karşılaştırma kullanılır; epsilon ile küçük gerçek editleri yutmayız. Scene doğrulamasında transform hesaplarının küçük sayısal farkları için tolerans vardır.

Registry fark hesabı:

```text
Yeni anahtar eski registry'de yok → component oluştur.
Anahtar var, değer değişmiş → mevcut componenti güncelle.
Anahtar var, değer aynı → componente dokunma.
Eski anahtar yeni listede yok → componenti ve colliderını kaldır.
```

Değişen/silinen/eklenen parçaların owner ID'leri `DirtyRooms` ve `DirtyConnections` kümelerine eklenir. Yalnız label değişmiş ve geometri aynı kalmışsa dirty geometri çıkmayabilir; bu doğru sonuçtur.

Bağlı olmayan koridorun üstüne taşınan Room da görülür: `CorridorRouting` tüm yeni Room boundslarını engel olarak değerlendirir. Genişlik, kapı ve duvar kalınlığı kontrolleri mevcut `ValidatePlan` içinde bütün sonuç üzerinde çalışır. Geçerli alternatif bulunursa değişen koridor parçaları diff'e girer; bulunamazsa açık hata çıkar. Başka odaları sessizce kaydırmak için `GenerateLayout` çağrılmaz.

## 6. Apply neden iki aşamalı?

Önce tüm spec'ler ve Engine Cube mesh kontrol edilir. Gerekli yeni componentler görünmez ve collisionsız hazırlanır, register edilir. Allocation/registration başarısızsa yalnız hazırlanan componentler kaldırılır; eski yayın korunur. Bu hazırlık sırasında generated tag verilmez; böylece Full temizliği yeni hazırlanan parçaları yanlışlıkla silmez.

Sonra commit yapılır: kaldırılacak eski parçalar temizlenir, yeni parçalar etkinleştirilir, değişen mevcut parçaların transform/materialı güncellenir. Güncellenen parça için pointer aynı kalır. `RemoveInstanceComponent` ve `DestroyComponent` ile silme yapılır; yalnız pointerı registry'den çıkarmak colliderı ortadan kaldırmaz. Component lifecycle ayrıntısı için [Epic Components belgesi](https://dev.epicgames.com/documentation/unreal-engine/components-in-unreal-engine).

Floor üst yüzeyi Z=0, kalınlığı aşağı doğrudur. Cube'un gerçek bounding box boyutu ve merkezi kullanılır; mesh boyutunun 100 cm olduğunu varsaymayız. Bütün transformlar root componente göre localdir. Actor taşınırken parçalar birlikte taşınır.

Floor ve Wall/Lintel `BlockAllDynamic`, `QueryAndPhysics` ve Pawn için Block kullanır. Floor üzerinde step-up açık, Wall/Lintel üzerinde kapalıdır. Custom navigation henüz meshlerden beslenmediği için `SetCanEverAffectNavigation(false)` mevcut davranışı korur.

Material `nullptr` olduğunda eski override temizlenir. Bu önemli: Hub materialından generic/default duruma dönünce önceki rengin kalmasını istemiyoruz. Gerçekte görünen material, Cube'un varsayılan materialına düşebilir; Verify bunu hesaba katar.

## 7. Actor tarafında tam olarak ne değişti?

### Header

`PlayableSketchComponentRegistry.h` include'u `.generated.h` include'undan önce gelir. `RebuildLocalGeometry`, `TestRebuildEquivalence`, `LastRebuildReport`, registry, global signature ve timing alanları eklenir. `PublishCandidate` artık full/local ve neden bilgisini alır. Test sınıfına friend erişimi yalnız testlerin registry ve kabul edilmiş planı incelemesi içindir.

### Mevcut metodlar

| Metod | Yeni davranış |
|---|---|
| `Tick` | Source değişince otomatik `RebuildLocalGeometry` çağırır. |
| `OnConstruction` | Otomatik rebuild için local girişini kullanır; gerekli fallback içerde seçilir. |
| `PostEditUndo` | Undo sonrası local girişinden yeni source değerlendirilir. |
| `RebuildGeometry` | Ortak `UpdateGeometry(true)` ile açık Full isteği gönderir. |
| `PublishCandidate` | Floor/Wall/Lintel spec'leri çıkarır, key üretir, registry'ye uygular. |
| `ClearFloors` | Registry dahil bütün generated parçaları temizler; saved yerleşimi tutar. |
| `InvalidatePreview` | Geçersiz tasarımda registry ve preview'ı birlikte temizler. |
| `ApplyFloorMaterials` | Registry dışından material yazmak yerine local rebuild'e yönlenir. |
| `BuildCandidate` | Mevcut hesapları korur; plan validation süresini ayrıca ölçer. |
| `GenerateLayout` | Yerleşim üretme işini korur, sonucu açık Full olarak yayınlar. |
| `TestFloorPath` | Var olan ilk grid testini korur; navigation süresini ayrıca loglar. |

### Yeni metodlar

`UpdateGeometry` input validation, kayıtlı bounds okuma, candidate üretme ve fallback kararını birleştirir. `RebuildLocalGeometry` bunun local girişidir. `GetGlobalRebuildSignature` global değişiklikleri ayırır. `TestRebuildEquivalence` mevcut source için önce Local, sonra Full sonucunu kontrol eder.

`PublishCandidate` sonunda eski `ApplyFloorMaterials()` çağrısı kaldırılmıştır. Kaldırmasaydık helper artık local rebuild'e yönlendiği için sonsuz recursion oluşurdu. Materiallar yeni spec'lerde zaten vardır.

## 8. Hangi durumda Full fallback var?

- İlk yayın yapılacaksa veya preview temizlenmişse.
- GraphAsset, Seed, SchemaVersion ya da global generation/geometry/validation ayarları değişmişse.
- Registry'deki component kaybolmuşsa, unregister olmuşsa, sayılar tutmuyorsa veya sahnedeki transform/material/collision beklenen değerden farklıysa.
- Kullanıcı açıkça `Rebuild Geometry (Full)` seçerse.

Room Type, Room Name, konum, boyut, kapı ayarı, connection boyutu veya material ataması normalde local girişinden işlenir. Global material alanı çok sayıda parçayı etkileyebilir; onları yerinde günceller, zorunlu olarak yeniden oluşturmaz.

Seed fallback'i mevcut SavedLayout/Locked boundslarını korur. Yeni seedle yeni yerleşim istiyorsan ayrıca `Generate Layout` seçmelisin. `RebuildGeometry` ile `GenerateLayout` aynı işlem değildir.

Yeni Auto Room için saved placement yoksa açıkça Generate Layout istenir. Local rebuild yeni oda için kendiliğinden yerleşim uydurmaz. Odayı önce Locked konumla ekleyebilir veya açıkça Generate Layout çalıştırabilirsin.

## 9. Hatalı editte ne görürsün?

Input, routing veya plan validation başarısızsa mevcut Day 4 politikasına uygun olarak preview temizlenir ve `LastIssues` gösterilir. Hatalı graph/position verisi kendiliğinden eski değerine alınmaz; düzeltmen veya Undo yapman gerekir. Registry ve fizik parçaları da temizlenir; sahnede eski collider bırakılmaz. Sonraki geçerli giriş ilk yayın gibi Full olabilir.

Apply sırasında allocation/registration başarısızsa staging geri alınır ve önceki kabul edilmiş preview **stale** olarak tutulur. Geçerli güncel sonuç gibi gösterilmez; path preview temizlenir. Bu iki hata türü bilinçli olarak ayrı ele alınır.

## 10. Derleme ve otomatik test

Editor kapalıyken IDE'den `PlayableSketchEditor / Development Editor / Win64` build et. Yeni test bir Unreal Automation Testtir; ayrıca test headerı veya Actor üzerinde `TestLocalRebuild` düğmesi gerekmez.

Editorü açınca Session Frontend → Automation içinden `PlayableSketch.Geometry.LocalRebuild` testini çalıştır. Konsol alternatifi:

```text
Automation RunTests PlayableSketch.Geometry.LocalRebuild
```

Test yeni, geçici bir world oluşturur; açık haritanı temizlemez. Aynı Graphı kullanan iki ayrı Actoru aynı başlangıçtan üretir. Birinde local, diğerinde full çalıştırır. Aşağıdaki 10 editin her biri bağımsız başlangıçtan denenir:

| # | Edit | Kontrol |
|---|---|---|
| 1 | Room Type → Hub | Material doğru, create/remove yok. |
| 2 | DisplayName değiştir | Geometriye sıfır yazma. |
| 3 | Room width artır | Floor, duvar, kapı/koridor sonuçları Full ile aynı. |
| 4 | Room depth artır | Etkilenen ölçüler ve routing Full ile aynı. |
| 5 | Room konumunu değiştir | Eski konum korunmaz, yeni ölçüler doğru. |
| 6 | Door width artır | Açıklık/lintel/komşu geometri doğru. |
| 7 | Corridor width artır | Floor ve dış sınır geometri doğru. |
| 8 | Connection sil | Graph bağlı kalır, connection parçaları silinir. |
| 9 | Room ve incident connectionları sil | Silinen owner parçaları ve registry kayıtları kalmaz. |
| 10 | Room/Connection array sırasını değiştir | Aynı keyler ve geometri, create/remove/update yok. |

Her editte Room bounds, Doors, corridor footprints, keyler, local transformlar, mesh, material, collision profile, Pawn response ve step-up davranışı karşılaştırılır. Değeri aynı kalan keylerin local component pointerları aynı kalmalıdır. Silinen component register edilmiş kalmamalıdır. Ayrıca seed fallback, temizleme ve taşınan bir Roomun incident olmayan corridor footprintine engel olmasının fark edilmesi kontrol edilir.

Bu testler fizik ayarlarını ve collider componentlerinin lifecycle'ını kontrol eder; gerçek karakterle kapıdan geçiş testinin yerine geçmez.

## 11. Kendi sahnende adım adım kontrol

1. Actorunu seç, GraphAsset ata, `Generate Layout` ile ilk sonucu üret. İlk raporda Full normaldir.
2. Geçişleri görmek için farklı Default ve Hub materialları ata. `bAutoRebuildGeometry` açıkken normal editler Tick üzerinden değerlendirilir.
3. Bir odanın türünü Hub yap. `Created=0`, `Removed=0` bekle. Start/Goal materialı atanmışsa bu roller Hub'ın önüne geçer; tür testini role=None odada yap.
4. Room Type'ı Generic'e döndür; eski Hub materialı kalmamalı.
5. Auto odanın mevcut yerini taşımak için önce Locked moduna geçip PositionCm'ye son görünen bounds.Min'i gir. Sonra konumu/boyutu değiştir. Local update sırasında diğer odalar kaymamalı. Mevcut koordinatı girmeden Auto→Locked geçişi oda varsayılan (0,0) konumuna dönebileceğinden ayrı bir gerçek edittir.
6. B'yi büyüt, kapı/koridorları incele; eski duvarın yerinde görünmez bir engel kalmadığını PIE'de dolaşarak kontrol et.
7. Bağlılığı koruyarak Connection sil. Gerekirse cycle içindeki bir edge'i seç. Graphı koparırsan validation hatası ve temizlenmiş preview beklenir.
8. Start/Goal olmayan bir odayı `Remove Room` ile sil; incident connectionlar da temizlenmeli. Sahne ve registry'de o ID'ye ait generated parça kalmamalı.
9. Bir Roomu bağlı olmadığı corridor alanına taşı. Alternatif rota veya açık hata bekle. Bu işlem sahnede başka Roomlarla overlap yapmasın; aksi halde önce overlap hatasını görürsün. Başarısız edit sonrası Undo yapıp geçerli tasarıma dön.
10. Actoru translate/rotate et; bütün parçalar birlikte gitmeli. Pointer kaybı/reinstancing varsa raporda fallback görülebilir.
11. Undo/Redo ve save/reopen dene. Registry transienttir; yeniden açılışta SavedLayout/Graph'tan yeniden kurulur. Generated componentleri kalıcı tasarım verisi olarak kullanma.

Elle karşılaştırmada `bAutoRebuildGeometry=false` yap. İlk preview'dan sonra tek bir edit uygula ve `Test Rebuild Equivalence` düğmesine bas. Bu düğme Local çıktısını snapshot alır, aynı source ve saved bounds üzerinden Full çalıştırıp karşılaştırır. Son görünen sahne Full sonucudur; test tasarım verisini değiştirmez. Bir sonraki edit için geçerli preview başlangıcı olarak kullanılabilir.

PASS satırındaki `LocalRan=1` gerçek local girişinin kullanıldığını gösterir. `LocalRan=0` ise ilk yayın/global değişiklik/fallback vardır; çıktı eşit olsa bile o örneği yerel edit başarısı olarak sayma. 10 edit otomatik testin yanında kendi sahnendeki önemli durumları da kaydet.

## 12. Süreleri nasıl okuyacaksın?

`LastRebuildReport` Details panelinde ve Output Log'da görünür.

```text
Mode=Local Reason=Descriptor changes only DirtyRooms=... DirtyConnections=...
Created=... Updated=... Removed=... Kept=...
PlanMs=... DirtyMs=... ApplyMs=... ValidationMs=... TotalMs=...
Navigation=not-run
```

- `PlanMs`: input/plan validation dışındaki hazırlık, saved room okuma, kapı/routing/wall hesabı ve floor/spec/key üretimi. Generate Layout'ta placement ve saved-layout transaction maliyeti de bu alana dahildir.
- `DirtyMs`: eski/yeni spec listesi farkı ve dirty owner kümeleri.
- `ApplyMs`: staging, component oluşturma/register, transform/material değişimi ve eski componentleri kaldırma.
- `ValidationMs`: input ve plan validation. Tüm plan için çalışır.
- `TotalMs`: girişten yayın tamamlanana kadar geçen süre. Signature, health kontrolü ve ortak ek maliyetleri de içerdiğinden yukarıdakilerin toplamına tam eşit olması gerekmez. Son log yazma/render/GPU/fizik frame tamamlama süresini ölçmez.
- `Navigation=not-run`: bu rebuild çağrısı grid navigation çalıştırmadı. Mevcut `Test Floor Path` düğmesi bunu ayrıca çalıştırır ve ayrı `NavigationMs` logu üretir; hata durumunda süre yine yazılır.

Raporu “bütün tool X kat hızlı” diye yorumlama. Önce aynı editte Local ve Full için TotalMs/ApplyMs değerlerini ayrı kaydet. Küçük sahnede local daha yavaş çıkabilir. Başarısız editin raporu `Result=Rejected` veya `Result=ApplyFailed` olur; önceki başarılı süreyi yeni sonuca aitmiş gibi kullanma.

## 13. Tamamlandı saymak için

- Editor build başarılı.
- `PlayableSketch.Geometry.LocalRebuild` başarılı: 10 edit eşit, değişmeyen pointerlar korunuyor.
- Kendi levelinde tür, hareket, resize, kapı, deletion, incident olmayan corridor, Undo/Redo ve save/reopen denendi.
- PIE'de kapıdan geçiliyor, duvar durduruyor, eski konumda collider kalmıyor.
- Fallback nedenleri raporda görülüyor; Full düğmesi yeni layout üretmiyor.
- Geometry yerel, routing/validation global, navigation ayrı ölçülüyor ayrımını açıklayabiliyorsun.

## 14. Bütün dosyaların tam kodu

Aşağıdaki bloklar paketteki Source dosyalarıyla birebir aynıdır. Kodları yeni/değişen dosyalara sen uygulayacaksın.

Doğrulama: Paket kaynakları ana Source'a uygulanmadan ayrı proje kopyasında UE 5.7.4, Development Editor / Win64 hedefinde derlendi. Build başarılı. `PlayableSketch.Geometry.LocalRebuild` otomasyon testi başarılı (10 bağımsız edit ve ek fallback/cleanup/engel kontrolleri). Çalıştırma NullRHI ile yapıldı; görsel kalite, gerçek Pawn ile fizik geçişi, kendi assetlerinde Undo/Redo ve save/reopen kontrollerini uygulamadan sonra sen yapmalısın. Ham sonuç `test-result.json` dosyasında.

<!-- FULL_SOURCE_START -->

### DEĞİŞTİR: `Source/PlayableSketch/PlayableSketchLevelActor.cpp`

```cpp
#include "PlayableSketchLevelActor.h"
#include "HAL/PlatformTime.h"
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
#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"

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
                RebuildLocalGeometry();
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
    ComponentRegistry.Clear(*this);
    PublishedGlobalSignature.Reset();
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    LastIssues.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");
    LastRebuildReport = TEXT("Result=Cleared");
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
    const double NavigationStart = FPlatformTime::Seconds();

    if (!FPlayableSketchGridNavigationTests::Run(
        GeneratedFloorPlan,
        GraphAsset->Graph.StartRoomId,
        GraphAsset->Graph.GoalRoomId,
        GridStepCm,
        Path))
    {
        UE_LOG(LogTemp, Warning, TEXT("NavigationMs=%.3f Result=Failed"),
            (FPlatformTime::Seconds() - NavigationStart) * 1000.0);
        return;
    }
    UE_LOG(LogTemp, Display, TEXT("NavigationMs=%.3f Result=Passed"),
        (FPlatformTime::Seconds() - NavigationStart) * 1000.0);
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
    RebuildLocalGeometry();
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

    const double ValidationStart = FPlatformTime::Seconds();
    LastIssues = FPlayableSketchValidation::ValidatePlan(GraphAsset->Graph, Plan, Pieces, GetValidationSettings());
    ValidationMs += (FPlatformTime::Seconds() - ValidationStart) * 1000.0;

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Validation failed. Preview cleared."));
        return false;
    }

    return true;
}

void APlayableSketchLevelActor::GenerateLayout()
{
    RebuildStartSeconds = FPlatformTime::Seconds();
    ValidationMs = 0.0;
    PlanMs = 0.0;
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

    const double InputStart = FPlatformTime::Seconds();
    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());
    ValidationMs += (FPlatformTime::Seconds() - InputStart) * 1000.0;

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

    PlanMs = FMath::Max(0.0, (FPlatformTime::Seconds() - RebuildStartSeconds) * 1000.0 - ValidationMs);
    PublishCandidate(Candidate, Pieces, true, TEXT("Generate Layout requested new placements"));
}

void APlayableSketchLevelActor::RebuildGeometry()
{
    UpdateGeometry(true);
}

void APlayableSketchLevelActor::RebuildLocalGeometry()
{
    UpdateGeometry(false);
}

FString APlayableSketchLevelActor::GetGlobalRebuildSignature() const
{
    if (!GraphAsset) return TEXT("NoGraphAsset");
    return GetPathNameSafe(GraphAsset.Get()) + FString::Printf(
        TEXT("|%d|%d|%d|%d|%d|%d|%.17g|%.17g|%.17g|%.17g|%.17g|%.17g|%.17g|%.17g"),
        GraphAsset->Graph.Seed, GraphAsset->Graph.SchemaVersion,
        GridStepCm, RoomGapCm, DoorCornerMarginCm, MaxPlacementAttempts,
        FloorThicknessCm, WallHeightCm, WallThicknessCm, DoorHeightCm,
        MinCorridorWidthCm, PawnRadiusCm, PawnHeightCm, ClearanceCm);
}

void APlayableSketchLevelActor::UpdateGeometry(bool bForceFull)
{
    RebuildStartSeconds = FPlatformTime::Seconds();
    ValidationMs = 0.0;
    PlanMs = 0.0;
    LastAttemptSignature = GetSourceSignature();
    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }
    const double InputStart = FPlatformTime::Seconds();
    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());
    ValidationMs += (FPlatformTime::Seconds() - InputStart) * 1000.0;
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
    if (!BuildCandidate(Candidate, Pieces)) return;
    PlanMs = FMath::Max(0.0, (FPlatformTime::Seconds() - RebuildStartSeconds) * 1000.0 - ValidationMs);

    bool bFull = bForceFull;
    FString Reason = bFull ? TEXT("Explicit full geometry rebuild") : TEXT("Descriptor changes only");
    if (!bFull && PublishedSignature.IsEmpty())
    {
        bFull = true;
        Reason = TEXT("Fallback: no published snapshot");
    }
    else if (!bFull && PublishedGlobalSignature != GetGlobalRebuildSignature())
    {
        bFull = true;
        Reason = TEXT("Fallback: graph asset, seed, schema or global settings changed; saved placements retained");
    }
    else if (!bFull && !ComponentRegistry.IsHealthy(*this))
    {
        bFull = true;
        Reason = TEXT("Fallback: component registry or scene was modified");
    }
    PublishCandidate(Candidate, Pieces, bFull, Reason);
}

void APlayableSketchLevelActor::PublishCandidate(
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
    bool bFull, const FString& Reason)
{
    const double SpecStart = FPlatformTime::Seconds();
    TArray<FPlayableSketchComponentSpec> Specs;
    auto AddFloor = [&](const FPlayableSketchRect& Bounds, const FGuid& Id, bool bRoom,
                        UMaterialInterface* Material)
    {
        FPlayableSketchComponentSpec S;
        S.SourceId = Id;
        S.bRoom = bRoom;
        S.Kind = EPlayableSketchPieceKind::Floor;
        const FVector2D Size = Bounds.Max - Bounds.Min;
        const FVector2D Center = (Bounds.Min + Bounds.Max) * 0.5;
        S.CenterCm = FVector(Center.X, Center.Y, -FloorThicknessCm * 0.5);
        S.SizeCm = FVector(Size.X, Size.Y, FloorThicknessCm);
        S.Material = Material;
        Specs.Add(S);
    };
    for (const FPlayableSketchPlacedRoom& Placed : Plan.Rooms)
    {
        UMaterialInterface* Material = DefaultFloorMaterial.Get();
        const FPlayableSketchRoom* Room = GraphAsset->Graph.Rooms.FindByPredicate(
            [&](const FPlayableSketchRoom& R) { return R.RoomId == Placed.RoomId; });
        if (Room)
        {
            if (Room->RoomRole == EPlayableSketchRoomRole::Start && StartFloorMaterial)
                Material = StartFloorMaterial.Get();
            else if (Room->RoomRole == EPlayableSketchRoomRole::Goal && GoalFloorMaterial)
                Material = GoalFloorMaterial.Get();
            else if (Room->RoomType == EPlayableSketchRoomType::Hub && HubFloorMaterial)
                Material = HubFloorMaterial.Get();
        }
        AddFloor(Placed.Bounds, Placed.RoomId, true, Material);
    }
    for (const FPlayableSketchCorridor& Corridor : Plan.Corridors)
        for (const FPlayableSketchRect& Rect : FPlayableSketchFloorBuilder::BuildCorridorFloorRects(Corridor.Footprints))
            AddFloor(Rect, Corridor.ConnectionId, false, DefaultFloorMaterial.Get());
    for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
    {
        FPlayableSketchComponentSpec S;
        S.SourceId = Piece.SourceId;
        S.bRoom = Piece.bRoom;
        S.Kind = Piece.Role == EPlayableSketchGeometryRole::Lintel
            ? EPlayableSketchPieceKind::Lintel : EPlayableSketchPieceKind::Wall;
        S.CenterCm = Piece.CenterCm;
        S.SizeCm = Piece.SizeCm;
        S.Material = WallMaterial.Get();
        Specs.Add(S);
    }
    FPlayableSketchComponentRegistry::AssignKeys(Specs);
    PlanMs += (FPlatformTime::Seconds() - SpecStart) * 1000.0;
    FString Error;
    if (!ComponentRegistry.Apply(*this, Specs, bFull, LastUpdateStats, Error))
    {
        // Apply rolls back staged components. The accepted preview stays visible but stale.
        PreviewPathPoints.Reset();
        bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty();
        PreviewStatus = TEXT("Geometry apply failed. Previous preview retained; it is not current.");
        LastRebuildReport = TEXT("Result=ApplyFailed; previous preview retained as stale.");
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-G003");
        Issue.Message = Error;
        LastIssues = { Issue };
        LogIssues();
        return;
    }
    GeneratedFloorPlan = Plan;
    PublishedSignature = GetSourceSignature();
    PublishedGlobalSignature = GetGlobalRebuildSignature();
    LastAttemptSignature = PublishedSignature;
    PreviewPathPoints.Reset();
    bPreviewStale = false;
    PreviewStatus = bFull ? TEXT("Current valid preview. Full geometry rebuild completed.")
                         : TEXT("Current valid preview. Local geometry update completed.");
    LastRebuildReport = FString::Printf(
        TEXT("Mode=%s Reason=%s DirtyRooms=%d DirtyConnections=%d Created=%d Updated=%d Removed=%d Kept=%d PlanMs=%.3f DirtyMs=%.3f ApplyMs=%.3f ValidationMs=%.3f TotalMs=%.3f Navigation=not-run"),
        bFull ? TEXT("Full") : TEXT("Local"), *Reason,
        LastUpdateStats.DirtyRooms.Num(), LastUpdateStats.DirtyConnections.Num(),
        LastUpdateStats.Created, LastUpdateStats.Updated, LastUpdateStats.Removed, LastUpdateStats.Kept,
        PlanMs, LastUpdateStats.DirtyMs, LastUpdateStats.ApplyMs, ValidationMs,
        (FPlatformTime::Seconds() - RebuildStartSeconds) * 1000.0);
    UE_LOG(LogTemp, Display, TEXT("%s"), *LastRebuildReport);
    LogIssues();
}

void APlayableSketchLevelActor::InvalidatePreview(
    const TArray<FPlayableSketchValidationIssue>& Issues,
    const FString& Status)
{
    LastIssues = Issues;
    AnnotateIssues();
    ComponentRegistry.Clear(*this);
    PublishedGlobalSignature.Reset();
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = Status;
    LastRebuildReport = TEXT("Result=Rejected; preview cleared; see Last Issues.");
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
        RebuildLocalGeometry();
    }
}

#if WITH_EDITOR
void APlayableSketchLevelActor::PostEditUndo()
{
    Super::PostEditUndo();
    LastAttemptSignature.Reset();
    if (bAutoRebuildGeometry) RebuildLocalGeometry();
}
#endif

void APlayableSketchLevelActor::TestAuthoringValidation()
{
    FPlayableSketchAuthoringValidationTests::Run();
}

void APlayableSketchLevelActor::TestRebuildEquivalence()
{
    if (!GetWorld() || GetWorld()->IsGameWorld())
    {
        UE_LOG(LogTemp, Error, TEXT("Run rebuild equivalence in the Editor world."));
        return;
    }
    const auto PreviousValues = ComponentRegistry.Capture();
    const auto PreviousPointers = ComponentRegistry.GetPointers();
    RebuildLocalGeometry();
    if (bPreviewStale || PublishedSignature != GetSourceSignature() || GeneratedFloorPlan.Rooms.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("Equivalence cannot run: current design is invalid or unpublished."));
        return;
    }
    const bool bWasLocal = LastRebuildReport.StartsWith(TEXT("Mode=Local"));
    FString Error;
    bool bPassed = ComponentRegistry.IsHealthy(*this) && ComponentRegistry.Verify(Error);
    const auto LocalValues = ComponentRegistry.Capture();
    const auto LocalPointers = ComponentRegistry.GetPointers();
    int32 StableCount = 0;
    if (bWasLocal)
    {
        for (const auto& Pair : PreviousValues)
        {
            const FString* NewValue = LocalValues.Find(Pair.Key);
            if (!NewValue || *NewValue != Pair.Value) continue;
            const auto* OldPointer = PreviousPointers.Find(Pair.Key);
            const auto* NewPointer = LocalPointers.Find(Pair.Key);
            if (!OldPointer || !NewPointer || *OldPointer != *NewPointer) bPassed = false;
            else ++StableCount;
        }
    }
    auto Fingerprint = [](const FPlayableSketchFloorPlan& Plan)
    {
        TArray<FString> Lines;
        auto RectText = [](const FPlayableSketchRect& R)
        {
            return FString::Printf(TEXT("%.17g,%.17g,%.17g,%.17g"), R.Min.X, R.Min.Y, R.Max.X, R.Max.Y);
        };
        auto DoorText = [](const FPlayableSketchDoorEndpoint& D)
        {
            return FString::Printf(TEXT("%s/%d/%.17g/%.17g/%.17g"), *D.RoomId.ToString(),
                static_cast<int32>(D.WallSide), D.PositionCm.X, D.PositionCm.Y, D.WidthCm);
        };
        for (const FPlayableSketchPlacedRoom& R : Plan.Rooms)
            Lines.Add(TEXT("Room/") + R.RoomId.ToString() + TEXT("/") + RectText(R.Bounds));
        for (const FPlayableSketchCorridor& C : Plan.Corridors)
        {
            const FString Prefix = TEXT("Connection/") + C.ConnectionId.ToString();
            Lines.Add(Prefix + TEXT("/Doors/") + DoorText(C.DoorA) + TEXT("/") + DoorText(C.DoorB));
            for (const FPlayableSketchRect& R : C.Footprints)
                Lines.Add(Prefix + TEXT("/Footprint/") + RectText(R));
        }
        Lines.Sort();
        return FString::Join(Lines, TEXT("\n"));
    };
    const FString LocalPlan = Fingerprint(GeneratedFloorPlan);
    RebuildGeometry();
    const auto FullValues = ComponentRegistry.Capture();
    bPassed = bPassed && !bPreviewStale && PublishedSignature == GetSourceSignature()
        && LocalPlan == Fingerprint(GeneratedFloorPlan)
        && LocalValues.Num() == FullValues.Num()
        && ComponentRegistry.IsHealthy(*this) && ComponentRegistry.Verify(Error);
    for (const auto& Pair : LocalValues)
    {
        const FString* Full = FullValues.Find(Pair.Key);
        if (!Full || *Full != Pair.Value) bPassed = false;
    }
    // Full must replace the old components, including their physics state.
    const auto FullPointers = ComponentRegistry.GetPointers();
    for (const auto& Pair : LocalPointers)
    {
        const UStaticMeshComponent* Old = Pair.Value.Get();
        if (Old && Old->IsRegistered()) bPassed = false;
        const auto* FullPointer = FullPointers.Find(Pair.Key);
        if (FullPointer && *FullPointer == Pair.Value) bPassed = false;
    }
    UE_LOG(LogTemp, Display, TEXT("%s: Rebuild equivalence. LocalRan=%d StableComponents=%d Pieces=%d %s"),
        bPassed ? TEXT("PASS") : TEXT("FAIL"), bWasLocal, StableCount, LocalValues.Num(), *Error);
}
```

### DEĞİŞTİR: `Source/PlayableSketch/PlayableSketchLevelActor.h`

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
#include "Geometry/PlayableSketchComponentRegistry.h"
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

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void RebuildLocalGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestRebuildEquivalence();

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Rebuild")
    FString LastRebuildReport;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateCurrentDesign();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestAuthoringValidation();

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
    friend class FPlayableSketchLocalRebuildTests;
    FString PublishedSignature;
    FString PublishedGlobalSignature;
    FPlayableSketchComponentRegistry ComponentRegistry;
    FPlayableSketchUpdateStats LastUpdateStats;
    double RebuildStartSeconds = 0.0;
    double ValidationMs = 0.0;
    double PlanMs = 0.0;

    FString GetGlobalRebuildSignature() const;
    void UpdateGeometry(bool bForceFull);

    FString GetSourceSignature() const;
    FPlayableSketchValidationSettings GetValidationSettings() const;
    bool ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const;
    bool BuildCandidate(FPlayableSketchFloorPlan& Plan, TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces, bool bFull = true, const FString& Reason = TEXT("Explicit full rebuild"));
    void InvalidatePreview(const TArray<FPlayableSketchValidationIssue>& Issues, const FString& Status);
    void FailStage(const TCHAR* Code, const FString& Message);
    void AnnotateIssues();
    void LogIssues() const;
    void DrawValidationIssues();
};
```

### YENİ: `Source/PlayableSketch/Private/Geometry/PlayableSketchComponentRegistry.cpp`

```cpp
#include "Geometry/PlayableSketchComponentRegistry.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"

namespace
{
    const FName RegistryTag(TEXT("PlayableSketch.RegistryPiece"));
    const FName FloorTag(TEXT("PlayableSketch.GeneratedFloor"));
    const FName WallTag(TEXT("PlayableSketch.GeneratedWall"));

    bool IsGenerated(const UStaticMeshComponent& C)
    {
        return C.ComponentHasTag(RegistryTag) || C.ComponentHasTag(FloorTag)
            || C.ComponentHasTag(WallTag);
    }

    void Destroy(AActor& Owner, UStaticMeshComponent* C)
    {
        if (IsValid(C))
        {
            C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            Owner.RemoveInstanceComponent(C);
            C->DestroyComponent();
        }
    }

    FVector ScaleFor(const FPlayableSketchComponentSpec& S, const UStaticMesh& Mesh)
    {
        const FVector M = Mesh.GetBoundingBox().GetSize();
        return FVector(S.SizeCm.X / M.X, S.SizeCm.Y / M.Y, S.SizeCm.Z / M.Z);
    }

    void Configure(UStaticMeshComponent& C, const FPlayableSketchComponentSpec& S,
        UStaticMesh& Mesh, bool bActive)
    {
        const bool bFloor = S.Kind == EPlayableSketchPieceKind::Floor;
        const FVector Scale = ScaleFor(S, Mesh);
        C.SetStaticMesh(&Mesh);
        C.SetRelativeTransform(FTransform(FQuat::Identity,
            S.CenterCm - Mesh.GetBoundingBox().GetCenter() * Scale, Scale));
        // nullptr also clears a previous material override.
        C.SetMaterial(0, S.Material.Get());
        C.SetCollisionProfileName(TEXT("BlockAllDynamic"));
        C.SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
        C.SetGenerateOverlapEvents(false);
        C.SetCanEverAffectNavigation(false);
        C.CanCharacterStepUpOn = bFloor ? ECB_Yes : ECB_No;
        C.SetCollisionEnabled(bActive ? ECollisionEnabled::QueryAndPhysics
                                     : ECollisionEnabled::NoCollision);
        C.SetVisibility(bActive);
        C.SetHiddenInGame(!bActive);
        // Staged components receive tags only at commit, so Clear ignores them.
        if (bActive)
        {
            C.ComponentTags.Reset();
            C.ComponentTags.Add(RegistryTag);
            C.ComponentTags.Add(bFloor ? FloorTag : WallTag);
            C.ComponentTags.Add(FName(*FString::Printf(TEXT("ComponentKey=%s"),
                *S.Key.ToString())));
            C.ComponentTags.Add(FName(*FString::Printf(TEXT("%s=%s"),
                S.bRoom ? TEXT("RoomId") : TEXT("ConnectionId"),
                *S.SourceId.ToString())));
            C.ComponentTags.Add(FName(bFloor
                ? (S.bRoom ? TEXT("PlayableSketch.RoomFloor") : TEXT("PlayableSketch.CorridorFloor"))
                : (S.Kind == EPlayableSketchPieceKind::Lintel
                    ? TEXT("PlayableSketch.Lintel") : TEXT("PlayableSketch.Wall"))));
        }
    }
}

bool FPlayableSketchComponentSpec::SameValue(const FPlayableSketchComponentSpec& O) const
{
    return Key == O.Key && SourceId == O.SourceId && bRoom == O.bRoom
        && Kind == O.Kind && CenterCm == O.CenterCm && SizeCm == O.SizeCm
        && Material.Get() == O.Material.Get();
}

void FPlayableSketchComponentRegistry::AssignKeys(TArray<FPlayableSketchComponentSpec>& Specs)
{
    Specs.Sort([](const FPlayableSketchComponentSpec& A, const FPlayableSketchComponentSpec& B)
    {
        if (A.bRoom != B.bRoom) return A.bRoom;
        if (A.SourceId != B.SourceId) return A.SourceId.ToString() < B.SourceId.ToString();
        if (A.Kind != B.Kind) return static_cast<uint8>(A.Kind) < static_cast<uint8>(B.Kind);
        if (A.CenterCm.X != B.CenterCm.X) return A.CenterCm.X < B.CenterCm.X;
        if (A.CenterCm.Y != B.CenterCm.Y) return A.CenterCm.Y < B.CenterCm.Y;
        if (A.CenterCm.Z != B.CenterCm.Z) return A.CenterCm.Z < B.CenterCm.Z;
        if (A.SizeCm.X != B.SizeCm.X) return A.SizeCm.X < B.SizeCm.X;
        if (A.SizeCm.Y != B.SizeCm.Y) return A.SizeCm.Y < B.SizeCm.Y;
        return A.SizeCm.Z < B.SizeCm.Z;
    });
    TMap<FString, int32> Counts;
    for (FPlayableSketchComponentSpec& S : Specs)
    {
        const FString Prefix = FString::Printf(TEXT("%s/%s/%d"),
            S.bRoom ? TEXT("Room") : TEXT("Connection"),
            *S.SourceId.ToString(), static_cast<int32>(S.Kind));
        int32& Index = Counts.FindOrAdd(Prefix);
        S.Key = FName(*FString::Printf(TEXT("%s/%d"), *Prefix, Index++));
    }
}

bool FPlayableSketchComponentRegistry::IsHealthy(const AActor& Owner) const
{
    int32 SceneCount = 0;
    TArray<UStaticMeshComponent*> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);
    for (const UStaticMeshComponent* C : Components)
        if (IsValid(C) && IsGenerated(*C)) ++SceneCount;
    if (SceneCount != Entries.Num()) return false;
    for (const auto& Pair : Entries)
    {
        const UStaticMeshComponent* C = Pair.Value.Component.Get();
        if (!C || C->GetOwner() != &Owner || !C->IsRegistered() || !IsGenerated(*C))
            return false;
    }
    FString Error;
    return Verify(Error);
}

void FPlayableSketchComponentRegistry::Clear(AActor& Owner)
{
    TArray<UStaticMeshComponent*> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);
    for (UStaticMeshComponent* C : Components)
        if (IsValid(C) && IsGenerated(*C)) Destroy(Owner, C);
    Entries.Reset();
}

bool FPlayableSketchComponentRegistry::Apply(AActor& Owner,
    const TArray<FPlayableSketchComponentSpec>& Specs, bool bFull,
    FPlayableSketchUpdateStats& Stats, FString& Error)
{
    Stats = FPlayableSketchUpdateStats();
    Error.Reset();
    if (!Owner.GetWorld() || !Owner.GetRootComponent())
    {
        Error = TEXT("Missing world or root component.");
        return false;
    }
    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Mesh || Mesh->GetBoundingBox().GetSize().GetMin() <= 0.0)
    {
        Error = TEXT("Invalid Engine Cube mesh.");
        return false;
    }
    TMap<FName, FPlayableSketchComponentSpec> Desired;
    for (const FPlayableSketchComponentSpec& S : Specs)
    {
        if (S.Key.IsNone() || !S.SourceId.IsValid() || S.CenterCm.ContainsNaN()
            || S.SizeCm.ContainsNaN() || S.SizeCm.GetMin() <= 0.0 || Desired.Contains(S.Key))
        {
            Error = TEXT("Invalid or duplicate component descriptor.");
            return false;
        }
        Desired.Add(S.Key, S);
    }
    if (!bFull && !IsHealthy(Owner))
    {
        Error = TEXT("Registry is stale. A full geometry rebuild is required.");
        return false;
    }
    const double DirtyStart = FPlatformTime::Seconds();
    TSet<FName> Changed;
    TArray<FName> Removed;
    auto MarkOwner = [&](const FPlayableSketchComponentSpec& S)
    {
        (S.bRoom ? Stats.DirtyRooms : Stats.DirtyConnections).Add(S.SourceId);
    };
    for (const auto& Pair : Desired)
    {
        const FEntry* Old = Entries.Find(Pair.Key);
        if (bFull || !Old || !Old->Spec.SameValue(Pair.Value))
        {
            Changed.Add(Pair.Key);
            MarkOwner(Pair.Value);
        }
        else ++Stats.Kept;
    }
    for (const auto& Pair : Entries)
    {
        if (bFull || !Desired.Contains(Pair.Key))
        {
            Removed.Add(Pair.Key);
            MarkOwner(Pair.Value.Spec);
        }
    }
    Stats.DirtyMs = (FPlatformTime::Seconds() - DirtyStart) * 1000.0;
    const double ApplyStart = FPlatformTime::Seconds();

    // Prepare every new component before touching the published scene.
    TMap<FName, UStaticMeshComponent*> Staged;
    auto Rollback = [&]()
    {
        for (const auto& Pair : Staged) Destroy(Owner, Pair.Value);
    };
    for (const FName Key : Changed)
    {
        if (!bFull && Entries.Contains(Key)) continue;
        UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(&Owner, NAME_None, RF_Transient);
        if (!C)
        {
            Rollback();
            Error = TEXT("Component allocation failed.");
            return false;
        }
        Staged.Add(Key, C);
        C->SetMobility(EComponentMobility::Movable);
        C->SetupAttachment(Owner.GetRootComponent());
        Configure(*C, Desired.FindChecked(Key), *Mesh, false);
        Owner.AddInstanceComponent(C);
        C->RegisterComponent();
        if (!C->IsRegistered())
        {
            Rollback();
            Error = TEXT("Component registration failed.");
            return false;
        }
    }

    // Commit. All recoverable allocation/registration errors were handled above.
    if (bFull)
    {
        Stats.Removed = Entries.Num();
        Clear(Owner);
    }
    else
    {
        for (const FName Key : Removed)
        {
            Destroy(Owner, Entries.FindChecked(Key).Component.Get());
            Entries.Remove(Key);
            ++Stats.Removed;
        }
    }
    for (const FName Key : Changed)
    {
        UStaticMeshComponent* C = nullptr;
        if (UStaticMeshComponent** NewComponent = Staged.Find(Key))
        {
            C = *NewComponent;
            ++Stats.Created;
        }
        else
        {
            C = Entries.FindChecked(Key).Component.Get();
            ++Stats.Updated;
        }
        const FPlayableSketchComponentSpec& S = Desired.FindChecked(Key);
        Configure(*C, S, *Mesh, true);
        FEntry Entry;
        Entry.Spec = S;
        Entry.Component = C;
        Entries.Add(Key, Entry);
    }
    Stats.ApplyMs = (FPlatformTime::Seconds() - ApplyStart) * 1000.0;
    return true;
}

bool FPlayableSketchComponentRegistry::Verify(FString& Error) const
{
    Error.Reset();
    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Mesh) { Error = TEXT("Engine Cube missing."); return false; }
    for (const auto& Pair : Entries)
    {
        const FPlayableSketchComponentSpec& S = Pair.Value.Spec;
        const UStaticMeshComponent* C = Pair.Value.Component.Get();
        const FVector Scale = ScaleFor(S, *Mesh);
        UMaterialInterface* ExpectedMaterial = S.Material.IsValid()
            ? S.Material.Get() : Mesh->GetMaterial(0);
        if (!C || !C->IsRegistered() || C->GetStaticMesh() != Mesh
            || !C->GetRelativeLocation().Equals(S.CenterCm - Mesh->GetBoundingBox().GetCenter() * Scale, 0.001)
            || !C->GetRelativeScale3D().Equals(Scale, 0.000001)
            || !C->GetRelativeRotation().IsNearlyZero(0.001)
            || C->GetMaterial(0) != ExpectedMaterial
            || C->GetCollisionEnabled() != ECollisionEnabled::QueryAndPhysics
            || C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block
            || C->GetCollisionProfileName() != FName(TEXT("BlockAllDynamic"))
            || C->CanCharacterStepUpOn != (S.Kind == EPlayableSketchPieceKind::Floor ? ECB_Yes : ECB_No)
            || !C->IsVisible())
        {
            Error = FString::Printf(TEXT("Scene mismatch: %s"), *Pair.Key.ToString());
            return false;
        }
    }
    return true;
}

TMap<FName, FString> FPlayableSketchComponentRegistry::Capture() const
{
    TMap<FName, FString> Result;
    for (const auto& Pair : Entries)
    {
        const UStaticMeshComponent* C = Pair.Value.Component.Get();
        if (!C) { Result.Add(Pair.Key, TEXT("Missing")); continue; }
        const FVector L = C->GetRelativeLocation();
        const FVector S = C->GetRelativeScale3D();
        const FRotator R = C->GetRelativeRotation();
        Result.Add(Pair.Key, FString::Printf(
            TEXT("%.17g,%.17g,%.17g|%.17g,%.17g,%.17g|%.17g,%.17g,%.17g|%s|%s|%d|%d|%d|%s"),
            L.X, L.Y, L.Z, S.X, S.Y, S.Z, R.Pitch, R.Yaw, R.Roll,
            *GetPathNameSafe(C->GetStaticMesh()), *GetPathNameSafe(C->GetMaterial(0)),
            static_cast<int32>(C->GetCollisionEnabled()),
            static_cast<int32>(C->GetCollisionResponseToChannel(ECC_Pawn)),
            static_cast<int32>(C->CanCharacterStepUpOn), *C->GetCollisionProfileName().ToString()));
    }
    return Result;
}

TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> FPlayableSketchComponentRegistry::GetPointers() const
{
    TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> Result;
    for (const auto& Pair : Entries) Result.Add(Pair.Key, Pair.Value.Component);
    return Result;
}
```

### YENİ: `Source/PlayableSketch/Private/Validation/Tests/PlayableSketchLocalRebuildTests.cpp`

```cpp
#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Materials/Material.h"
#include "Misc/AutomationTest.h"
#include "Layout/PlayableSketchCorridorRouting.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchLocalRebuildTests,
    "PlayableSketch.Geometry.LocalRebuild",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPlayableSketchLocalRebuildTests::RunTest(const FString& Parameters)
{
    const UWorld::InitializationValues IV = UWorld::InitializationValues()
        .AllowAudioPlayback(false).RequiresHitProxies(false).CreatePhysicsScene(true)
        .CreateNavigation(false).CreateAISystem(false).ShouldSimulatePhysics(false)
        .EnableTraceCollision(true).CreateFXSystem(false).SetTransactional(false);
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, NAME_None,
        nullptr, true, ERHIFeatureLevel::Num, &IV);
    if (!TestNotNull(TEXT("Transient test world"), World)) return false;
    APlayableSketchLevelActor* Local = World->SpawnActor<APlayableSketchLevelActor>();
    APlayableSketchLevelActor* Full = World->SpawnActor<APlayableSketchLevelActor>();
    if (!Local || !Full)
    {
        AddError(TEXT("Test actors could not be created."));
        World->DestroyWorld(false);
        return false;
    }
    Local->bAutoRebuildGeometry = Full->bAutoRebuildGeometry = false;
    UPlayableSketchGraphAsset* Asset = NewObject<UPlayableSketchGraphAsset>(Local);
    Local->GraphAsset = Full->GraphAsset = Asset;
    UMaterialInterface* HubMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    Local->HubFloorMaterial = Full->HubFloorMaterial = HubMaterial;

    FPlayableSketchGraph Base;
    const FVector2D Positions[] = { {0, 0}, {1400, 0}, {1400, 1400}, {0, 1400} };
    for (int32 I = 0; I < 4; ++I)
    {
        FPlayableSketchRoom R;
        R.RoomId = FGuid(I + 1, 0, 0, 1);
        R.PositionMode = EPlayableSketchPositionMode::Locked;
        R.PositionCm = Positions[I];
        R.RoomRole = I == 0 ? EPlayableSketchRoomRole::Start
            : (I == 2 ? EPlayableSketchRoomRole::Goal : EPlayableSketchRoomRole::None);
        Base.Rooms.Add(R);
    }
    for (int32 I = 0; I < 4; ++I)
    {
        FPlayableSketchConnection C;
        C.ConnectionId = FGuid(100 + I, 0, 0, 1);
        C.RoomAId = Base.Rooms[I].RoomId;
        C.RoomBId = Base.Rooms[(I + 1) % 4].RoomId;
        Base.Connections.Add(C);
    }
    Base.StartRoomId = Base.Rooms[0].RoomId;
    Base.GoalRoomId = Base.Rooms[2].RoomId;

    auto ComparePlans = [&](const FPlayableSketchFloorPlan& A, const FPlayableSketchFloorPlan& B)
    {
        bool bSame = A.Rooms.Num() == B.Rooms.Num() && A.Corridors.Num() == B.Corridors.Num();
        for (const FPlayableSketchPlacedRoom& R : A.Rooms)
        {
            const auto* Other = B.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& O)
                { return O.RoomId == R.RoomId; });
            bSame &= Other && R.Bounds.Min == Other->Bounds.Min && R.Bounds.Max == Other->Bounds.Max;
        }
        auto SameDoor = [](const FPlayableSketchDoorEndpoint& X, const FPlayableSketchDoorEndpoint& Y)
        {
            return X.RoomId == Y.RoomId && X.WallSide == Y.WallSide
                && X.PositionCm == Y.PositionCm && X.WidthCm == Y.WidthCm;
        };
        for (const FPlayableSketchCorridor& C : A.Corridors)
        {
            const auto* Other = B.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& O)
                { return O.ConnectionId == C.ConnectionId; });
            if (!Other) { bSame = false; continue; }
            bSame &= SameDoor(C.DoorA, Other->DoorA) && SameDoor(C.DoorB, Other->DoorB)
                && C.Footprints.Num() == Other->Footprints.Num();
            for (int32 I = 0; I < FMath::Min(C.Footprints.Num(), Other->Footprints.Num()); ++I)
                bSame &= C.Footprints[I].Min == Other->Footprints[I].Min
                    && C.Footprints[I].Max == Other->Footprints[I].Max;
        }
        return bSame;
    };

    for (int32 Edit = 0; Edit < 10; ++Edit)
    {
        Asset->Graph = Base;
        Local->RebuildGeometry();
        Full->RebuildGeometry();
        if (Local->GeneratedFloorPlan.Rooms.IsEmpty() || Full->GeneratedFloorPlan.Rooms.IsEmpty())
        {
            AddError(TEXT("Baseline generation failed."));
            break;
        }
        const auto Before = Local->ComponentRegistry.Capture();
        const auto BeforePointers = Local->ComponentRegistry.GetPointers();
        switch (Edit)
        {
        case 0: Asset->Graph.Rooms[1].RoomType = EPlayableSketchRoomType::Hub; break;
        case 1: Asset->Graph.Rooms[1].DisplayName = TEXT("Renamed Room"); break;
        case 2: Asset->Graph.Rooms[0].WidthCm = 650; break;
        case 3: Asset->Graph.Rooms[1].DepthCm = 650; break;
        case 4: Asset->Graph.Rooms[3].PositionCm.X -= 50; break;
        case 5: Asset->Graph.Connections[0].DoorWidthCm = 200; break;
        case 6: Asset->Graph.Connections[0].CorridorWidthCm = 250; break;
        case 7: Asset->Graph.Connections.RemoveAt(3); break;
        case 8:
            Asset->Graph.Rooms.RemoveAt(3);
            Asset->Graph.Connections.SetNum(2);
            break;
        case 9:
            Asset->Graph.Rooms.Swap(0, 3);
            Asset->Graph.Connections.Swap(0, 3);
            break;
        }
        Local->RebuildLocalGeometry();
        Full->RebuildGeometry();
        const FString Label = FString::Printf(TEXT("Edit %d"), Edit + 1);
        TestTrue(Label + TEXT(" used local update"), Local->LastRebuildReport.StartsWith(TEXT("Mode=Local")));
        TestFalse(Label + TEXT(" local is stale"), Local->bPreviewStale);
        TestEqual(Label + TEXT(" local source"), Local->PublishedSignature, Local->GetSourceSignature());
        TestEqual(Label + TEXT(" full source"), Full->PublishedSignature, Full->GetSourceSignature());
        TestTrue(Label + TEXT(" plans, doors, footprints"), ComparePlans(Local->GeneratedFloorPlan, Full->GeneratedFloorPlan));
        FString Error;
        TestTrue(Label + TEXT(" local scene and collision settings"), Local->ComponentRegistry.IsHealthy(*Local));
        TestTrue(Label + TEXT(" full scene and collision settings"), Full->ComponentRegistry.IsHealthy(*Full));
        const auto After = Local->ComponentRegistry.Capture();
        const auto Expected = Full->ComponentRegistry.Capture();
        const auto AfterPointers = Local->ComponentRegistry.GetPointers();
        TestEqual(Label + TEXT(" piece count"), After.Num(), Expected.Num());
        for (const auto& Pair : After)
        {
            const FString* Value = Expected.Find(Pair.Key);
            TestTrue(Label + TEXT(" piece ") + Pair.Key.ToString(), Value && *Value == Pair.Value);
        }
        for (const auto& Pair : Before)
        {
            const FString* Value = After.Find(Pair.Key);
            const auto* OldPointer = BeforePointers.Find(Pair.Key);
            const auto* NewPointer = AfterPointers.Find(Pair.Key);
            if (Value && *Value == Pair.Value)
                TestTrue(Label + TEXT(" unchanged identity ") + Pair.Key.ToString(),
                    OldPointer && NewPointer && *OldPointer == *NewPointer);
            if (!Value && OldPointer)
            {
                const UStaticMeshComponent* Old = OldPointer->Get();
                TestTrue(Label + TEXT(" deleted collider removed"), !Old || !Old->IsRegistered());
            }
        }
        if (Edit == 0 || Edit == 1 || Edit == 9)
        {
            TestEqual(Label + TEXT(" no new components"), Local->LastUpdateStats.Created, 0);
            TestEqual(Label + TEXT(" no removed components"), Local->LastUpdateStats.Removed, 0);
        }
        if (Edit == 1 || Edit == 9)
            TestEqual(Label + TEXT(" no geometry updates"), Local->LastUpdateStats.Updated, 0);
    }

    // Global fallback keeps saved/locked room placements.
    Asset->Graph = Base;
    Local->RebuildGeometry();
    const auto OldPlan = Local->GeneratedFloorPlan;
    ++Asset->Graph.Seed;
    Local->RebuildLocalGeometry();
    TestTrue(TEXT("Seed change triggers documented fallback"),
        Local->LastRebuildReport.Contains(TEXT("Fallback: graph asset, seed")));
    TestTrue(TEXT("Fallback retains placement"), ComparePlans(OldPlan, Local->GeneratedFloorPlan));

    // A moved room must invalidate even a corridor to which it is not connected.
    Asset->Graph = Base;
    Local->RebuildGeometry();
    FPlayableSketchFloorPlan Obstructed = Local->GeneratedFloorPlan;
    const FGuid UnrelatedId = Base.Connections[2].ConnectionId;
    const auto* Unrelated = Obstructed.Corridors.FindByPredicate(
        [&](const FPlayableSketchCorridor& C) { return C.ConnectionId == UnrelatedId; });
    if (TestNotNull(TEXT("Nonincident corridor exists"), Unrelated))
    {
        FPlayableSketchCorridorCandidate Candidate;
        Candidate.Footprints = Unrelated->Footprints;
        Obstructed.Rooms[0].Bounds = FPlayableSketchRect(
            FVector2D(650, 1400), FVector2D(1250, 2000));
        FString Error;
        TestFalse(TEXT("Unrelated corridor footprint detects moved room"),
            FPlayableSketchCorridorRouting::ValidateCandidate(Candidate, Obstructed.Rooms, {}, Error));
        TestTrue(TEXT("Obstruction error identifies the moved room"),
            Error.Contains(Base.Rooms[0].RoomId.ToString()));
    }

    Local->ClearFloors();
    TestEqual(TEXT("Clear empties registry"), Local->ComponentRegistry.Capture().Num(), 0);
    TestTrue(TEXT("Clear removes generated scene components"), Local->ComponentRegistry.IsHealthy(*Local));
    Full->ClearFloors();
    World->DestroyWorld(false);
    return !HasAnyErrors();
}

#endif
```

### YENİ: `Source/PlayableSketch/Public/Geometry/PlayableSketchComponentRegistry.h`

```cpp
#pragma once

#include "CoreMinimal.h"

class AActor;
class UStaticMeshComponent;
class UMaterialInterface;

enum class EPlayableSketchPieceKind : uint8 { Floor, Wall, Lintel };

// Same owner + kind + canonical ordinal identifies the same output slot.
struct PLAYABLESKETCH_API FPlayableSketchComponentSpec
{
    FName Key;
    FGuid SourceId;
    bool bRoom = false;
    EPlayableSketchPieceKind Kind = EPlayableSketchPieceKind::Floor;
    FVector CenterCm = FVector::ZeroVector;
    FVector SizeCm = FVector::OneVector;
    TWeakObjectPtr<UMaterialInterface> Material;

    bool SameValue(const FPlayableSketchComponentSpec& Other) const;
};

struct PLAYABLESKETCH_API FPlayableSketchUpdateStats
{
    TSet<FGuid> DirtyRooms;
    TSet<FGuid> DirtyConnections;
    int32 Created = 0;
    int32 Updated = 0;
    int32 Removed = 0;
    int32 Kept = 0;
    double DirtyMs = 0.0;
    double ApplyMs = 0.0;
};

class PLAYABLESKETCH_API FPlayableSketchComponentRegistry
{
public:
    static void AssignKeys(TArray<FPlayableSketchComponentSpec>& Specs);
    bool IsHealthy(const AActor& Owner) const;
    void Clear(AActor& Owner);
    bool Apply(AActor& Owner, const TArray<FPlayableSketchComponentSpec>& Specs,
        bool bFull, FPlayableSketchUpdateStats& Stats, FString& Error);
    bool Verify(FString& Error) const;
    TMap<FName, FString> Capture() const;
    TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> GetPointers() const;

private:
    struct FEntry
    {
        FPlayableSketchComponentSpec Spec;
        TWeakObjectPtr<UStaticMeshComponent> Component;
    };
    TMap<FName, FEntry> Entries;
};
```

### DEĞİŞTİR: `Source/PlayableSketch/Public/Geometry/PlayableSketchFloorBuilder.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

class AActor;

class PLAYABLESKETCH_API FPlayableSketchFloorBuilder
{
public:
    static bool Build(AActor& Owner, const FPlayableSketchFloorPlan& FloorPlan, double ThicknessCm, FString& OutError);
    static void Clear(AActor& Owner);

    // Shared deterministic corridor floor decomposition; does not create components.
    static TArray<FPlayableSketchRect> BuildCorridorFloorRects(const TArray<FPlayableSketchRect>& Footprints);
};
```
