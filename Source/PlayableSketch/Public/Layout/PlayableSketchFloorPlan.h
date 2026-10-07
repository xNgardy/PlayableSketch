#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchRect.h"

enum class EPlayableSketchWallSide : uint8
{
    North,
    East,
    South,
    West
};

struct PLAYABLESKETCH_API FPlayableSketchPlacedRoom
{
    FGuid RoomId;
    FPlayableSketchRect Bounds;
};

struct PLAYABLESKETCH_API FPlayableSketchDoorEndpoint
{
    FGuid RoomId;
    EPlayableSketchWallSide WallSide = EPlayableSketchWallSide::North;

    FVector2D PositionCm = FVector2D::ZeroVector;
    double WidthCm = 150.0;
};

struct PLAYABLESKETCH_API FPlayableSketchCorridor
{
    FGuid ConnectionId;

    FPlayableSketchDoorEndpoint DoorA;
    FPlayableSketchDoorEndpoint DoorB;

    TArray<FPlayableSketchRect> Footprints;
};

struct PLAYABLESKETCH_API FPlayableSketchFloorPlan
{
    TArray<FPlayableSketchPlacedRoom> Rooms;
    TArray<FPlayableSketchCorridor> Corridors;
};