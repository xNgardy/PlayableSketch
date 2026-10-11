# PlayableSketch — Authoring Validation testleri

Test adları yaptıkları işi anlatacak şekilde düzenlendi. Authoring, Room ve Connection verisini düzenleme işlemlerini ifade eder. Validation, bu düzenlemelerin geçerli bir tasarım üretip üretmediğini kontrol eder. Testlerin davranışı aynı kaldı; dosya, sınıf, fonksiyon, include, log ve automation adları birlikte değiştirildi.

## Uygulama

1. Unreal Editor'ı kapat.
2. Aşağıdaki iki Actor dosyasının içeriğini tam olarak değiştir.
3. İki test dosyasını aşağıdaki yeni dosya adlarıyla oluştur. Önceki isimlerle oluşturduğun bu test dosyaları varsa, onların yerine bu dosyaları kullan; iki sürümü Source altında birlikte bırakma.
4. Visual Studio'da Development Editor / Win64 yapılandırmasıyla build al. Visual Studio dosya listesini yenilemen gerekiyorsa .uproject üzerinden Generate Visual Studio project files çalıştır.
5. Unreal Editor'ı aç. Level Actor'ın Details panelinde PlayableSketch > Tests altında Test Authoring Validation düğmesine bas.
6. Output Log'da `Authoring validation tests finished: Failures=0` sonucunu kontrol et. Automation penceresindeki test yolu `PlayableSketch.Authoring.Validation` olur.

Bu isim değişikliği yalnızca aşağıdaki dört dosyayı etkiliyor. Source dosyaların otomatik değiştirilmedi; implementasyonu sen yapacaksın. Zip içinde önceki tam uygulama paketinin 14 dosyası da yeni isimlerle bulunuyor. Önceki paketi tamamen uyguladıysan yalnızca bu dört dosyayı güncellemen yeterli.

| Öğe | Yeni ad |
|---|---|
| Test dosyaları | PlayableSketchAuthoringValidationTests.h / .cpp |
| Test sınıfı | FPlayableSketchAuthoringValidationTests |
| Actor fonksiyonu | TestAuthoringValidation |
| Editör düğmesi | Test Authoring Validation |
| Automation testi | PlayableSketch.Authoring.Validation |

## Kontrol

Paketin dosya ve sembol adları, include yolları ve automation adı birlikte kontrol edildi. Kodda takvim aşaması belirten ad veya yorum satırı bulunmuyor. Önceki paket izole projede UE 5.7.4 Editor build ve 21 test kontrolünden geçmişti. Bu isim değişikliğinden sonra build ve Unreal testleri tekrar çalıştırılmadı.

## Değişen dört dosyanın tam son halleri

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

void APlayableSketchLevelActor::TestAuthoringValidation()
{
    FPlayableSketchAuthoringValidationTests::Run();
}
```

### Source/PlayableSketch/Public/Validation/Tests/PlayableSketchAuthoringValidationTests.h

```cpp
#pragma once

#include "CoreMinimal.h"

class PLAYABLESKETCH_API FPlayableSketchAuthoringValidationTests
{
public:
    static bool Run();
};
```

### Source/PlayableSketch/Private/Validation/Tests/PlayableSketchAuthoringValidationTests.cpp

```cpp
#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"
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

bool FPlayableSketchAuthoringValidationTests::Run()
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
            const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "TestResize", "Authoring validation test resize"));
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

    UE_LOG(LogTemp, Display, TEXT("Authoring validation tests finished: Failures=%d"), Failures);
    return Failures == 0;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchAuthoringValidationAutomationTest, "PlayableSketch.Authoring.Validation", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPlayableSketchAuthoringValidationAutomationTest::RunTest(const FString& Parameters)
{
    return FPlayableSketchAuthoringValidationTests::Run();
}
#endif
```

