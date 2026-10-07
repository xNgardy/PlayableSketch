#pragma once

#include "CoreMinimal.h"
#include "PlayableSketchConnection.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchConnection
{
    GENERATED_BODY()

public:
	FPlayableSketchConnection() : ConnectionId(FGuid::NewGuid()) 
	{
	}
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Identity",meta = (IgnoreForMemberInitializationTest))
    FGuid ConnectionId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomAId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomBId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 CorridorWidthCm = 200;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 DoorWidthCm = 150;
};