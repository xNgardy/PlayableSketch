#include "Algo/Reverse.h"
#include "PlayableSketchLevelActor.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#if WITH_EDITOR
#include "ScopedTransaction.h"
#endif

namespace
{
FPlayableSketchExplicitSettings DesiredSettings(const APlayableSketchLevelActor &Actor,
                                                const FPlayableSketchExplicitSettings &Source)
{

    auto Value = [](float Current, double Original) {
        return Current == static_cast<float>(Original) ? Original : static_cast<double>(Current);
    };
    return {Value(Actor.WallThicknessCm, Source.WallThicknessCm),
            Value(Actor.WallHeightCm, Source.WallHeightCm),
            Value(Actor.DoorHeightCm, Source.DoorHeightCm),
            Value(Actor.FloorThicknessCm, Source.FloorThicknessCm)};
}
}

void APlayableSketchLevelActor::ImportCanonicalLayoutJson()
{
    const FString Path =
        FPaths::IsRelative(ImportLayoutJsonPath)
            ? FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), ImportLayoutJsonPath)
            : ImportLayoutJsonPath;
    FString Json, Error;
    if (ImportLayoutJsonPath.IsEmpty() || IFileManager::Get().FileSize(*Path) > 2 * 1024 * 1024 ||
        !FFileHelper::LoadFileToString(Json, *Path))
    {
        LastImportReport = TEXT(
            "Rejected: choose a readable canonical JSON file (maximum 2 MB). Existing design retained.");
        return;
    }
    ImportCanonicalLayoutJsonText(Json, Error);
}

bool APlayableSketchLevelActor::ImportCanonicalLayoutJsonText(const FString &Json,
                                                              FString &OutError)
{
    auto Reject = [&](const FString &Error) {
        OutError = Error;
        LastImportReport = TEXT("Rejected: ") + Error + TEXT(" Existing design retained.");
        return false;
    };
    if (!GetWorld() || !ImportedLayoutAsset || !GetActorScale3D().Equals(FVector::OneVector))
        return Reject(TEXT("Assign an ImportedLayoutAsset and use unit actor scale."));
#if WITH_EDITOR
    if (GetWorld()->WorldType != EWorldType::Editor &&
        GetWorld()->WorldType != EWorldType::EditorPreview)
        return Reject(TEXT("Canonical import is an Editor authoring action."));
#else
    return Reject(TEXT("Canonical import is an Editor authoring action."));
#endif
    FPlayableSketchExplicitLayout Layout;
    FPlayableSketchExplicitGeometry Geometry;
    FString Error;
    if (!FPlayableSketchExplicitLayoutBuilder::Parse(Json, Layout, Error) ||
        !BuildExplicitGeometry(Layout, Geometry, Error))
        return Reject(Error);
    if (!PublishExplicitLayout(
            Layout, Geometry, Json,
            LayoutSource != EPlayableSketchLayoutSource::ImportedExplicitLayout ||
                !ImportedLayoutAsset->DocumentId.Equals(Layout.DocumentId,
                                                        ESearchCase::CaseSensitive),
            Error))
        return Reject(Error);
    int32 RoomCount = 0;
    for (const auto &R : Layout.Regions)
        if (!R.bCorridor)
            ++RoomCount;
    LastImportReport = FString::Printf(
        TEXT(
            "Imported canonical %s / %s: %d rooms, %d corridors, %d unique walls, %d openings. Centerline cm layout "
            "preserved. External image/evidence links are provenance; agent navigation is separate."),
        *Layout.DocumentId, *Layout.RevisionId, RoomCount, Layout.Regions.Num() - RoomCount,
        Layout.Walls.Num(), Layout.Openings.Num());
    OutError.Reset();
    return true;
}

bool APlayableSketchLevelActor::PublishExplicitLayout(
    const FPlayableSketchExplicitLayout &Layout, const FPlayableSketchExplicitGeometry &Geometry,
    const FString &Json, bool bFull, FString &Error)
{
    auto Specs = Geometry.Specs;
    for (auto &Spec : Specs)
    {
        Spec.Material = Spec.Kind == EPlayableSketchPieceKind::Floor ? DefaultFloorMaterial.Get()
                                                                     : WallMaterial.Get();
        if (Spec.Kind != EPlayableSketchPieceKind::Floor || !Spec.bRoom)
            continue;
        for (const auto &R : Layout.Regions)
        {
            if (R.bCorridor || Spec.SourceId != FPlayableSketchExplicitLayoutBuilder::StableId(
                                                    Layout.DocumentId, TEXT("room"), R.Id))
                continue;
            if (R.Role == TEXT("start") && StartFloorMaterial)
                Spec.Material = StartFloorMaterial.Get();
            if (R.Role == TEXT("goal") && GoalFloorMaterial)
                Spec.Material = GoalFloorMaterial.Get();
            break;
        }
    }
    bFull = bFull || !ComponentRegistry.IsHealthy(*this);
    if (!ComponentRegistry.Apply(*this, Specs, bFull, LastUpdateStats, Error))
    {
        return false;
    }

    auto ApplyActorSettings = [&]() {
        LayoutSource = EPlayableSketchLayoutSource::ImportedExplicitLayout;
        WallThicknessCm = Layout.Settings.WallThicknessCm;
        WallHeightCm = Layout.Settings.WallHeightCm;
        DoorHeightCm = Layout.Settings.DoorHeightCm;
        FloorThicknessCm = Layout.Settings.FloorThicknessCm;
    };
#if WITH_EDITOR
    const bool bEditor = GetWorld() && !GetWorld()->IsGameWorld();
    const bool bAssetChanged =
        !ImportedLayoutAsset->CanonicalJson.Equals(Json, ESearchCase::CaseSensitive) ||
        !ImportedLayoutAsset->DocumentId.Equals(Layout.DocumentId, ESearchCase::CaseSensitive) ||
        !ImportedLayoutAsset->RevisionId.Equals(Layout.RevisionId, ESearchCase::CaseSensitive) ||
        !ImportedLayoutAsset->ImageHash.Equals(Layout.ImageHash, ESearchCase::CaseSensitive);
    const bool bActorChanged =
        LayoutSource != EPlayableSketchLayoutSource::ImportedExplicitLayout ||
        WallThicknessCm != static_cast<float>(Layout.Settings.WallThicknessCm) ||
        WallHeightCm != static_cast<float>(Layout.Settings.WallHeightCm) ||
        DoorHeightCm != static_cast<float>(Layout.Settings.DoorHeightCm) ||
        FloorThicknessCm != static_cast<float>(Layout.Settings.FloorThicknessCm);
    if (bEditor && (bAssetChanged || bActorChanged) && !GIsTransacting)
    {
        const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "PublishExplicit",
                                                       "Update PlayableSketch Explicit Layout"));
        Modify();
        if (bAssetChanged)
        {
            ImportedLayoutAsset->Modify();
            ImportedLayoutAsset->CanonicalJson = Json;
            ImportedLayoutAsset->DocumentId = Layout.DocumentId;
            ImportedLayoutAsset->RevisionId = Layout.RevisionId;
            ImportedLayoutAsset->ImageHash = Layout.ImageHash;
            ImportedLayoutAsset->MarkPackageDirty();
        }
        ApplyActorSettings();
        MarkPackageDirty();
    }
#endif
    ApplyActorSettings();
    ExplicitSettingsAsset = ImportedLayoutAsset;
    ExplicitSettingsSourceJson = ImportedLayoutAsset->CanonicalJson;
    GeneratedFloorPlan = Geometry.FloorPlan;
    LastIssues.Reset();
    bPreviewStale = false;
    PublishedSignature = LastAttemptSignature = GetSourceSignature();
    PublishedGlobalSignature = GetGlobalRebuildSignature();
    ReportExplicitNavigation();
    PreviewStatus = TEXT("Current valid explicit preview. Canonical walls and openings preserved.");
    LastRebuildReport = FString::Printf(
        TEXT(
            "Mode=%s Source=Explicit Revision=%s DirtyRooms=%d DirtyCorridors=%d DirtyWalls=%d Created=%d Updated=%d "
            "Removed=%d Kept=%d; agent navigation not certified."),
        bFull ? TEXT("Full") : TEXT("Local"), *Layout.RevisionId, LastUpdateStats.DirtyRooms.Num(),
        LastUpdateStats.DirtyConnections.Num(), LastUpdateStats.DirtyWalls.Num(),
        LastUpdateStats.Created, LastUpdateStats.Updated, LastUpdateStats.Removed,
        LastUpdateStats.Kept);
    UE_LOG(LogTemp, Display, TEXT("%s"), *LastRebuildReport);
    return true;
}

void APlayableSketchLevelActor::UpdateExplicitGeometry(bool bForceFull)
{
    LastAttemptSignature = GetSourceSignature();
    FString Error, Json;
    FPlayableSketchExplicitLayout Layout;
    FPlayableSketchExplicitGeometry Geometry;
    bool bValid = GetWorld() && ImportedLayoutAsset && GetActorScale3D().Equals(FVector::OneVector);
    if (!bValid)
        Error = TEXT("Assign an ImportedLayoutAsset and use unit actor scale.");
    if (bValid)
        bValid = FPlayableSketchExplicitLayoutBuilder::Parse(ImportedLayoutAsset->CanonicalJson,
                                                             Layout, Error);
    if (bValid)
    {

        const bool bSameSource =
            ExplicitSettingsAsset == ImportedLayoutAsset &&
            ExplicitSettingsSourceJson.Equals(ImportedLayoutAsset->CanonicalJson,
                                              ESearchCase::CaseSensitive);
        const auto Settings =
            bSameSource ? DesiredSettings(*this, Layout.Settings) : Layout.Settings;
        bValid = FPlayableSketchExplicitLayoutBuilder::ResolveSettings(
                     ImportedLayoutAsset->CanonicalJson, Settings, Json, Layout, Error) &&
                 BuildExplicitGeometry(Layout, Geometry, Error);
    }
    if (bValid && PublishExplicitLayout(Layout, Geometry, Json,
                                        bForceFull || PublishedSignature.IsEmpty(), Error))
        return;
    ResetNavigation();
    bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty();
    PreviewStatus =
        TEXT("Explicit rebuild rejected. Previous geometry retained; preview is stale.");
    LastRebuildReport = TEXT("Result=Rejected Source=Explicit: ") + Error;
    FPlayableSketchValidationIssue Issue;
    Issue.Code = TEXT("PS-E001");
    Issue.Message = Error;
    LastIssues = {Issue};
}

void APlayableSketchLevelActor::ValidateExplicitDesign()
{
    FString Error, Json;
    FPlayableSketchExplicitLayout Layout;
    FPlayableSketchExplicitGeometry Geometry;
    bool bValid = ImportedLayoutAsset && FPlayableSketchExplicitLayoutBuilder::Parse(
                                             ImportedLayoutAsset->CanonicalJson, Layout, Error);
    if (bValid)
    {
        const bool bSameSource =
            ExplicitSettingsAsset == ImportedLayoutAsset &&
            ExplicitSettingsSourceJson.Equals(ImportedLayoutAsset->CanonicalJson,
                                              ESearchCase::CaseSensitive);
        const auto Settings =
            bSameSource ? DesiredSettings(*this, Layout.Settings) : Layout.Settings;
        bValid = FPlayableSketchExplicitLayoutBuilder::ResolveSettings(
                     ImportedLayoutAsset->CanonicalJson, Settings, Json, Layout, Error) &&
                 BuildExplicitGeometry(Layout, Geometry, Error);
    }
    bPreviewStale =
        !GeneratedFloorPlan.Rooms.IsEmpty() && PublishedSignature != GetSourceSignature();
    if (bValid)
    {
        LastIssues.Reset();
        PreviewStatus = TEXT("Explicit design validation passed. Rebuild publishes geometry.");
    }
    else
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-E001");
        Issue.Message = ImportedLayoutAsset ? Error : TEXT("ImportedLayoutAsset is not assigned.");
        LastIssues = {Issue};
        PreviewStatus = TEXT("Explicit design validation failed. Previous geometry retained.");
    }
}

void APlayableSketchLevelActor::ReportExplicitNavigation()
{
    ResetNavigation();
    FPlayableSketchExplicitLayout Layout;
    FString Error;
    ExplicitNavigationResult = FPlayableSketchExplicitNavigationReport();
    if (!ImportedLayoutAsset || bPreviewStale || PublishedSignature != GetSourceSignature() ||
        !ComponentRegistry.IsHealthy(*this) ||
        !FPlayableSketchExplicitLayoutBuilder::Parse(ImportedLayoutAsset->CanonicalJson, Layout,
                                                     Error))
    {
        NavigationReport = TEXT("Not run: rebuild current valid explicit geometry. ") + Error;
        ExplicitNavigationResult.Reason = NavigationReport;
        return;
    }
    ApplyRuntimeCoordinates(Layout);
    FPlayableSketchExplicitAgent Agent;
    Agent.RadiusCm = PawnRadiusCm;
    Agent.HalfHeightCm = PawnHeightCm / 2;
    Agent.ClearanceCm = ClearanceCm;
    Agent.CellSizeCm = ExplicitNavigationCellSizeCm;
    Agent.GridOffsetCm = NavigationGridOffsetCm;
    Agent.MaxCells = NavigationMaxCells;
    ExplicitNavigationResult = FPlayableSketchExplicitNavigation::Analyze(*this, Layout, Agent);
    PreviewPathPoints = ExplicitNavigationResult.Path;
    NavigationReport = ExplicitNavigationResult.Summary();
}

void APlayableSketchLevelActor::VerifyExplicitPawnTraversal()
{
    AnalyzeNavigation();
    if (LayoutSource != EPlayableSketchLayoutSource::ImportedExplicitLayout ||
        !ExplicitNavigationResult.bAnalysisCompleted || !ExplicitNavigationResult.bReachable)
        return;
    const auto Path = ExplicitNavigationResult.Path;
    FPlayableSketchExplicitNavigation::TraversePawn(*this, Path, ExplicitNavigationResult);
    NavigationReport = ExplicitNavigationResult.Summary();
}

bool APlayableSketchLevelActor::ImportRuntimeCanonicalJsonText(const FString &Json,
                                                               FString &OutError)
{
    if (!GetWorld() || !GetWorld()->IsGameWorld() || !GetActorScale3D().Equals(FVector::OneVector))
    {
        OutError = TEXT("Runtime import requires a game world and unit scale.");
        return false;
    }
    FPlayableSketchExplicitLayout Layout;
    FPlayableSketchExplicitGeometry Geometry;
    if (!FPlayableSketchExplicitLayoutBuilder::Parse(Json, Layout, OutError) ||
        !BuildExplicitGeometry(Layout, Geometry, OutError))
        return false;
    auto *Previous = ImportedLayoutAsset.Get();
    auto *Candidate = NewObject<UPlayableSketchImportedLayoutAsset>(this, NAME_None, RF_Transient);
    Candidate->CanonicalJson = Json;
    Candidate->DocumentId = Layout.DocumentId;
    Candidate->RevisionId = Layout.RevisionId;
    Candidate->ImageHash = Layout.ImageHash;
    ImportedLayoutAsset = Candidate;
    if (!PublishExplicitLayout(Layout, Geometry, Json, true, OutError))
    {
        ImportedLayoutAsset = Previous;
        return false;
    }
    LastImportReport = TEXT("Runtime canonical source published: ") + Layout.DocumentId +
                       TEXT(" / ") + Layout.RevisionId;
    return true;
}

void APlayableSketchLevelActor::ApplyRuntimeCoordinates(FPlayableSketchExplicitLayout &Layout) const
{
    if (!bUseSketchViewCoordinates)
        return;
    TMap<FString, FVector2D> Points;
    for (auto &Vertex : Layout.Vertices)
    {
        Vertex.PositionCm.Y = -Vertex.PositionCm.Y;
        Points.Add(Vertex.Id, Vertex.PositionCm);
    }
    for (auto &Region : Layout.Regions)
    {
        const double Minimum = Region.Bounds.Min.Y;
        Region.Bounds.Min.Y = -Region.Bounds.Max.Y;
        Region.Bounds.Max.Y = -Minimum;
        Algo::Reverse(Region.VertexIds);
        Algo::Reverse(Region.WallIds);
        if (Region.WallIds.Num() > 1)
        {
            const FString First = Region.WallIds[0];
            Region.WallIds.RemoveAt(0);
            Region.WallIds.Add(First);
        }
    }
    for (auto &Wall : Layout.Walls)
    {
        if (Wall.Axis != 1)
            continue;
        const double Length = FMath::Abs(Points[Wall.EndVertexId].Y - Points[Wall.StartVertexId].Y);
        Swap(Wall.StartVertexId, Wall.EndVertexId);
        for (auto &Opening : Layout.Openings)
            if (Opening.WallId == Wall.Id)
                Opening.CenterOffsetCm = Length - Opening.CenterOffsetCm;
    }
}
bool APlayableSketchLevelActor::BuildExplicitGeometry(FPlayableSketchExplicitLayout &Layout,
                                                      FPlayableSketchExplicitGeometry &Geometry,
                                                      FString &Error) const
{
    ApplyRuntimeCoordinates(Layout);
    return FPlayableSketchExplicitLayoutBuilder::Build(Layout, Geometry, Error);
}
