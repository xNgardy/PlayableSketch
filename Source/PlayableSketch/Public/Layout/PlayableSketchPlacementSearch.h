#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

class PLAYABLESKETCH_API FPlayableSketchPlacementSearch
{
public:
    static bool FindPlacement(const FGuid& RoomId, const FVector2D& SizeCm, const FVector2D& PreferredMinCm,
            const TArray<FPlayableSketchPlacedRoom>& ExistingRooms, int32 GridStepCm, int32 RoomGapCm,
            int32 MaxAttempts, FPlayableSketchPlacedRoom& OutRoom, FString& OutError);
};