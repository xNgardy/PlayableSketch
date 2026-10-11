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
