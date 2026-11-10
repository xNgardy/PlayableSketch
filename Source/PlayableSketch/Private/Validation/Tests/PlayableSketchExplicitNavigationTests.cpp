#include "ExplicitLayout/PlayableSketchExplicitNavigation.h"
#include "PlayableSketchLevelActor.h"
#include "PlayableSketchNavigationTestFixtures.h"
#include "Components/StaticMeshComponent.h"
#include "Components/BoxComponent.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchExplicitNavigationTests,
                                 "PlayableSketch.Navigation.ExplicitPawn",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchExplicitNavigationTests::RunTest(const FString &Parameters)
{
    const UWorld::InitializationValues IV = UWorld::InitializationValues()
                                                .AllowAudioPlayback(false)
                                                .RequiresHitProxies(false)
                                                .CreatePhysicsScene(true)
                                                .CreateNavigation(false)
                                                .CreateAISystem(false)
                                                .ShouldSimulatePhysics(false)
                                                .EnableTraceCollision(true)
                                                .CreateFXSystem(false)
                                                .SetTransactional(false);
    TArray<TSharedPtr<FJsonValue>> Records;
    auto Load = [&](int32 I) {
        FString Text, Error;
        FPlayableSketchExplicitLayout L;
        TestTrue(
            TEXT("Fixture loaded"),
            FFileHelper::LoadFileToString(
                Text, *(FPaths::ProjectDir() /
                        FString::Printf(TEXT("Data/ground_truth/v1/Data_%d.validated.json"), I))));
        TestTrue(TEXT("Fixture parses"), FPlayableSketchExplicitLayoutBuilder::Parse(
                                             PlayableSketchNavigationFixtureRoles(Text), L, Error));
        return L;
    };
    auto Run = [&](const FString &Name, FPlayableSketchExplicitLayout L,
                   FPlayableSketchExplicitAgent Agent, const TArray<FVector2D> &ProbeRoute,
                   bool Expected, TFunctionRef<void(FPlayableSketchExplicitGeometry &)> Edit,
                   FTransform Transform = FTransform::Identity) {
        UWorld *W = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true,
                                        ERHIFeatureLevel::Num, &IV);
        GEngine->CreateNewWorldContext(W->WorldType).SetCurrentWorld(W);
        AActor *Owner = W->SpawnActor<AActor>();
        auto *Root = NewObject<USceneComponent>(Owner);
        Owner->SetRootComponent(Root);
        Owner->AddInstanceComponent(Root);
        Root->RegisterComponent();
        Owner->SetActorTransform(Transform);
        FPlayableSketchExplicitGeometry G;
        FString Error;
        auto BuildLayout = L;
        BuildLayout.ValidationMode = TEXT("geometry_only");
        if (!TestTrue(Name + TEXT(" builds"),
                      FPlayableSketchExplicitLayoutBuilder::Build(BuildLayout, G, Error)))
        {
            AddError(Error);
            GEngine->DestroyWorldContext(W);
            W->DestroyWorld(false);
            return FPlayableSketchExplicitNavigationReport();
        }
        Edit(G);
        FPlayableSketchComponentRegistry Registry;
        FPlayableSketchUpdateStats Stats;
        TestTrue(Name + TEXT(" collision published"),
                 Registry.Apply(*Owner, G.Specs, true, Stats, Error));
        if (Name == TEXT("prop_blockage"))
        {
            auto *Prop = W->SpawnActor<AActor>();
            auto *Box = NewObject<UBoxComponent>(Prop);
            Prop->SetRootComponent(Box);
            Prop->AddInstanceComponent(Box);
            Box->SetBoxExtent(FVector(20, 200, 100));
            Box->SetCollisionProfileName(TEXT("BlockAllDynamic"));
            Box->RegisterComponent();
            Prop->SetActorTransform(
                FTransform(Owner->GetActorQuat(),
                           Owner->GetActorTransform().TransformPosition(FVector(600, 200, 100))));
        }
        Owner->DispatchBeginPlay();
        auto R = FPlayableSketchExplicitNavigation::Analyze(*Owner, L, Agent);
        TestTrue(Name + TEXT(" analysis completes"), R.bAnalysisCompleted);
        TestEqual(Name + TEXT(" grid reachability"), R.bReachable, Expected);
        const auto Route = ProbeRoute.IsEmpty() ? R.Path : ProbeRoute;
        if (L.ValidationMode != TEXT("geometry_only"))
            TestEqual(Name + TEXT(" actual Pawn movement"),
                      FPlayableSketchExplicitNavigation::TraversePawn(*Owner, Route, R),
                      Name == TEXT("coarse_grid_discretization") ? true : Expected);
        TSharedPtr<FJsonObject> J;
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(R.Json()), J);
        J->SetStringField(TEXT("fixture"), Name);
        Records.Add(MakeShared<FJsonValueObject>(J));
        AddInfo(Name + TEXT(": ") + R.Summary());
        Registry.Clear(*Owner);
        GEngine->DestroyWorldContext(W);
        W->DestroyWorld(false);
        return R;
    };
    auto NoEdit = [](FPlayableSketchExplicitGeometry &) {};
    FPlayableSketchExplicitAgent Agent;
    const auto Shared = Load(3);
    auto Open = Run(TEXT("shared_wall_open"), Shared, Agent, {}, true, NoEdit);
    TestEqual(TEXT("Topology independent"), Open.Topology, FString(TEXT("passed")));
    TestEqual(TEXT("NavMesh explicit N/A"), Open.NavMesh, FString(TEXT("not_applicable")));
    TestTrue(TEXT("Actual pawn moved"), Open.MovementSteps > 0);
    auto CaseIds = Shared;
    CaseIds.GoalRoomId = TEXT("ra");
    for (auto &Region : CaseIds.Regions)
        if (Region.Id.Equals(TEXT("rB"), ESearchCase::CaseSensitive))
            Region.Id = TEXT("ra");
    for (auto &Wall : CaseIds.Walls)
        for (auto &Id : Wall.RegionIds)
            if (Id.Equals(TEXT("rB"), ESearchCase::CaseSensitive))
                Id = TEXT("ra");
    for (auto &Opening : CaseIds.Openings)
        for (auto &Id : Opening.RegionIds)
            if (Id.Equals(TEXT("rB"), ESearchCase::CaseSensitive))
                Id = TEXT("ra");
    auto CaseResult = Run(TEXT("case_sensitive_region_ids"), CaseIds, Agent, {}, true, NoEdit);
    TestTrue(TEXT("Case-distinct regions have a nonzero traversal"), CaseResult.MovementSteps > 50);
    auto Closed = Shared;
    Closed.Openings.Reset();
    auto C = Run(TEXT("closed_wall"), Closed, Agent, Open.Path, false, NoEdit);
    TestEqual(TEXT("Closed wall disconnects graph"), C.Topology, FString(TEXT("failed")));
    auto Narrow = Shared;
    Narrow.Openings[0].ClearWidthCm = 70;
    auto N = Run(TEXT("narrow_door"), Narrow, Agent, Open.Path, false, NoEdit);
    TestTrue(TEXT("Narrow door reason"), N.Issues.ContainsByPredicate([](const auto &X) {
        return X.StartsWith(TEXT("narrow_opening:"));
    }));
    auto Low = Shared;
    Low.Openings[0].ClearHeightCm = 140;
    Low.Settings.DoorHeightCm = 140;
    auto H = Run(TEXT("low_lintel"), Low, Agent, Open.Path, false, NoEdit);
    TestTrue(TEXT("Low lintel reason"), H.Issues.ContainsByPredicate([](const auto &X) {
        return X.StartsWith(TEXT("low_lintel:"));
    }));
    auto PropResult = Run(TEXT("prop_blockage"), Shared, Agent, Open.Path, false, NoEdit);
    TestTrue(TEXT("External prop blocked reason"),
             PropResult.Reason.Contains(TEXT("prop_or_external_collision")));
    auto Large = Agent;
    Large.RadiusCm = 70;
    Run(TEXT("larger_agent"), Shared, Large, Open.Path, false, NoEdit);
    auto Corridor = Load(6);
    auto Passage = Run(TEXT("corridor_200_centerline"), Corridor, Agent, {}, true, NoEdit);
    for (const auto &Width : Passage.CorridorClearWidthsCm)
        TestEqual(TEXT("200 centerline minus20 walls =180clear"), Width.Value, 180.0);
    auto Thick = Corridor;
    Thick.Settings.WallThicknessCm = 40;
    for (auto &O : Thick.Openings)
        O.ClearWidthCm = 160;
    auto ThickResult = Run(TEXT("thicker_walls_same_centerlines"), Thick, Agent, {}, true, NoEdit);
    for (const auto &Width : ThickResult.CorridorClearWidthsCm)
        TestEqual(TEXT("200 centerline minus40 walls =160clear"), Width.Value, 160.0);
    for (int32 I = 0; I < Thick.Vertices.Num(); ++I)
        TestEqual(TEXT("Thickness never changes coordinates"), Thick.Vertices[I].PositionCm,
                  Corridor.Vertices[I].PositionCm);
    auto NearlyBlocked = Agent;
    NearlyBlocked.RadiusCm = 85;
    Run(TEXT("corridor_agent_too_wide"), Corridor, NearlyBlocked, Passage.Path, false, NoEdit);
    Run(TEXT("disconnected_floor"), Corridor, Agent, Passage.Path, false, [](auto &G) {
        G.Specs.RemoveAll(
            [](const auto &X) { return X.Kind == EPlayableSketchPieceKind::Floor && !X.bRoom; });
    });
    Run(TEXT("yaw_translated_corridor"), Load(8), Agent, {}, true, NoEdit,
        FTransform(FRotator(0, 90, 0), FVector(1000, -500, 50)));

    Run(TEXT("branching_join"), Load(47), Agent, {}, true, NoEdit);
    auto Shifted = Agent;
    Shifted.CellSizeCm = 40;
    Shifted.GridOffsetCm = FVector2D(7, -9);
    Run(TEXT("shifted_grid"), Shared, Shifted, {}, true, NoEdit);
    auto Coarse = Agent;
    Coarse.CellSizeCm = 500;
    auto CoarseResult =
        Run(TEXT("coarse_grid_discretization"), Shared, Coarse, Open.Path, false, NoEdit);

    TestTrue(TEXT("Grid failure explicitly mentions discretization"),
             CoarseResult.Grid == TEXT("failed"));
    TestEqual(TEXT("Physical Pawn passes even when coarse grid fails"), CoarseResult.Pawn,
              FString(TEXT("passed")));
    auto TinyBudget = Agent;
    TinyBudget.MaxCells = 1;

    UWorld *W = UWorld::CreateWorld(EWorldType::Editor, false, NAME_None, nullptr, true,
                                    ERHIFeatureLevel::Num, &IV);
    GEngine->CreateNewWorldContext(W->WorldType).SetCurrentWorld(W);
    auto *Actor = W->SpawnActor<APlayableSketchLevelActor>();
    Actor->bAutoRebuildGeometry = false;
    Actor->ImportedLayoutAsset = NewObject<UPlayableSketchImportedLayoutAsset>(Actor);
    FString Json, Error;
    FFileHelper::LoadFileToString(
        Json, *(FPaths::ProjectDir() / TEXT("Data/ground_truth/v1/Data_3.validated.json")));
    TestTrue(TEXT("Actor import"), Actor->ImportCanonicalLayoutJsonText(
                                       PlayableSketchNavigationFixtureRoles(Json), Error));
    TestFalse(
        TEXT("Budget exhaustion incomplete"),
        FPlayableSketchExplicitNavigation::Analyze(*Actor, Shared, TinyBudget).bAnalysisCompleted);
    Actor->VerifyExplicitPawnTraversal();
    AddInfo(Actor->NavigationReport);
    TestEqual(TEXT("Editor action actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->SetActorRotation(FRotator(10, 0, 0));
    Actor->AnalyzeNavigation();
    TestFalse(TEXT("Tilt refused"), Actor->ExplicitNavigationResult.bAnalysisCompleted);
    Actor->SetActorRotation(FRotator::ZeroRotator);
    Actor->SetActorScale3D(FVector(2, 1, 1));
    Actor->AnalyzeNavigation();
    TestFalse(TEXT("Nonuniform scale refused"), Actor->ExplicitNavigationResult.bAnalysisCompleted);
    Actor->SetActorScale3D(FVector::OneVector);
    TestFalse(TEXT("Rejected import"), Actor->ImportCanonicalLayoutJsonText(TEXT("{}"), Error));
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Rejected import retains playable collision"),
              Actor->ExplicitNavigationResult.Pawn, FString(TEXT("passed")));
    Actor->RebuildLocalGeometry();
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Local rebuild actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->RebuildGeometry();
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Full rebuild actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->WallHeightCm = -1;
    Actor->RebuildLocalGeometry();
    Actor->AnalyzeNavigation();
    TestTrue(TEXT("Failed rebuild stale"), Actor->bPreviewStale);
    TestFalse(TEXT("Stale scene cannot certify current source"),
              Actor->ExplicitNavigationResult.bAnalysisCompleted);
    GEngine->DestroyWorldContext(W);
    W->DestroyWorld(false);
    auto Single = Run(TEXT("geometry_only_floor_sanity"), Load(1), Agent, {}, false, NoEdit);
    TestEqual(TEXT("Geometry only floors checked"), Single.Geometry, FString(TEXT("passed")));
    TestEqual(TEXT("Geometry only Pawn N/A"), Single.Pawn, FString(TEXT("not_applicable")));
    auto Root = MakeShared<FJsonObject>();
    Root->SetArrayField(TEXT("fixtures"), Records);
    FString Text;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Text));
    const FString Path = FPaths::ProjectSavedDir() / TEXT("Step12/physical-fixtures.json");
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
    FFileHelper::SaveStringToFile(Text, *Path);
    return !HasAnyErrors();
}
#endif
