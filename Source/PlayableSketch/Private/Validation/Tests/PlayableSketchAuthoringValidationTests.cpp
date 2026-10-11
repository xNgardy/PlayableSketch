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