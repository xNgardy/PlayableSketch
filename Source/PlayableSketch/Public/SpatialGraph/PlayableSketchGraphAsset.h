#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "PlayableSketchGraphAsset.generated.h"

UCLASS(BlueprintType)
class PLAYABLESKETCH_API UPlayableSketchGraphAsset : public UDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Graph")
    FPlayableSketchGraph Graph;
};