#include "Geometry/PlayableSketchWallGeometry.h"

namespace
{
FPlayableSketchWallSegment MakeRoomWall(const FPlayableSketchPlacedRoom &Room,
                                        EPlayableSketchWallSide Side);

bool GetRoomOpenings(const FPlayableSketchPlacedRoom &Room, EPlayableSketchWallSide Side,
                     const FPlayableSketchWallSegment &Wall,
                     const FPlayableSketchFloorPlan &FloorPlan,
                     TArray<FPlayableSketchWallOpening> &OutOpenings, FString &OutError);

bool BuildCorridorBoundary(const TArray<FPlayableSketchRect> &Footprints,
                           TArray<FPlayableSketchWallSegment> &OutWalls, FString &OutError)
{
    OutWalls.Reset();

    TArray<double> XEdges;
    TArray<double> YEdges;

    for (const FPlayableSketchRect &Footprint : Footprints)
    {
        if (!Footprint.IsValid())
        {
            OutError = TEXT("Invalid corridor footprint.");
            return false;
        }

        XEdges.AddUnique(Footprint.Min.X);
        XEdges.AddUnique(Footprint.Max.X);
        YEdges.AddUnique(Footprint.Min.Y);
        YEdges.AddUnique(Footprint.Max.Y);
    }

    XEdges.Sort();
    YEdges.Sort();

    const int32 CountX = XEdges.Num() - 1;
    const int32 CountY = YEdges.Num() - 1;
    const int64 CellCount = static_cast<int64>(CountX) * CountY;

    if (CountX <= 0 || CountY <= 0 || CellCount > 100000)
    {
        OutError = TEXT("Invalid or oversized corridor boundary input.");
        return false;
    }

    TArray<uint8> Covered;
    Covered.Init(0, static_cast<int32>(CellCount));

    for (int32 Y = 0; Y < CountY; ++Y)
    {
        for (int32 X = 0; X < CountX; ++X)
        {
            const FVector2D Center(XEdges[X] + (XEdges[X + 1] - XEdges[X]) * 0.5,
                                   YEdges[Y] + (YEdges[Y + 1] - YEdges[Y]) * 0.5);

            for (const FPlayableSketchRect &Footprint : Footprints)
            {
                if (Center.X > Footprint.Min.X && Center.X < Footprint.Max.X &&
                    Center.Y > Footprint.Min.Y && Center.Y < Footprint.Max.Y)
                {
                    Covered[Y * CountX + X] = 1;
                    break;
                }
            }
        }
    }

    auto IsCovered = [&](int32 X, int32 Y) {
        return X >= 0 && X < CountX && Y >= 0 && Y < CountY && Covered[Y * CountX + X] != 0;
    };

    auto AddWall = [&](const FVector2D &Start, const FVector2D &Tangent, const FVector2D &Outward,
                       double Length) {
        FPlayableSketchWallSegment Wall;
        Wall.StartCm = Start;
        Wall.Tangent = Tangent;
        Wall.Outward = Outward;
        Wall.LengthCm = Length;

        OutWalls.Add(Wall);
    };

    for (int32 Y = 0; Y < CountY; ++Y)
    {
        for (int32 X = 0; X < CountX; ++X)
        {
            if (!IsCovered(X, Y))
            {
                continue;
            }

            const double MinX = XEdges[X];
            const double MaxX = XEdges[X + 1];
            const double MinY = YEdges[Y];
            const double MaxY = YEdges[Y + 1];

            if (!IsCovered(X, Y - 1))
            {
                AddWall(FVector2D(MinX, MinY), FVector2D(1.0, 0.0), FVector2D(0.0, -1.0),
                        MaxX - MinX);
            }

            if (!IsCovered(X, Y + 1))
            {
                AddWall(FVector2D(MinX, MaxY), FVector2D(1.0, 0.0), FVector2D(0.0, 1.0),
                        MaxX - MinX);
            }

            if (!IsCovered(X - 1, Y))
            {
                AddWall(FVector2D(MinX, MinY), FVector2D(0.0, 1.0), FVector2D(-1.0, 0.0),
                        MaxY - MinY);
            }

            if (!IsCovered(X + 1, Y))
            {
                AddWall(FVector2D(MaxX, MinY), FVector2D(0.0, 1.0), FVector2D(1.0, 0.0),
                        MaxY - MinY);
            }
        }
    }

    return true;
}

bool GetContactInterval(const FPlayableSketchWallSegment &Boundary,
                        const FPlayableSketchWallSegment &RoomWall, double &OutStartCm,
                        double &OutEndCm)
{
    if (Boundary.Tangent != RoomWall.Tangent ||
        FVector2D::DotProduct(Boundary.Outward, RoomWall.Outward) > -0.5)
    {
        return false;
    }

    const FVector2D Delta = RoomWall.StartCm - Boundary.StartCm;

    if (!FMath::IsNearlyZero(FVector2D::DotProduct(Delta, Boundary.Outward), 0.01))
    {
        return false;
    }

    const double StartCm = FVector2D::DotProduct(Delta, Boundary.Tangent);

    OutStartCm = FMath::Max(0.0, StartCm);
    OutEndCm = FMath::Min(Boundary.LengthCm, StartCm + RoomWall.LengthCm);

    return OutEndCm > OutStartCm;
}

bool IsDoorCovered(const FPlayableSketchDoorEndpoint &Door, const FPlayableSketchPlacedRoom &Room,
                   const TArray<FPlayableSketchWallSegment> &Boundary)
{
    const FPlayableSketchWallSegment RoomWall = MakeRoomWall(Room, Door.WallSide);

    if (RoomWall.LengthCm <= 0.0)
    {
        return false;
    }

    const double CenterCm =
        FVector2D::DotProduct(Door.PositionCm - RoomWall.StartCm, RoomWall.Tangent);
    const double DoorStartCm = CenterCm - Door.WidthCm * 0.5;
    const double DoorEndCm = CenterCm + Door.WidthCm * 0.5;
    double CoveredLengthCm = 0.0;

    for (const FPlayableSketchWallSegment &Edge : Boundary)
    {
        double ContactStartCm = 0.0;
        double ContactEndCm = 0.0;

        if (!GetContactInterval(Edge, RoomWall, ContactStartCm, ContactEndCm))
        {
            continue;
        }

        const double EdgeOffsetCm =
            FVector2D::DotProduct(Edge.StartCm - RoomWall.StartCm, RoomWall.Tangent);
        const double StartCm = EdgeOffsetCm + ContactStartCm;
        const double EndCm = EdgeOffsetCm + ContactEndCm;

        CoveredLengthCm +=
            FMath::Max(0.0, FMath::Min(EndCm, DoorEndCm) - FMath::Max(StartCm, DoorStartCm));
    }

    return CoveredLengthCm >= Door.WidthCm - 0.01;
}

bool AppendCorridorWalls(const FPlayableSketchCorridor &Corridor,
                         const FPlayableSketchPlacedRoom &RoomA,
                         const FPlayableSketchPlacedRoom &RoomB,
                         const TArray<FPlayableSketchWallSegment> &Boundary,
                         const FPlayableSketchWallSettings &Settings,
                         TArray<FPlayableSketchGeometryDescriptor> &OutPieces, FString &OutError)
{
    const FPlayableSketchWallSegment RoomWalls[] = {MakeRoomWall(RoomA, Corridor.DoorA.WallSide),
                                                    MakeRoomWall(RoomB, Corridor.DoorB.WallSide)};

    for (const FPlayableSketchWallSegment &Edge : Boundary)
    {
        TArray<FPlayableSketchWallOpening> Contacts;
        TArray<double> Cuts;
        Cuts.Add(0.0);
        Cuts.Add(Edge.LengthCm);

        for (const FPlayableSketchWallSegment &RoomWall : RoomWalls)
        {
            FPlayableSketchWallOpening Contact;

            if (GetContactInterval(Edge, RoomWall, Contact.StartCm, Contact.EndCm))
            {
                Contacts.Add(Contact);
                Cuts.AddUnique(Contact.StartCm);
                Cuts.AddUnique(Contact.EndCm);
            }
        }

        Cuts.Sort();

        for (int32 Index = 0; Index + 1 < Cuts.Num(); ++Index)
        {
            const double MidCm = (Cuts[Index] + Cuts[Index + 1]) * 0.5;
            bool bRoomContact = false;

            for (const FPlayableSketchWallOpening &Contact : Contacts)
            {
                if (MidCm >= Contact.StartCm && MidCm <= Contact.EndCm)
                {
                    bRoomContact = true;
                    break;
                }
            }

            if (bRoomContact)
            {
                continue;
            }

            FPlayableSketchWallSegment PieceWall = Edge;
            PieceWall.StartCm += Edge.Tangent * Cuts[Index];
            PieceWall.LengthCm = Cuts[Index + 1] - Cuts[Index];

            TArray<FPlayableSketchGeometryDescriptor> Pieces;

            if (!FPlayableSketchWallGeometry::SplitWall(
                    PieceWall, TArray<FPlayableSketchWallOpening>(), Settings,
                    Corridor.ConnectionId, false, Pieces, OutError))
            {
                return false;
            }

            OutPieces.Append(Pieces);
        }
    }

    return true;
}
}

namespace
{
bool IsValidSettings(const FPlayableSketchWallSettings &Settings)
{
    return FMath::IsFinite(Settings.HeightCm) && FMath::IsFinite(Settings.ThicknessCm) &&
           FMath::IsFinite(Settings.DoorHeightCm) && FMath::IsFinite(Settings.CornerMarginCm) &&
           Settings.HeightCm > 0.0 && Settings.ThicknessCm > 0.0 && Settings.DoorHeightCm > 0.0 &&
           Settings.DoorHeightCm <= Settings.HeightCm && Settings.CornerMarginCm >= 0.0;
}

void AddPiece(const FPlayableSketchWallSegment &Wall, double StartCm, double EndCm, double BottomCm,
              double TopCm, const FPlayableSketchWallSettings &Settings, const FGuid &SourceId,
              bool bRoom, EPlayableSketchGeometryRole Role,
              TArray<FPlayableSketchGeometryDescriptor> &Pieces)
{
    if (EndCm <= StartCm || TopCm <= BottomCm)
    {
        return;
    }

    const double LengthCm = EndCm - StartCm;

    const FVector2D Center2D = Wall.StartCm + Wall.Tangent * ((StartCm + EndCm) * 0.5) +
                               Wall.Outward * (Settings.ThicknessCm * 0.5);

    FPlayableSketchGeometryDescriptor Piece;
    Piece.SourceId = SourceId;
    Piece.bRoom = bRoom;
    Piece.Role = Role;
    Piece.CenterCm = FVector(Center2D.X, Center2D.Y, (BottomCm + TopCm) * 0.5);

    if (Wall.Tangent.X != 0.0)
    {
        Piece.SizeCm = FVector(LengthCm, Settings.ThicknessCm, TopCm - BottomCm);
    }
    else
    {
        Piece.SizeCm = FVector(Settings.ThicknessCm, LengthCm, TopCm - BottomCm);
    }

    Pieces.Add(Piece);
}
}

bool FPlayableSketchWallGeometry::SplitWall(const FPlayableSketchWallSegment &Wall,
                                            const TArray<FPlayableSketchWallOpening> &Openings,
                                            const FPlayableSketchWallSettings &Settings,
                                            const FGuid &SourceId, bool bRoom,
                                            TArray<FPlayableSketchGeometryDescriptor> &OutPieces,
                                            FString &OutError)
{
    OutPieces.Reset();
    OutError.Reset();

    const bool bHorizontal =
        Wall.Tangent == FVector2D(1.0, 0.0) &&
        (Wall.Outward == FVector2D(0.0, 1.0) || Wall.Outward == FVector2D(0.0, -1.0));

    const bool bVertical =
        Wall.Tangent == FVector2D(0.0, 1.0) &&
        (Wall.Outward == FVector2D(1.0, 0.0) || Wall.Outward == FVector2D(-1.0, 0.0));

    if (!SourceId.IsValid() || !IsValidSettings(Settings) || !FMath::IsFinite(Wall.StartCm.X) ||
        !FMath::IsFinite(Wall.StartCm.Y) || !FMath::IsFinite(Wall.LengthCm) ||
        Wall.LengthCm <= 0.0 || (!bHorizontal && !bVertical))
    {
        OutError = TEXT("Invalid wall input.");
        return false;
    }

    TArray<FPlayableSketchWallOpening> Sorted = Openings;

    Sorted.Sort([](const FPlayableSketchWallOpening &A, const FPlayableSketchWallOpening &B) {
        return A.StartCm < B.StartCm;
    });

    double PreviousEndCm = 0.0;

    for (const FPlayableSketchWallOpening &Opening : Sorted)
    {
        if (!FMath::IsFinite(Opening.StartCm) || !FMath::IsFinite(Opening.EndCm) ||
            Opening.EndCm <= Opening.StartCm || Opening.StartCm < Settings.CornerMarginCm ||
            Opening.EndCm > Wall.LengthCm - Settings.CornerMarginCm)
        {
            OutError = FString::Printf(
                TEXT("Door opening is outside the allowed wall interval: Source %s."),
                *SourceId.ToString());

            return false;
        }

        if (Opening.StartCm < PreviousEndCm)
        {
            OutError =
                FString::Printf(TEXT("Door openings overlap: Source %s."), *SourceId.ToString());

            return false;
        }

        PreviousEndCm = Opening.EndCm;
    }

    TArray<FPlayableSketchGeometryDescriptor> Result;
    double CursorCm = 0.0;

    for (const FPlayableSketchWallOpening &Opening : Sorted)
    {
        AddPiece(Wall, CursorCm, Opening.StartCm, 0.0, Settings.HeightCm, Settings, SourceId, bRoom,
                 EPlayableSketchGeometryRole::Wall, Result);

        AddPiece(Wall, Opening.StartCm, Opening.EndCm, Settings.DoorHeightCm, Settings.HeightCm,
                 Settings, SourceId, bRoom, EPlayableSketchGeometryRole::Lintel, Result);

        CursorCm = Opening.EndCm;
    }

    AddPiece(Wall, CursorCm, Wall.LengthCm, 0.0, Settings.HeightCm, Settings, SourceId, bRoom,
             EPlayableSketchGeometryRole::Wall, Result);

    OutPieces = MoveTemp(Result);

    return true;
}

bool FPlayableSketchWallGeometry::Generate(const FPlayableSketchFloorPlan &FloorPlan,
                                           const FPlayableSketchWallSettings &Settings,
                                           TArray<FPlayableSketchGeometryDescriptor> &OutPieces,
                                           FString &OutError)
{
    OutPieces.Reset();
    OutError.Reset();

    if (!IsValidSettings(Settings) || FloorPlan.Rooms.IsEmpty())
    {
        OutError = TEXT("Invalid wall generation input.");
        return false;
    }

    for (const FPlayableSketchPlacedRoom &Room : FloorPlan.Rooms)
    {
        if (!Room.RoomId.IsValid() || !Room.Bounds.IsValid())
        {
            OutError = TEXT("Invalid Room wall input.");
            return false;
        }
    }

    TArray<FPlayableSketchGeometryDescriptor> Result;

    const EPlayableSketchWallSide Sides[] = {
        EPlayableSketchWallSide::North, EPlayableSketchWallSide::East,
        EPlayableSketchWallSide::South, EPlayableSketchWallSide::West};

    for (const FPlayableSketchPlacedRoom &Room : FloorPlan.Rooms)
    {
        for (EPlayableSketchWallSide Side : Sides)
        {
            const FPlayableSketchWallSegment Wall = MakeRoomWall(Room, Side);

            TArray<FPlayableSketchWallOpening> Openings;
            TArray<FPlayableSketchGeometryDescriptor> Pieces;

            if (!GetRoomOpenings(Room, Side, Wall, FloorPlan, Openings, OutError))
            {
                return false;
            }

            if (!SplitWall(Wall, Openings, Settings, Room.RoomId, true, Pieces, OutError))
            {
                return false;
            }

            Result.Append(Pieces);
        }
    }

    for (const FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        const FPlayableSketchPlacedRoom *RoomA =
            FloorPlan.Rooms.FindByPredicate([&Corridor](const FPlayableSketchPlacedRoom &Room) {
                return Room.RoomId == Corridor.DoorA.RoomId;
            });

        const FPlayableSketchPlacedRoom *RoomB =
            FloorPlan.Rooms.FindByPredicate([&Corridor](const FPlayableSketchPlacedRoom &Room) {
                return Room.RoomId == Corridor.DoorB.RoomId;
            });

        if (!Corridor.ConnectionId.IsValid() || Corridor.Footprints.IsEmpty() || !RoomA || !RoomB ||
            RoomA == RoomB)
        {
            OutError = TEXT("Invalid corridor wall input.");
            return false;
        }

        TArray<FPlayableSketchWallSegment> Boundary;

        if (!BuildCorridorBoundary(Corridor.Footprints, Boundary, OutError))
        {
            return false;
        }

        if (!IsDoorCovered(Corridor.DoorA, *RoomA, Boundary) ||
            !IsDoorCovered(Corridor.DoorB, *RoomB, Boundary))
        {
            OutError = FString::Printf(
                TEXT("Corridor does not cover its complete Door opening: Connection %s."),
                *Corridor.ConnectionId.ToString());

            return false;
        }

        if (!AppendCorridorWalls(Corridor, *RoomA, *RoomB, Boundary, Settings, Result, OutError))
        {
            return false;
        }
    }

    OutPieces = MoveTemp(Result);

    return true;
}

namespace
{
FPlayableSketchWallSegment MakeRoomWall(const FPlayableSketchPlacedRoom &Room,
                                        EPlayableSketchWallSide Side)
{
    FPlayableSketchWallSegment Wall;
    const FVector2D SizeCm = Room.Bounds.Max - Room.Bounds.Min;

    switch (Side)
    {
    case EPlayableSketchWallSide::North:
        Wall.StartCm = FVector2D(Room.Bounds.Min.X, Room.Bounds.Max.Y);
        Wall.Tangent = FVector2D(1.0, 0.0);
        Wall.Outward = FVector2D(0.0, 1.0);
        Wall.LengthCm = SizeCm.X;
        break;

    case EPlayableSketchWallSide::East:
        Wall.StartCm = FVector2D(Room.Bounds.Max.X, Room.Bounds.Min.Y);
        Wall.Tangent = FVector2D(0.0, 1.0);
        Wall.Outward = FVector2D(1.0, 0.0);
        Wall.LengthCm = SizeCm.Y;
        break;

    case EPlayableSketchWallSide::South:
        Wall.StartCm = Room.Bounds.Min;
        Wall.Tangent = FVector2D(1.0, 0.0);
        Wall.Outward = FVector2D(0.0, -1.0);
        Wall.LengthCm = SizeCm.X;
        break;

    case EPlayableSketchWallSide::West:
        Wall.StartCm = Room.Bounds.Min;
        Wall.Tangent = FVector2D(0.0, 1.0);
        Wall.Outward = FVector2D(-1.0, 0.0);
        Wall.LengthCm = SizeCm.Y;
        break;
    }

    return Wall;
}

bool GetRoomOpenings(const FPlayableSketchPlacedRoom &Room, EPlayableSketchWallSide Side,
                     const FPlayableSketchWallSegment &Wall,
                     const FPlayableSketchFloorPlan &FloorPlan,
                     TArray<FPlayableSketchWallOpening> &OutOpenings, FString &OutError)
{
    OutOpenings.Reset();

    for (const FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        const FPlayableSketchDoorEndpoint *Doors[] = {&Corridor.DoorA, &Corridor.DoorB};

        for (const FPlayableSketchDoorEndpoint *Door : Doors)
        {
            if (Door->RoomId != Room.RoomId || Door->WallSide != Side)
            {
                continue;
            }

            const FVector2D Delta = Door->PositionCm - Wall.StartCm;

            if (!FMath::IsFinite(Door->PositionCm.X) || !FMath::IsFinite(Door->PositionCm.Y) ||
                !FMath::IsFinite(Door->WidthCm) || Door->WidthCm <= 0.0 ||
                !FMath::IsNearlyZero(FVector2D::DotProduct(Delta, Wall.Outward), 0.01))
            {
                OutError = FString::Printf(TEXT("Door is not on its Room wall: Connection %s."),
                                           *Corridor.ConnectionId.ToString());

                return false;
            }

            const double CenterOffsetCm = FVector2D::DotProduct(Delta, Wall.Tangent);

            FPlayableSketchWallOpening Opening;
            Opening.StartCm = CenterOffsetCm - Door->WidthCm * 0.5;
            Opening.EndCm = CenterOffsetCm + Door->WidthCm * 0.5;

            OutOpenings.Add(Opening);
        }
    }

    return true;
}
}
