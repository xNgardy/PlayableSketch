#include "ExplicitLayout/PlayableSketchExplicitNavigation.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/FloatingPawnMovement.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "HAL/PlatformTime.h"
#include "Misc/ScopeExit.h"
#include "Algo/Reverse.h"

namespace
{
constexpr double Lift = 0.5;
bool Supported(const AActor &A, const FPlayableSketchExplicitAgent &S)
{
    return A.GetWorld() && !A.GetActorLocation().ContainsNaN() &&
           A.GetActorLocation().GetAbsMax() <= 1.e9 &&
           A.GetActorScale3D().Equals(FVector::OneVector, 0.0001) &&
           A.GetActorQuat().GetUpVector().Equals(FVector::UpVector, 0.0001) &&
           FMath::IsFinite(S.RadiusCm) && FMath::IsFinite(S.HalfHeightCm) &&
           FMath::IsFinite(S.ClearanceCm) && FMath::IsFinite(S.CellSizeCm) &&
           !S.GridOffsetCm.ContainsNaN() && S.RadiusCm > 0 && S.HalfHeightCm >= S.RadiusCm &&
           S.ClearanceCm >= 0 && S.HalfHeightCm >= S.RadiusCm + S.ClearanceCm / 2 &&
           S.StepHeightCm == 0 && S.CellSizeCm >= 1 && S.RadiusCm <= 1.e6 &&
           S.HalfHeightCm <= 1.e6 && S.ClearanceCm <= 1.e6 && S.CellSizeCm <= 1.e6 &&
           S.MaxCells > 0 && S.MaxCells <= 250000 && S.MaxQueries > 0 && S.MaxQueries <= 2000000;
}
struct FProbe
{
    AActor &Owner;
    FPlayableSketchExplicitNavigationReport &R;
    const AActor *Ignored = nullptr;
    bool bBudget = false;
    TArray<FBox2D> Floors;
    FProbe(AActor &InOwner, FPlayableSketchExplicitNavigationReport &InReport,
           const AActor *InIgnored = nullptr)
        : Owner(InOwner), R(InReport), Ignored(InIgnored)
    {
        TArray<UStaticMeshComponent *> Components;
        Owner.GetComponents(Components);
        for (const auto *C : Components)
        {
            if (!C->ComponentHasTag(TEXT("PlayableSketch.GeneratedFloor")) || !C->GetStaticMesh() ||
                !C->IsQueryCollisionEnabled() ||
                C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block)
                continue;
            const FBox Box =
                C->GetStaticMesh()->GetBoundingBox().TransformBy(C->GetRelativeTransform());
            if (FMath::Abs(Box.Max.Z) < 0.001)
                Floors.Add(
                    FBox2D(FVector2D(Box.Min.X, Box.Min.Y), FVector2D(Box.Max.X, Box.Max.Y)));
        }
    }
    bool Support(const FVector2D &A, const FVector2D &B)
    {

        TArray<FBox2D> Uncovered{FBox2D(A, B)};
        for (const auto &Floor : Floors)
        {
            TArray<FBox2D> Next;
            for (const auto &Box : Uncovered)
            {
                if (!Consume())
                    return false;
                const FVector2D Lo(FMath::Max(Box.Min.X, Floor.Min.X),
                                   FMath::Max(Box.Min.Y, Floor.Min.Y));
                const FVector2D Hi(FMath::Min(Box.Max.X, Floor.Max.X),
                                   FMath::Min(Box.Max.Y, Floor.Max.Y));
                if (Hi.X <= Lo.X || Hi.Y <= Lo.Y)
                {
                    Next.Add(Box);
                    continue;
                }
                auto Add = [&](FVector2D Min, FVector2D Max) {
                    if (Max.X > Min.X + 0.000001 && Max.Y > Min.Y + 0.000001)
                        Next.Add(FBox2D(Min, Max));
                };
                Add(Box.Min, FVector2D(Lo.X, Box.Max.Y));
                Add(FVector2D(Hi.X, Box.Min.Y), Box.Max);
                Add(FVector2D(Lo.X, Box.Min.Y), FVector2D(Hi.X, Lo.Y));
                Add(FVector2D(Lo.X, Hi.Y), FVector2D(Hi.X, Box.Max.Y));
            }
            if (Next.Num() > 4096)
            {
                bBudget = true;
                return false;
            }
            Uncovered = MoveTemp(Next);
            if (Uncovered.IsEmpty())
                return true;
        }
        return false;
    }
    bool Consume()
    {
        if (++R.Queries > R.Agent.MaxQueries)
        {
            bBudget = true;
            return false;
        }
        return true;
    }
    FVector World(const FVector2D &P) const
    {
        return Owner.GetActorTransform().TransformPosition(
            FVector(P.X, P.Y, R.Agent.HalfHeightCm + Lift));
    }
    FCollisionQueryParams Params() const
    {
        FCollisionQueryParams Q(SCENE_QUERY_STAT(PlayableSketchExplicitAgent), false);
        if (Ignored)
            Q.AddIgnoredActor(Ignored);
        return Q;
    }
    bool Floor(const FVector2D &P)
    {
        const double Radius = R.Agent.RadiusCm + R.Agent.ClearanceCm;
        if (!Support(P - FVector2D(Radius, Radius), P + FVector2D(Radius, Radius)) || !Consume())
            return false;
        const FVector Start = Owner.GetActorTransform().TransformPosition(FVector(P.X, P.Y, Lift));
        FHitResult Hit;
        return Owner.GetWorld()->LineTraceSingleByChannel(Hit, Start, Start - FVector(0, 0, 2),
                                                          ECC_Pawn, Params()) &&
               Hit.ImpactNormal.Z >= 0.99;
    }
    bool Clear(const FVector2D &P)
    {
        if (!Consume())
            return false;
        const double Radius = R.Agent.RadiusCm + R.Agent.ClearanceCm;

        const double Half = R.Agent.HalfHeightCm + R.Agent.ClearanceCm / 2;
        const FVector Center = World(P) + FVector(0, 0, R.Agent.ClearanceCm / 2);
        return !Owner.GetWorld()->OverlapBlockingTestByChannel(
                   Center, FQuat::Identity, ECC_Pawn,
                   FCollisionShape::MakeCapsule(Radius, FMath::Max(Radius, Half)), Params()) &&
               Floor(P);
    }
    bool Edge(const FVector2D &A, const FVector2D &B)
    {
        if (!Consume())
            return false;
        const double Radius = R.Agent.RadiusCm + R.Agent.ClearanceCm;
        const double Half = FMath::Max(Radius, R.Agent.HalfHeightCm + R.Agent.ClearanceCm / 2);
        const FVector LiftTop(0, 0, R.Agent.ClearanceCm / 2);
        if (Owner.GetWorld()->SweepTestByChannel(
                World(A) + LiftTop, World(B) + LiftTop, FQuat::Identity, ECC_Pawn,
                FCollisionShape::MakeCapsule(Radius, Half), Params()))
            return false;
        return Support(FVector2D(FMath::Min(A.X, B.X) - Radius, FMath::Min(A.Y, B.Y) - Radius),
                       FVector2D(FMath::Max(A.X, B.X) + Radius, FMath::Max(A.Y, B.Y) + Radius));
    }
};
}

FString FPlayableSketchExplicitNavigationReport::Summary() const
{
    return FString::Printf(
        TEXT(
            "analysis_completed=%s reachable=%s topology=%s geometry=%s grid=%s NavMesh=%s Pawn=%s; %s"),
        bAnalysisCompleted ? TEXT("true") : TEXT("false"),
        bReachable ? TEXT("true") : TEXT("false"), *Topology, *Geometry, *Grid, *NavMesh, *Pawn,
        *Reason);
}

FString FPlayableSketchExplicitNavigationReport::Json() const
{
    auto J = MakeShared<FJsonObject>();
    J->SetStringField(TEXT("schema_version"), TEXT("explicit-navigation/v1"));
    J->SetStringField(TEXT("document_id"), DocumentId);
    J->SetStringField(TEXT("revision_id"), RevisionId);
    J->SetBoolField(TEXT("analysis_completed"), bAnalysisCompleted);
    J->SetBoolField(TEXT("reachable"), bReachable);
    for (const auto &P : TMap<FString, FString>{{TEXT("topology"), Topology},
                                                {TEXT("geometry"), Geometry},
                                                {TEXT("grid"), Grid},
                                                {TEXT("navmesh"), NavMesh},
                                                {TEXT("pawn"), Pawn},
                                                {TEXT("reason"), Reason}})
        J->SetStringField(P.Key, P.Value);
    J->SetStringField(TEXT("movement_model"),
                      TEXT("flat_floor_swept_capsule_pawn; no gravity/steps/AI; ECC_Pawn"));
    J->SetStringField(
        TEXT("navmesh_policy"),
        TEXT(
            "not_applicable: bounded collision grid drives movement; generated components opt out of Recast"));
    J->SetStringField(
        TEXT("floor_policy"),
        TEXT(
            "conservative square footprint and swept rectangle union coverage of published flat floor boxes, plus engine floor trace"));
    J->SetStringField(TEXT("actor_transform"), ActorTransform.ToString());
    auto A = MakeShared<FJsonObject>();
    A->SetNumberField(TEXT("radius_cm"), Agent.RadiusCm);
    A->SetNumberField(TEXT("half_height_cm"), Agent.HalfHeightCm);
    A->SetNumberField(TEXT("clearance_cm"), Agent.ClearanceCm);
    A->SetNumberField(TEXT("step_height_cm"), Agent.StepHeightCm);
    A->SetNumberField(TEXT("cell_size_cm"), Agent.CellSizeCm);
    A->SetNumberField(TEXT("max_cells"), Agent.MaxCells);
    A->SetNumberField(TEXT("max_queries"), Agent.MaxQueries);
    A->SetNumberField(TEXT("grid_offset_x_cm"), Agent.GridOffsetCm.X);
    A->SetNumberField(TEXT("grid_offset_y_cm"), Agent.GridOffsetCm.Y);
    J->SetObjectField(TEXT("agent"), A);
    auto Widths = MakeShared<FJsonObject>();
    for (const auto &P : CorridorClearWidthsCm)
        Widths->SetNumberField(P.Key, P.Value);
    J->SetObjectField(TEXT("corridor_clear_widths_cm"), Widths);
    J->SetNumberField(TEXT("queries"), Queries);
    J->SetNumberField(TEXT("walkable_cells"), WalkableCells);
    J->SetNumberField(TEXT("movement_steps"), MovementSteps);
    J->SetNumberField(TEXT("analysis_ms"), AnalysisMs);
    J->SetNumberField(TEXT("pawn_ms"), PawnMs);
    J->SetNumberField(TEXT("origin_x_cm"), OriginCm.X);
    J->SetNumberField(TEXT("origin_y_cm"), OriginCm.Y);
    J->SetNumberField(TEXT("columns"), Dimensions.X);
    J->SetNumberField(TEXT("rows"), Dimensions.Y);
    TArray<TSharedPtr<FJsonValue>> V;
    for (const auto &P : Path)
    {
        auto Point = MakeShared<FJsonObject>();
        Point->SetNumberField(TEXT("x"), P.X);
        Point->SetNumberField(TEXT("y"), P.Y);
        V.Add(MakeShared<FJsonValueObject>(Point));
    }
    J->SetArrayField(TEXT("path_local_cm"), V);
    V.Reset();
    for (const auto &I : Issues)
        V.Add(MakeShared<FJsonValueString>(I));
    J->SetArrayField(TEXT("issues"), V);
    FString Text;
    FJsonSerializer::Serialize(J, TJsonWriterFactory<>::Create(&Text));
    return Text;
}

FPlayableSketchExplicitNavigationReport FPlayableSketchExplicitNavigation::Analyze(
    AActor &Owner, const FPlayableSketchExplicitLayout &L, const FPlayableSketchExplicitAgent &S)
{
    FPlayableSketchExplicitNavigationReport R;
    R.Agent = S;
    R.DocumentId = L.DocumentId;
    R.RevisionId = L.RevisionId;
    R.ActorTransform = Owner.GetActorTransform();
    const double Begin = FPlatformTime::Seconds();
    ON_SCOPE_EXIT
    {
        R.AnalysisMs = (FPlatformTime::Seconds() - Begin) * 1000;
    };
    if (!Supported(Owner, S) || L.Regions.IsEmpty())
    {
        R.Reason = TEXT(
            "unsupported_agent_or_transform: unit scale, horizontal floor, flat movement and bounded finite settings required");
        return R;
    }
    FVector2D Min = L.Regions[0].Bounds.Min, Max = L.Regions[0].Bounds.Max;
    FProbe Probe{Owner, R};
    bool Floors = true;
    for (const auto &Region : L.Regions)
    {
        Min.X = FMath::Min(Min.X, Region.Bounds.Min.X);
        Min.Y = FMath::Min(Min.Y, Region.Bounds.Min.Y);
        Max.X = FMath::Max(Max.X, Region.Bounds.Max.X);
        Max.Y = FMath::Max(Max.Y, Region.Bounds.Max.Y);
        Floors &= Probe.Floor((Region.Bounds.Min + Region.Bounds.Max) / 2);
        if (Region.bCorridor)
            R.CorridorClearWidthsCm.Add(Region.Id,
                                        FMath::Min(Region.Bounds.Max.X - Region.Bounds.Min.X,
                                                   Region.Bounds.Max.Y - Region.Bounds.Min.Y) -
                                            L.Settings.WallThicknessCm);
    }
    R.Geometry = Floors ? TEXT("passed") : TEXT("failed");
    if (!Floors)
        R.Issues.Add(TEXT("floor_support_missing_at_region_center"));
    const double RequiredWidth = 2 * (S.RadiusCm + S.ClearanceCm);
    for (const auto &O : L.Openings)
    {
        if (O.ClearWidthCm < RequiredWidth)
            R.Issues.Add(TEXT("narrow_opening:") + O.Id);
        if (O.ClearHeightCm < 2 * S.HalfHeightCm + S.ClearanceCm + Lift)
            R.Issues.Add(TEXT("low_lintel:") + O.Id);
    }
    if (L.ValidationMode == TEXT("geometry_only"))
    {
        R.Topology = R.Grid = R.Pawn = TEXT("not_applicable");
        R.bAnalysisCompleted = !Probe.bBudget;
        R.Reason = TEXT("geometry_only: floor sanity checked; room traversal not applicable");
        return R;
    }
    const auto *Start = L.Regions.FindByPredicate(
        [&](const auto &X) { return X.Id.Equals(L.StartRoomId, ESearchCase::CaseSensitive); });
    const auto *Goal = L.Regions.FindByPredicate(
        [&](const auto &X) { return X.Id.Equals(L.GoalRoomId, ESearchCase::CaseSensitive); });
    if (!Start || !Goal)
    {
        R.Reason = TEXT("missing_start_goal");
        return R;
    }
    auto RegionKey = [&](const FString &Id) {
        return FPlayableSketchExplicitLayoutBuilder::StableId(L.DocumentId, TEXT("region"), Id);
    };
    TSet<FGuid> Seen{RegionKey(L.StartRoomId)};
    TArray<FString> RoomQueue{L.StartRoomId};
    for (int32 I = 0; I < RoomQueue.Num(); ++I)
        for (const auto &O : L.Openings)
            if (O.RegionIds.ContainsByPredicate([&](const auto &Id) {
                    return Id.Equals(RoomQueue[I], ESearchCase::CaseSensitive);
                }))
                for (const auto &Id : O.RegionIds)
                    if (!Seen.Contains(RegionKey(Id)))
                    {
                        Seen.Add(RegionKey(Id));
                        RoomQueue.Add(Id);
                    }
    R.Topology = Seen.Contains(RegionKey(L.GoalRoomId)) ? TEXT("passed") : TEXT("failed");
    R.OriginCm = FVector2D(FMath::FloorToDouble(Min.X / S.CellSizeCm) * S.CellSizeCm,
                           FMath::FloorToDouble(Min.Y / S.CellSizeCm) * S.CellSizeCm) +
                 S.GridOffsetCm;
    const double NX = FMath::CeilToDouble((Max.X - R.OriginCm.X) / S.CellSizeCm);
    const double NY = FMath::CeilToDouble((Max.Y - R.OriginCm.Y) / S.CellSizeCm);
    if (NX <= 0 || NY <= 0 || NX * NY > S.MaxCells)
    {
        R.Reason = TEXT("grid_cell_budget_exceeded");
        return R;
    }
    R.Dimensions = FIntPoint(static_cast<int32>(NX), static_cast<int32>(NY));
    auto Point = [&](int32 I) {
        return R.OriginCm +
               FVector2D(I % R.Dimensions.X + 0.5, I / R.Dimensions.X + 0.5) * S.CellSizeCm;
    };
    const int32 Count = R.Dimensions.X * R.Dimensions.Y;
    TArray<uint8> Clear;
    Clear.Init(0, Count);
    const FVector2D StartPoint = (Start->Bounds.Min + Start->Bounds.Max) / 2;
    const FVector2D GoalPoint = (Goal->Bounds.Min + Goal->Bounds.Max) / 2;
    int32 First = INDEX_NONE, Last = INDEX_NONE;
    double DS = MAX_dbl, DG = MAX_dbl;
    for (int32 I = 0; I < Count && !Probe.bBudget; ++I)
    {
        const auto P = Point(I);
        if (!Probe.Clear(P))
            continue;
        Clear[I] = 1;
        ++R.WalkableCells;
        const double A = FVector2D::DistSquared(P, StartPoint),
                     B = FVector2D::DistSquared(P, GoalPoint);
        if (A < DS && Probe.Edge(StartPoint, P))
        {
            First = I;
            DS = A;
        }
        if (B < DG && Probe.Edge(GoalPoint, P))
        {
            Last = I;
            DG = B;
        }
    }
    TArray<int32> Queue, Parent;
    Parent.Init(INDEX_NONE, Count);
    if (First != INDEX_NONE && Last != INDEX_NONE && Probe.Clear(StartPoint) &&
        Probe.Clear(GoalPoint))
    {
        Queue.Add(First);
        Parent[First] = First;
    }
    for (int32 Q = 0; Q < Queue.Num() && !Probe.bBudget; ++Q)
    {
        const int32 I = Queue[Q];
        if (I == Last)
            break;
        for (const auto &D : {FIntPoint(1, 0), FIntPoint(-1, 0), FIntPoint(0, 1), FIntPoint(0, -1)})
        {
            const int32 X = I % R.Dimensions.X + D.X, Y = I / R.Dimensions.X + D.Y;
            if (X < 0 || Y < 0 || X >= R.Dimensions.X || Y >= R.Dimensions.Y)
                continue;
            const int32 J = Y * R.Dimensions.X + X;
            if (Clear[J] && Parent[J] == INDEX_NONE && Probe.Edge(Point(I), Point(J)))
            {
                Parent[J] = I;
                Queue.Add(J);
            }
        }
    }
    if (Probe.bBudget)
    {
        R.Reason = TEXT("collision_query_budget_exceeded");
        return R;
    }
    R.bAnalysisCompleted = true;
    R.bReachable = Last != INDEX_NONE && Parent[Last] != INDEX_NONE;
    R.Grid = R.bReachable ? TEXT("passed") : TEXT("failed");
    if (R.bReachable)
    {
        for (int32 I = Last;; I = Parent[I])
        {
            R.Path.Add(Point(I));
            if (I == First)
                break;
        }
        Algo::Reverse(R.Path);
        R.Path.Insert(StartPoint, 0);
        R.Path.Add(GoalPoint);
        R.Reason = TEXT("collision_grid_route_found; Pawn not yet run");
    }
    else
    {
        R.Reason = TEXT(
            "collision_or_floor_or_grid_discretization_blocked; no continuous unreachability claim; inspect issues and retry finer/shifted grid");
        R.Issues.Add(
            TEXT("grid_unreachable_may_include_discretization; retry_resolution_or_origin"));
    }
    return R;
}

bool FPlayableSketchExplicitNavigation::TraversePawn(AActor &Owner, const TArray<FVector2D> &Route,
                                                     FPlayableSketchExplicitNavigationReport &R)
{
    const double Begin = FPlatformTime::Seconds();
    ON_SCOPE_EXIT
    {
        R.PawnMs = (FPlatformTime::Seconds() - Begin) * 1000;
    };
    R.Pawn = TEXT("failed");
    R.MovementSteps = 0;
    if (!Supported(Owner, R.Agent) || Route.Num() < 2 || Route.Num() > 250002 ||
        !Owner.GetActorTransform().Equals(R.ActorTransform))
    {
        R.Reason = TEXT("pawn_invalid_route_agent_or_changed_transform");
        return false;
    }
    for (const auto &P : Route)
        if (P.ContainsNaN() || FMath::Max(FMath::Abs(P.X), FMath::Abs(P.Y)) > 1.e7)
        {
            R.Reason = TEXT("pawn_nonfinite_route");
            return false;
        }
    auto *Pawn = Owner.GetWorld()->SpawnActor<APawn>();
    if (!Pawn)
    {
        R.Reason = TEXT("pawn_spawn_failed");
        return false;
    }
    ON_SCOPE_EXIT
    {
        Pawn->Destroy();
    };
    auto *Capsule = NewObject<UCapsuleComponent>(Pawn);
    Pawn->SetRootComponent(Capsule);
    Pawn->AddInstanceComponent(Capsule);
    const double Radius = R.Agent.RadiusCm + R.Agent.ClearanceCm;
    const double Half = FMath::Max(Radius, R.Agent.HalfHeightCm + R.Agent.ClearanceCm / 2);
    Capsule->InitCapsuleSize(Radius, Half);
    Capsule->SetCollisionProfileName(TEXT("Pawn"));
    Capsule->SetGenerateOverlapEvents(false);
    Capsule->RegisterComponent();
    auto *Movement = NewObject<UFloatingPawnMovement>(Pawn);
    Pawn->AddInstanceComponent(Movement);
    Movement->RegisterComponent();
    Movement->SetUpdatedComponent(Capsule);
    Pawn->DispatchBeginPlay();
    FProbe Probe{Owner, R, Pawn};
    auto Position = [&](const FVector2D &P) {
        return Probe.World(P) + FVector(0, 0, R.Agent.ClearanceCm / 2);
    };
    Pawn->SetActorLocation(Position(Route[0]));
    if (!Probe.Clear(Route[0]))
    {
        R.Reason = TEXT("pawn_start_collision_or_floor_support");
        return false;
    }
    for (int32 I = 1; I < Route.Num(); ++I)
    {
        const int32 Steps = FMath::CeilToInt(FVector2D::Distance(Route[I - 1], Route[I]) / 5.0);
        if (Steps > 100000 || R.MovementSteps + Steps > 100000)
        {
            R.Reason = TEXT("pawn_movement_budget_exceeded");
            return false;
        }
        for (int32 J = 1; J <= Steps; ++J)
        {
            const FVector2D P = FMath::Lerp(Route[I - 1], Route[I], static_cast<double>(J) / Steps);
            if (!Probe.Support(FVector2D(FMath::Min(Route[I - 1].X, P.X) - Radius,
                                         FMath::Min(Route[I - 1].Y, P.Y) - Radius),
                               FVector2D(FMath::Max(Route[I - 1].X, P.X) + Radius,
                                         FMath::Max(Route[I - 1].Y, P.Y) + Radius)) ||
                !Probe.Floor(P))
            {
                R.Reason = Probe.bBudget ? TEXT("pawn_query_budget_exceeded")
                                         : TEXT("pawn_floor_disconnect");
                return false;
            }
            FHitResult Hit;
            Movement->SafeMoveUpdatedComponent(Position(P) - Pawn->GetActorLocation(),
                                               FQuat::Identity, true, Hit);
            ++R.MovementSteps;
            if (Hit.bBlockingHit || !Pawn->GetActorLocation().Equals(Position(P), 0.1))
            {
                const auto *Blocker = Hit.GetComponent();
                FString Kind = TEXT("prop_or_external_collision");
                FString Key = GetNameSafe(Blocker);
                if (Blocker)
                {
                    if (Blocker->ComponentHasTag(TEXT("PlayableSketch.Lintel")))
                        Kind = TEXT("low_lintel");
                    else if (Blocker->ComponentHasTag(TEXT("PlayableSketch.Wall")))
                        Kind = TEXT("wall_or_jamb");
                    for (const auto &Tag : Blocker->ComponentTags)
                        if (Tag.ToString().StartsWith(TEXT("ComponentKey=")))
                            Key = Tag.ToString();
                }
                R.Reason = TEXT("pawn_blocked:") + Kind + TEXT(":") + Key;
                return false;
            }
        }
    }
    R.Pawn = TEXT("passed");
    R.Reason = TEXT("actual_capsule_pawn_completed_flat_floor_route");
    return true;
}

bool FPlayableSketchExplicitNavigation::CanMove(AActor &Owner, const FVector2D &From,
                                                const FVector2D &To,
                                                const FPlayableSketchExplicitAgent &Agent,
                                                const AActor *Ignore)
{
    if (!Supported(Owner, Agent) || From.ContainsNaN() || To.ContainsNaN() ||
        FVector2D::Distance(From, To) > 1000)
        return false;
    FPlayableSketchExplicitNavigationReport Report;
    Report.Agent = Agent;
    FProbe Probe{Owner, Report, Ignore};
    return Probe.Clear(From) && Probe.Clear(To) && Probe.Edge(From, To) && !Probe.bBudget;
}
