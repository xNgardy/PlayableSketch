#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"

enum class EPlayableSketchGeometryRole : uint8
{
    Wall,
    Lintel
};

struct PLAYABLESKETCH_API FPlayableSketchWallSegment
{
    FVector2D StartCm = FVector2D::ZeroVector;
    FVector2D Tangent = FVector2D(1.0, 0.0);
    FVector2D Outward = FVector2D(0.0, 1.0);
    double LengthCm = 0.0;
};

struct PLAYABLESKETCH_API FPlayableSketchWallOpening
{
    double StartCm = 0.0;
    double EndCm = 0.0;
};

struct PLAYABLESKETCH_API FPlayableSketchWallSettings
{
    double HeightCm = 300.0;
    double ThicknessCm = 20.0;
    double DoorHeightCm = 220.0;
    double CornerMarginCm = 50.0;
};

struct PLAYABLESKETCH_API FPlayableSketchGeometryDescriptor
{
    FGuid SourceId;
    bool bRoom = false;
    EPlayableSketchGeometryRole Role = EPlayableSketchGeometryRole::Wall;
    FVector CenterCm = FVector::ZeroVector;
    FVector SizeCm = FVector::ZeroVector;
};

class PLAYABLESKETCH_API FPlayableSketchWallGeometry
{
public:
    static bool SplitWall(
        const FPlayableSketchWallSegment& Wall,
        const TArray<FPlayableSketchWallOpening>& Openings,
        const FPlayableSketchWallSettings& Settings,
        const FGuid& SourceId,
        bool bRoom,
        TArray<FPlayableSketchGeometryDescriptor>& OutPieces,
        FString& OutError);

    static bool Generate(
        const FPlayableSketchFloorPlan& FloorPlan,
        const FPlayableSketchWallSettings& Settings,
        TArray<FPlayableSketchGeometryDescriptor>& OutPieces,
        FString& OutError);
};