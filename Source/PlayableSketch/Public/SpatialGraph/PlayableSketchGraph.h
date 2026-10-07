#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "PlayableSketchGraph.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchGraph
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Graph")
    TArray<FPlayableSketchRoom> Rooms;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Graph")
    TArray<FPlayableSketchConnection> Connections;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Graph")
    FGuid StartRoomId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Graph")
    FGuid GoalRoomId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Generation")
    int32 Seed = 12345;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Version")
    int32 SchemaVersion = 1;
};