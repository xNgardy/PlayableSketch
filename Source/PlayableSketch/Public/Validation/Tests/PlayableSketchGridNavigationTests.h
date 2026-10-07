#pragma once

#include "CoreMinimal.h"
#include "Navigation/PlayableSketchGridNavigation.h"

class PLAYABLESKETCH_API FPlayableSketchGridNavigationTests
{
public:
    static bool Run(const FPlayableSketchFloorPlan& FloorPlan, const FGuid& StartRoomId, const FGuid& GoalRoomId, int32 GridStepCm, FPlayableSketchGridPath& OutPath);
};