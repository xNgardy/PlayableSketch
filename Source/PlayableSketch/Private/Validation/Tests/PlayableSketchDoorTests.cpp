#include "Validation/Tests/PlayableSketchDoorTests.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchLayoutGenerator.h"

void FPlayableSketchDoorTests::Run(const FPlayableSketchGraph& Graph)
{
    int32 PassedCount = 0;
    int32 TotalCount = 0;

    auto Check = [&PassedCount, &TotalCount](const TCHAR* Name, bool bPassed)
        {
            ++TotalCount;

            if (bPassed)
            {
                ++PassedCount;

                UE_LOG(LogTemp, Display, TEXT("[PASS] %s"), Name);
            }
            else
            {
                UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), Name);
            }
        };

    FPlayableSketchPlacedRoom TestRoom;
    TestRoom.RoomId = FGuid(1, 0, 0, 0);
    TestRoom.Bounds = FPlayableSketchRect(FVector2D(100, 200), FVector2D(700, 800));

    FPlayableSketchDoorEndpoint Door;
    FString Error;

    auto TestSide = [&](const TCHAR* Name, EPlayableSketchWallSide Side, const FVector2D& ExpectedPosition)
        {
            const bool bSuccess = FPlayableSketchDoorGenerator::CreateEndpoint(TestRoom, Side, 150.0, 50, Door, Error);

            Check(Name, bSuccess && Door.RoomId == TestRoom.RoomId && Door.WallSide == Side && Door.PositionCm == ExpectedPosition && Door.WidthCm == 150.0 && Error.IsEmpty());
        };

    TestSide(TEXT("North Door position"), EPlayableSketchWallSide::North, FVector2D(400, 800));
    TestSide(TEXT("East Door position"), EPlayableSketchWallSide::East, FVector2D(700, 500));
    TestSide(TEXT("South Door position"), EPlayableSketchWallSide::South, FVector2D(400, 200));
    TestSide(TEXT("West Door position"), EPlayableSketchWallSide::West, FVector2D(100, 500));

    bool bSuccess = FPlayableSketchDoorGenerator::CreateEndpoint(TestRoom, EPlayableSketchWallSide::East, 500.0, 50, Door, Error);

    Check(TEXT("Exact corner margin is accepted"), bSuccess && Door.WidthCm == 500.0);

    bSuccess = FPlayableSketchDoorGenerator::CreateEndpoint(TestRoom, EPlayableSketchWallSide::East, 501.0, 50, Door, Error);

    Check(TEXT("Door exceeding corner margin is rejected"), !bSuccess && !Door.RoomId.IsValid() && Error.Contains(TestRoom.RoomId.ToString()));

    bSuccess = FPlayableSketchDoorGenerator::CreateEndpoint(TestRoom, EPlayableSketchWallSide::East, 0.0, 50, Door, Error);

    Check(TEXT("Zero Door width is rejected"), !bSuccess);

    FPlayableSketchFloorPlan FloorPlan;

    if (!FPlayableSketchLayoutGenerator::Generate(Graph, 50, 100, FloorPlan, Error))
    {
        Check(TEXT("Graph Room placement"), false);
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    if (!FPlayableSketchDoorGenerator::Generate(Graph, FloorPlan, 50, Error))
    {
        Check(TEXT("Graph Door generation"), false);
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return;
    }

    Check(TEXT("One endpoint pair per Connection"), FloorPlan.Corridors.Num() == Graph.Connections.Num());

    bool bCorrectOwnership = true;

    for (const FPlayableSketchCorridor& Corridor : FloorPlan.Corridors)
    {
        const FPlayableSketchConnection* Connection = Graph.Connections.FindByPredicate([&Corridor](const FPlayableSketchConnection& Item)
            {
                return Item.ConnectionId == Corridor.ConnectionId;
            });

        if (!Connection || Corridor.DoorA.RoomId != Connection->RoomAId || Corridor.DoorB.RoomId != Connection->RoomBId || Corridor.DoorA.WidthCm != Connection->DoorWidthCm || Corridor.DoorB.WidthCm != Connection->DoorWidthCm || !Corridor.Footprints.IsEmpty())
        {
            bCorrectOwnership = false;
        }

        UE_LOG(LogTemp, Display, TEXT("Connection %s | DoorA Room=%s Side=%d Pos=(%.0f, %.0f) | DoorB Room=%s Side=%d Pos=(%.0f, %.0f)"), *Corridor.ConnectionId.ToString(), *Corridor.DoorA.RoomId.ToString(), static_cast<int32>(Corridor.DoorA.WallSide), Corridor.DoorA.PositionCm.X, Corridor.DoorA.PositionCm.Y, *Corridor.DoorB.RoomId.ToString(), static_cast<int32>(Corridor.DoorB.WallSide), Corridor.DoorB.PositionCm.X, Corridor.DoorB.PositionCm.Y);
    }

    Check(TEXT("Endpoint ownership, width and empty routing footprints"), bCorrectOwnership);

    bSuccess = FPlayableSketchDoorGenerator::Generate(Graph, FloorPlan, 50, Error);

    Check(TEXT("Repeat generation does not duplicate endpoint pairs"), bSuccess && FloorPlan.Corridors.Num() == Graph.Connections.Num());

    UE_LOG(LogTemp, Display, TEXT("Door tests: %d/%d passed."), PassedCount, TotalCount);
}