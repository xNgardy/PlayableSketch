#include "Validation/Tests/PlayableSketchCorridorRoutingTests.h"
#include "Layout/PlayableSketchCorridorRouting.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchLayoutGenerator.h"

void FPlayableSketchCorridorRoutingTests::Run(const FPlayableSketchGraph &Graph)
{
    int32 PassedCount = 0;
    int32 TotalCount = 0;

    auto Check = [&PassedCount, &TotalCount](const TCHAR *Name, bool bPassed) {
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

    if (Graph.Connections.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("Routing test requires at least one Connection."));
        return;
    }

    FPlayableSketchFloorPlan FloorPlan;
    FString Error;

    if (!FPlayableSketchLayoutGenerator::Generate(Graph, 50, 400, FloorPlan, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    if (!FPlayableSketchDoorGenerator::Generate(Graph, FloorPlan, 50, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    if (!FPlayableSketchCorridorRouting::Generate(Graph, FloorPlan, 50, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    Check(TEXT("Every Connection has a routed corridor"),
          FloorPlan.Corridors.Num() == Graph.Connections.Num());

    bool bAllRoutesValid = true;

    TArray<FPlayableSketchCorridor> Accepted;

    for (const FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        FPlayableSketchCorridorCandidate Candidate;
        Candidate.Footprints = Corridor.Footprints;

        if (!FPlayableSketchCorridorRouting::ValidateCandidate(Candidate, FloorPlan.Rooms, Accepted,
                                                               Error))
        {
            bAllRoutesValid = false;
            UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
        }

        Accepted.Add(Corridor);

        UE_LOG(LogTemp, Display, TEXT("Routed Connection %s | Footprints=%d"),
               *Corridor.ConnectionId.ToString(), Corridor.Footprints.Num());
    }

    Check(TEXT("Routes avoid Room interiors and other corridors"), bAllRoutesValid);

    const TArray<FPlayableSketchCorridor> Baseline = FloorPlan.Corridors;

    bool bSuccess = FPlayableSketchCorridorRouting::Generate(Graph, FloorPlan, 50, Error);
    bool bSameResult = bSuccess && FloorPlan.Corridors.Num() == Baseline.Num();

    if (bSameResult)
    {
        for (int32 Index = 0; Index < Baseline.Num(); ++Index)
        {
            const FPlayableSketchCorridor &A = Baseline[Index];
            const FPlayableSketchCorridor &B = FloorPlan.Corridors[Index];

            if (A.ConnectionId != B.ConnectionId || A.Footprints.Num() != B.Footprints.Num())
            {
                bSameResult = false;
                break;
            }

            for (int32 FootprintIndex = 0; FootprintIndex < A.Footprints.Num(); ++FootprintIndex)
            {
                if (A.Footprints[FootprintIndex].Min != B.Footprints[FootprintIndex].Min ||
                    A.Footprints[FootprintIndex].Max != B.Footprints[FootprintIndex].Max)
                {
                    bSameResult = false;
                    break;
                }
            }
        }
    }

    Check(TEXT("Repeat routing preserves footprints without duplication"), bSameResult);

    FPlayableSketchCorridorCandidate CrossingCandidate;
    CrossingCandidate.Footprints = Baseline[0].Footprints;

    const TArray<FPlayableSketchPlacedRoom> NoRooms;
    TArray<FPlayableSketchCorridor> ExistingCorridors;
    ExistingCorridors.Add(Baseline[0]);

    bSuccess = FPlayableSketchCorridorRouting::ValidateCandidate(CrossingCandidate, NoRooms,
                                                                 ExistingCorridors, Error);

    Check(TEXT("Overlapping another corridor is rejected"),
          !bSuccess && Error.Contains(Baseline[0].ConnectionId.ToString()));

    FPlayableSketchPlacedRoom Blocker;
    Blocker.RoomId = FGuid(9, 8, 7, 6);

    FVector2D BlockerMin = FloorPlan.Rooms[0].Bounds.Min;
    FVector2D BlockerMax = FloorPlan.Rooms[0].Bounds.Max;

    for (const FPlayableSketchPlacedRoom &Room : FloorPlan.Rooms)
    {
        BlockerMin.X = FMath::Min(BlockerMin.X, Room.Bounds.Min.X);
        BlockerMin.Y = FMath::Min(BlockerMin.Y, Room.Bounds.Min.Y);
        BlockerMax.X = FMath::Max(BlockerMax.X, Room.Bounds.Max.X);
        BlockerMax.Y = FMath::Max(BlockerMax.Y, Room.Bounds.Max.Y);
    }

    Blocker.Bounds =
        FPlayableSketchRect(BlockerMin - FVector2D(1000, 1000), BlockerMax + FVector2D(1000, 1000));

    FPlayableSketchFloorPlan BlockedPlan = FloorPlan;
    BlockedPlan.Rooms.Add(Blocker);

    bSuccess = FPlayableSketchCorridorRouting::Generate(Graph, BlockedPlan, 50, Error);

    const bool bCorrectFailure = !bSuccess && Error.Contains(TEXT("Routing failed")) &&
                                 Error.Contains(Baseline[0].ConnectionId.ToString());

    Check(TEXT("Blocked routing reports the Connection ID"), bCorrectFailure);

    UE_LOG(LogTemp, Display, TEXT("Expected routing failure: %s"), *Error);

    bool bNoStaleFootprints = true;

    for (const FPlayableSketchCorridor &Corridor : BlockedPlan.Corridors)
    {
        if (!Corridor.Footprints.IsEmpty())
        {
            bNoStaleFootprints = false;
        }
    }

    Check(TEXT("Failed routing leaves no stale corridor footprints"), bNoStaleFootprints);

    UE_LOG(LogTemp, Display, TEXT("Corridor routing tests: %d/%d passed."), PassedCount,
           TotalCount);
}