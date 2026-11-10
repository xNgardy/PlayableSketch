#pragma once

#include "CoreMinimal.h"
#include "Geometry/PlayableSketchWallGeometry.h"

class AActor;
class UMaterialInterface;

class PLAYABLESKETCH_API FPlayableSketchWallBuilder
{
  public:
    static bool Build(AActor &Owner, const TArray<FPlayableSketchGeometryDescriptor> &Pieces,
                      UMaterialInterface *Material, FString &OutError);

    static void Clear(AActor &Owner);
};