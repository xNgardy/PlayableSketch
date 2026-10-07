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
}

void APlayableSketchLevelActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
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

    if (!FPlayableSketchLayoutGenerator::Generate(GraphAsset->Graph, GridStepCm, RoomGapCm, Result, Error, MaxPlacementAttempts))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchDoorGenerator::Generate(GraphAsset->Graph, Result, DoorCornerMarginCm, Error))
    {
        ClearFloors();
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchCorridorRouting::Generate(GraphAsset->Graph, Result, GridStepCm, Error))
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

    GeneratedFloorPlan = MoveTemp(Result);
}

void APlayableSketchLevelActor::ClearFloors()
{
    FPlayableSketchFloorBuilder::Clear(*this);
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
}

void APlayableSketchLevelActor::TestFloorPath()
{
    if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("Assign GraphAsset and run Generate Floors before testing the path."));
        return;
    }

    FPlayableSketchGridPath Path;

    if (!FPlayableSketchGridNavigationTests::Run(GeneratedFloorPlan, GraphAsset->Graph.StartRoomId, GraphAsset->Graph.GoalRoomId, GridStepCm, Path))
    {
        return;
    }

    const FTransform ActorTransform = GetActorTransform();

    for (int32 Index = 0; Index + 1 < Path.Points.Num(); ++Index)
    {
        const FVector A = ActorTransform.TransformPosition(FVector(Path.Points[Index].X, Path.Points[Index].Y, 10.0));
        const FVector B = ActorTransform.TransformPosition(FVector(Path.Points[Index + 1].X, Path.Points[Index + 1].Y, 10.0));

        DrawDebugLine(GetWorld(), A, B, FColor::Green, false, 20.0f, 0, 5.0f);
    }
}