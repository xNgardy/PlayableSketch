#include "Validation/Tests/PlayableSketchCorridorCandidateTests.h"
#include "Layout/PlayableSketchCorridorRouter.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchLayoutGenerator.h"

void FPlayableSketchCorridorCandidateTests::Run(const FPlayableSketchGraph &Graph)
{
    FPlayableSketchFloorPlan FloorPlan;
    FString Error;

    constexpr int32 GridStepCm = 50;
    constexpr int32 RoomGapCm = 400;

    if (Graph.Connections.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("Corridor candidate test requires at least one Connection."));
        return;
    }

    if (!FPlayableSketchLayoutGenerator::Generate(Graph, GridStepCm, RoomGapCm, FloorPlan, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    if (!FPlayableSketchDoorGenerator::Generate(Graph, FloorPlan, 50, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    for (const FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        const FPlayableSketchConnection *Connection =
            Graph.Connections.FindByPredicate([&Corridor](const FPlayableSketchConnection &Item) {
                return Item.ConnectionId == Corridor.ConnectionId;
            });

        if (!Connection)
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] Missing source Connection."));
            return;
        }

        TArray<FPlayableSketchCorridorCandidate> Candidates;

        if (!FPlayableSketchCorridorRouter::BuildCandidates(Corridor, Connection->CorridorWidthCm,
                                                            GridStepCm, Candidates, Error))
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
            return;
        }

        for (int32 CandidateIndex = 0; CandidateIndex < Candidates.Num(); ++CandidateIndex)
        {
            const FPlayableSketchCorridorCandidate &Candidate = Candidates[CandidateIndex];

            if (Candidate.Waypoints.Num() < 2 || Candidate.Footprints.IsEmpty() ||
                Candidate.Waypoints[0] != Corridor.DoorA.PositionCm ||
                Candidate.Waypoints.Last() != Corridor.DoorB.PositionCm)
            {
                UE_LOG(LogTemp, Error,
                       TEXT("[FAIL] Candidate endpoints or footprints are incorrect."));
                return;
            }

            for (int32 Index = 0; Index + 1 < Candidate.Waypoints.Num(); ++Index)
            {
                const FVector2D Delta = Candidate.Waypoints[Index + 1] - Candidate.Waypoints[Index];

                const bool bHorizontal = Delta.X != 0.0 && Delta.Y == 0.0;
                const bool bVertical = Delta.X == 0.0 && Delta.Y != 0.0;

                if (!bHorizontal && !bVertical)
                {
                    UE_LOG(LogTemp, Error,
                           TEXT("[FAIL] Non-orthogonal or zero-length corridor segment."));
                    return;
                }

                const FPlayableSketchRect &Segment = Candidate.Footprints[Index];
                const FVector2D SegmentSize = Segment.Max - Segment.Min;

                const double ActualWidthCm = bHorizontal ? SegmentSize.Y : SegmentSize.X;

                if (!FMath::IsNearlyEqual(ActualWidthCm,
                                          static_cast<double>(Connection->CorridorWidthCm)))
                {
                    UE_LOG(LogTemp, Error, TEXT("[FAIL] Corridor footprint width is incorrect."));
                    return;
                }
            }

            for (const FPlayableSketchRect &Footprint : Candidate.Footprints)
            {
                if (!Footprint.IsValid())
                {
                    UE_LOG(LogTemp, Error, TEXT("[FAIL] Invalid corridor footprint."));
                    return;
                }
            }

            UE_LOG(LogTemp, Display,
                   TEXT("Connection %s | Candidate %d | Waypoints=%d Footprints=%d"),
                   *Corridor.ConnectionId.ToString(), CandidateIndex, Candidate.Waypoints.Num(),
                   Candidate.Footprints.Num());

            for (const FVector2D &Point : Candidate.Waypoints)
            {
                UE_LOG(LogTemp, Display, TEXT("  Point=(%.0f, %.0f)"), Point.X, Point.Y);
            }
        }

        TArray<FPlayableSketchCorridorCandidate> Repeated;

        if (!FPlayableSketchCorridorRouter::BuildCandidates(Corridor, Connection->CorridorWidthCm,
                                                            GridStepCm, Repeated, Error) ||
            Repeated.Num() != Candidates.Num())
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] Repeat candidate generation changed the result."));
            return;
        }

        for (int32 Index = 0; Index < Candidates.Num(); ++Index)
        {
            if (Candidates[Index].Waypoints != Repeated[Index].Waypoints ||
                Candidates[Index].Footprints.Num() != Repeated[Index].Footprints.Num())
            {
                UE_LOG(LogTemp, Error,
                       TEXT("[FAIL] Repeat candidate generation changed the result."));
                return;
            }

            for (int32 FootprintIndex = 0; FootprintIndex < Candidates[Index].Footprints.Num();
                 ++FootprintIndex)
            {
                const FPlayableSketchRect &A = Candidates[Index].Footprints[FootprintIndex];
                const FPlayableSketchRect &B = Repeated[Index].Footprints[FootprintIndex];

                if (A.Min != B.Min || A.Max != B.Max)
                {
                    UE_LOG(LogTemp, Error, TEXT("[FAIL] Repeat generation changed a footprint."));
                    return;
                }
            }
        }
    }

    UE_LOG(
        LogTemp, Display,
        TEXT(
            "[PASS] Corridor candidates have correct endpoints, orthogonal segments, footprint widths and repeatable results."));
    UE_LOG(LogTemp, Display, TEXT("Corridor candidate tests passed. Connections: %d"),
           FloorPlan.Corridors.Num());
}