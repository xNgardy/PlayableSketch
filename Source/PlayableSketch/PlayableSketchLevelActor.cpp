#include "PlayableSketchLevelActor.h"
#include "HAL/PlatformTime.h"
#include "Navigation/PlayableSketchNavigationExamples.h"
#include "Misc/Paths.h"
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
            ResetNavigation();
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
    DrawNavigationGrid();
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
    ResetNavigation();
    LastIssues.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");
    LastRebuildReport = TEXT("Result=Cleared");
}

void APlayableSketchLevelActor::TestFloorPath()
{
    // Preserve the existing button, but use the solid/agent-aware analysis now.
    AnalyzeNavigation();
}
void APlayableSketchLevelActor::DrawFloorPathPreview()
{
    if (!GetWorld() || !bNavigationCurrent || PreviewPathPoints.Num() < 2 || bPreviewStale
        || PublishedSignature != GetSourceSignature() || !GetActorScale3D().Equals(FVector::OneVector, 0.0001)
        || !GetActorQuat().GetUpVector().Equals(FVector::UpVector, 0.0001))
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
        + GetPathNameSafe(GoalFloorMaterial.Get())
        + FString::Printf(TEXT("|NavigationMaxCells=%d"), NavigationMaxCells);
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
        ResetNavigation();
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
    ResetNavigation();
    bPreviewStale = false;
    RefreshNavigation(Pieces);
    PreviewStatus = bFull ? TEXT("Current valid preview. Full geometry rebuild completed.")
                         : TEXT("Current valid preview. Local geometry update completed.");
    LastRebuildReport = FString::Printf(
        TEXT("Mode=%s Reason=%s DirtyRooms=%d DirtyConnections=%d Created=%d Updated=%d Removed=%d Kept=%d PlanMs=%.3f DirtyMs=%.3f ApplyMs=%.3f ValidationMs=%.3f TotalMs=%.3f NavigationMs=%.3f NavigationAnalyzed=%d"),
        bFull ? TEXT("Full") : TEXT("Local"), *Reason,
        LastUpdateStats.DirtyRooms.Num(), LastUpdateStats.DirtyConnections.Num(),
        LastUpdateStats.Created, LastUpdateStats.Updated, LastUpdateStats.Removed, LastUpdateStats.Kept,
        PlanMs, LastUpdateStats.DirtyMs, LastUpdateStats.ApplyMs, ValidationMs,
        (FPlatformTime::Seconds() - RebuildStartSeconds) * 1000.0, NavigationResult.TotalMs, bNavigationCurrent);
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
    ResetNavigation();
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

FPlayableSketchNavigationSettings APlayableSketchLevelActor::GetNavigationSettings() const
{
    FPlayableSketchNavigationSettings Settings;
    Settings.CellSizeCm = GridStepCm;
    Settings.AgentRadiusCm = PawnRadiusCm;
    Settings.AgentHeightCm = PawnHeightCm;
    Settings.ClearanceCm = ClearanceCm;
    Settings.MaxCells = NavigationMaxCells;
    return Settings;
}

void APlayableSketchLevelActor::ResetNavigation()
{
    NavigationResult = FPlayableSketchNavigationResult();
    bNavigationCurrent = false;
    PreviewPathPoints.Reset();
    NavigationReport = TEXT("No current navigation analysis.");
}

void APlayableSketchLevelActor::RefreshNavigation(const TArray<FPlayableSketchGeometryDescriptor>& Pieces)
{
    ResetNavigation();
    if (!GetActorScale3D().Equals(FVector::OneVector, 0.0001)
        || !GetActorQuat().GetUpVector().Equals(FVector::UpVector, 0.0001))
    {
        NavigationReport = TEXT("Navigation requires unit Actor scale and a horizontal floor (yaw rotation is supported).");
        return;
    }
    FString Error;
    bNavigationCurrent = GraphAsset && FPlayableSketchNavigation::Analyze(GeneratedFloorPlan, Pieces,
        GraphAsset->Graph.StartRoomId, GraphAsset->Graph.GoalRoomId, GetNavigationSettings(), NavigationResult, Error);
    NavigationReport = bNavigationCurrent ? NavigationResult.Summary() : TEXT("Navigation analysis failed: ") + Error;
    if (bNavigationCurrent) PreviewPathPoints = NavigationResult.PathPoints;
    UE_LOG(LogTemp, Display, TEXT("%s"), *NavigationReport);
}

void APlayableSketchLevelActor::AnalyzeNavigation()
{
    ResetNavigation();
    if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty() || bPreviewStale
        || PublishedSignature != GetSourceSignature() || !ComponentRegistry.IsHealthy(*this))
    {
        NavigationReport = TEXT("Rebuild the current valid geometry before analyzing navigation.");
        UE_LOG(LogTemp, Warning, TEXT("%s"), *NavigationReport);
        return;
    }
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    FString Error;
    if (!FPlayableSketchWallGeometry::Generate(GeneratedFloorPlan, GetValidationSettings().Walls, Pieces, Error))
    {
        NavigationReport = TEXT("Navigation geometry failed: ") + Error;
        return;
    }
    RefreshNavigation(Pieces);
}

void APlayableSketchLevelActor::ExportNavigationReport()
{
    AnalyzeNavigation();
    if (!bNavigationCurrent) return;
    FPlayableSketchNavigationSample Sample;
    Sample.Name = GetName();
    Sample.Seed = GraphAsset->Graph.Seed;
    Sample.RoomCount = GeneratedFloorPlan.Rooms.Num();
    Sample.ConnectionCount = GeneratedFloorPlan.Corridors.Num();
    Sample.Settings = GetNavigationSettings();
    Sample.Result = NavigationResult;
    const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Navigation/NavigationReport.json"));
    FString Error;
    if (FPlayableSketchNavigation::ExportJson({ Sample }, Filename, Error))
    {
        NavigationExportPath = Filename;
        UE_LOG(LogTemp, Display, TEXT("Navigation report exported: %s"), *Filename);
    }
    else UE_LOG(LogTemp, Warning, TEXT("%s"), *Error);
}

void APlayableSketchLevelActor::RunNavigationExamples()
{
    TArray<FPlayableSketchNavigationSample> Samples;
    FString Error;
    const FString Filename = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Navigation/NavigationExamples.json"));
    if (!FPlayableSketchNavigationExamples::Run(Samples, Error)
        || !FPlayableSketchNavigation::ExportJson(Samples, Filename, Error))
    {
        UE_LOG(LogTemp, Warning, TEXT("Navigation examples failed: %s"), *Error);
        return;
    }
    NavigationExportPath = Filename;
    for (const auto& Sample : Samples)
        UE_LOG(LogTemp, Display, TEXT("%s: %s"), *Sample.Name, *Sample.Result.Summary());
    UE_LOG(LogTemp, Display, TEXT("Five fixed-layout navigation examples exported: %s"), *Filename);
}

void APlayableSketchLevelActor::DrawNavigationGrid()
{
    if (!bShowNavigationGrid || !bNavigationCurrent || !GetWorld() || bPreviewStale
        || PublishedSignature != GetSourceSignature() || !GetActorScale3D().Equals(FVector::OneVector, 0.0001)
        || !GetActorQuat().GetUpVector().Equals(FVector::UpVector, 0.0001)) return;
    const FTransform Transform = GetActorTransform();
    const double Half = NavigationResult.CellSizeCm * 0.45;
    const FVector Extent(Half, Half, 1.0);
    // Visualization is bounded independently of the analysis grid.
    const int32 Count = NavigationResult.Dimensions.X * NavigationResult.Dimensions.Y;
    const int32 Stride = FMath::Max(1, FMath::DivideAndRoundUp(Count, 5000));
    for (int32 Index = 0; Index < Count; Index += Stride)
    {
        const FIntPoint Cell(Index % NavigationResult.Dimensions.X, Index / NavigationResult.Dimensions.X);
        const bool bWalkable = NavigationResult.WalkableCells.Contains(Cell);
        if (!bWalkable && !bShowBlockedNavigationCells) continue;
        const FVector2D Center = NavigationResult.CellCenter(Cell);
        DrawDebugBox(GetWorld(), Transform.TransformPosition(FVector(Center.X, Center.Y, 5.0)),
            Extent, Transform.GetRotation(), bWalkable ? FColor::Cyan : FColor::Red, false, -1.0f, 0, 1.0f);
    }
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
