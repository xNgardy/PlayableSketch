#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

struct PLAYABLESKETCH_API FPlayableSketchGridPath
{
    TArray<FVector2D> Points;
    int32 WalkableCellCount = 0;
    int32 VisitedCellCount = 0;
};

class PLAYABLESKETCH_API FPlayableSketchGridNavigation
{
  public:
    static bool FindPath(const FPlayableSketchFloorPlan &FloorPlan, const FGuid &StartRoomId,
                         const FGuid &GoalRoomId, int32 GridStepCm,
                         FPlayableSketchGridPath &OutPath, FString &OutError);

  private:
    static bool ContainsPoint(const FPlayableSketchRect &Rect, const FVector2D &Point);
};