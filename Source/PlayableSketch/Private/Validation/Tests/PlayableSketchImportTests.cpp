#include "Import/PlayableSketchLayoutImporter.h"
#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchImportTests, "PlayableSketch.Import.LegacyJson",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchImportTests::RunTest(const FString &Parameters)
{
    FString Json, Error;
    const FString Fixture = FPaths::Combine(
        FPaths::ProjectDir(), TEXT("Data/import_examples/legacy_two_rooms.legacy-import.json"));
    if (!TestTrue(TEXT("Import fixture exists"), FFileHelper::LoadFileToString(Json, *Fixture)))
        return false;
    FPlayableSketchLegacyImport Import;
    if (!TestTrue(TEXT("Strict bridge parsing"),
                  FPlayableSketchLayoutImporter::Parse(Json, Import, Error)))
    {
        AddError(Error);
        return false;
    }
    TestEqual(TEXT("Exact off-grid room width"), Import.Graph.Rooms[0].WidthCm, 435);
    TestTrue(TEXT("Clear bounds use half-thickness inset"),
             Import.Graph.Rooms[0].PositionCm.Equals({10, 10}));
    TestTrue(TEXT("Locked positioning"),
             Import.Graph.Rooms[0].PositionMode == EPlayableSketchPositionMode::Locked);
    TestEqual(TEXT("Door offset rebased from centerline minimum"),
              Import.Graph.Connections[0].DoorASettings.OffsetCm, 290.0);
    const FGuid StableRoom = Import.Graph.Rooms[0].RoomId;
    FPlayableSketchLegacyImport Revision;
    TestTrue(
        TEXT("Another revision parses"),
        FPlayableSketchLayoutImporter::Parse(
            Json.Replace(TEXT("manual-1-accepted"), TEXT("manual-2-accepted")), Revision, Error));
    TestTrue(TEXT("Room ID stable across revision"), Revision.Graph.Rooms[0].RoomId == StableRoom);
    const FGuid StableConnection = Import.Graph.Connections[0].ConnectionId;
    TestTrue(TEXT("Connection ID stable across revision"),
             Revision.Graph.Connections[0].ConnectionId == StableConnection);

    const TArray<FString> Invalid = {
        Json.Replace(TEXT("playablesketch-legacy-import/1.0"), TEXT("playablesketch-layout/1.0")),
        Json.Replace(TEXT("\"units\": \"cm\""), TEXT("\"units\": \"px\"")),
        Json.Replace(TEXT("\"width_cm\": 435"), TEXT("\"width_cm\": 435.5")),
        Json.Replace(TEXT("\"width_cm\": 435"), TEXT("\"width_cm\": -1")),
        Json.Replace(TEXT("\"width_cm\": 435"), TEXT("\"width_cm\": true")),
        Json.Replace(TEXT("\"name\": \"Start\""), TEXT("\"name\": 123")),
        Json.Replace(TEXT("\"width_cm\": 435"), TEXT("\"width_cm\": 435, \"width_cm\": 450")),
        Json.Replace(TEXT("\"room_b_id\": \"rB\""), TEXT("\"room_b_id\": \"missing\""))};
    for (int32 I = 0; I < Invalid.Num(); ++I)
    {
        TestFalse(FString::Printf(TEXT("Invalid import %d rejected"), I),
                  FPlayableSketchLayoutImporter::Parse(Invalid[I], Revision, Error));
        TestTrue(TEXT("Parse failure retains prior output"),
                 Revision.Graph.Rooms[0].RoomId == StableRoom);
    }
    FPlayableSketchValidationSettings Settings;
    FPlayableSketchFloorPlan Plan;
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    if (!TestTrue(TEXT("Legacy geometry preflight"),
                  FPlayableSketchLayoutImporter::Prepare(Import, Settings, Plan, Pieces, Error)))
    {
        AddError(Error);
        return false;
    }
    TestTrue(TEXT("One exact straight footprint"),
             Plan.Corridors.Num() == 1 && Plan.Corridors[0].Footprints.Num() == 1 &&
                 Plan.Corridors[0].Footprints[0].Min.Equals({445, 200}) &&
                 Plan.Corridors[0].Footprints[0].Max.Equals({1065, 400}));
    TestFalse(TEXT("Walls generated"), Pieces.IsEmpty());
    auto BadRoute = Import;
    BadRoute.ExpectedCorridor.Max.X += 50;
    TestFalse(TEXT("Changed corridor cannot be silently accepted"),
              FPlayableSketchLayoutImporter::Prepare(BadRoute, Settings, Plan, Pieces, Error));
    TestTrue(TEXT("Prepare failure retains prior output"),
             Plan.Corridors[0].Footprints[0].Max.Equals({1065, 400}));

    auto Vertical = Import;
    for (auto &Room : Vertical.Graph.Rooms)
    {
        Room.PositionCm = FVector2D(-Room.PositionCm.Y - Room.DepthCm, Room.PositionCm.X);
        Swap(Room.WidthCm, Room.DepthCm);
    }
    Vertical.Graph.Connections[0].DoorASettings.WallSide = EPlayableSketchWallSide::North;
    Vertical.Graph.Connections[0].DoorBSettings.WallSide = EPlayableSketchWallSide::South;
    Vertical.ExpectedCorridor = FPlayableSketchRect({-400, 445}, {-200, 1065});
    FPlayableSketchFloorPlan VerticalPlan;
    TArray<FPlayableSketchGeometryDescriptor> VerticalPieces;
    TestTrue(TEXT("Vertical corridor preflight"),
             FPlayableSketchLayoutImporter::Prepare(Vertical, Settings, VerticalPlan,
                                                    VerticalPieces, Error));

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
    UWorld *World = UWorld::CreateWorld(EWorldType::Editor, false, NAME_None, nullptr, true,
                                        ERHIFeatureLevel::Num, &IV);
    if (!TestNotNull(TEXT("Editor test world"), World))
        return false;
    auto *Actor = World->SpawnActor<APlayableSketchLevelActor>();
    if (!Actor)
    {
        World->DestroyWorld(false);
        return false;
    }
    Actor->bAutoRebuildGeometry = false;
    Actor->GraphAsset = NewObject<UPlayableSketchGraphAsset>(Actor);
    auto *AssignedAsset = Actor->GraphAsset.Get();
    if (TestTrue(TEXT("Actor import publishes geometry"), Actor->ImportLayoutJsonText(Json, Error)))
    {
        TestTrue(TEXT("Assigned asset retained"), Actor->GraphAsset.Get() == AssignedAsset);
        TestEqual(TEXT("Persisted imported width"), AssignedAsset->Graph.Rooms[0].WidthCm, 435);
        TestEqual(TEXT("Saved placements"), AssignedAsset->SavedLayout.Rooms.Num(), 2);
        TestEqual(TEXT("Import provenance persisted"), AssignedAsset->ImportDocumentId,
                  Import.DocumentId);
        TestFalse(TEXT("Imported preview current"), Actor->bPreviewStale);
        TArray<UStaticMeshComponent *> Before;
        Actor->GetComponents<UStaticMeshComponent>(Before);
        TestTrue(TEXT("Actual preview components"), Before.Num() > 0);
        TestTrue(TEXT("Repeat import"), Actor->ImportLayoutJsonText(Json, Error));
        TArray<UStaticMeshComponent *> After;
        Actor->GetComponents<UStaticMeshComponent>(After);
        TestEqual(TEXT("No duplicate components after reimport"), After.Num(), Before.Num());
        const FString Source = AssignedAsset->GetSourceText();
        TestFalse(TEXT("Invalid import rejected without clearing preview"),
                  Actor->ImportLayoutJsonText(Invalid[0], Error));
        TArray<UStaticMeshComponent *> Retained;
        Actor->GetComponents<UStaticMeshComponent>(Retained);
        TestEqual(TEXT("Rejected import preserves asset"), AssignedAsset->GetSourceText(), Source);
        TestEqual(TEXT("Rejected import preserves component count"), Retained.Num(), After.Num());
        for (int32 I = 0; I < After.Num(); ++I)
            TestTrue(TEXT("Rejected import preserves component identity"),
                     Retained.Contains(After[I]));
        Actor->RebuildGeometry();
        TestEqual(TEXT("Rebuild does not ceil 435 to grid"), AssignedAsset->Graph.Rooms[0].WidthCm,
                  435);
        TestTrue(TEXT("Rebuild completed"), Actor->LastRebuildReport.StartsWith(TEXT("Mode=Full")));
    }
    else
        AddError(Error);
    World->DestroyWorld(false);
    return true;
}

#endif
