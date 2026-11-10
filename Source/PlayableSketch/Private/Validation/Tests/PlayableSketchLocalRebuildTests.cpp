#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Materials/Material.h"
#include "Misc/AutomationTest.h"
#include "Layout/PlayableSketchCorridorRouting.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchLocalRebuildTests,
                                 "PlayableSketch.Geometry.LocalRebuild",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchLocalRebuildTests::RunTest(const FString &Parameters)
{
    const UWorld::InitializationValues IV = UWorld::InitializationValues()
                                                .AllowAudioPlayback(false)
                                                .RequiresHitProxies(false)
                                                .CreatePhysicsScene(true)
                                                .CreateNavigation(false)
                                                .CreateAISystem(false)
                                                .ShouldSimulatePhysics(false)
                                                .EnableTraceCollision(true)
                                                .CreateFXSystem(false)
                                                .SetTransactional(false);
    UWorld *World = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true,
                                        ERHIFeatureLevel::Num, &IV);
    if (!TestNotNull(TEXT("Transient test world"), World))
        return false;
    APlayableSketchLevelActor *Local = World->SpawnActor<APlayableSketchLevelActor>();
    APlayableSketchLevelActor *Full = World->SpawnActor<APlayableSketchLevelActor>();
    if (!Local || !Full)
    {
        AddError(TEXT("Test actors could not be created."));
        World->DestroyWorld(false);
        return false;
    }
    Local->bAutoRebuildGeometry = Full->bAutoRebuildGeometry = false;
    UPlayableSketchGraphAsset *Asset = NewObject<UPlayableSketchGraphAsset>(Local);
    Local->GraphAsset = Full->GraphAsset = Asset;
    UMaterialInterface *HubMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    Local->HubFloorMaterial = Full->HubFloorMaterial = HubMaterial;

    FPlayableSketchGraph Base;
    const FVector2D Positions[] = {{0, 0}, {1400, 0}, {1400, 1400}, {0, 1400}};
    for (int32 I = 0; I < 4; ++I)
    {
        FPlayableSketchRoom R;
        R.RoomId = FGuid(I + 1, 0, 0, 1);
        R.PositionMode = EPlayableSketchPositionMode::Locked;
        R.PositionCm = Positions[I];
        R.RoomRole = I == 0
                         ? EPlayableSketchRoomRole::Start
                         : (I == 2 ? EPlayableSketchRoomRole::Goal : EPlayableSketchRoomRole::None);
        Base.Rooms.Add(R);
    }
    for (int32 I = 0; I < 4; ++I)
    {
        FPlayableSketchConnection C;
        C.ConnectionId = FGuid(100 + I, 0, 0, 1);
        C.RoomAId = Base.Rooms[I].RoomId;
        C.RoomBId = Base.Rooms[(I + 1) % 4].RoomId;
        Base.Connections.Add(C);
    }
    Base.StartRoomId = Base.Rooms[0].RoomId;
    Base.GoalRoomId = Base.Rooms[2].RoomId;

    auto ComparePlans = [&](const FPlayableSketchFloorPlan &A, const FPlayableSketchFloorPlan &B) {
        bool bSame = A.Rooms.Num() == B.Rooms.Num() && A.Corridors.Num() == B.Corridors.Num();
        for (const FPlayableSketchPlacedRoom &R : A.Rooms)
        {
            const auto *Other = B.Rooms.FindByPredicate(
                [&](const FPlayableSketchPlacedRoom &O) { return O.RoomId == R.RoomId; });
            bSame &=
                Other && R.Bounds.Min == Other->Bounds.Min && R.Bounds.Max == Other->Bounds.Max;
        }
        auto SameDoor = [](const FPlayableSketchDoorEndpoint &X,
                           const FPlayableSketchDoorEndpoint &Y) {
            return X.RoomId == Y.RoomId && X.WallSide == Y.WallSide &&
                   X.PositionCm == Y.PositionCm && X.WidthCm == Y.WidthCm;
        };
        for (const FPlayableSketchCorridor &C : A.Corridors)
        {
            const auto *Other = B.Corridors.FindByPredicate(
                [&](const FPlayableSketchCorridor &O) { return O.ConnectionId == C.ConnectionId; });
            if (!Other)
            {
                bSame = false;
                continue;
            }
            bSame &= SameDoor(C.DoorA, Other->DoorA) && SameDoor(C.DoorB, Other->DoorB) &&
                     C.Footprints.Num() == Other->Footprints.Num();
            for (int32 I = 0; I < FMath::Min(C.Footprints.Num(), Other->Footprints.Num()); ++I)
                bSame &= C.Footprints[I].Min == Other->Footprints[I].Min &&
                         C.Footprints[I].Max == Other->Footprints[I].Max;
        }
        return bSame;
    };

    for (int32 Edit = 0; Edit < 10; ++Edit)
    {
        Asset->Graph = Base;
        Local->RebuildGeometry();
        Full->RebuildGeometry();
        if (Local->GeneratedFloorPlan.Rooms.IsEmpty() || Full->GeneratedFloorPlan.Rooms.IsEmpty())
        {
            AddError(TEXT("Baseline generation failed."));
            break;
        }
        const auto Before = Local->ComponentRegistry.Capture();
        const auto BeforePointers = Local->ComponentRegistry.GetPointers();
        switch (Edit)
        {
        case 0:
            Asset->Graph.Rooms[1].RoomType = EPlayableSketchRoomType::Hub;
            break;
        case 1:
            Asset->Graph.Rooms[1].DisplayName = TEXT("Renamed Room");
            break;
        case 2:
            Asset->Graph.Rooms[0].WidthCm = 650;
            break;
        case 3:
            Asset->Graph.Rooms[1].DepthCm = 650;
            break;
        case 4:
            Asset->Graph.Rooms[3].PositionCm.X -= 50;
            break;
        case 5:
            Asset->Graph.Connections[0].DoorWidthCm = 200;
            break;
        case 6:
            Asset->Graph.Connections[0].CorridorWidthCm = 250;
            break;
        case 7:
            Asset->Graph.Connections.RemoveAt(3);
            break;
        case 8:
            Asset->Graph.Rooms.RemoveAt(3);
            Asset->Graph.Connections.SetNum(2);
            break;
        case 9:
            Asset->Graph.Rooms.Swap(0, 3);
            Asset->Graph.Connections.Swap(0, 3);
            break;
        }
        Local->RebuildLocalGeometry();
        Full->RebuildGeometry();
        const FString Label = FString::Printf(TEXT("Edit %d"), Edit + 1);
        TestTrue(Label + TEXT(" used local update"),
                 Local->LastRebuildReport.StartsWith(TEXT("Mode=Local")));
        TestFalse(Label + TEXT(" local is stale"), Local->bPreviewStale);
        TestEqual(Label + TEXT(" local source"), Local->PublishedSignature,
                  Local->GetSourceSignature());
        TestEqual(Label + TEXT(" full source"), Full->PublishedSignature,
                  Full->GetSourceSignature());
        TestTrue(Label + TEXT(" plans, doors, footprints"),
                 ComparePlans(Local->GeneratedFloorPlan, Full->GeneratedFloorPlan));
        FString Error;
        TestTrue(Label + TEXT(" local scene and collision settings"),
                 Local->ComponentRegistry.IsHealthy(*Local));
        TestTrue(Label + TEXT(" full scene and collision settings"),
                 Full->ComponentRegistry.IsHealthy(*Full));
        const auto After = Local->ComponentRegistry.Capture();
        const auto Expected = Full->ComponentRegistry.Capture();
        const auto AfterPointers = Local->ComponentRegistry.GetPointers();
        TestEqual(Label + TEXT(" piece count"), After.Num(), Expected.Num());
        for (const auto &Pair : After)
        {
            const FString *Value = Expected.Find(Pair.Key);
            TestTrue(Label + TEXT(" piece ") + Pair.Key.ToString(), Value && *Value == Pair.Value);
        }
        for (const auto &Pair : Before)
        {
            const FString *Value = After.Find(Pair.Key);
            const auto *OldPointer = BeforePointers.Find(Pair.Key);
            const auto *NewPointer = AfterPointers.Find(Pair.Key);
            if (Value && *Value == Pair.Value)
                TestTrue(Label + TEXT(" unchanged identity ") + Pair.Key.ToString(),
                         OldPointer && NewPointer && *OldPointer == *NewPointer);
            if (!Value && OldPointer)
            {
                const UStaticMeshComponent *Old = OldPointer->Get();
                TestTrue(Label + TEXT(" deleted collider removed"), !Old || !Old->IsRegistered());
            }
        }
        if (Edit == 0 || Edit == 1 || Edit == 9)
        {
            TestEqual(Label + TEXT(" no new components"), Local->LastUpdateStats.Created, 0);
            TestEqual(Label + TEXT(" no removed components"), Local->LastUpdateStats.Removed, 0);
        }
        if (Edit == 1 || Edit == 9)
            TestEqual(Label + TEXT(" no geometry updates"), Local->LastUpdateStats.Updated, 0);
    }

    Asset->Graph = Base;
    Local->RebuildGeometry();
    const auto OldPlan = Local->GeneratedFloorPlan;
    ++Asset->Graph.Seed;
    Local->RebuildLocalGeometry();
    TestTrue(TEXT("Seed change triggers documented fallback"),
             Local->LastRebuildReport.Contains(TEXT("Fallback: graph asset, seed")));
    TestTrue(TEXT("Fallback retains placement"), ComparePlans(OldPlan, Local->GeneratedFloorPlan));

    Asset->Graph = Base;
    Local->RebuildGeometry();
    FPlayableSketchFloorPlan Obstructed = Local->GeneratedFloorPlan;
    const FGuid UnrelatedId = Base.Connections[2].ConnectionId;
    const auto *Unrelated = Obstructed.Corridors.FindByPredicate(
        [&](const FPlayableSketchCorridor &C) { return C.ConnectionId == UnrelatedId; });
    if (TestNotNull(TEXT("Nonincident corridor exists"), Unrelated))
    {
        FPlayableSketchCorridorCandidate Candidate;
        Candidate.Footprints = Unrelated->Footprints;
        Obstructed.Rooms[0].Bounds =
            FPlayableSketchRect(FVector2D(650, 1400), FVector2D(1250, 2000));
        FString Error;
        TestFalse(TEXT("Unrelated corridor footprint detects moved room"),
                  FPlayableSketchCorridorRouting::ValidateCandidate(Candidate, Obstructed.Rooms, {},
                                                                    Error));
        TestTrue(TEXT("Obstruction error identifies the moved room"),
                 Error.Contains(Base.Rooms[0].RoomId.ToString()));
    }

    Local->ClearFloors();
    TestEqual(TEXT("Clear empties registry"), Local->ComponentRegistry.Capture().Num(), 0);
    TestTrue(TEXT("Clear removes generated scene components"),
             Local->ComponentRegistry.IsHealthy(*Local));
    Full->ClearFloors();
    World->DestroyWorld(false);
    return !HasAnyErrors();
}

#endif
