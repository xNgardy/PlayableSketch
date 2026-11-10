#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchPlacementSearch.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

bool FPlayableSketchLayoutGenerator::Generate(const FPlayableSketchGraph &Graph, int32 GridStepCm,
                                              int32 RoomGapCm,
                                              FPlayableSketchFloorPlan &OutFloorPlan,
                                              FString &OutError, int32 MaxPlacementAttempts)
{
    OutFloorPlan = FPlayableSketchFloorPlan();
    OutError.Reset();

    if (GridStepCm <= 0 || RoomGapCm < 0 || MaxPlacementAttempts <= 0)
    {
        OutError = TEXT(
            "GridStepCm and MaxPlacementAttempts must be positive. RoomGapCm cannot be negative.");
        return false;
    }

    const TArray<FString> ValidationErrors = FPlayableSketchGraphValidator::Validate(Graph);

    if (!ValidationErrors.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Graph validation failed: %s"), *ValidationErrors[0]);
        return false;
    }

    TArray<FGuid> Queue;
    TSet<FGuid> DiscoveredRoomIds;

    Queue.Add(Graph.StartRoomId);
    DiscoveredRoomIds.Add(Graph.StartRoomId);

    for (int32 QueueIndex = 0; QueueIndex < Queue.Num(); ++QueueIndex)
    {
        const FGuid CurrentRoomId = Queue[QueueIndex];

        TArray<FGuid> NeighborIds;

        for (const FPlayableSketchConnection &Connection : Graph.Connections)
        {
            if (Connection.RoomAId == CurrentRoomId)
            {
                NeighborIds.Add(Connection.RoomBId);
            }
            else if (Connection.RoomBId == CurrentRoomId)
            {
                NeighborIds.Add(Connection.RoomAId);
            }
        }

        NeighborIds.Sort(
            [](const FGuid &A, const FGuid &B) { return A.ToString() < B.ToString(); });

        for (const FGuid &NeighborId : NeighborIds)
        {
            if (!DiscoveredRoomIds.Contains(NeighborId))
            {
                DiscoveredRoomIds.Add(NeighborId);
                Queue.Add(NeighborId);
            }
        }
    }

    for (const FPlayableSketchRoom &Room : Graph.Rooms)
    {
        if (!DiscoveredRoomIds.Contains(Room.RoomId))
        {
            OutError =
                FString::Printf(TEXT("Placement failed: Room %s is not reachable from Start."),
                                *Room.RoomId.ToString());
            return false;
        }
    }

    FPlayableSketchFloorPlan Result;

    TArray<FPlayableSketchPlacedRoom> Occupied;

    for (const FPlayableSketchRoom &Room : Graph.Rooms)
    {
        if (Room.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        FPlayableSketchPlacedRoom LockedRoom;
        LockedRoom.RoomId = Room.RoomId;
        LockedRoom.Bounds = FPlayableSketchRect(
            Room.PositionCm, Room.PositionCm + FVector2D(Room.WidthCm, Room.DepthCm));

        if (!LockedRoom.Bounds.IsValid())
        {
            OutError =
                FString::Printf(TEXT("Invalid Locked position: Room %s."), *Room.RoomId.ToString());
            return false;
        }

        for (const FPlayableSketchPlacedRoom &Existing : Occupied)
        {
            if (!LockedRoom.Bounds.HasRequiredGap(Existing.Bounds, RoomGapCm))
            {
                OutError =
                    FString::Printf(TEXT("Locked Rooms overlap or violate RoomGapCm: %s and %s."),
                                    *Room.RoomId.ToString(), *Existing.RoomId.ToString());
                return false;
            }
        }

        Occupied.Add(LockedRoom);
    }

    double NextX = 0.0;

    for (const FGuid &RoomId : Queue)
    {
        const FPlayableSketchRoom *SourceRoom = Graph.Rooms.FindByPredicate(
            [&RoomId](const FPlayableSketchRoom &Room) { return Room.RoomId == RoomId; });

        if (!SourceRoom)
        {
            OutError = FString::Printf(TEXT("Placement failed: Room %s was not found."),
                                       *RoomId.ToString());
            return false;
        }

        const FVector2D SizeCm(SourceRoom->WidthCm, SourceRoom->DepthCm);
        const FVector2D PreferredMinCm(NextX, 0.0);

        FPlayableSketchPlacedRoom PlacedRoom;

        if (SourceRoom->PositionMode == EPlayableSketchPositionMode::Locked)
        {
            PlacedRoom.RoomId = RoomId;
            PlacedRoom.Bounds =
                FPlayableSketchRect(SourceRoom->PositionCm, SourceRoom->PositionCm + SizeCm);
        }
        else
        {
            if (!FPlayableSketchPlacementSearch::FindPlacement(
                    RoomId, SizeCm, PreferredMinCm, Occupied, GridStepCm, RoomGapCm,
                    MaxPlacementAttempts, PlacedRoom, OutError))
            {
                return false;
            }

            Occupied.Add(PlacedRoom);
        }

        Result.Rooms.Add(PlacedRoom);

        NextX = PlacedRoom.Bounds.Max.X + RoomGapCm;
    }

    OutFloorPlan = MoveTemp(Result);

    return true;
}