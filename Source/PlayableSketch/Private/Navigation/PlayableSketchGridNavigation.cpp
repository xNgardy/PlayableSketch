#include "Navigation/PlayableSketchGridNavigation.h"

bool FPlayableSketchGridNavigation::ContainsPoint(const FPlayableSketchRect &Rect,
                                                  const FVector2D &Point)
{
    return Point.X >= Rect.Min.X && Point.X < Rect.Max.X && Point.Y >= Rect.Min.Y &&
           Point.Y < Rect.Max.Y;
}

bool FPlayableSketchGridNavigation::FindPath(const FPlayableSketchFloorPlan &FloorPlan,
                                             const FGuid &StartRoomId, const FGuid &GoalRoomId,
                                             int32 GridStepCm, FPlayableSketchGridPath &OutPath,
                                             FString &OutError)
{
    OutPath = FPlayableSketchGridPath();
    OutError.Reset();

    if (GridStepCm <= 0 || !StartRoomId.IsValid() || !GoalRoomId.IsValid() ||
        StartRoomId == GoalRoomId)
    {
        OutError = TEXT("Invalid navigation input.");
        return false;
    }

    const FPlayableSketchPlacedRoom *StartRoom =
        FloorPlan.Rooms.FindByPredicate([&StartRoomId](const FPlayableSketchPlacedRoom &Room) {
            return Room.RoomId == StartRoomId;
        });

    const FPlayableSketchPlacedRoom *GoalRoom = FloorPlan.Rooms.FindByPredicate(
        [&GoalRoomId](const FPlayableSketchPlacedRoom &Room) { return Room.RoomId == GoalRoomId; });

    if (!StartRoom || !GoalRoom)
    {
        OutError = TEXT("Start or Goal Room is missing from FloorPlan.");
        return false;
    }

    TArray<FPlayableSketchRect> Areas;

    for (const FPlayableSketchPlacedRoom &Room : FloorPlan.Rooms)
    {
        Areas.Add(Room.Bounds);
    }

    for (const FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        Areas.Append(Corridor.Footprints);
    }

    for (const FPlayableSketchRect &Area : Areas)
    {
        if (!Area.IsValid())
        {
            OutError = TEXT("Navigation input contains invalid bounds.");
            return false;
        }
    }

    FVector2D Min = Areas[0].Min;
    FVector2D Max = Areas[0].Max;

    for (const FPlayableSketchRect &Area : Areas)
    {
        Min.X = FMath::Min(Min.X, Area.Min.X);
        Min.Y = FMath::Min(Min.Y, Area.Min.Y);
        Max.X = FMath::Max(Max.X, Area.Max.X);
        Max.Y = FMath::Max(Max.Y, Area.Max.Y);
    }

    const double Grid = static_cast<double>(GridStepCm);

    const double MinCellX = FMath::FloorToDouble(Min.X / Grid);
    const double MinCellY = FMath::FloorToDouble(Min.Y / Grid);
    const double MaxCellX = FMath::CeilToDouble(Max.X / Grid) - 1.0;
    const double MaxCellY = FMath::CeilToDouble(Max.Y / Grid) - 1.0;

    const double CellCountX = MaxCellX - MinCellX + 1.0;
    const double CellCountY = MaxCellY - MinCellY + 1.0;

    if (MinCellX <= MIN_int32 || MinCellY <= MIN_int32 || MaxCellX >= MAX_int32 ||
        MaxCellY >= MAX_int32)
    {
        OutError = TEXT("Navigation grid coordinates exceed the supported range.");
        return false;
    }

    if (CellCountX <= 0.0 || CellCountY <= 0.0 || CellCountX * CellCountY > 1000000.0)
    {
        OutError = TEXT("Navigation grid exceeds the 1000000 cell limit.");
        return false;
    }

    TSet<FIntPoint> WalkableCells;

    for (int32 Y = static_cast<int32>(MinCellY); Y <= static_cast<int32>(MaxCellY); ++Y)
    {
        for (int32 X = static_cast<int32>(MinCellX); X <= static_cast<int32>(MaxCellX); ++X)
        {
            const FVector2D Center((static_cast<double>(X) + 0.5) * Grid,
                                   (static_cast<double>(Y) + 0.5) * Grid);

            for (const FPlayableSketchRect &Area : Areas)
            {
                if (ContainsPoint(Area, Center))
                {
                    WalkableCells.Add(FIntPoint(X, Y));
                    break;
                }
            }
        }
    }

    OutPath.WalkableCellCount = WalkableCells.Num();

    const FVector2D StartCenter =
        StartRoom->Bounds.Min + (StartRoom->Bounds.Max - StartRoom->Bounds.Min) * 0.5;
    const FVector2D GoalCenter =
        GoalRoom->Bounds.Min + (GoalRoom->Bounds.Max - GoalRoom->Bounds.Min) * 0.5;

    const FIntPoint StartCell(FMath::FloorToInt(StartCenter.X / Grid),
                              FMath::FloorToInt(StartCenter.Y / Grid));
    const FIntPoint GoalCell(FMath::FloorToInt(GoalCenter.X / Grid),
                             FMath::FloorToInt(GoalCenter.Y / Grid));

    if (!WalkableCells.Contains(StartCell) || !WalkableCells.Contains(GoalCell))
    {
        OutError = TEXT("Start or Goal cell is not walkable at this grid resolution.");
        return false;
    }

    TArray<FIntPoint> Queue;
    TSet<FIntPoint> Visited;
    TMap<FIntPoint, FIntPoint> Parents;

    Queue.Add(StartCell);
    Visited.Add(StartCell);

    const FIntPoint Directions[] = {FIntPoint(1, 0), FIntPoint(0, 1), FIntPoint(-1, 0),
                                    FIntPoint(0, -1)};

    for (int32 QueueIndex = 0; QueueIndex < Queue.Num(); ++QueueIndex)
    {
        const FIntPoint Current = Queue[QueueIndex];

        if (Current == GoalCell)
        {
            FIntPoint PathCell = GoalCell;

            while (true)
            {
                OutPath.Points.Add(FVector2D((static_cast<double>(PathCell.X) + 0.5) * Grid,
                                             (static_cast<double>(PathCell.Y) + 0.5) * Grid));

                if (PathCell == StartCell)
                {
                    break;
                }

                PathCell = Parents.FindChecked(PathCell);
            }

            for (int32 Index = 0; Index < OutPath.Points.Num() / 2; ++Index)
            {
                OutPath.Points.Swap(Index, OutPath.Points.Num() - 1 - Index);
            }

            OutPath.VisitedCellCount = Visited.Num();

            return true;
        }

        for (const FIntPoint &Direction : Directions)
        {
            const FIntPoint Neighbor = Current + Direction;

            if (WalkableCells.Contains(Neighbor) && !Visited.Contains(Neighbor))
            {
                Visited.Add(Neighbor);
                Parents.Add(Neighbor, Current);
                Queue.Add(Neighbor);
            }
        }
    }

    OutPath.VisitedCellCount = Visited.Num();
    OutError = TEXT("No floor grid path found from Start to Goal.");

    return false;
}