#include "Navigation/PlayableSketchNavigationExamples.h"
#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchNavigationTests,
                                 "PlayableSketch.Navigation.GridAndMetrics",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchNavigationTests::RunTest(const FString &Parameters)
{
    TArray<FPlayableSketchNavigationSample> Samples;
    FString Error;
    if (!TestTrue(TEXT("Five example analyses complete"),
                  FPlayableSketchNavigationExamples::Run(Samples, Error)))
    {
        AddError(Error);
        return false;
    }
    TestEqual(TEXT("Five examples"), Samples.Num(), 5);
    TestTrue(TEXT("Three rooms reachable"), Samples[0].Result.bReachable);
    TestTrue(TEXT("Straight chain shortest distance is 2800 cm"),
             Samples[0].Result.RouteLengthCm.IsSet() &&
                 Samples[0].Result.RouteLengthCm.GetValue() == 2800.0);
    TestFalse(TEXT("Chain has no alternative"), Samples[0].Result.bAlternativeRoute);
    TestEqual(TEXT("Start and Goal excluded from chain dead ends"), Samples[0].Result.DeadEndCount,
              0);
    TestEqual(TEXT("Branch adds one physical dead end"), Samples[1].Result.DeadEndCount, 1);
    TestTrue(TEXT("Ring has an alternative after each route portal is closed"),
             Samples[2].Result.bAlternativeRoute);
    TestEqual(TEXT("Ring has four physical connections"),
              Samples[2].Result.PhysicalConnections.Num(), 4);
    TestFalse(TEXT("Connected input with closed door is unreachable"),
              Samples[3].Result.bReachable);
    TestFalse(TEXT("Unreachable length is absent, not zero"),
              Samples[3].Result.RouteLengthCm.IsSet());
    TestEqual(TEXT("Closed door is not a physical connection"),
              Samples[3].Result.PhysicalConnections.Num(), 1);
    TestFalse(TEXT("Larger agent cannot fit"), Samples[4].Result.bReachable);
    TestTrue(TEXT("Large agent reports unreachable rooms"),
             !Samples[4].Result.UnreachableRooms.IsEmpty());

    FPlayableSketchFloorPlan Plan;
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    FGuid Start, Goal;
    if (!TestTrue(TEXT("Fixture geometry generated"),
                  FPlayableSketchNavigationExamples::MakePlan(false, false, Plan, Pieces, Start,
                                                              Goal, Error)))
        return false;
    FPlayableSketchNavigationSettings Settings;
    FPlayableSketchNavigationResult Result;
    auto Analyze = [&]() {
        return FPlayableSketchNavigation::Analyze(Plan, Pieces, Start, Goal, Settings, Result,
                                                  Error);
    };
    TestTrue(TEXT("Baseline analyzes"), Analyze());
    const auto BaselinePath = Result.PathPoints;
    TestTrue(TEXT("Repeated BFS analyzes"), Analyze());
    TestTrue(TEXT("Repeated BFS is deterministic"), Result.PathPoints == BaselinePath);
    for (int32 I = 1; I < Result.PathPoints.Num(); ++I)
    {
        const FVector2D D = Result.PathPoints[I] - Result.PathPoints[I - 1];
        TestTrue(TEXT("Only four-neighbor steps"),
                 (FMath::Abs(D.X) == Settings.CellSizeCm && D.Y == 0) ||
                     (FMath::Abs(D.Y) == Settings.CellSizeCm && D.X == 0));
    }
    Plan.Rooms.Swap(0, 2);
    Plan.Corridors.Swap(0, 1);
    TestTrue(TEXT("Reordered arrays analyze"), Analyze());
    TestTrue(TEXT("Array order does not change shortest path"), Result.PathPoints == BaselinePath);

    FPlayableSketchGeometryDescriptor Blocker;
    Blocker.SourceId = Start;
    Blocker.CenterCm = FVector(1000, 300, 150);
    Blocker.SizeCm = FVector(2, 200, 300);
    Pieces.Add(Blocker);
    TestTrue(TEXT("Thin cap analysis completes"), Analyze());
    TestFalse(TEXT("Thin cap cannot be jumped between sampled cell centers"), Result.bReachable);
    Pieces.Pop();
    Blocker.Role = EPlayableSketchGeometryRole::Lintel;
    Blocker.CenterCm = FVector(610, 300, 260);
    Blocker.SizeCm = FVector(20, 200, 80);
    Pieces.Add(Blocker);
    TestTrue(TEXT("High lintel analyzes"), Analyze());
    TestTrue(TEXT("High lintel leaves head clearance"), Result.bReachable);
    Pieces.Last().CenterCm.Z = 235;
    Pieces.Last().SizeCm.Z = 130;
    TestTrue(TEXT("Low lintel analyzes"), Analyze());
    TestFalse(TEXT("Low lintel blocks agent"), Result.bReachable);
    Pieces.Pop();
    Settings.AgentHeightCm = 230;
    TestTrue(TEXT("Tall agent analyzes"), Analyze());
    TestFalse(TEXT("Tall agent is blocked by existing lintels"), Result.bReachable);
    Settings.AgentHeightCm = 180;

    Blocker.CenterCm = FVector(300, 300, 150);
    Blocker.SizeCm = FVector(200, 200, 300);
    Pieces.Add(Blocker);
    TestTrue(TEXT("Blocked start center analyzes"), Analyze());
    TestTrue(TEXT("Nearby walkable representative still reaches Goal"), Result.bReachable);
    if (!Result.PathPoints.IsEmpty())
        TestTrue(TEXT("Start representative moves away from blocked center"),
                 Result.PathPoints[0] != FVector2D(300, 300));
    Pieces.Pop();

    Blocker.CenterCm = FVector(3100, 300, 150);
    Blocker.SizeCm = FVector(600, 600, 300);
    Pieces.Add(Blocker);
    TestTrue(TEXT("Entirely blocked Goal analyzes"), Analyze());
    TestFalse(TEXT("No walkable Goal cell"), Result.bReachable);
    TestTrue(TEXT("Goal explicitly listed as unreachable"), Result.UnreachableRooms.Contains(Goal));
    TestTrue(TEXT("No-cell status is explicit"), Result.Status.Contains(TEXT("no walkable cell")));
    Pieces.Pop();

    Settings.MaxCells = 1;
    TestFalse(TEXT("Oversized grid rejected"), Analyze());
    TestTrue(TEXT("Grid limit error"), Error.Contains(TEXT("MaxCells")));
    Settings.MaxCells = 250000;
    Settings.MaxWork = 1;
    TestFalse(TEXT("Work budget enforced"), Analyze());
    Settings.MaxWork = 50000000;
    Settings.CellSizeCm = 0;
    TestFalse(TEXT("Zero cell size rejected"), Analyze());
    Settings.CellSizeCm = 50;
    Settings.AgentRadiusCm = -1;
    TestFalse(TEXT("Negative radius rejected"), Analyze());
    Settings.AgentRadiusCm = 40;
    const FGuid SavedGoal = Goal;
    Goal = FGuid(999, 0, 0, 0);
    TestFalse(TEXT("Missing Goal rejected"), Analyze());
    Goal = SavedGoal;

    FPlayableSketchFloorPlan Seam;
    FPlayableSketchPlacedRoom A, B;
    A.RoomId = Start;
    A.Bounds = FPlayableSketchRect(FVector2D(0, 0), FVector2D(600, 600));
    B.RoomId = Goal;
    B.Bounds = FPlayableSketchRect(FVector2D(600, 0), FVector2D(1200, 600));
    Seam.Rooms = {A, B};
    TestTrue(TEXT("Union seam analysis completes"),
             FPlayableSketchNavigation::Analyze(Seam, {}, Start, Goal, Settings, Result, Error));
    TestTrue(TEXT("Floor union seam remains walkable"), Result.bReachable);
    Seam.Rooms[1].Bounds.Min.X += 50;
    Seam.Rooms[1].Bounds.Max.X += 50;
    TestTrue(TEXT("Gap analysis completes"),
             FPlayableSketchNavigation::Analyze(Seam, {}, Start, Goal, Settings, Result, Error));
    TestFalse(TEXT("Gap between floors blocks path"), Result.bReachable);

    const FString Filename = FPaths::ConvertRelativePathToFull(
        FPaths::ProjectSavedDir() / TEXT("Navigation/NavigationExamples.json"));
    TestTrue(TEXT("Five samples exported"),
             FPlayableSketchNavigation::ExportJson(Samples, Filename, Error));
    FString Text;
    TestTrue(TEXT("Export reopened from disk"), FFileHelper::LoadFileToString(Text, *Filename));
    TSharedPtr<FJsonObject> Json;
    TestTrue(TEXT("Export is valid JSON"),
             FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json));
    if (Json)
    {
        const auto &Records = Json->GetArrayField(TEXT("samples"));
        TestEqual(TEXT("Five disk records"), Records.Num(), 5);
        if (Records.Num() == 5)
        {
            TestTrue(
                TEXT("Unreachable route serialized as JSON null"),
                Records[3]->AsObject()->TryGetField(TEXT("shortest_route_length_cm"))->IsNull());
            TestEqual(TEXT("Agent radius retained"),
                      Records[4]->AsObject()->GetNumberField(TEXT("agent_radius_cm")), 110.0);
            TestTrue(TEXT("Fixed layouts identified honestly"),
                     Records[0]->AsObject()->GetBoolField(TEXT("fixed_layout_fixture")));
        }
    }
    return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchNavigationIntegrationTests,
                                 "PlayableSketch.Navigation.ActorLifecycle",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchNavigationIntegrationTests::RunTest(const FString &Parameters)
{
    const UWorld::InitializationValues IV = UWorld::InitializationValues()
                                                .AllowAudioPlayback(false)
                                                .RequiresHitProxies(false)
                                                .CreatePhysicsScene(true)
                                                .CreateNavigation(false)
                                                .CreateAISystem(false)
                                                .ShouldSimulatePhysics(false)
                                                .CreateFXSystem(false)
                                                .SetTransactional(false);
    UWorld *World = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true,
                                        ERHIFeatureLevel::Num, &IV);
    if (!TestNotNull(TEXT("Test world"), World))
        return false;
    APlayableSketchLevelActor *Actor = World->SpawnActor<APlayableSketchLevelActor>();
    if (!Actor)
    {
        World->DestroyWorld(false);
        AddError(TEXT("Actor spawn failed."));
        return false;
    }
    Actor->bAutoRebuildGeometry = false;
    Actor->GraphAsset = NewObject<UPlayableSketchGraphAsset>(Actor);
    auto &Graph = Actor->GraphAsset->Graph;
    for (int32 I = 0; I < 3; ++I)
    {
        FPlayableSketchRoom Room;
        Room.RoomId = FGuid(I + 1, 0, 0, 1);
        Room.PositionMode = EPlayableSketchPositionMode::Locked;
        Room.PositionCm = FVector2D(I * 1400, 0);
        Graph.Rooms.Add(Room);
        if (I > 0)
        {
            FPlayableSketchConnection Connection;
            Connection.ConnectionId = FGuid(100 + I, 0, 0, 1);
            Connection.RoomAId = Graph.Rooms[I - 1].RoomId;
            Connection.RoomBId = Room.RoomId;
            Connection.DoorWidthCm = 200;
            Graph.Connections.Add(Connection);
        }
    }
    Graph.StartRoomId = Graph.Rooms[0].RoomId;
    Graph.GoalRoomId = Graph.Rooms[2].RoomId;
    Actor->RebuildGeometry();
    TestTrue(TEXT("Publish automatically analyzes navigation"), Actor->bNavigationCurrent);
    TestTrue(TEXT("Published path is reachable"), Actor->NavigationResult.bReachable);
    TestTrue(TEXT("Rebuild reports navigation time"),
             Actor->LastRebuildReport.Contains(TEXT("NavigationMs=")));
    Graph.Rooms[1].DisplayName = TEXT("Renamed");
    Actor->RebuildLocalGeometry();
    TestTrue(TEXT("Local publish refreshes navigation"), Actor->bNavigationCurrent);
    TestEqual(TEXT("Navigation does not force mesh recreation"), Actor->LastUpdateStats.Created, 0);

    Graph.Connections[0].DoorWidthCm = 100;
    Actor->RebuildLocalGeometry();
    TestFalse(TEXT("Geometrically valid narrow door does not invalidate preview"),
              Actor->bPreviewStale);
    TestTrue(TEXT("Narrow passage analysis is current"), Actor->bNavigationCurrent);
    TestFalse(TEXT("Conservative agent clearance blocks narrow door"),
              Actor->NavigationResult.bReachable);
    TestTrue(TEXT("Old green path removed"), Actor->PreviewPathPoints.IsEmpty());
    Actor->ExportNavigationReport();
    TestTrue(TEXT("Actor current report exported"),
             FPaths::FileExists(Actor->NavigationExportPath));
    Actor->ClearFloors();
    TestFalse(TEXT("Clear invalidates navigation snapshot"), Actor->bNavigationCurrent);
    TestTrue(TEXT("Clear removes path"), Actor->PreviewPathPoints.IsEmpty());
    TestTrue(TEXT("Clear removes navigation grid"),
             Actor->NavigationResult.WalkableCells.IsEmpty());
    World->DestroyWorld(false);
    return !HasAnyErrors();
}

#endif
