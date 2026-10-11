#include "PlayableSketchLevelActor.h"
#include "Engine/World.h"
#include "Materials/Material.h"
#include "Misc/AutomationTest.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchCorridorRouting.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
namespace SketchExperiment
{
using FObject = TSharedPtr<FJsonObject>;
using FValues = TArray<TSharedPtr<FJsonValue>>;
FObject Object() { return MakeShared<FJsonObject>(); }
TSharedPtr<FJsonValue> Value(const FObject& O) { return MakeShared<FJsonValueObject>(O); }
void Null(const FObject& O, const TCHAR* Key) { O->SetField(Key, MakeShared<FJsonValueNull>()); }
FString Text(const FObject& O)
{
    FString S;
    FJsonSerializer::Serialize(O.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&S));
    return S;
}
FGuid Id(const FString& S) { FGuid G; FGuid::Parse(S, G); return G; }
FString Hash(const FString& S) { return FMD5::HashAnsiString(*S); }
double Ms(double Start) { return (FPlatformTime::Seconds() - Start) * 1000.0; }
FValues Strings(TArray<FString> S)
{
    S.Sort(); FValues V;
    for (const auto& X : S) V.Add(MakeShared<FJsonValueString>(X));
    return V;
}
FValues Ids(const TArray<FGuid>& A)
{
    TArray<FString> S; for (const auto& G : A) S.Add(G.ToString()); return Strings(S);
}
FPlayableSketchGraph Graph(const FObject& O)
{
    FPlayableSketchGraph G;
    G.Seed = O->GetIntegerField(TEXT("seed"));
    G.SchemaVersion = O->GetIntegerField(TEXT("schema_version"));
    G.StartRoomId = Id(O->GetStringField(TEXT("start")));
    G.GoalRoomId = Id(O->GetStringField(TEXT("goal")));
    for (const auto& V : O->GetArrayField(TEXT("rooms")))
    {
        const auto R = V->AsObject(); FPlayableSketchRoom Room;
        Room.RoomId = Id(R->GetStringField(TEXT("id")));
        Room.DisplayName = R->GetStringField(TEXT("name"));
        Room.RoomType = static_cast<EPlayableSketchRoomType>(R->GetIntegerField(TEXT("type")));
        Room.RoomRole = static_cast<EPlayableSketchRoomRole>(R->GetIntegerField(TEXT("role")));
        Room.PositionMode = R->GetBoolField(TEXT("locked")) ? EPlayableSketchPositionMode::Locked : EPlayableSketchPositionMode::Auto;
        const auto& P = R->GetArrayField(TEXT("position"));
        Room.PositionCm = FVector2D(P[0]->AsNumber(), P[1]->AsNumber());
        Room.WidthCm = R->GetIntegerField(TEXT("width")); Room.DepthCm = R->GetIntegerField(TEXT("depth"));
        G.Rooms.Add(Room);
    }
    for (const auto& V : O->GetArrayField(TEXT("connections")))
    {
        const auto C = V->AsObject(); FPlayableSketchConnection Connection;
        Connection.ConnectionId = Id(C->GetStringField(TEXT("id")));
        Connection.RoomAId = Id(C->GetStringField(TEXT("a"))); Connection.RoomBId = Id(C->GetStringField(TEXT("b")));
        Connection.CorridorWidthCm = C->GetIntegerField(TEXT("corridor_width"));
        Connection.DoorWidthCm = C->GetIntegerField(TEXT("door_width"));
        auto Door = [](const FObject& D, FPlayableSketchDoorOverride& Out)
        {
            Out.bManual = D->GetBoolField(TEXT("manual"));
            Out.WallSide = static_cast<EPlayableSketchWallSide>(D->GetIntegerField(TEXT("side")));
            Out.OffsetCm = D->GetNumberField(TEXT("offset"));
        };
        Door(C->GetObjectField(TEXT("door_a")), Connection.DoorASettings);
        Door(C->GetObjectField(TEXT("door_b")), Connection.DoorBSettings);
        G.Connections.Add(Connection);
    }
    return G;
}
FObject Plan(const FPlayableSketchFloorPlan& P)
{
    // Canonical, lossless %.17g strings permit comparison independently of array order.
    auto Rect = [](const FPlayableSketchRect& R)
    { return FString::Printf(TEXT("%.17g,%.17g,%.17g,%.17g"), R.Min.X, R.Min.Y, R.Max.X, R.Max.Y); };
    auto Door = [](const FPlayableSketchDoorEndpoint& D)
    { return FString::Printf(TEXT("%s/%d/%.17g/%.17g/%.17g"), *D.RoomId.ToString(), int32(D.WallSide), D.PositionCm.X, D.PositionCm.Y, D.WidthCm); };
    TArray<FString> Rooms, Corridors;
    for (const auto& R : P.Rooms) Rooms.Add(R.RoomId.ToString() + TEXT(":") + Rect(R.Bounds));
    for (const auto& C : P.Corridors)
    {
        TArray<FString> Footprints; for (const auto& F : C.Footprints) Footprints.Add(Rect(F));
        Footprints.Sort();
        Corridors.Add(C.ConnectionId.ToString() + TEXT(":") + Door(C.DoorA) + TEXT("|") + Door(C.DoorB)
            + TEXT("|") + FString::Join(Footprints, TEXT(";")));
    }
    auto O = Object(); O->SetArrayField(TEXT("rooms"), Strings(Rooms)); O->SetArrayField(TEXT("corridors"), Strings(Corridors)); return O;
}
FString Scene(const TMap<FName, FString>& Capture)
{
    TArray<FString> S; for (const auto& P : Capture) S.Add(P.Key.ToString() + TEXT("=") + P.Value);
    S.Sort(); return FString::Join(S, TEXT("\n"));
}
FObject Navigation(const FPlayableSketchNavigationResult& N, bool bComplete)
{
    auto O = Object(); O->SetBoolField(TEXT("completed"), bComplete);
    for (const TCHAR* K : { TEXT("reachable"), TEXT("route_length_cm"), TEXT("dead_end_count"), TEXT("alternative_route"), TEXT("unreachable_room_count") }) Null(O, K);
    if (!bComplete) return O;
    O->SetBoolField(TEXT("reachable"), N.bReachable);
    if (N.RouteLengthCm.IsSet()) O->SetNumberField(TEXT("route_length_cm"), N.RouteLengthCm.GetValue());
    O->SetNumberField(TEXT("dead_end_count"), N.DeadEndCount);
    O->SetBoolField(TEXT("alternative_route"), N.bAlternativeRoute);
    O->SetNumberField(TEXT("unreachable_room_count"), N.UnreachableRooms.Num());
    O->SetArrayField(TEXT("unreachable_rooms"), Ids(N.UnreachableRooms));
    O->SetArrayField(TEXT("physical_connections"), Ids(N.PhysicalConnections));
    // Route order and path point order are significant.
    FValues Route, Path;
    for (const auto& G : N.RouteConnections) Route.Add(MakeShared<FJsonValueString>(G.ToString()));
    for (const auto& P : N.PathPoints) Path.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%.17g,%.17g"), P.X, P.Y)));
    O->SetArrayField(TEXT("route_connections"), Route); O->SetArrayField(TEXT("path_points_cm"), Path);
    O->SetNumberField(TEXT("grid_width"), N.Dimensions.X); O->SetNumberField(TEXT("grid_height"), N.Dimensions.Y);
    O->SetStringField(TEXT("grid_origin_cm"), FString::Printf(TEXT("%.17g,%.17g"), N.OriginCm.X, N.OriginCm.Y));
    O->SetNumberField(TEXT("cell_cm"), N.CellSizeCm);
    TArray<FString> Cells;
    for (const auto& C : N.WalkableCells) Cells.Add(FString::Printf(TEXT("%d,%d"), C.X, C.Y));
    Cells.Sort(); O->SetStringField(TEXT("walkable_cells_md5"), Hash(FString::Join(Cells, TEXT(";"))));
    O->SetNumberField(TEXT("walkable_cell_count"), Cells.Num()); O->SetNumberField(TEXT("visited_cell_count"), N.VisitedCellCount);
    return O;
}
void Issues(const FObject& O, const TArray<FPlayableSketchValidationIssue>& A)
{
    FValues V;
    for (const auto& I : A)
    {
        auto X = Object(); X->SetStringField(TEXT("code"), I.Code.ToString()); X->SetStringField(TEXT("message"), I.Message);
        X->SetNumberField(TEXT("severity"), int32(I.Severity)); X->SetArrayField(TEXT("element_ids"), Ids(I.ElementIds)); V.Add(Value(X));
    }
    O->SetArrayField(TEXT("validation_issues"), V);
}
}

// The only access added to the production actor is this friend. The measured paths are
// its existing RebuildLocalGeometry/RebuildGeometry methods, with no benchmark shortcut.
class FPlayableSketchExperimentRunner
{
public:
    static bool Run(FAutomationTestBase& Test)
    {
        using namespace SketchExperiment;
        FString ManifestText;
        const FString ManifestPath = FPaths::Combine(FPaths::ProjectDir(), TEXT("Experiments/manifest.json"));
        FObject Manifest;
        if (!FFileHelper::LoadFileToString(ManifestText, *ManifestPath)
            || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ManifestText), Manifest) || !Manifest.IsValid())
        { Test.AddError(TEXT("Cannot read experiment manifest.")); return false; }
        const auto& Cases = Manifest->GetArrayField(TEXT("cases"));
        const auto& Benchmarks = Manifest->GetArrayField(TEXT("benchmarks"));
        if (!Test.TestEqual(TEXT("Fixed generation case count"), Cases.Num(), 30)
            || !Test.TestEqual(TEXT("Fixed edit pair count"), Benchmarks.Num(), 10)
            || !Test.TestEqual(TEXT("Warmups"), Manifest->GetIntegerField(TEXT("warmups")), 1)
            || !Test.TestEqual(TEXT("Measured repetitions"), Manifest->GetIntegerField(TEXT("repetitions")), 5)) return false;
        const auto S = Manifest->GetObjectField(TEXT("settings"));
        auto Setting = [&](const TCHAR* K) { return S->GetNumberField(K); };
        FPlayableSketchValidationSettings Validation;
        Validation.GridStepCm = int32(Setting(TEXT("grid_cm")));
        Validation.Walls.HeightCm = Setting(TEXT("wall_height_cm")); Validation.Walls.ThicknessCm = Setting(TEXT("wall_thickness_cm"));
        Validation.Walls.DoorHeightCm = Setting(TEXT("door_height_cm")); Validation.Walls.CornerMarginCm = Setting(TEXT("corner_margin_cm"));
        Validation.MinCorridorWidthCm = Setting(TEXT("min_corridor_width_cm"));
        Validation.PawnRadiusCm = Setting(TEXT("agent_radius_cm")); Validation.PawnHeightCm = Setting(TEXT("agent_height_cm"));
        Validation.ClearanceCm = Setting(TEXT("clearance_cm"));
        FPlayableSketchNavigationSettings Nav;
        Nav.CellSizeCm = Validation.GridStepCm; Nav.AgentRadiusCm = Validation.PawnRadiusCm;
        Nav.AgentHeightCm = Validation.PawnHeightCm; Nav.ClearanceCm = Validation.ClearanceCm;
        Nav.MaxCells = int32(Setting(TEXT("navigation_max_cells"))); Nav.MaxWork = int64(Setting(TEXT("navigation_max_work")));
        auto Output = Object();
        Output->SetObjectField(TEXT("manifest"), Manifest); Output->SetStringField(TEXT("manifest_text_md5"), Hash(ManifestText));
        Output->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
        Output->SetStringField(TEXT("cpu"), FPlatformMisc::GetCPUBrand());
        Output->SetStringField(TEXT("started_utc"), FDateTime::UtcNow().ToIso8601());
#ifdef _MSC_FULL_VER
        Output->SetNumberField(TEXT("msvc_full_version"), _MSC_FULL_VER);
#endif
        Output->SetStringField(TEXT("execution"), TEXT("Win64 Development Editor; NullRHI; transient world; sequential game thread"));
        FValues Results;
        TMap<FString, int32> Families;
        for (const auto& V : Cases)
        {
            const auto C = V->AsObject(); const auto G = Graph(C->GetObjectField(TEXT("graph")));
            auto R = Object(); R->SetStringField(TEXT("case_id"), C->GetStringField(TEXT("id")));
            const FString Family = C->GetStringField(TEXT("family")); Families.FindOrAdd(Family)++;
            R->SetStringField(TEXT("family"), Family); R->SetNumberField(TEXT("seed"), G.Seed);
            R->SetNumberField(TEXT("room_count"), G.Rooms.Num()); R->SetNumberField(TEXT("connection_count"), G.Connections.Num());
            R->SetBoolField(TEXT("input_valid"), false); R->SetBoolField(TEXT("layout_success"), false);
            Null(R, TEXT("geometry_valid")); Null(R, TEXT("navigation_success"));
            R->SetObjectField(TEXT("navigation"), Navigation(FPlayableSketchNavigationResult(), false));
            for (const TCHAR* K : { TEXT("layout_ms"), TEXT("doors_ms"), TEXT("routing_ms"), TEXT("walls_ms"), TEXT("navigation_ms"), TEXT("geometry_pipeline_ms") }) Null(R, K);
            FString Error, Stage = TEXT("input_validation");
            FPlayableSketchFloorPlan P; TArray<FPlayableSketchGeometryDescriptor> Pieces;
            double T = FPlatformTime::Seconds(); auto FoundIssues = FPlayableSketchValidation::ValidateInput(G, Validation);
            double ValidationMs = Ms(T); bool Ok = !FPlayableSketchValidation::HasErrors(FoundIssues);
            R->SetBoolField(TEXT("input_valid"), Ok);
            if (Ok)
            {
                Stage = TEXT("layout"); T = FPlatformTime::Seconds();
                Ok = FPlayableSketchLayoutGenerator::Generate(G, Validation.GridStepCm, int32(Setting(TEXT("room_gap_cm"))), P, Error, int32(Setting(TEXT("max_placement_attempts"))));
                R->SetNumberField(TEXT("layout_ms"), Ms(T)); R->SetBoolField(TEXT("layout_success"), Ok);
            }
            const double GeometryStart = FPlatformTime::Seconds();
            if (Ok)
            {
                Stage = TEXT("doors"); T = FPlatformTime::Seconds();
                Ok = FPlayableSketchDoorGenerator::Generate(G, P, Validation.Walls.CornerMarginCm, Error); R->SetNumberField(TEXT("doors_ms"), Ms(T));
            }
            if (Ok)
            {
                Stage = TEXT("routing"); T = FPlatformTime::Seconds();
                Ok = FPlayableSketchCorridorRouting::Generate(G, P, Validation.GridStepCm, Error); R->SetNumberField(TEXT("routing_ms"), Ms(T));
            }
            if (Ok)
            {
                Stage = TEXT("walls"); T = FPlatformTime::Seconds();
                Ok = FPlayableSketchWallGeometry::Generate(P, Validation.Walls, Pieces, Error); R->SetNumberField(TEXT("walls_ms"), Ms(T));
            }
            if (Ok)
            {
                Stage = TEXT("plan_validation"); T = FPlatformTime::Seconds();
                FoundIssues.Append(FPlayableSketchValidation::ValidatePlan(G, P, Pieces, Validation)); ValidationMs += Ms(T);
                Ok = !FPlayableSketchValidation::HasErrors(FoundIssues); R->SetBoolField(TEXT("geometry_valid"), Ok);
            }
            if (R->GetBoolField(TEXT("layout_success"))) R->SetNumberField(TEXT("geometry_pipeline_ms"), Ms(GeometryStart));
            if (Ok)
            {
                Stage = TEXT("navigation"); FPlayableSketchNavigationResult N; T = FPlatformTime::Seconds();
                Ok = FPlayableSketchNavigation::Analyze(P, Pieces, G.StartRoomId, G.GoalRoomId, Nav, N, Error);
                R->SetNumberField(TEXT("navigation_ms"), Ms(T)); R->SetObjectField(TEXT("navigation"), Navigation(N, Ok));
                if (Ok) R->SetBoolField(TEXT("navigation_success"), N.bReachable);
            }
            R->SetNumberField(TEXT("validation_ms"), ValidationMs); Issues(R, FoundIssues);
            R->SetStringField(TEXT("status"), Ok ? TEXT("completed") : TEXT("failed"));
            R->SetStringField(TEXT("failure_stage"), Ok ? TEXT("") : Stage);
            R->SetStringField(TEXT("error_code"), Ok ? TEXT("") : TEXT("EXPERIMENT_") + Stage.ToUpper());
            R->SetStringField(TEXT("error"), Error); R->SetObjectField(TEXT("plan"), Plan(P));
            Results.Add(Value(R));
        }
        for (const TCHAR* Family : { TEXT("chain"), TEXT("branching"), TEXT("ring") })
            Test.TestEqual(FString(Family) + TEXT(" manifest count"), Families.FindRef(Family), 10);
        Output->SetArrayField(TEXT("generation_results"), Results);

        const UWorld::InitializationValues IV = UWorld::InitializationValues()
            .AllowAudioPlayback(false).RequiresHitProxies(false).CreatePhysicsScene(true)
            .CreateNavigation(false).CreateAISystem(false).ShouldSimulatePhysics(false)
            .EnableTraceCollision(true).CreateFXSystem(false).SetTransactional(false);
        UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true, ERHIFeatureLevel::Num, &IV);
        if (!Test.TestNotNull(TEXT("Experiment world"), World)) return false;
        APlayableSketchLevelActor* Local = World->SpawnActor<APlayableSketchLevelActor>();
        APlayableSketchLevelActor* Full = World->SpawnActor<APlayableSketchLevelActor>();
        if (!Local || !Full) { Test.AddError(TEXT("Cannot create experiment actors.")); World->DestroyWorld(false); return false; }
        auto Asset = NewObject<UPlayableSketchGraphAsset>(Local); Local->GraphAsset = Full->GraphAsset = Asset;
        for (auto* A : { Local, Full })
        {
            A->bAutoRebuildGeometry = false; A->bGenerateOnBeginPlay = false;
            A->GridStepCm = Validation.GridStepCm; A->RoomGapCm = int32(Setting(TEXT("room_gap_cm")));
            A->MaxPlacementAttempts = int32(Setting(TEXT("max_placement_attempts")));
            A->DoorCornerMarginCm = int32(Validation.Walls.CornerMarginCm);
            A->WallHeightCm = Validation.Walls.HeightCm; A->WallThicknessCm = Validation.Walls.ThicknessCm;
            A->DoorHeightCm = Validation.Walls.DoorHeightCm; A->FloorThicknessCm = Setting(TEXT("floor_thickness_cm"));
            A->MinCorridorWidthCm = Validation.MinCorridorWidthCm; A->PawnRadiusCm = Validation.PawnRadiusCm;
            A->PawnHeightCm = Validation.PawnHeightCm; A->ClearanceCm = Validation.ClearanceCm; A->NavigationMaxCells = Nav.MaxCells;
            A->HubFloorMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
        }
        FValues Measurements, Snapshots;
        int32 CaseIndex = 0, ValidPairs = 0;
        for (const auto& V : Benchmarks)
        {
            const auto B = V->AsObject(); const FString CaseId = B->GetStringField(TEXT("id"));
            const auto Base = Graph(B->GetObjectField(TEXT("baseline"))); const auto Edited = Graph(B->GetObjectField(TEXT("edited")));
            bool bPairValid = true;
            for (int32 Repeat = 0; Repeat < 6; ++Repeat)
            {
                Asset->Graph = Base; Local->RebuildGeometry(); Full->RebuildGeometry();
                const FString BaselinePlan = Text(Plan(Local->GeneratedFloorPlan));
                const FString BaselineScene = Scene(Local->ComponentRegistry.Capture());
                const bool bSameBaseline = !Local->bPreviewStale && !Full->bPreviewStale
                    && !Local->GeneratedFloorPlan.Rooms.IsEmpty() && !Full->GeneratedFloorPlan.Rooms.IsEmpty()
                    && BaselinePlan == Text(Plan(Full->GeneratedFloorPlan))
                    && BaselineScene == Scene(Full->ComponentRegistry.Capture());
                if (Repeat == 0)
                {
                    auto Snapshot = Object(); Snapshot->SetStringField(TEXT("case_id"), CaseId);
                    Snapshot->SetObjectField(TEXT("baseline_plan"), Plan(Local->GeneratedFloorPlan));
                    Snapshot->SetStringField(TEXT("baseline_scene_canonical"), BaselineScene); Snapshots.Add(Value(Snapshot));
                }
                Asset->Graph = Edited;
                FObject Records[2];
                // Alternate execution order to reduce systematic first/second bias.
                for (int32 Order = 0; Order < 2; ++Order)
                {
                    const int32 Mode = (CaseIndex + Repeat + Order) % 2; auto* A = Mode == 0 ? Local : Full;
                    const double Start = FPlatformTime::Seconds();
                    if (Mode == 0) A->RebuildLocalGeometry(); else A->RebuildGeometry();
                    const double Total = Ms(Start);
                    auto R = Object(); Records[Mode] = R;
                    R->SetStringField(TEXT("case_id"), CaseId); R->SetStringField(TEXT("requested_mode"), Mode == 0 ? TEXT("Local") : TEXT("Full"));
                    R->SetBoolField(TEXT("warmup"), Repeat == 0); R->SetNumberField(TEXT("repeat"), Repeat);
                    R->SetNumberField(TEXT("execution_order"), Order); R->SetNumberField(TEXT("seed"), Base.Seed);
                    R->SetNumberField(TEXT("room_count"), Edited.Rooms.Num()); R->SetNumberField(TEXT("connection_count"), Edited.Connections.Num());
                    R->SetBoolField(TEXT("same_baseline"), bSameBaseline);
                    R->SetStringField(TEXT("baseline_plan_md5"), Hash(BaselinePlan)); R->SetStringField(TEXT("baseline_scene_md5"), Hash(BaselineScene));
                    R->SetStringField(TEXT("report"), A->LastRebuildReport);
                    R->SetBoolField(TEXT("actual_local"), A->LastRebuildReport.StartsWith(TEXT("Mode=Local")));
                    const int32 ReasonStart = A->LastRebuildReport.Find(TEXT("Reason="));
                    const int32 ReasonEnd = A->LastRebuildReport.Find(TEXT(" DirtyRooms="));
                    R->SetStringField(TEXT("reason"), ReasonStart >= 0 && ReasonEnd > ReasonStart ? A->LastRebuildReport.Mid(ReasonStart + 7, ReasonEnd - ReasonStart - 7) : A->PreviewStatus);
                    const bool bValid = !A->bPreviewStale && A->PublishedSignature == A->GetSourceSignature()
                        && !A->GeneratedFloorPlan.Rooms.IsEmpty() && A->ComponentRegistry.IsHealthy(*A);
                    R->SetBoolField(TEXT("geometry_valid"), bValid); R->SetNumberField(TEXT("total_ms"), Total);
                    R->SetNumberField(TEXT("plan_ms"), A->PlanMs); R->SetNumberField(TEXT("validation_ms"), A->ValidationMs);
                    R->SetNumberField(TEXT("dirty_ms"), A->LastUpdateStats.DirtyMs); R->SetNumberField(TEXT("apply_ms"), A->LastUpdateStats.ApplyMs);
                    R->SetNumberField(TEXT("navigation_ms"), A->NavigationResult.TotalMs);
                    R->SetNumberField(TEXT("created"), A->LastUpdateStats.Created); R->SetNumberField(TEXT("updated"), A->LastUpdateStats.Updated);
                    R->SetNumberField(TEXT("removed"), A->LastUpdateStats.Removed); R->SetNumberField(TEXT("kept"), A->LastUpdateStats.Kept);
                    R->SetNumberField(TEXT("dirty_rooms"), A->LastUpdateStats.DirtyRooms.Num()); R->SetNumberField(TEXT("dirty_connections"), A->LastUpdateStats.DirtyConnections.Num());
                    R->SetObjectField(TEXT("plan"), Plan(A->GeneratedFloorPlan));
                    R->SetStringField(TEXT("scene_canonical"), Scene(A->ComponentRegistry.Capture()));
                    R->SetObjectField(TEXT("navigation"), Navigation(A->NavigationResult, A->bNavigationCurrent)); Issues(R, A->LastIssues);
                }
                const bool bPlans = Text(Records[0]->GetObjectField(TEXT("plan"))) == Text(Records[1]->GetObjectField(TEXT("plan")));
                const bool bScenes = Records[0]->GetStringField(TEXT("scene_canonical")) == Records[1]->GetStringField(TEXT("scene_canonical"));
                const bool bNavigation = Text(Records[0]->GetObjectField(TEXT("navigation"))) == Text(Records[1]->GetObjectField(TEXT("navigation")))
                    && Local->NavigationResult.WalkableCells.Num() == Full->NavigationResult.WalkableCells.Num()
                    && Local->NavigationResult.WalkableCells.Includes(Full->NavigationResult.WalkableCells);
                const bool bEqual = bSameBaseline && bPlans && bScenes && bNavigation
                    && Records[0]->GetBoolField(TEXT("geometry_valid")) && Records[1]->GetBoolField(TEXT("geometry_valid"))
                    && Local->bNavigationCurrent && Full->bNavigationCurrent && Records[0]->GetBoolField(TEXT("actual_local"));
                bPairValid &= bEqual;
                for (auto R : Records)
                {
                    R->SetBoolField(TEXT("plan_equal"), bPlans); R->SetBoolField(TEXT("scene_equal"), bScenes);
                    R->SetBoolField(TEXT("navigation_equal"), bNavigation); R->SetBoolField(TEXT("equivalent"), bEqual);
                    Measurements.Add(Value(R));
                }
                Test.TestTrue(CaseId + FString::Printf(TEXT(" repetition %d equivalence"), Repeat), bEqual);
            }
            if (bPairValid) ++ValidPairs;
            ++CaseIndex;
        }
        Output->SetArrayField(TEXT("benchmark_snapshots"), Snapshots); Output->SetArrayField(TEXT("benchmark_results"), Measurements);
        Output->SetNumberField(TEXT("valid_edit_pair_count"), ValidPairs);
        Test.TestEqual(TEXT("Ten distinct valid edit pairs"), ValidPairs, 10);
        World->DestroyWorld(false);
        Output->SetStringField(TEXT("finished_utc"), FDateTime::UtcNow().ToIso8601());
        const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Experiments"));
        IFileManager::Get().MakeDirectory(*Directory, true);
        FString Json; FJsonSerializer::Serialize(Output.ToSharedRef(), TJsonWriterFactory<>::Create(&Json));
        return Test.TestTrue(TEXT("Raw results saved"), FFileHelper::SaveStringToFile(Json, *FPaths::Combine(Directory, TEXT("raw_results.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM));
    }
};

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchExperimentTests, "PlayableSketch.Experiments.Run",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FPlayableSketchExperimentTests::RunTest(const FString& Parameters) { return FPlayableSketchExperimentRunner::Run(*this); }
#endif
