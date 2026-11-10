#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Validation/PlayableSketchValidation.h"

struct PLAYABLESKETCH_API FPlayableSketchLegacyImport
{
    FPlayableSketchGraph Graph;
    FString DocumentId;
    FString RevisionId;
    FString SourceHash;
    FPlayableSketchWallSettings Walls;
    double FloorThicknessCm = 20.0;
    FPlayableSketchRect ExpectedCorridor;
};

class PLAYABLESKETCH_API FPlayableSketchLayoutImporter
{
  public:
    static bool Parse(const FString &Json, FPlayableSketchLegacyImport &OutImport, FString &Error);
    static bool Prepare(const FPlayableSketchLegacyImport &Import,
                        const FPlayableSketchValidationSettings &ActorSettings,
                        FPlayableSketchFloorPlan &OutPlan,
                        TArray<FPlayableSketchGeometryDescriptor> &OutPieces, FString &Error);
};
