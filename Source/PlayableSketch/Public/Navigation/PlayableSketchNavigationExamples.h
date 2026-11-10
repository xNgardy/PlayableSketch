#pragma once

#include "Navigation/PlayableSketchNavigation.h"

class PLAYABLESKETCH_API FPlayableSketchNavigationExamples
{
  public:
    static bool MakePlan(bool bRing, bool bBranch, FPlayableSketchFloorPlan &Plan,
                         TArray<FPlayableSketchGeometryDescriptor> &Pieces, FGuid &Start,
                         FGuid &Goal, FString &Error);
    static bool Run(TArray<FPlayableSketchNavigationSample> &Samples, FString &Error);
};
