#include "Layout/PlayableSketchPlacementSearch.h"

bool FPlayableSketchPlacementSearch::FindPlacement(const FGuid& RoomId, const FVector2D& SizeCm, const FVector2D& PreferredMinCm, const TArray<FPlayableSketchPlacedRoom>& ExistingRooms, int32 GridStepCm, int32 RoomGapCm, int32 MaxAttempts, FPlayableSketchPlacedRoom& OutRoom, FString& OutError)
{
    OutRoom = FPlayableSketchPlacedRoom();
    OutError.Reset();

    if (!RoomId.IsValid() || GridStepCm <= 0 || RoomGapCm < 0 || MaxAttempts <= 0)
    {
        OutError = FString::Printf(TEXT("Invalid placement settings for Room %s."), *RoomId.ToString());
        return false;
    }

    if (!FMath::IsFinite(SizeCm.X) || !FMath::IsFinite(SizeCm.Y) || !FMath::IsFinite(PreferredMinCm.X) || !FMath::IsFinite(PreferredMinCm.Y) || SizeCm.X <= 0.0 || SizeCm.Y <= 0.0)
    {
        OutError = FString::Printf(TEXT("Invalid placement dimensions or position for Room %s."), *RoomId.ToString());
        return false;
    }

    for (const FPlayableSketchPlacedRoom& ExistingRoom : ExistingRooms)
    {
        if (!ExistingRoom.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid existing bounds: Room %s."), *ExistingRoom.RoomId.ToString());
            return false;
        }
    }

    const double Grid = static_cast<double>(GridStepCm);

    const FVector2D AlignedSize(FMath::CeilToDouble(SizeCm.X / Grid) * Grid, FMath::CeilToDouble(SizeCm.Y / Grid) * Grid);
    const FVector2D AlignedMin(FMath::CeilToDouble(PreferredMinCm.X / Grid) * Grid, FMath::CeilToDouble(PreferredMinCm.Y / Grid) * Grid);

    for (int32 Attempt = 0; Attempt < MaxAttempts; ++Attempt)
    {
        const FVector2D CandidateMin = AlignedMin + FVector2D(static_cast<double>(Attempt) * Grid, 0.0);

        FPlayableSketchPlacedRoom Candidate;
        Candidate.RoomId = RoomId;
        Candidate.Bounds = FPlayableSketchRect(CandidateMin, CandidateMin + AlignedSize);

        if (!Candidate.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid candidate bounds for Room %s."), *RoomId.ToString());
            return false;
        }

        bool bFits = true;

        for (const FPlayableSketchPlacedRoom& ExistingRoom : ExistingRooms)
        {
            if (!Candidate.Bounds.HasRequiredGap(ExistingRoom.Bounds, RoomGapCm))
            {
                bFits = false;
                break;
            }
        }

        if (bFits)
        {
            OutRoom = Candidate;
            return true;
        }
    }

    OutError = FString::Printf(TEXT("Placement failed: Room %s, no valid position found after %d attempts."), *RoomId.ToString(), MaxAttempts);

    return false;
}