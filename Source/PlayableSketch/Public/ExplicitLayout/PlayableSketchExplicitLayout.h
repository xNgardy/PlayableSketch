#pragma once

#include "CoreMinimal.h"
#include "Geometry/PlayableSketchComponentRegistry.h"
#include "Layout/PlayableSketchFloorPlan.h"

struct PLAYABLESKETCH_API FPlayableSketchExplicitSettings
{
    double WallThicknessCm = 20.0;
    double WallHeightCm = 300.0;
    double DoorHeightCm = 220.0;
    double FloorThicknessCm = 20.0;

    bool operator==(const FPlayableSketchExplicitSettings &Other) const;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitVertex
{
    FString Id;
    FVector2D PositionCm = FVector2D::ZeroVector;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitWall
{
    FString Id;
    FString StartVertexId;
    FString EndVertexId;
    int32 Axis = 0;
    TArray<FString> RegionIds;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitRegion
{
    FString Id;
    FString Name;
    FString Role;
    bool bCorridor = false;
    FPlayableSketchRect Bounds;
    TArray<FString> VertexIds;
    TArray<FString> WallIds;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitOpening
{
    FString Id;
    FString WallId;
    FString Type;
    TArray<FString> RegionIds;
    double CenterOffsetCm = 0.0;
    double ClearWidthCm = 0.0;
    double ClearHeightCm = 0.0;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitLayout
{
    FString DocumentId;
    FString RevisionId;
    FString ImageHash;
    FString ValidationMode;
    FString StartRoomId;
    FString GoalRoomId;
    FPlayableSketchExplicitSettings Settings;
    TArray<FPlayableSketchExplicitVertex> Vertices;
    TArray<FPlayableSketchExplicitWall> Walls;
    TArray<FPlayableSketchExplicitRegion> Regions;
    TArray<FPlayableSketchExplicitOpening> Openings;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitGeometry
{
    TArray<FPlayableSketchComponentSpec> Specs;

    FPlayableSketchFloorPlan FloorPlan;
};

class PLAYABLESKETCH_API FPlayableSketchExplicitLayoutBuilder
{
  public:
    static bool Parse(const FString &Json, FPlayableSketchExplicitLayout &OutLayout,
                      FString &Error);
    static bool Build(const FPlayableSketchExplicitLayout &Layout,
                      FPlayableSketchExplicitGeometry &OutGeometry, FString &Error);

    static bool ResolveSettings(const FString &Json,
                                const FPlayableSketchExplicitSettings &Settings, FString &OutJson,
                                FPlayableSketchExplicitLayout &OutLayout, FString &Error);
    static FGuid StableId(const FString &DocumentId, const TCHAR *Kind, const FString &ExternalId);
};
