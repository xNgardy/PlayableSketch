#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Layout/PlayableSketchFloorPlan.h"

class PLAYABLESKETCH_API FPlayableSketchLayoutGenerator
{
  public:
    static bool Generate(const FPlayableSketchGraph &Graph, int32 GridStepCm, int32 RoomGapCm,
                         FPlayableSketchFloorPlan &OutFloorPlan, FString &OutError,
                         int32 MaxPlacementAttempts = 128);
};