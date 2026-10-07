#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Layout/PlayableSketchFloorPlan.h"

class PLAYABLESKETCH_API FPlayableSketchDoorGenerator
{
public:
    static bool CreateEndpoint(const FPlayableSketchPlacedRoom& Room, EPlayableSketchWallSide WallSide,
            double DoorWidthCm, int32 CornerMarginCm, FPlayableSketchDoorEndpoint& OutDoor, FString& OutError);

    static bool Generate(const FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& FloorPlan, int32 CornerMarginCm, FString& OutError);

private:
    static bool OpeningsOverlap(const FPlayableSketchDoorEndpoint& A, const FPlayableSketchDoorEndpoint& B);
};