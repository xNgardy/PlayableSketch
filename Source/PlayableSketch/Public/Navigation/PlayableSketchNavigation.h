#pragma once

#include "CoreMinimal.h"
#include "Geometry/PlayableSketchWallGeometry.h"

struct PLAYABLESKETCH_API FPlayableSketchNavigationSettings
{
    int32 CellSizeCm = 50;
    double AgentRadiusCm = 40.0;
    double AgentHeightCm = 180.0;
    double ClearanceCm = 10.0;
    int32 MaxCells = 250000;
    int64 MaxWork = 50000000;
};

struct PLAYABLESKETCH_API FPlayableSketchNavigationResult
{
    bool bReachable = false;
    TOptional<double> RouteLengthCm;
    int32 DeadEndCount = 0;
    bool bAlternativeRoute = false;
    TArray<FGuid> UnreachableRooms;
    TArray<FGuid> PhysicalConnections;
    TArray<FGuid> RouteConnections;
    TArray<FVector2D> PathPoints;
    FVector2D OriginCm = FVector2D::ZeroVector;
    FIntPoint Dimensions = FIntPoint::ZeroValue;
    int32 CellSizeCm = 50;
    TSet<FIntPoint> WalkableCells;
    int32 VisitedCellCount = 0;
    double BuildMs = 0.0;
    double SearchMs = 0.0;
    double MetricsMs = 0.0;
    double TotalMs = 0.0;
    FString Status;

    FVector2D CellCenter(const FIntPoint &Cell) const;
    FString Summary() const;
};

struct PLAYABLESKETCH_API FPlayableSketchNavigationSample
{
    FString Name;
    int32 Seed = 12345;
    bool bFixedLayout = false;
    int32 RoomCount = 0;
    int32 ConnectionCount = 0;
    FPlayableSketchNavigationSettings Settings;
    FPlayableSketchNavigationResult Result;
};

class PLAYABLESKETCH_API FPlayableSketchNavigation
{
  public:
    static bool Analyze(const FPlayableSketchFloorPlan &Plan,
                        const TArray<FPlayableSketchGeometryDescriptor> &SolidPieces,
                        const FGuid &StartRoomId, const FGuid &GoalRoomId,
                        const FPlayableSketchNavigationSettings &Settings,
                        FPlayableSketchNavigationResult &Result, FString &Error);

    static bool ExportJson(const TArray<FPlayableSketchNavigationSample> &Samples,
                           const FString &Filename, FString &Error);
};
