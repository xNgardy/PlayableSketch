#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "PlayableSketchImportedLayoutAsset.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchLayoutSource : uint8
{
    ProceduralGraph,
    ImportedExplicitLayout
};

UCLASS(BlueprintType)
class PLAYABLESKETCH_API UPlayableSketchImportedLayoutAsset : public UDataAsset
{
    GENERATED_BODY()

  public:
    UPROPERTY(VisibleAnywhere, Category = "Layout")
    FString CanonicalJson;

    UPROPERTY(VisibleAnywhere, Category = "Import")
    FString DocumentId;

    UPROPERTY(VisibleAnywhere, Category = "Import")
    FString RevisionId;

    UPROPERTY(VisibleAnywhere, Category = "Import")
    FString ImageHash;
};
