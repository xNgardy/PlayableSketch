#include "Validation/Tests/PlayableSketchGridNavigationTests.h"

bool FPlayableSketchGridNavigationTests::Run(const FPlayableSketchFloorPlan& FloorPlan, const FGuid& StartRoomId, const FGuid& GoalRoomId, int32 GridStepCm, FPlayableSketchGridPath& OutPath)
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

    FString Error;

    bool bSuccess = FPlayableSketchGridNavigation::FindPath(FloorPlan, StartRoomId, GoalRoomId, GridStepCm, OutPath, Error);

    Check(TEXT("Start can reach Goal through floor cells"), bSuccess && !OutPath.Points.IsEmpty());

    if (!bSuccess)
    {
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        return false;
    }

    bool bAdjacentSteps = true;

    for (int32 Index = 0; Index + 1 < OutPath.Points.Num(); ++Index)
    {
        const FVector2D Delta = OutPath.Points[Index + 1] - OutPath.Points[Index];

        const bool bHorizontal = FMath::Abs(Delta.X) == GridStepCm && Delta.Y == 0.0;
        const bool bVertical = Delta.X == 0.0 && FMath::Abs(Delta.Y) == GridStepCm;

        if (!bHorizontal && !bVertical)
        {
            bAdjacentSteps = false;
            break;
        }
    }

    Check(TEXT("Path uses adjacent orthogonal cells"), bAdjacentSteps);

    FPlayableSketchGridPath Repeated;

    bSuccess = FPlayableSketchGridNavigation::FindPath(FloorPlan, StartRoomId, GoalRoomId, GridStepCm, Repeated, Error);

    Check(TEXT("Repeated search produces the same path"), bSuccess && Repeated.Points == OutPath.Points);

    FPlayableSketchPlacedRoom RoomA;
    RoomA.RoomId = FGuid(1, 0, 0, 0);
    RoomA.Bounds = FPlayableSketchRect(FVector2D(0, 0), FVector2D(100, 100));

    FPlayableSketchPlacedRoom RoomB;
    RoomB.RoomId = FGuid(2, 0, 0, 0);
    RoomB.Bounds = FPlayableSketchRect(FVector2D(200, 0), FVector2D(300, 100));

    FPlayableSketchFloorPlan Disconnected;
    Disconnected.Rooms.Add(RoomA);
    Disconnected.Rooms.Add(RoomB);

    FPlayableSketchGridPath FailedPath;

    bSuccess = FPlayableSketchGridNavigation::FindPath(Disconnected, RoomA.RoomId, RoomB.RoomId, 50, FailedPath, Error);

    Check(TEXT("Disconnected floors return no path"), !bSuccess && FailedPath.Points.IsEmpty() && Error.Contains(TEXT("No floor grid path")));

    bSuccess = FPlayableSketchGridNavigation::FindPath(FloorPlan, StartRoomId, GoalRoomId, 0, FailedPath, Error);

    Check(TEXT("Zero grid step is rejected"), !bSuccess && !Error.IsEmpty());

    UE_LOG(LogTemp, Display, TEXT("Grid navigation tests: %d/%d passed."), PassedCount, TotalCount);
    UE_LOG(LogTemp, Display, TEXT("Floor path: Points=%d WalkableCells=%d VisitedCells=%d"), OutPath.Points.Num(), OutPath.WalkableCellCount, OutPath.VisitedCellCount);

    return PassedCount == TotalCount;
}