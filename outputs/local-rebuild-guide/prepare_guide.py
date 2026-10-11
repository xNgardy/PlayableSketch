from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
src = root / 'Source/PlayableSketch'
dst = out / 'Source/PlayableSketch'

def replace_once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new, 1)

h = (src / 'PlayableSketchLevelActor.h').read_text(encoding='utf-8-sig')
h = replace_once(h, '#include "PlayableSketchLevelActor.generated.h"', '#include "Geometry/PlayableSketchComponentRegistry.h"\n#include "PlayableSketchLevelActor.generated.h"')
h = replace_once(h, '    void RebuildGeometry();', '''    void RebuildGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void RebuildLocalGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestRebuildEquivalence();

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Rebuild")
    FString LastRebuildReport;''')
h = replace_once(h, '    FString PublishedSignature;', '''    friend class FPlayableSketchLocalRebuildTests;
    FString PublishedSignature;
    FString PublishedGlobalSignature;
    FPlayableSketchComponentRegistry ComponentRegistry;
    FPlayableSketchUpdateStats LastUpdateStats;
    double RebuildStartSeconds = 0.0;
    double ValidationMs = 0.0;
    double PlanMs = 0.0;

    FString GetGlobalRebuildSignature() const;
    void UpdateGeometry(bool bForceFull);''')
h = replace_once(h, 'void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces);', 'void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces, bool bFull = true, const FString& Reason = TEXT("Explicit full rebuild"));')
(dst / 'PlayableSketchLevelActor.h').write_text(h, encoding='utf-8')

c = (src / 'PlayableSketchLevelActor.cpp').read_text(encoding='utf-8-sig')
c = replace_once(c, '#include "PlayableSketchLevelActor.h"', '#include "PlayableSketchLevelActor.h"\n#include "HAL/PlatformTime.h"')

def method(text, name, body):
    pattern = re.compile(r'(?m)^(?:void|bool|FString) APlayableSketchLevelActor::' + name + r'\(')
    match = pattern.search(text)
    assert match, name
    start = match.start()
    opening = text.index('{', match.end())
    depth = 1
    end = opening + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[:start] + body.rstrip() + text[end:]

# Only the automatic call sites change. BeginPlay retains explicit full rebuild.
c = replace_once(c, '''            if (bAutoRebuildGeometry)
            {
                RebuildGeometry();
            }''', '''            if (bAutoRebuildGeometry)
            {
                RebuildLocalGeometry();
            }''')
c = replace_once(c, '''        RebuildGeometry();
    }
}

#if WITH_EDITOR
void APlayableSketchLevelActor::PostEditUndo()''', '''        RebuildLocalGeometry();
    }
}

#if WITH_EDITOR
void APlayableSketchLevelActor::PostEditUndo()''')
c = replace_once(c, 'if (bAutoRebuildGeometry) RebuildGeometry();', 'if (bAutoRebuildGeometry) RebuildLocalGeometry();')

# Clearing and invalidation must also clear the registry/snapshot.
c = c.replace('    FPlayableSketchWallBuilder::Clear(*this);\n    FPlayableSketchFloorBuilder::Clear(*this);',
    '    ComponentRegistry.Clear(*this);\n    PublishedGlobalSignature.Reset();')
c = replace_once(c, '    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");',
    '    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");\n    LastRebuildReport = TEXT("Result=Cleared");')
c = replace_once(c, '    PreviewStatus = Status;',
    '    PreviewStatus = Status;\n    LastRebuildReport = TEXT("Result=Rejected; preview cleared; see Last Issues.");')

c = replace_once(c, '    LastIssues = FPlayableSketchValidation::ValidatePlan(GraphAsset->Graph, Plan, Pieces, GetValidationSettings());', '''    const double ValidationStart = FPlatformTime::Seconds();
    LastIssues = FPlayableSketchValidation::ValidatePlan(GraphAsset->Graph, Plan, Pieces, GetValidationSettings());
    ValidationMs += (FPlatformTime::Seconds() - ValidationStart) * 1000.0;''')
c = replace_once(c, '''void APlayableSketchLevelActor::GenerateLayout()
{
    LastAttemptSignature''', '''void APlayableSketchLevelActor::GenerateLayout()
{
    RebuildStartSeconds = FPlatformTime::Seconds();
    ValidationMs = 0.0;
    PlanMs = 0.0;
    LastAttemptSignature''')
# Measure input validation in both generation and common update.
c = c.replace('''    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))''', '''    const double InputStart = FPlatformTime::Seconds();
    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());
    ValidationMs += (FPlatformTime::Seconds() - InputStart) * 1000.0;

    if (FPlayableSketchValidation::HasErrors(LastIssues))''', 1)
c = replace_once(c, '    PublishCandidate(Candidate, Pieces);\n}\n\nvoid APlayableSketchLevelActor::RebuildGeometry()', '''    PlanMs = FMath::Max(0.0, (FPlatformTime::Seconds() - RebuildStartSeconds) * 1000.0 - ValidationMs);
    PublishCandidate(Candidate, Pieces, true, TEXT("Generate Layout requested new placements"));
}

void APlayableSketchLevelActor::RebuildGeometry()''')

c = method(c, 'RebuildGeometry', '''void APlayableSketchLevelActor::RebuildGeometry()
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
}''')

c = method(c, 'PublishCandidate', '''void APlayableSketchLevelActor::PublishCandidate(
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
}''')

# Old helper would mutate components outside registry. Route it through the new publisher.
c = method(c, 'ApplyFloorMaterials', '''void APlayableSketchLevelActor::ApplyFloorMaterials()
{
    RebuildLocalGeometry();
}''')

# Optional grid preview gets an honest independent timer, not a fake zero.
c = replace_once(c, '    FPlayableSketchGridPath Path;\n', '    FPlayableSketchGridPath Path;\n    const double NavigationStart = FPlatformTime::Seconds();\n')
c = replace_once(c, '''        Path))
    {
        return;
    }

    PreviewPathPoints = MoveTemp(Path.Points);''', '''        Path))
    {
        UE_LOG(LogTemp, Warning, TEXT("NavigationMs=%.3f Result=Failed"),
            (FPlatformTime::Seconds() - NavigationStart) * 1000.0);
        return;
    }
    UE_LOG(LogTemp, Display, TEXT("NavigationMs=%.3f Result=Passed"),
        (FPlatformTime::Seconds() - NavigationStart) * 1000.0);
    PreviewPathPoints = MoveTemp(Path.Points);''')

c += '''

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
        return FString::Join(Lines, TEXT("\\n"));
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
'''
(dst / 'PlayableSketchLevelActor.cpp').write_text(c, encoding='utf-8')

floor = (src / 'Public/Geometry/PlayableSketchFloorBuilder.h').read_text(encoding='utf-8-sig')
floor = replace_once(floor, '\nprivate:\n', '\n    // Shared deterministic corridor floor decomposition; does not create components.\n')
(dst / 'Public/Geometry/PlayableSketchFloorBuilder.h').write_text(floor, encoding='utf-8')
print('Prepared three modified files in the guide package. Project Source was not edited.')
