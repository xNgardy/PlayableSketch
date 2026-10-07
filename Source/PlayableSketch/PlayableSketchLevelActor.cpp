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
        GenerateFloors();
    }
}

void APlayableSketchLevelActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    DrawFloorPathPreview();
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
    if (!GraphAsset)
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    FPlayableSketchFloorPlan Result;
    FString Error;

    if (!FPlayableSketchLayoutGenerator::Generate(
        GraphAsset->Graph,
        GridStepCm,
        RoomGapCm,
        Result,
        Error,
        MaxPlacementAttempts))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchDoorGenerator::Generate(
        GraphAsset->Graph,
        Result,
        DoorCornerMarginCm,
        Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchCorridorRouting::Generate(
        GraphAsset->Graph,
        Result,
        GridStepCm,
        Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    FPlayableSketchWallSettings Settings;
    Settings.HeightCm = WallHeightCm;
    Settings.ThicknessCm = WallThicknessCm;
    Settings.DoorHeightCm = DoorHeightCm;
    Settings.CornerMarginCm = DoorCornerMarginCm;

    TArray<FPlayableSketchGeometryDescriptor> WallPieces;

    if (!FPlayableSketchWallGeometry::Generate(Result, Settings, WallPieces, Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchFloorBuilder::Build(*this, Result, FloorThicknessCm, Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchWallBuilder::Build(*this, WallPieces, WallMaterial.Get(), Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    PreviewPathPoints.Reset();
    GeneratedFloorPlan = MoveTemp(Result);

    ApplyFloorMaterials();
}

void APlayableSketchLevelActor::ClearFloors()
{
    FPlayableSketchWallBuilder::Clear(*this);
    FPlayableSketchFloorBuilder::Clear(*this);

    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
}

void APlayableSketchLevelActor::TestFloorPath()
{
    PreviewPathPoints.Reset();

    if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty())
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("Assign GraphAsset and run Generate Floors before testing the path."));

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
    if (!GetWorld() || PreviewPathPoints.Num() < 2)
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