#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

struct PLAYABLESKETCH_API FPlayableSketchCorridorCandidate
{
    TArray<FVector2D> Waypoints;
    TArray<FPlayableSketchRect> Footprints;
};

class PLAYABLESKETCH_API FPlayableSketchCorridorRouter
{
  public:
    static bool BuildCandidates(const FPlayableSketchCorridor &Corridor, int32 CorridorWidthCm,
                                int32 GridStepCm,
                                TArray<FPlayableSketchCorridorCandidate> &OutCandidates,
                                FString &OutError);

  private:
    static FVector2D GetOutwardDirection(EPlayableSketchWallSide WallSide);
    static bool BuildCandidate(const TArray<FVector2D> &Points, double WidthCm,
                               FPlayableSketchCorridorCandidate &OutCandidate);
};