#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Layout/PlayableSketchCorridorRouter.h"

class PLAYABLESKETCH_API FPlayableSketchCorridorRouting
{
public:
    static bool ValidateCandidate(const FPlayableSketchCorridorCandidate& Candidate, const TArray<FPlayableSketchPlacedRoom>& Rooms, const TArray<FPlayableSketchCorridor>& AcceptedCorridors, FString& OutError);

    static bool Generate(const FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& FloorPlan, int32 GridStepCm, FString& OutError);
};