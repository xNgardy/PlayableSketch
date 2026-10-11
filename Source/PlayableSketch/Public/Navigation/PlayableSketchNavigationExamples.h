#pragma once

#include "Navigation/PlayableSketchNavigation.h"

class PLAYABLESKETCH_API FPlayableSketchNavigationExamples
{
public:
    // Fixed layouts, not random generation experiments. Shared by demo and regression tests.
    static bool MakePlan(bool bRing, bool bBranch, FPlayableSketchFloorPlan& Plan,
        TArray<FPlayableSketchGeometryDescriptor>& Pieces, FGuid& Start, FGuid& Goal, FString& Error);
    static bool Run(TArray<FPlayableSketchNavigationSample>& Samples, FString& Error);
};
