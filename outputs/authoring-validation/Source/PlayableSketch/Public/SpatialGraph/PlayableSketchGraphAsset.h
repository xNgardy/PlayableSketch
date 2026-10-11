#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "PlayableSketchGraphAsset.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedPlacement
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FGuid RoomId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FVector2D MinCm = FVector2D::ZeroVector;
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedLayout
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    TArray<FPlayableSketchSavedPlacement> Rooms;
};

UCLASS(BlueprintType)
class PLAYABLESKETCH_API UPlayableSketchGraphAsset : public UDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Graph")
    FPlayableSketchGraph Graph;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FPlayableSketchSavedLayout SavedLayout;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomAId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomBId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid RoomToRemoveId;

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddRoom();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddConnection();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void RemoveRoom();

    FString GetSourceText() const;

#if WITH_EDITOR
    virtual void PreEditChange(FProperty* PropertyAboutToChange) override;
    virtual void PreEditChange(FEditPropertyChain& PropertyAboutToChange) override;
    virtual void PostEditChangeChainProperty(FPropertyChangedChainEvent& PropertyChangedEvent) override;
#endif

private:
    TSet<FGuid> RoomsBeforeEdit;
    void CaptureRoomIds();
    void RemoveDeletedRoomConnections();
    void AssignUniqueIds();
};
