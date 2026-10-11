#include "Validation/PlayableSketchValidation.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

namespace
{
    const double ToleranceCm = 0.01;

    void AddIssue(
        TArray<FPlayableSketchValidationIssue>& Issues,
        const TCHAR* Code,
        const FString& Message,
        const TArray<FGuid>& Ids,
        const FVector& Position,
        const FVector& Extent = FVector(25.0, 25.0, 25.0))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = FName(Code);
        Issue.Message = Message;
        Issue.ElementIds = Ids;
        Issue.bHasPosition = !Position.ContainsNaN();
        Issue.PositionCm = Issue.bHasPosition ? Position : FVector::ZeroVector;
        Issue.ExtentCm = Extent;
        Issues.Add(Issue);
    }

    FVector RoomCenter(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Center = (Room.Bounds.Min + Room.Bounds.Max) * 0.5;
        return FVector(Center.X, Center.Y, 25.0);
    }

    FVector RoomExtent(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Half = (Room.Bounds.Max - Room.Bounds.Min) * 0.5;
        return FVector(Half.X, Half.Y, 25.0);
    }

    bool GetWallFrame(
        const FPlayableSketchPlacedRoom& Room,
        EPlayableSketchWallSide Side,
        FVector2D& Origin,
        FVector2D& Tangent,
        FVector2D& Normal,
        double& Length)
    {
        const FVector2D Size = Room.Bounds.Max - Room.Bounds.Min;

        switch (Side)
        {
        case EPlayableSketchWallSide::North:
            Origin = FVector2D(Room.Bounds.Min.X, Room.Bounds.Max.Y);
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, 1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::South:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, -1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::East:
            Origin = FVector2D(Room.Bounds.Max.X, Room.Bounds.Min.Y);
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(1.0, 0.0);
            Length = Size.Y;
            return true;

        case EPlayableSketchWallSide::West:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(-1.0, 0.0);
            Length = Size.Y;
            return true;
        }

        return false;
    }

    bool FootprintsConnected(const TArray<FPlayableSketchRect>& Rects)
    {
        if (Rects.IsEmpty())
        {
            return false;
        }

        TSet<int32> Visited;
        TArray<int32> Queue;
        Queue.Add(0);
        Visited.Add(0);

        for (int32 Head = 0; Head < Queue.Num(); ++Head)
        {
            const FPlayableSketchRect& A = Rects[Queue[Head]];

            for (int32 Index = 0; Index < Rects.Num(); ++Index)
            {
                if (Visited.Contains(Index))
                {
                    continue;
                }

                const FPlayableSketchRect& B = Rects[Index];
                const double OverlapX = FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X);
                const double OverlapY = FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y);
                const bool bConnected = (OverlapX > ToleranceCm && OverlapY >= -ToleranceCm)
                    || (OverlapY > ToleranceCm && OverlapX >= -ToleranceCm);

                if (bConnected)
                {
                    Visited.Add(Index);
                    Queue.Add(Index);
                }
            }
        }

        return Visited.Num() == Rects.Num();
    }

    bool CoversDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FVector2D& Origin,
        const FVector2D& Tangent,
        const FVector2D& Normal,
        const TArray<FPlayableSketchRect>& Rects)
    {
        const double Center = FVector2D::DotProduct(Door.PositionCm - Origin, Tangent);
        const double Start = Center - Door.WidthCm * 0.5;
        const double End = Center + Door.WidthCm * 0.5;
        TArray<FVector2D> Intervals;

        for (const FPlayableSketchRect& Rect : Rects)
        {
            bool bContact = false;

            if (Normal.X > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.X, Origin.X, ToleranceCm);
            }
            else if (Normal.X < 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.X, Origin.X, ToleranceCm);
            }
            else if (Normal.Y > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.Y, Origin.Y, ToleranceCm);
            }
            else
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.Y, Origin.Y, ToleranceCm);
            }

            if (bContact)
            {
                const double Min = FVector2D::DotProduct(Rect.Min - Origin, Tangent);
                const double Max = FVector2D::DotProduct(Rect.Max - Origin, Tangent);
                Intervals.Add(FVector2D(Min, Max));
            }
        }

        Intervals.Sort([](const FVector2D& A, const FVector2D& B)
        {
            return A.X < B.X;
        });

        double Cursor = Start;

        for (const FVector2D& Interval : Intervals)
        {
            if (Interval.Y < Cursor - ToleranceCm)
            {
                continue;
            }

            if (Interval.X > Cursor + ToleranceCm)
            {
                return false;
            }

            Cursor = FMath::Max(Cursor, Interval.Y);

            if (Cursor >= End - ToleranceCm)
            {
                return true;
            }
        }

        return false;
    }

    bool BoxesOverlap(const FBox& A, const FBox& B)
    {
        return FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X) > ToleranceCm
            && FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y) > ToleranceCm
            && FMath::Min(A.Max.Z, B.Max.Z) - FMath::Max(A.Min.Z, B.Min.Z) > ToleranceCm;
    }

    bool CheckDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FGuid& ExpectedRoomId,
        const FPlayableSketchConnection& Connection,
        const FPlayableSketchFloorPlan& Plan,
        const TArray<FPlayableSketchRect>& Rects,
        const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
        const FPlayableSketchValidationSettings& Settings,
        TArray<FPlayableSketchValidationIssue>& Issues)
    {
        const FVector Position(Door.PositionCm.X, Door.PositionCm.Y, 40.0);
        const TArray<FGuid> Ids = { Connection.ConnectionId, ExpectedRoomId };
        const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item)
        {
            return Item.RoomId == ExpectedRoomId;
        });

        FVector2D Origin;
        FVector2D Tangent;
        FVector2D Normal;
        double Length = 0.0;

        if (!Room || Door.RoomId != ExpectedRoomId
            || !Room->Bounds.IsValid()
            || !FMath::IsFinite(Door.PositionCm.X) || !FMath::IsFinite(Door.PositionCm.Y)
            || !FMath::IsFinite(Door.WidthCm) || Door.WidthCm <= 0.0
            || !GetWallFrame(*Room, Door.WallSide, Origin, Tangent, Normal, Length))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door ownership, side or coordinates are invalid."), Ids, Position);
            return false;
        }

        const FVector2D Delta = Door.PositionCm - Origin;
        const double Offset = FVector2D::DotProduct(Delta, Tangent);

        if (!FMath::IsNearlyZero(FVector2D::DotProduct(Delta, Normal), ToleranceCm)
            || Offset - Door.WidthCm * 0.5 < Settings.Walls.CornerMarginCm
            || Offset + Door.WidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm
            || !FMath::IsNearlyEqual(Door.WidthCm, static_cast<double>(Connection.DoorWidthCm), ToleranceCm))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door must lie on its wall, respect corner margin and match DoorWidthCm."), Ids, Position);
            return false;
        }

        if (Door.WidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door is too narrow for the configured Pawn and clearance."), Ids, Position);
            return false;
        }

        if (!CoversDoor(Door, Origin, Tangent, Normal, Rects))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor does not cover the full Door opening."), Ids, Position);
            return false;
        }

        const FVector2D Center2D = Door.PositionCm + Normal * (Settings.Walls.ThicknessCm * 0.5);
        const FVector OpeningCenter(Center2D.X, Center2D.Y, Settings.Walls.DoorHeightCm * 0.5);
        const FVector OpeningSize = Tangent.X != 0.0
            ? FVector(Door.WidthCm, Settings.Walls.ThicknessCm, Settings.Walls.DoorHeightCm)
            : FVector(Settings.Walls.ThicknessCm, Door.WidthCm, Settings.Walls.DoorHeightCm);
        const FBox OpeningBox(OpeningCenter - OpeningSize * 0.5, OpeningCenter + OpeningSize * 0.5);

        bool bBlocked = false;
        bool bHasLintel = Settings.Walls.DoorHeightCm == Settings.Walls.HeightCm;

        for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
        {
            if (Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN())
            {
                continue;
            }

            const FBox Box(Piece.CenterCm - Piece.SizeCm * 0.5, Piece.CenterCm + Piece.SizeCm * 0.5);

            if (BoxesOverlap(OpeningBox, Box))
            {
                bBlocked = true;
                AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated wall or lintel blocks the Door opening."), { Connection.ConnectionId, ExpectedRoomId, Piece.SourceId }, Position);
            }

            if (Piece.bRoom && Piece.SourceId == ExpectedRoomId && Piece.Role == EPlayableSketchGeometryRole::Lintel
                && Box.Min.X <= OpeningBox.Min.X + ToleranceCm && Box.Max.X >= OpeningBox.Max.X - ToleranceCm
                && Box.Min.Y <= OpeningBox.Min.Y + ToleranceCm && Box.Max.Y >= OpeningBox.Max.Y - ToleranceCm
                && FMath::IsNearlyEqual(Box.Min.Z, Settings.Walls.DoorHeightCm, ToleranceCm)
                && FMath::IsNearlyEqual(Box.Max.Z, Settings.Walls.HeightCm, ToleranceCm))
            {
                bHasLintel = true;
            }
        }

        if (!bHasLintel)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Expected Door lintel is missing or has incorrect dimensions."), Ids, Position);
        }

        return !bBlocked && bHasLintel;
    }
}

bool FPlayableSketchValidation::HasErrors(const TArray<FPlayableSketchValidationIssue>& Issues)
{
    return Issues.ContainsByPredicate([](const FPlayableSketchValidationIssue& Issue)
    {
        return Issue.Severity == EPlayableSketchIssueSeverity::Error;
    });
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidateInput(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues;

    for (const FString& Error : FPlayableSketchGraphValidator::Validate(Graph))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = Error;
        for (const FPlayableSketchRoom& Room : Graph.Rooms)
        {
            if (Error.Contains(Room.RoomId.ToString()))
            {
                Issue.ElementIds.AddUnique(Room.RoomId);
            }
        }
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (Error.Contains(Connection.ConnectionId.ToString()))
            {
                Issue.ElementIds.AddUnique(Connection.ConnectionId);
            }
        }
        if (Error.StartsWith(TEXT("Invalid Start")))
        {
            Issue.ElementIds.AddUnique(Graph.StartRoomId);
        }
        if (Error.StartsWith(TEXT("Invalid Goal")))
        {
            Issue.ElementIds.AddUnique(Graph.GoalRoomId);
        }
        Issues.Add(Issue);
    }

    const bool bSettingsValid = Settings.GridStepCm > 0
        && FMath::IsFinite(Settings.MinCorridorWidthCm) && Settings.MinCorridorWidthCm > 0.0
        && FMath::IsFinite(Settings.PawnRadiusCm) && Settings.PawnRadiusCm > 0.0
        && FMath::IsFinite(Settings.PawnHeightCm) && Settings.PawnHeightCm > 0.0
        && FMath::IsFinite(Settings.ClearanceCm) && Settings.ClearanceCm >= 0.0
        && FMath::IsFinite(Settings.Walls.HeightCm) && Settings.Walls.HeightCm > 0.0
        && FMath::IsFinite(Settings.Walls.ThicknessCm) && Settings.Walls.ThicknessCm > 0.0
        && FMath::IsFinite(Settings.Walls.DoorHeightCm) && Settings.Walls.DoorHeightCm > 0.0
        && Settings.Walls.DoorHeightCm <= Settings.Walls.HeightCm
        && FMath::IsFinite(Settings.Walls.CornerMarginCm) && Settings.Walls.CornerMarginCm >= 0.0;

    if (!bSettingsValid)
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = TEXT("Invalid validation or wall settings.");
        Issues.Add(Issue);
        return Issues;
    }

    if (Settings.Walls.DoorHeightCm < Settings.PawnHeightCm + Settings.ClearanceCm)
    {
        AddIssue(Issues, TEXT("PS-V002"), TEXT("Door height is too low for the configured Pawn and clearance."), {}, FVector::ZeroVector);
    }

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        if (Connection.CorridorWidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V003"), FString::Printf(TEXT("Corridor width %d cm is below required %.1f cm."), Connection.CorridorWidthCm, Settings.RequiredWidthCm()), { Connection.ConnectionId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        if (Connection.DoorWidthCm < Settings.RequiredWidthCm() || Connection.DoorWidthCm > Connection.CorridorWidthCm)
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door width must fit the Corridor and the configured Pawn."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        const FPlayableSketchDoorOverride* Overrides[] = { &Connection.DoorASettings, &Connection.DoorBSettings };
        const FGuid RoomIds[] = { Connection.RoomAId, Connection.RoomBId };

        for (int32 Index = 0; Index < 2; ++Index)
        {
            if (!Overrides[Index]->bManual)
            {
                continue;
            }

            const FPlayableSketchRoom* Room = Graph.Rooms.FindByPredicate([&](const FPlayableSketchRoom& Item)
            {
                return Item.RoomId == RoomIds[Index];
            });

            const EPlayableSketchWallSide Side = Overrides[Index]->WallSide;
            const bool bValidSide = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South
                || Side == EPlayableSketchWallSide::East || Side == EPlayableSketchWallSide::West;
            const bool bHorizontal = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South;
            double Length = Room ? (bHorizontal ? Room->WidthCm : Room->DepthCm) : 0.0;
            if (Room && Room->PositionMode == EPlayableSketchPositionMode::Auto)
            {
                Length = FMath::CeilToDouble(Length / Settings.GridStepCm) * Settings.GridStepCm;
            }
            const double Offset = Overrides[Index]->OffsetCm;

            if (!Room || !bValidSide || !FMath::IsFinite(Offset)
                || Offset - Connection.DoorWidthCm * 0.5 < Settings.Walls.CornerMarginCm
                || Offset + Connection.DoorWidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm)
            {
                AddIssue(Issues, TEXT("PS-V002"), TEXT("Manual Door side or offset is invalid."), { Connection.ConnectionId, RoomIds[Index] }, FVector::ZeroVector);
                Issues.Last().bHasPosition = false;
            }
        }
    }

    for (int32 A = 0; A < Graph.Rooms.Num(); ++A)
    {
        const FPlayableSketchRoom& RoomA = Graph.Rooms[A];

        if (RoomA.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        const FPlayableSketchRect BoundsA(RoomA.PositionCm, RoomA.PositionCm + FVector2D(RoomA.WidthCm, RoomA.DepthCm));

        if (!BoundsA.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Locked Room coordinates are invalid."), { RoomA.RoomId }, FVector::ZeroVector);
            continue;
        }

        for (int32 B = A + 1; B < Graph.Rooms.Num(); ++B)
        {
            const FPlayableSketchRoom& RoomB = Graph.Rooms[B];
            const FPlayableSketchRect BoundsB(RoomB.PositionCm, RoomB.PositionCm + FVector2D(RoomB.WidthCm, RoomB.DepthCm));

            if (RoomB.PositionMode == EPlayableSketchPositionMode::Locked && BoundsA.OverlapsInterior(BoundsB))
            {
                const FVector2D Center = (BoundsA.Min + BoundsA.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Locked Rooms overlap."), { RoomA.RoomId, RoomB.RoomId }, FVector(Center.X, Center.Y, 25.0), FVector(RoomA.WidthCm * 0.5, RoomA.DepthCm * 0.5, 25.0));
            }
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Queue.Add(Graph.StartRoomId);
    Reachable.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room is disconnected from Start in the Graph."), { Room.RoomId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }
    }

    return Issues;
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidatePlan(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues = ValidateInput(Graph, Settings);

    for (int32 A = 0; A < Plan.Rooms.Num(); ++A)
    {
        const FPlayableSketchPlacedRoom& Room = Plan.Rooms[A];
        if (!Room.Bounds.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Invalid placed Room bounds."), { Room.RoomId }, FVector::ZeroVector);
            return Issues;
        }
        for (int32 B = A + 1; B < Plan.Rooms.Num(); ++B)
        {
            if (Room.Bounds.OverlapsInterior(Plan.Rooms[B].Bounds))
            {
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Placed Rooms overlap."), { Room.RoomId, Plan.Rooms[B].RoomId }, RoomCenter(Room), RoomExtent(Room));
            }
        }
    }

    TSet<FGuid> ValidConnections;

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item)
        {
            return Item.ConnectionId == Connection.ConnectionId;
        });

        if (!Corridor)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Connection has no routed Corridor."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
            continue;
        }

        bool bValidRects = !Corridor->Footprints.IsEmpty();
        for (const FPlayableSketchRect& Rect : Corridor->Footprints)
        {
            bValidRects &= Rect.IsValid();
            if (Rect.IsValid()
                && (!FMath::IsNearlyEqual(Rect.Max.X - Rect.Min.X, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)
                    && !FMath::IsNearlyEqual(Rect.Max.Y - Rect.Min.Y, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)))
            {
                const FVector2D Center = (Rect.Min + Rect.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V003"), TEXT("Corridor footprint width does not match its declared CorridorWidthCm."), { Connection.ConnectionId }, FVector(Center.X, Center.Y, 25.0));
            }
        }

        const FVector Position(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
        const bool bConnected = bValidRects && FootprintsConnected(Corridor->Footprints);

        if (!bConnected)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor footprints are invalid or physically disconnected."), { Connection.ConnectionId }, Position);
        }

        const bool bDoorAValid = CheckDoor(Corridor->DoorA, Connection.RoomAId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);
        const bool bDoorBValid = CheckDoor(Corridor->DoorB, Connection.RoomBId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);

        if (bConnected && bDoorAValid && bDoorBValid && Connection.CorridorWidthCm >= Settings.RequiredWidthCm())
        {
            ValidConnections.Add(Connection.ConnectionId);
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Reachable.Add(Graph.StartRoomId);
    Queue.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (!ValidConnections.Contains(Connection.ConnectionId)) continue;
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room has no validated physical route from Start."), { Room.RoomId }, RoomCenter(Room), RoomExtent(Room));
        }
    }

    for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
    {
        if (!Piece.SourceId.IsValid() || Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN()
            || Piece.SizeCm.X <= 0.0 || Piece.SizeCm.Y <= 0.0 || Piece.SizeCm.Z <= 0.0)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated geometry descriptor is invalid."), { Piece.SourceId }, FVector::ZeroVector);
            continue;
        }

        if (Piece.CenterCm.Z - Piece.SizeCm.Z * 0.5 >= Settings.PawnHeightCm)
        {
            continue;
        }

        const FPlayableSketchRect WallRect(
            FVector2D(Piece.CenterCm.X - Piece.SizeCm.X * 0.5, Piece.CenterCm.Y - Piece.SizeCm.Y * 0.5),
            FVector2D(Piece.CenterCm.X + Piece.SizeCm.X * 0.5, Piece.CenterCm.Y + Piece.SizeCm.Y * 0.5));

        for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
        {
            if (WallRect.OverlapsInterior(Room.Bounds))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Room interior."), { Piece.SourceId, Room.RoomId }, Piece.CenterCm);
            }
        }

        for (const FPlayableSketchCorridor& Corridor : Plan.Corridors)
        {
            if (Piece.bRoom && (Corridor.DoorA.RoomId == Piece.SourceId || Corridor.DoorB.RoomId == Piece.SourceId))
            {
                continue;
            }

            if (Corridor.Footprints.ContainsByPredicate([&](const FPlayableSketchRect& Rect)
                {
                    return WallRect.OverlapsInterior(Rect);
                }))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Corridor interior."), { Piece.SourceId, Corridor.ConnectionId }, Piece.CenterCm);
            }
        }
    }

    for (FPlayableSketchValidationIssue& Issue : Issues)
    {
        if (Issue.bHasPosition) continue;
        for (const FGuid& Id : Issue.ElementIds)
        {
            const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item) { return Item.RoomId == Id; });
            if (Room)
            {
                Issue.PositionCm = RoomCenter(*Room);
                Issue.ExtentCm = RoomExtent(*Room);
                Issue.bHasPosition = true;
                break;
            }
            const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item) { return Item.ConnectionId == Id; });
            if (Corridor)
            {
                Issue.PositionCm = FVector(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
                Issue.bHasPosition = true;
                break;
            }
        }
    }

    return Issues;
}
