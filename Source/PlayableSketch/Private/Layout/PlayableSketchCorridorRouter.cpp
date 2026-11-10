#include "Layout/PlayableSketchCorridorRouter.h"

FVector2D FPlayableSketchCorridorRouter::GetOutwardDirection(EPlayableSketchWallSide WallSide)
{
    switch (WallSide)
    {
    case EPlayableSketchWallSide::North:
        return FVector2D(0.0, 1.0);

    case EPlayableSketchWallSide::East:
        return FVector2D(1.0, 0.0);

    case EPlayableSketchWallSide::South:
        return FVector2D(0.0, -1.0);

    case EPlayableSketchWallSide::West:
        return FVector2D(-1.0, 0.0);

    default:
        return FVector2D::ZeroVector;
    }
}

bool FPlayableSketchCorridorRouter::BuildCandidate(const TArray<FVector2D> &Points, double WidthCm,
                                                   FPlayableSketchCorridorCandidate &OutCandidate)
{
    OutCandidate = FPlayableSketchCorridorCandidate();

    for (const FVector2D &Point : Points)
    {
        if (!FMath::IsFinite(Point.X) || !FMath::IsFinite(Point.Y))
        {
            return false;
        }

        if (OutCandidate.Waypoints.IsEmpty() || OutCandidate.Waypoints.Last() != Point)
        {
            OutCandidate.Waypoints.Add(Point);
        }
    }

    for (int32 Index = 1; Index + 1 < OutCandidate.Waypoints.Num();)
    {
        const FVector2D PreviousDelta =
            OutCandidate.Waypoints[Index] - OutCandidate.Waypoints[Index - 1];
        const FVector2D NextDelta =
            OutCandidate.Waypoints[Index + 1] - OutCandidate.Waypoints[Index];

        const bool bBothHorizontal = PreviousDelta.Y == 0.0 && NextDelta.Y == 0.0;
        const bool bBothVertical = PreviousDelta.X == 0.0 && NextDelta.X == 0.0;

        if (bBothHorizontal || bBothVertical)
        {
            if (FVector2D::DotProduct(PreviousDelta, NextDelta) <= 0.0)
            {
                return false;
            }

            OutCandidate.Waypoints.RemoveAt(Index);
        }
        else
        {
            ++Index;
        }
    }

    if (OutCandidate.Waypoints.Num() < 2)
    {
        return false;
    }

    const double HalfWidthCm = WidthCm * 0.5;

    for (int32 Index = 0; Index + 1 < OutCandidate.Waypoints.Num(); ++Index)
    {
        const FVector2D A = OutCandidate.Waypoints[Index];
        const FVector2D B = OutCandidate.Waypoints[Index + 1];

        FPlayableSketchRect Footprint;

        if (A.Y == B.Y && A.X != B.X)
        {
            Footprint = FPlayableSketchRect(FVector2D(FMath::Min(A.X, B.X), A.Y - HalfWidthCm),
                                            FVector2D(FMath::Max(A.X, B.X), A.Y + HalfWidthCm));
        }
        else if (A.X == B.X && A.Y != B.Y)
        {
            Footprint = FPlayableSketchRect(FVector2D(A.X - HalfWidthCm, FMath::Min(A.Y, B.Y)),
                                            FVector2D(A.X + HalfWidthCm, FMath::Max(A.Y, B.Y)));
        }
        else
        {
            return false;
        }

        if (!Footprint.IsValid())
        {
            return false;
        }

        OutCandidate.Footprints.Add(Footprint);
    }

    for (int32 Index = 1; Index + 1 < OutCandidate.Waypoints.Num(); ++Index)
    {
        const FVector2D Center = OutCandidate.Waypoints[Index];
        const FVector2D Padding(HalfWidthCm, HalfWidthCm);

        OutCandidate.Footprints.Add(FPlayableSketchRect(Center - Padding, Center + Padding));
    }

    return true;
}

bool FPlayableSketchCorridorRouter::BuildCandidates(
    const FPlayableSketchCorridor &Corridor, int32 CorridorWidthCm, int32 GridStepCm,
    TArray<FPlayableSketchCorridorCandidate> &OutCandidates, FString &OutError)
{
    OutCandidates.Reset();
    OutError.Reset();

    if (!Corridor.ConnectionId.IsValid() || !Corridor.DoorA.RoomId.IsValid() ||
        !Corridor.DoorB.RoomId.IsValid() || CorridorWidthCm <= 0 || GridStepCm <= 0)
    {
        OutError = TEXT("Invalid corridor routing input.");
        return false;
    }

    const FVector2D DirectionA = GetOutwardDirection(Corridor.DoorA.WallSide);
    const FVector2D DirectionB = GetOutwardDirection(Corridor.DoorB.WallSide);

    if (DirectionA == FVector2D::ZeroVector || DirectionB == FVector2D::ZeroVector)
    {
        OutError = TEXT("Invalid corridor Door wall side.");
        return false;
    }

    const double ExitDistanceCm = static_cast<double>(CorridorWidthCm) * 0.5 + GridStepCm;

    const FVector2D OutsideA = Corridor.DoorA.PositionCm + DirectionA * ExitDistanceCm;
    const FVector2D OutsideB = Corridor.DoorB.PositionCm + DirectionB * ExitDistanceCm;

    auto AddCandidate = [&](const FVector2D &Elbow) {
        TArray<FVector2D> Points;
        Points.Add(Corridor.DoorA.PositionCm);
        Points.Add(OutsideA);
        Points.Add(Elbow);
        Points.Add(OutsideB);
        Points.Add(Corridor.DoorB.PositionCm);

        FPlayableSketchCorridorCandidate Candidate;

        if (!BuildCandidate(Points, CorridorWidthCm, Candidate))
        {
            return;
        }

        for (const FPlayableSketchCorridorCandidate &Existing : OutCandidates)
        {
            if (Existing.Waypoints == Candidate.Waypoints)
            {
                return;
            }
        }

        OutCandidates.Add(MoveTemp(Candidate));
    };

    AddCandidate(FVector2D(OutsideB.X, OutsideA.Y));

    AddCandidate(FVector2D(OutsideA.X, OutsideB.Y));

    if (OutCandidates.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Routing failed: no valid L candidate for Connection %s."),
                                   *Corridor.ConnectionId.ToString());
        return false;
    }

    return true;
}