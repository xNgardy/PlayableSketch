#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

class AActor;

class PLAYABLESKETCH_API FPlayableSketchFloorBuilder
{
public:
    static bool Build(AActor& Owner, const FPlayableSketchFloorPlan& FloorPlan, double ThicknessCm, FString& OutError);
    static void Clear(AActor& Owner);

    // Shared deterministic corridor floor decomposition; does not create components.
    static TArray<FPlayableSketchRect> BuildCorridorFloorRects(const TArray<FPlayableSketchRect>& Footprints);
};