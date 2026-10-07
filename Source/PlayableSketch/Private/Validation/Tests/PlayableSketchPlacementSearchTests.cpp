#include "Validation/Tests/PlayableSketchPlacementSearchTests.h"
#include "Layout/PlayableSketchPlacementSearch.h"

void FPlayableSketchPlacementSearchTests::Run()
{
    const FGuid RoomId(1, 0, 0, 0);
    const FGuid ObstacleId(2, 0, 0, 0);

    FPlayableSketchPlacedRoom Obstacle;
    Obstacle.RoomId = ObstacleId;
    Obstacle.Bounds = FPlayableSketchRect(FVector2D(0, 0), FVector2D(50, 50));

    TArray<FPlayableSketchPlacedRoom> ExistingRooms;
    ExistingRooms.Add(Obstacle);

    FPlayableSketchPlacedRoom Result;
    FString Error;

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

    bool bSuccess = FPlayableSketchPlacementSearch::FindPlacement(RoomId, FVector2D(50, 50), FVector2D(0, 0), ExistingRooms, 50, 0, 1, Result, Error);

    Check(TEXT("One blocked attempt returns failure"), !bSuccess && !Result.RoomId.IsValid());
    Check(TEXT("Failure includes Room ID and attempt count"), Error.Contains(RoomId.ToString()) && Error.Contains(TEXT("after 1 attempts")));

    UE_LOG(LogTemp, Display, TEXT("Expected failure: %s"), *Error);

    bSuccess = FPlayableSketchPlacementSearch::FindPlacement(RoomId, FVector2D(50, 50), FVector2D(0, 0), ExistingRooms, 50, 0, 2, Result, Error);

    Check(TEXT("Second candidate succeeds at X=50"), bSuccess && Result.RoomId == RoomId && Result.Bounds.Min == FVector2D(50, 0) && Result.Bounds.Max == FVector2D(100, 50) && Error.IsEmpty());

    bSuccess = FPlayableSketchPlacementSearch::FindPlacement(RoomId, FVector2D(50, 50), FVector2D(0, 0), ExistingRooms, 50, 50, 2, Result, Error);

    Check(TEXT("Gap blocks the first two candidates"), !bSuccess && !Result.RoomId.IsValid());

    bSuccess = FPlayableSketchPlacementSearch::FindPlacement(RoomId, FVector2D(50, 50), FVector2D(0, 0), ExistingRooms, 50, 50, 3, Result, Error);

    Check(TEXT("Third candidate preserves 50 cm gap"), bSuccess && Result.Bounds.Min == FVector2D(100, 0));

    bSuccess = FPlayableSketchPlacementSearch::FindPlacement(RoomId, FVector2D(50, 50), FVector2D(0, 0), ExistingRooms, 50, 0, 0, Result, Error);

    Check(TEXT("Zero attempt limit is rejected"), !bSuccess && !Error.IsEmpty() && !Result.RoomId.IsValid());

    UE_LOG(LogTemp, Display, TEXT("Placement search tests: %d/%d passed."), PassedCount, TotalCount);
}