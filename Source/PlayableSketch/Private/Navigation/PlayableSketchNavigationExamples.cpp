#include "Navigation/PlayableSketchNavigationExamples.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchCorridorRouting.h"

bool FPlayableSketchNavigationExamples::MakePlan(bool bRing, bool bBranch,
                                                 FPlayableSketchFloorPlan &Plan,
                                                 TArray<FPlayableSketchGeometryDescriptor> &Pieces,
                                                 FGuid &Start, FGuid &Goal, FString &Error)
{
    Plan = FPlayableSketchFloorPlan();
    Pieces.Reset();
    FPlayableSketchGraph Graph;
    TArray<FVector2D> Positions =
        bRing ? TArray<FVector2D>{{0, 0}, {1400, 0}, {1400, 1400}, {0, 1400}}
              : TArray<FVector2D>{{0, 0}, {1400, 0}, {2800, 0}};
    if (bBranch && !bRing)
        Positions.Add(FVector2D(1400, 1400));
    for (int32 I = 0; I < Positions.Num(); ++I)
    {
        FPlayableSketchRoom R;
        R.RoomId = FGuid(I + 1, 0, 0, 1);
        R.PositionMode = EPlayableSketchPositionMode::Locked;
        R.PositionCm = Positions[I];
        Graph.Rooms.Add(R);
        FPlayableSketchPlacedRoom P;
        P.RoomId = R.RoomId;
        P.Bounds = FPlayableSketchRect(R.PositionCm, R.PositionCm + FVector2D(600, 600));
        Plan.Rooms.Add(P);
    }
    auto AddConnection = [&](int32 A, int32 B) {
        FPlayableSketchConnection C;
        C.ConnectionId = FGuid(100 + Graph.Connections.Num(), 0, 0, 1);
        C.RoomAId = Graph.Rooms[A].RoomId;
        C.RoomBId = Graph.Rooms[B].RoomId;
        C.DoorWidthCm = 200;
        Graph.Connections.Add(C);
    };
    AddConnection(0, 1);
    AddConnection(1, 2);
    if (bRing)
    {
        AddConnection(2, 3);
        AddConnection(3, 0);
    }
    else if (bBranch)
        AddConnection(1, 3);
    Start = Graph.StartRoomId = Graph.Rooms[0].RoomId;
    Goal = Graph.GoalRoomId = Graph.Rooms[2].RoomId;
    return FPlayableSketchDoorGenerator::Generate(Graph, Plan, 50, Error) &&
           FPlayableSketchCorridorRouting::Generate(Graph, Plan, 50, Error) &&
           FPlayableSketchWallGeometry::Generate(Plan, FPlayableSketchWallSettings(), Pieces,
                                                 Error);
}

bool FPlayableSketchNavigationExamples::Run(TArray<FPlayableSketchNavigationSample> &Samples,
                                            FString &Error)
{
    Samples.Reset();
    const TCHAR *Names[] = {TEXT("ThreeRooms"), TEXT("ChainWithBranch"), TEXT("Ring"),
                            TEXT("BlockedDoor"), TEXT("LargeAgent")};
    for (int32 I = 0; I < 5; ++I)
    {
        FPlayableSketchFloorPlan Plan;
        TArray<FPlayableSketchGeometryDescriptor> Pieces;
        FGuid Start, Goal;
        if (!MakePlan(I == 2, I == 1, Plan, Pieces, Start, Goal, Error))
            return false;
        FPlayableSketchNavigationSample Sample;
        Sample.Name = Names[I];
        Sample.bFixedLayout = true;
        Sample.RoomCount = Plan.Rooms.Num();
        Sample.ConnectionCount = Plan.Corridors.Num();
        if (I == 3)
        {
            FPlayableSketchGeometryDescriptor Cap;
            Cap.SourceId = Start;
            Cap.bRoom = true;
            Cap.CenterCm = FVector(610, 300, 150);
            Cap.SizeCm = FVector(20, 200, 300);
            Pieces.Add(Cap);
        }
        if (I == 4)
            Sample.Settings.AgentRadiusCm = 110;
        if (!FPlayableSketchNavigation::Analyze(Plan, Pieces, Start, Goal, Sample.Settings,
                                                Sample.Result, Error))
            return false;
        Samples.Add(MoveTemp(Sample));
    }
    return true;
}
