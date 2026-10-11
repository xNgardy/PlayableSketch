#include "Layout/PlayableSketchDoorGenerator.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

namespace
{
    bool ApplyDoorOverride(
        const FPlayableSketchPlacedRoom& Room,
        const FPlayableSketchDoorOverride& Override,
        int32 CornerMarginCm,
        FPlayableSketchDoorEndpoint& Door,
        FString& OutError)
    {
        if (!Override.bManual)
        {
            return true;
        }

        if (!FPlayableSketchDoorGenerator::CreateEndpoint(Room, Override.WallSide, Door.WidthCm, CornerMarginCm, Door, OutError))
        {
            return false;
        }

        const bool bHorizontal = Override.WallSide == EPlayableSketchWallSide::North || Override.WallSide == EPlayableSketchWallSide::South;
        const double LengthCm = bHorizontal ? Room.Bounds.Max.X - Room.Bounds.Min.X : Room.Bounds.Max.Y - Room.Bounds.Min.Y;

        if (!FMath::IsFinite(Override.OffsetCm)
            || Override.OffsetCm - Door.WidthCm * 0.5 < CornerMarginCm
            || Override.OffsetCm + Door.WidthCm * 0.5 > LengthCm - CornerMarginCm)
        {
            OutError = FString::Printf(TEXT("PS-V002: Manual Door offset does not fit Room %s."), *Room.RoomId.ToString());
            return false;
        }

        if (bHorizontal)
        {
            Door.PositionCm.X = Room.Bounds.Min.X + Override.OffsetCm;
        }
        else
        {
            Door.PositionCm.Y = Room.Bounds.Min.Y + Override.OffsetCm;
        }

        return true;
    }
}


bool FPlayableSketchDoorGenerator::CreateEndpoint(const FPlayableSketchPlacedRoom& Room, EPlayableSketchWallSide WallSide, double DoorWidthCm,
    int32 CornerMarginCm, FPlayableSketchDoorEndpoint& OutDoor, FString& OutError)
{
    OutDoor = FPlayableSketchDoorEndpoint();
    OutError.Reset();

    if (!Room.RoomId.IsValid() || !Room.Bounds.IsValid() || !FMath::IsFinite(DoorWidthCm) || DoorWidthCm <= 0.0 || CornerMarginCm < 0)
    {
        OutError = FString::Printf(TEXT("Invalid Door input for Room %s."), *Room.RoomId.ToString());
        return false;
    }

    const FVector2D SizeCm = Room.Bounds.Max - Room.Bounds.Min;
    const FVector2D CenterCm = Room.Bounds.Min + SizeCm * 0.5;

    double WallLengthCm = 0.0;
    FVector2D PositionCm = FVector2D::ZeroVector;

    switch (WallSide)
    {
    case EPlayableSketchWallSide::North:
        WallLengthCm = SizeCm.X;
        PositionCm = FVector2D(CenterCm.X, Room.Bounds.Max.Y);
        break;

    case EPlayableSketchWallSide::East:
        WallLengthCm = SizeCm.Y;
        PositionCm = FVector2D(Room.Bounds.Max.X, CenterCm.Y);
        break;

    case EPlayableSketchWallSide::South:
        WallLengthCm = SizeCm.X;
        PositionCm = FVector2D(CenterCm.X, Room.Bounds.Min.Y);
        break;

    case EPlayableSketchWallSide::West:
        WallLengthCm = SizeCm.Y;
        PositionCm = FVector2D(Room.Bounds.Min.X, CenterCm.Y);
        break;

    default:
        OutError = TEXT("Invalid Door wall side.");
        return false;
    }

    const double RequiredLengthCm = DoorWidthCm + 2.0 * static_cast<double>(CornerMarginCm);

    if (RequiredLengthCm > WallLengthCm)
    {
        OutError = FString::Printf(TEXT("Door does not fit: Room %s, wall length=%.0f, Door width=%.0f, corner margin=%d."), *Room.RoomId.ToString(), WallLengthCm, DoorWidthCm, CornerMarginCm);
        return false;
    }

    OutDoor.RoomId = Room.RoomId;
    OutDoor.WallSide = WallSide;
    OutDoor.PositionCm = PositionCm;
    OutDoor.WidthCm = DoorWidthCm;

    return true;
}

bool FPlayableSketchDoorGenerator::Generate(const FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& FloorPlan, int32 CornerMarginCm, FString& OutError)
{
    FloorPlan.Corridors.Reset();
    OutError.Reset();

    if (CornerMarginCm < 0)
    {
        OutError = TEXT("CornerMarginCm cannot be negative.");
        return false;
    }

    const TArray<FString> ValidationErrors = FPlayableSketchGraphValidator::Validate(Graph);

    if (!ValidationErrors.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Graph validation failed: %s"), *ValidationErrors[0]);
        return false;
    }

    TArray<int32> ConnectionOrder;

    for (int32 Index = 0; Index < Graph.Connections.Num(); ++Index)
    {
        ConnectionOrder.Add(Index);
    }

    ConnectionOrder.Sort([&Graph](int32 A, int32 B)
        {
            return Graph.Connections[A].ConnectionId.ToString() < Graph.Connections[B].ConnectionId.ToString();
        });

    TArray<FPlayableSketchCorridor> Result;

    for (int32 ConnectionIndex : ConnectionOrder)
    {
        const FPlayableSketchConnection& Connection = Graph.Connections[ConnectionIndex];

        const FPlayableSketchPlacedRoom* RoomA = FloorPlan.Rooms.FindByPredicate([&Connection](const FPlayableSketchPlacedRoom& Room)
            {
                return Room.RoomId == Connection.RoomAId;
            });

        const FPlayableSketchPlacedRoom* RoomB = FloorPlan.Rooms.FindByPredicate([&Connection](const FPlayableSketchPlacedRoom& Room)
            {
                return Room.RoomId == Connection.RoomBId;
            });

        if (!RoomA || !RoomB)
        {
            OutError = FString::Printf(TEXT("Door generation failed: missing placed Room for Connection %s."), *Connection.ConnectionId.ToString());
            return false;
        }

        if (!RoomA->Bounds.IsValid() || !RoomB->Bounds.IsValid() || RoomA->Bounds.OverlapsInterior(RoomB->Bounds))
        {
            OutError = FString::Printf(TEXT("Door generation failed: invalid or overlapping Rooms for Connection %s."), *Connection.ConnectionId.ToString());
            return false;
        }

        const FVector2D CenterA = RoomA->Bounds.Min + (RoomA->Bounds.Max - RoomA->Bounds.Min) * 0.5;
        const FVector2D CenterB = RoomB->Bounds.Min + (RoomB->Bounds.Max - RoomB->Bounds.Min) * 0.5;
        const FVector2D Direction = CenterB - CenterA;

        EPlayableSketchWallSide SideA;
        EPlayableSketchWallSide SideB;

        if (FMath::Abs(Direction.X) >= FMath::Abs(Direction.Y))
        {
            SideA = Direction.X >= 0.0 ? EPlayableSketchWallSide::East : EPlayableSketchWallSide::West;
            SideB = Direction.X >= 0.0 ? EPlayableSketchWallSide::West : EPlayableSketchWallSide::East;
        }
        else
        {
            SideA = Direction.Y >= 0.0 ? EPlayableSketchWallSide::North : EPlayableSketchWallSide::South;
            SideB = Direction.Y >= 0.0 ? EPlayableSketchWallSide::South : EPlayableSketchWallSide::North;
        }

        FPlayableSketchCorridor Corridor;
        Corridor.ConnectionId = Connection.ConnectionId;

        if (!CreateEndpoint(*RoomA, Connection.DoorASettings.bManual ? Connection.DoorASettings.WallSide : SideA, Connection.DoorWidthCm, CornerMarginCm, Corridor.DoorA, OutError))
        {
            OutError = FString::Printf(TEXT("Connection %s: %s"), *Connection.ConnectionId.ToString(), *OutError);
            return false;
        }

        if (!CreateEndpoint(*RoomB, Connection.DoorBSettings.bManual ? Connection.DoorBSettings.WallSide : SideB, Connection.DoorWidthCm, CornerMarginCm, Corridor.DoorB, OutError))
        {
            OutError = FString::Printf(TEXT("Connection %s: %s"), *Connection.ConnectionId.ToString(), *OutError);
            return false;
        }

        if (!ApplyDoorOverride(*RoomA, Connection.DoorASettings, CornerMarginCm, Corridor.DoorA, OutError)
            || !ApplyDoorOverride(*RoomB, Connection.DoorBSettings, CornerMarginCm, Corridor.DoorB, OutError))
        {
            return false;
        }

        for (const FPlayableSketchCorridor& Existing : Result)
        {
            const bool bDoorAOverlap = OpeningsOverlap(Corridor.DoorA, Existing.DoorA) || OpeningsOverlap(Corridor.DoorA, Existing.DoorB);
            const bool bDoorBOverlap = OpeningsOverlap(Corridor.DoorB, Existing.DoorA) || OpeningsOverlap(Corridor.DoorB, Existing.DoorB);

            if (bDoorAOverlap || bDoorBOverlap)
            {
                OutError = FString::Printf(TEXT("Door overlap: Connections %s and %s."), *Corridor.ConnectionId.ToString(), *Existing.ConnectionId.ToString());
                return false;
            }
        }

        Result.Add(Corridor);
    }

    FloorPlan.Corridors = MoveTemp(Result);

    return true;
}

bool FPlayableSketchDoorGenerator::OpeningsOverlap(const FPlayableSketchDoorEndpoint& A, const FPlayableSketchDoorEndpoint& B)
{
    if (A.RoomId != B.RoomId || A.WallSide != B.WallSide)
    {
        return false;
    }

    const bool bHorizontalWall = A.WallSide == EPlayableSketchWallSide::North || A.WallSide == EPlayableSketchWallSide::South;

    const double CenterA = bHorizontalWall ? A.PositionCm.X : A.PositionCm.Y;
    const double CenterB = bHorizontalWall ? B.PositionCm.X : B.PositionCm.Y;

    return FMath::Abs(CenterA - CenterB) < (A.WidthCm + B.WidthCm) * 0.5;
}
