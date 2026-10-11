#pragma once

#include "CoreMinimal.h"
#include "PlayableSketchRoom.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchRoomType : uint8
{
    Generic,
    Hub
};

UENUM(BlueprintType)
enum class EPlayableSketchRoomRole : uint8
{
    None,
    Start,
    Goal
};

UENUM(BlueprintType)
enum class EPlayableSketchPositionMode : uint8
{
    Auto,
    Locked
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchRoom
{
    GENERATED_BODY()

public:
    FPlayableSketchRoom()
        : RoomId(FGuid::NewGuid())
    {
    }
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Identity", meta = (IgnoreForMemberInitializationTest))
    FGuid RoomId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    FString DisplayName = TEXT("Room");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    EPlayableSketchRoomType RoomType = EPlayableSketchRoomType::Generic;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Room")
    EPlayableSketchRoomRole RoomRole = EPlayableSketchRoomRole::None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement")
    EPlayableSketchPositionMode PositionMode = EPlayableSketchPositionMode::Auto;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement", meta = (EditCondition = "PositionMode == EPlayableSketchPositionMode::Locked"))
    FVector2D PositionCm = FVector2D::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))
    int32 WidthCm = 600;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))
    int32 DepthCm = 600;
};