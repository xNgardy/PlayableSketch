#include "Navigation/PlayableSketchNavigation.h"
#include "Algo/Reverse.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

namespace
{
const FIntPoint Directions[] = {{1, 0}, {0, 1}, {-1, 0}, {0, -1}};

bool Contains(const FPlayableSketchRect &R, const FVector2D &P)
{
    return P.X >= R.Min.X && P.X < R.Max.X && P.Y >= R.Min.Y && P.Y < R.Max.Y;
}

bool Covered(const FPlayableSketchRect &Required, const TArray<FPlayableSketchRect> &Floors,
             int64 &Work, int64 Limit)
{
    TArray<FPlayableSketchRect> Remaining = {Required};
    for (const FPlayableSketchRect &Floor : Floors)
    {
        TArray<FPlayableSketchRect> Next;
        for (const FPlayableSketchRect &R : Remaining)
        {
            if (++Work > Limit)
                return false;
            if (!R.OverlapsInterior(Floor))
            {
                Next.Add(R);
                continue;
            }
            const FVector2D Lo(FMath::Max(R.Min.X, Floor.Min.X), FMath::Max(R.Min.Y, Floor.Min.Y));
            const FVector2D Hi(FMath::Min(R.Max.X, Floor.Max.X), FMath::Min(R.Max.Y, Floor.Max.Y));
            if (R.Min.X < Lo.X)
                Next.Emplace(R.Min, FVector2D(Lo.X, R.Max.Y));
            if (Hi.X < R.Max.X)
                Next.Emplace(FVector2D(Hi.X, R.Min.Y), R.Max);
            if (R.Min.Y < Lo.Y)
                Next.Emplace(FVector2D(Lo.X, R.Min.Y), FVector2D(Hi.X, Lo.Y));
            if (Hi.Y < R.Max.Y)
                Next.Emplace(FVector2D(Lo.X, Hi.Y), FVector2D(Hi.X, R.Max.Y));
        }
        Remaining = MoveTemp(Next);
        if (Remaining.IsEmpty())
            return true;
    }
    return false;
}

FPlayableSketchRect Portal(const FPlayableSketchDoorEndpoint &Door, double Padding)
{
    const bool bHorizontal = Door.WallSide == EPlayableSketchWallSide::North ||
                             Door.WallSide == EPlayableSketchWallSide::South;

    const FVector2D Half = bHorizontal ? FVector2D(Door.WidthCm * 0.5 + Padding, Padding + 0.001)
                                       : FVector2D(Padding + 0.001, Door.WidthCm * 0.5 + Padding);
    return FPlayableSketchRect(Door.PositionCm - Half, Door.PositionCm + Half);
}

bool TouchesPortal(const FVector2D &P, const FPlayableSketchCorridor &C, double Padding)
{
    return Contains(Portal(C.DoorA, Padding), P) || Contains(Portal(C.DoorB, Padding), P);
}

bool Search(const FPlayableSketchNavigationResult &Grid, const FIntPoint &Start,
            const TOptional<FIntPoint> &Goal, const TSet<FIntPoint> *Allowed,
            const FPlayableSketchCorridor *Closed, double Padding, int64 &Work, int64 Limit,
            TSet<FIntPoint> &Visited, TArray<FIntPoint> &Path)
{
    Visited.Reset();
    Path.Reset();
    auto Passable = [&](const FIntPoint &Cell) {
        return Grid.WalkableCells.Contains(Cell) && (!Allowed || Allowed->Contains(Cell)) &&
               (!Closed || !TouchesPortal(Grid.CellCenter(Cell), *Closed, Padding));
    };
    if (!Passable(Start))
        return false;
    TArray<FIntPoint> Queue = {Start};
    TMap<FIntPoint, FIntPoint> Parents;
    Visited.Add(Start);
    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        if (++Work > Limit)
            return false;
        const FIntPoint Current = Queue[Head];
        if (Goal.IsSet() && Current == Goal.GetValue())
        {
            for (FIntPoint P = Current;; P = Parents.FindChecked(P))
            {
                Path.Add(P);
                if (P == Start)
                    break;
            }
            Algo::Reverse(Path);
            return true;
        }
        for (const FIntPoint &D : Directions)
        {
            const FIntPoint Next = Current + D;
            if (!Visited.Contains(Next) && Passable(Next))
            {
                Visited.Add(Next);
                Parents.Add(Next, Current);
                Queue.Add(Next);
            }
        }
    }
    return !Goal.IsSet();
}

TArray<TSharedPtr<FJsonValue>> IdValues(const TArray<FGuid> &Ids)
{
    TArray<TSharedPtr<FJsonValue>> Values;
    for (const FGuid &Id : Ids)
        Values.Add(MakeShared<FJsonValueString>(Id.ToString()));
    return Values;
}
}

FVector2D FPlayableSketchNavigationResult::CellCenter(const FIntPoint &Cell) const
{
    return OriginCm + FVector2D((static_cast<double>(Cell.X) + 0.5) * CellSizeCm,
                                (static_cast<double>(Cell.Y) + 0.5) * CellSizeCm);
}

FString FPlayableSketchNavigationResult::Summary() const
{
    const FString Length = RouteLengthCm.IsSet()
                               ? FString::Printf(TEXT("%.0f cm"), RouteLengthCm.GetValue())
                               : TEXT("NA");
    return FString::Printf(
        TEXT(
            "Reachable=%s RouteLength=%s UnreachableRooms=%d DeadEnds=%d AlternativeRoute=%s Walkable=%d Visited=%d NavigationMs=%.3f | %s"),
        bReachable ? TEXT("true") : TEXT("false"), *Length, UnreachableRooms.Num(), DeadEndCount,
        bAlternativeRoute ? TEXT("true") : TEXT("false"), WalkableCells.Num(), VisitedCellCount,
        TotalMs, *Status);
}

bool FPlayableSketchNavigation::Analyze(
    const FPlayableSketchFloorPlan &Plan,
    const TArray<FPlayableSketchGeometryDescriptor> &SolidPieces, const FGuid &StartRoomId,
    const FGuid &GoalRoomId, const FPlayableSketchNavigationSettings &S,
    FPlayableSketchNavigationResult &Result, FString &Error)
{
    Result = FPlayableSketchNavigationResult();
    Error.Reset();
    const double TotalStart = FPlatformTime::Seconds();
    auto Fail = [&](const TCHAR *Message) {
        Result = FPlayableSketchNavigationResult();
        Error = Message;
        Result.TotalMs = (FPlatformTime::Seconds() - TotalStart) * 1000.0;
        return false;
    };
    if (S.CellSizeCm <= 0 || S.MaxCells <= 0 || S.MaxCells > 1000000 || S.MaxWork <= 0 ||
        S.MaxWork > 100000000 || !FMath::IsFinite(S.AgentRadiusCm) || S.AgentRadiusCm < 0.0 ||
        !FMath::IsFinite(S.AgentHeightCm) || S.AgentHeightCm <= 0.0 ||
        !FMath::IsFinite(S.ClearanceCm) || S.ClearanceCm < 0.0 ||
        !FMath::IsFinite(S.AgentHeightCm + S.ClearanceCm) || Plan.Rooms.IsEmpty() ||
        !StartRoomId.IsValid() || !GoalRoomId.IsValid() || StartRoomId == GoalRoomId)
        return Fail(TEXT("Invalid navigation settings or endpoints."));
    TMap<FGuid, FPlayableSketchRect> Rooms;
    TArray<FPlayableSketchRect> Floors;
    for (const FPlayableSketchPlacedRoom &R : Plan.Rooms)
    {
        if (!R.RoomId.IsValid() || Rooms.Contains(R.RoomId) || !R.Bounds.IsValid())
            return Fail(TEXT("Invalid or duplicate navigation room."));
        Rooms.Add(R.RoomId, R.Bounds);
        Floors.Add(R.Bounds);
    }
    if (!Rooms.Contains(StartRoomId) || !Rooms.Contains(GoalRoomId))
        return Fail(TEXT("Start or Goal Room is missing from FloorPlan."));
    TSet<FGuid> ConnectionIds;
    for (const FPlayableSketchCorridor &C : Plan.Corridors)
    {
        if (!C.ConnectionId.IsValid() || ConnectionIds.Contains(C.ConnectionId) ||
            !Rooms.Contains(C.DoorA.RoomId) || !Rooms.Contains(C.DoorB.RoomId) ||
            C.DoorA.RoomId == C.DoorB.RoomId || C.Footprints.IsEmpty())
            return Fail(TEXT("Invalid navigation corridor."));
        ConnectionIds.Add(C.ConnectionId);
        for (const FPlayableSketchDoorEndpoint *D : {&C.DoorA, &C.DoorB})
        {
            const FPlayableSketchRect &R = Rooms.FindChecked(D->RoomId);
            const bool bHorizontal = D->WallSide == EPlayableSketchWallSide::North ||
                                     D->WallSide == EPlayableSketchWallSide::South;
            double Boundary = 0.0;
            switch (D->WallSide)
            {
            case EPlayableSketchWallSide::North:
                Boundary = R.Max.Y;
                break;
            case EPlayableSketchWallSide::South:
                Boundary = R.Min.Y;
                break;
            case EPlayableSketchWallSide::East:
                Boundary = R.Max.X;
                break;
            case EPlayableSketchWallSide::West:
                Boundary = R.Min.X;
                break;
            default:
                return Fail(TEXT("Invalid navigation door side."));
            }
            const double Axis = bHorizontal ? D->PositionCm.Y : D->PositionCm.X;
            const double Along = bHorizontal ? D->PositionCm.X : D->PositionCm.Y;
            const double Lo = bHorizontal ? R.Min.X : R.Min.Y;
            const double Hi = bHorizontal ? R.Max.X : R.Max.Y;
            if (D->PositionCm.ContainsNaN() || !FMath::IsFinite(D->WidthCm) || D->WidthCm <= 0.0 ||
                !FMath::IsNearlyEqual(Axis, Boundary, 0.001) || Along - D->WidthCm * 0.5 < Lo ||
                Along + D->WidthCm * 0.5 > Hi)
                return Fail(TEXT("Invalid navigation door position or width."));
        }
        for (const FPlayableSketchRect &R : C.Footprints)
        {
            if (!R.IsValid())
                return Fail(TEXT("Invalid navigation floor footprint."));
            Floors.Add(R);
        }
    }
    TArray<FPlayableSketchRect> Obstacles;
    for (const FPlayableSketchGeometryDescriptor &P : SolidPieces)
    {
        if (P.CenterCm.ContainsNaN() || P.SizeCm.ContainsNaN() || P.SizeCm.GetMin() <= 0.0)
            return Fail(TEXT("Invalid navigation solid descriptor."));

        if (P.CenterCm.Z + P.SizeCm.Z * 0.5 > 0.0 &&
            P.CenterCm.Z - P.SizeCm.Z * 0.5 < S.AgentHeightCm + S.ClearanceCm)
            Obstacles.Emplace(
                FVector2D(P.CenterCm.X - P.SizeCm.X * 0.5, P.CenterCm.Y - P.SizeCm.Y * 0.5),
                FVector2D(P.CenterCm.X + P.SizeCm.X * 0.5, P.CenterCm.Y + P.SizeCm.Y * 0.5));
    }
    FVector2D Min = Floors[0].Min, Max = Floors[0].Max;
    for (const auto &R : Floors)
    {
        Min.X = FMath::Min(Min.X, R.Min.X);
        Min.Y = FMath::Min(Min.Y, R.Min.Y);
        Max.X = FMath::Max(Max.X, R.Max.X);
        Max.Y = FMath::Max(Max.Y, R.Max.Y);
    }
    const double Cell = S.CellSizeCm;
    const double Padding = S.AgentRadiusCm + S.ClearanceCm + Cell * 0.5;
    if (!FMath::IsFinite(Padding) || Min.GetAbsMax() / Cell >= MAX_int32 ||
        Max.GetAbsMax() / Cell >= MAX_int32)
        return Fail(TEXT("Navigation coordinates exceed supported range."));

    Result.OriginCm = FVector2D(FMath::FloorToDouble(Min.X / Cell) * Cell - Cell * 0.5,
                                FMath::FloorToDouble(Min.Y / Cell) * Cell - Cell * 0.5);
    const double NX = FMath::CeilToDouble((Max.X - Result.OriginCm.X) / Cell);
    const double NY = FMath::CeilToDouble((Max.Y - Result.OriginCm.Y) / Cell);
    if (NX <= 0.0 || NY <= 0.0 || NX * NY > S.MaxCells)
        return Fail(TEXT("Navigation grid exceeds MaxCells."));
    Result.Dimensions = FIntPoint(static_cast<int32>(NX), static_cast<int32>(NY));
    Result.CellSizeCm = S.CellSizeCm;
    int64 Work = 0;
    for (int32 Y = 0; Y < Result.Dimensions.Y; ++Y)
    {
        for (int32 X = 0; X < Result.Dimensions.X; ++X)
        {
            const FIntPoint Index(X, Y);
            const FVector2D Center = Result.CellCenter(Index);
            const FPlayableSketchRect Support(Center - FVector2D(Padding, Padding),
                                              Center + FVector2D(Padding, Padding));
            if (!Covered(Support, Floors, Work, S.MaxWork))
            {
                if (Work > S.MaxWork)
                    return Fail(TEXT("Navigation analysis exceeds MaxWork."));
                continue;
            }
            bool bBlocked = false;
            for (const auto &Obstacle : Obstacles)
            {
                if (++Work > S.MaxWork)
                    return Fail(TEXT("Navigation analysis exceeds MaxWork."));
                if (Support.OverlapsInterior(Obstacle))
                {
                    bBlocked = true;
                    break;
                }
            }
            if (!bBlocked)
                Result.WalkableCells.Add(Index);
        }
    }
    Result.BuildMs = (FPlatformTime::Seconds() - TotalStart) * 1000.0;
    const double SearchStart = FPlatformTime::Seconds();

    TMap<FGuid, FIntPoint> Representatives;
    for (const auto &Pair : Rooms)
    {
        const FVector2D Center = (Pair.Value.Min + Pair.Value.Max) * 0.5;
        double Best = TNumericLimits<double>::Max();
        FIntPoint Chosen = FIntPoint::ZeroValue;
        for (const auto &Index : Result.WalkableCells)
        {
            if (++Work > S.MaxWork)
                return Fail(TEXT("Navigation analysis exceeds MaxWork."));
            const FVector2D P = Result.CellCenter(Index);
            if (!Contains(Pair.Value, P))
                continue;
            const double Distance = (P - Center).SizeSquared();
            if (Distance < Best ||
                (Distance == Best &&
                 (Index.Y < Chosen.Y || (Index.Y == Chosen.Y && Index.X < Chosen.X))))
            {
                Best = Distance;
                Chosen = Index;
            }
        }
        if (Best != TNumericLimits<double>::Max())
            Representatives.Add(Pair.Key, Chosen);
    }
    TSet<FIntPoint> Visited;
    TArray<FIntPoint> Path;
    const FIntPoint *Start = Representatives.Find(StartRoomId);
    const FIntPoint *Goal = Representatives.Find(GoalRoomId);
    if (Start)
    {
        Search(Result, *Start, {}, nullptr, nullptr, Padding, Work, S.MaxWork, Visited, Path);
        Result.VisitedCellCount = Visited.Num();
        for (const auto &Pair : Rooms)
        {
            const auto *R = Representatives.Find(Pair.Key);
            if (!R || !Visited.Contains(*R))
                Result.UnreachableRooms.Add(Pair.Key);
        }
        if (Goal && Visited.Contains(*Goal))
        {
            Result.bReachable = Search(Result, *Start, *Goal, nullptr, nullptr, Padding, Work,
                                       S.MaxWork, Visited, Path);
            if (Result.bReachable)
            {
                Result.RouteLengthCm = static_cast<double>(Path.Num() - 1) * Cell;
                for (const auto &Index : Path)
                    Result.PathPoints.Add(Result.CellCenter(Index));
            }
        }
    }
    else
        for (const auto &Pair : Rooms)
            Result.UnreachableRooms.Add(Pair.Key);
    Result.UnreachableRooms.Sort(
        [](const FGuid &A, const FGuid &B) { return A.ToString() < B.ToString(); });
    Result.SearchMs = (FPlatformTime::Seconds() - SearchStart) * 1000.0;
    const double MetricsStart = FPlatformTime::Seconds();
    TMap<FGuid, int32> Degree;
    for (const FPlayableSketchCorridor &C : Plan.Corridors)
    {
        const auto *A = Representatives.Find(C.DoorA.RoomId);
        const auto *B = Representatives.Find(C.DoorB.RoomId);
        if (!A || !B)
            continue;
        TSet<FIntPoint> Allowed;
        TArray<FPlayableSketchRect> ConnectionFloors = C.Footprints;
        ConnectionFloors.Add(Rooms.FindChecked(C.DoorA.RoomId));
        ConnectionFloors.Add(Rooms.FindChecked(C.DoorB.RoomId));
        for (const auto &Index : Result.WalkableCells)
        {
            const FVector2D P = Result.CellCenter(Index);
            for (const auto &R : ConnectionFloors)
            {
                if (++Work > S.MaxWork)
                    return Fail(TEXT("Navigation analysis exceeds MaxWork."));
                if (Contains(R, P))
                {
                    Allowed.Add(Index);
                    break;
                }
            }
        }
        if (Search(Result, *A, *B, &Allowed, nullptr, Padding, Work, S.MaxWork, Visited, Path))
        {
            Result.PhysicalConnections.Add(C.ConnectionId);
            ++Degree.FindOrAdd(C.DoorA.RoomId);
            ++Degree.FindOrAdd(C.DoorB.RoomId);
            for (const FVector2D &P : Result.PathPoints)
                if (TouchesPortal(P, C, Cell * 0.5))
                {
                    Result.RouteConnections.Add(C.ConnectionId);
                    break;
                }
        }
    }
    for (const auto &Pair : Degree)
        if (Pair.Value == 1 && Pair.Key != StartRoomId && Pair.Key != GoalRoomId)
            ++Result.DeadEndCount;
    Result.bAlternativeRoute = Result.bReachable && !Result.RouteConnections.IsEmpty();
    for (const FGuid &Id : Result.RouteConnections)
    {
        const auto *Closed = Plan.Corridors.FindByPredicate(
            [&](const FPlayableSketchCorridor &C) { return C.ConnectionId == Id; });
        if (!Search(Result, *Start, *Goal, nullptr, Closed, Padding, Work, S.MaxWork, Visited,
                    Path))
            Result.bAlternativeRoute = false;
    }
    if (Work > S.MaxWork)
        return Fail(TEXT("Navigation analysis exceeds MaxWork."));
    Result.PhysicalConnections.Sort(
        [](const FGuid &A, const FGuid &B) { return A.ToString() < B.ToString(); });
    Result.RouteConnections.Sort(
        [](const FGuid &A, const FGuid &B) { return A.ToString() < B.ToString(); });
    Result.MetricsMs = (FPlatformTime::Seconds() - MetricsStart) * 1000.0;
    Result.TotalMs = (FPlatformTime::Seconds() - TotalStart) * 1000.0;
    Result.Status =
        !Start ? TEXT("Start room has no walkable cell.")
               : (!Goal ? TEXT("Goal room has no walkable cell.")
                        : (Result.bReachable ? TEXT("Shortest four-neighbor grid route found.")
                                             : TEXT("No agent-safe route from Start to Goal.")));
    return true;
}

bool FPlayableSketchNavigation::ExportJson(const TArray<FPlayableSketchNavigationSample> &Samples,
                                           const FString &Filename, FString &Error)
{
    Error.Reset();
    TArray<TSharedPtr<FJsonValue>> Values;
    for (const auto &Sample : Samples)
    {
        const auto &R = Sample.Result;
        const auto &S = Sample.Settings;
        const TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
        O->SetStringField(TEXT("name"), Sample.Name);
        O->SetNumberField(TEXT("seed"), Sample.Seed);
        O->SetBoolField(TEXT("fixed_layout_fixture"), Sample.bFixedLayout);
        O->SetNumberField(TEXT("room_count"), Sample.RoomCount);
        O->SetNumberField(TEXT("connection_count"), Sample.ConnectionCount);
        O->SetNumberField(TEXT("cell_size_cm"), S.CellSizeCm);
        O->SetNumberField(TEXT("agent_radius_cm"), S.AgentRadiusCm);
        O->SetNumberField(TEXT("agent_height_cm"), S.AgentHeightCm);
        O->SetNumberField(TEXT("clearance_cm"), S.ClearanceCm);
        O->SetStringField(
            TEXT("clearance_model"),
            TEXT("axis-aligned square: radius + margin + half cell; floor union coverage"));
        O->SetBoolField(TEXT("reachable"), R.bReachable);
        if (R.RouteLengthCm.IsSet())
            O->SetNumberField(TEXT("shortest_route_length_cm"), R.RouteLengthCm.GetValue());
        else
            O->SetField(TEXT("shortest_route_length_cm"), MakeShared<FJsonValueNull>());
        O->SetArrayField(TEXT("unreachable_rooms"), IdValues(R.UnreachableRooms));
        O->SetNumberField(TEXT("dead_end_count"), R.DeadEndCount);
        O->SetBoolField(TEXT("alternative_route"), R.bAlternativeRoute);
        O->SetArrayField(TEXT("physical_connections"), IdValues(R.PhysicalConnections));
        O->SetArrayField(TEXT("route_connections"), IdValues(R.RouteConnections));
        O->SetNumberField(TEXT("walkable_cells"), R.WalkableCells.Num());
        O->SetNumberField(TEXT("visited_cells"), R.VisitedCellCount);
        O->SetNumberField(TEXT("grid_origin_x_cm"), R.OriginCm.X);
        O->SetNumberField(TEXT("grid_origin_y_cm"), R.OriginCm.Y);
        O->SetNumberField(TEXT("grid_columns"), R.Dimensions.X);
        O->SetNumberField(TEXT("grid_rows"), R.Dimensions.Y);
        O->SetNumberField(TEXT("build_ms"), R.BuildMs);
        O->SetNumberField(TEXT("search_ms"), R.SearchMs);
        O->SetNumberField(TEXT("metrics_ms"), R.MetricsMs);
        O->SetNumberField(TEXT("total_ms"), R.TotalMs);
        O->SetStringField(TEXT("status"), R.Status);
        Values.Add(MakeShared<FJsonValueObject>(O));
    }
    const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetNumberField(TEXT("schema_version"), 1);
    Root->SetArrayField(TEXT("samples"), Values);
    FString Text;
    const auto Writer = TJsonWriterFactory<>::Create(&Text);
    if (!FJsonSerializer::Serialize(Root, Writer) ||
        !IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true) ||
        !FFileHelper::SaveStringToFile(Text, *Filename,
                                       FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
    {
        Error = TEXT("Navigation JSON export failed.");
        return false;
    }
    return true;
}
