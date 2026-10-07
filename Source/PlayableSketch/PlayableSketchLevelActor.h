#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "PlayableSketchLevelActor.generated.h"

UCLASS()
class PLAYABLESKETCH_API APlayableSketchLevelActor : public AActor
{
	GENERATED_BODY()
	
public:	
	APlayableSketchLevelActor();

	UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
	TArray<FPlayableSketchRoom> Rooms;

	UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
	TArray<FPlayableSketchConnection> Connections;

	UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
	FPlayableSketchGraph Graph;

	UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
	TObjectPtr<UPlayableSketchGraphAsset> GraphAsset = nullptr;

	UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
	void ValidateGraph();

protected:
	virtual void BeginPlay() override;

public:	
	virtual void Tick(float DeltaTime) override;

};
