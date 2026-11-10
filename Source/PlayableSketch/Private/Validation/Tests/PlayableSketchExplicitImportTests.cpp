#include "ExplicitLayout/PlayableSketchExplicitLayout.h"
#include "Algo/Reverse.h"
#include "PlayableSketchLevelActor.h"
#include "PlayableSketchNavigationTestFixtures.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/ObjectAndNameAsStringProxyArchive.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchExplicitImportTests,
                                 "PlayableSketch.Import.CanonicalExplicit",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchExplicitImportTests::RunTest(const FString &Parameters)
{
    auto Load = [&](int32 Index, const TCHAR *Kind = TEXT("validated")) {
        FString Json;
        TestTrue(TEXT("Reference exists"),
                 FFileHelper::LoadFileToString(
                     Json, *(FPaths::ProjectDir() /
                             FString::Printf(TEXT("Data/ground_truth/v1/Data_%d.%s.json"), Index,
                                             Kind))));
        return Json;
    };
    auto Modify = [](const FString &Json,
                     TFunctionRef<void(const TSharedPtr<FJsonObject> &)> Edit) {
        TSharedPtr<FJsonObject> Root;
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root);
        Edit(Root);
        FString Result;
        FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Result));
        return Result;
    };
    TArray<FString> Sources;
    for (int32 I = 1; I <= 8; ++I)
    {
        Sources.Add(Load(I));
        FPlayableSketchExplicitLayout L;
        FPlayableSketchExplicitGeometry G;
        FString Error;
        if (!TestTrue(FString::Printf(TEXT("Data_%d parses"), I),
                      FPlayableSketchExplicitLayoutBuilder::Parse(Sources.Last(), L, Error)))
        {
            AddError(Error);
            return false;
        }
        if (I == 5)
        {
            TestFalse(
                TEXT(
                    "Data_5 edge 450 plus width 150 reaches a junction; physical opening must be rejected"),
                FPlayableSketchExplicitLayoutBuilder::Build(L, G, Error));
            TestTrue(TEXT("Data_5 reports blocked clear opening"),
                     Error.StartsWith(TEXT("SKETCH_OPENING_BLOCKED")));
            continue;
        }
        if (!TestTrue(FString::Printf(TEXT("Data_%d builds without closing openings"), I),
                      FPlayableSketchExplicitLayoutBuilder::Build(L, G, Error)))
        {
            AddError(Error);
            return false;
        }
        TSet<FGuid> WallOwners;
        int32 Floors = 0, Lintels = 0;
        for (const auto &Spec : G.Specs)
        {
            TestTrue(TEXT("Positive geometry sizes"), Spec.SizeCm.GetMin() > 0);
            if (Spec.Kind == EPlayableSketchPieceKind::Floor)
            {
                ++Floors;
                TestEqual(TEXT("Floor top at ground plane"), Spec.CenterCm.Z + Spec.SizeCm.Z / 2,
                          0.0);
            }
            else
            {
                TestTrue(TEXT("Canonical wall owns solids"), Spec.OwnerKind == TEXT("Wall"));
                WallOwners.Add(Spec.SourceId);
                if (Spec.Kind == EPlayableSketchPieceKind::Lintel)
                    ++Lintels;
            }
        }
        TestEqual(TEXT("Unique shared-wall ownership"), WallOwners.Num(), L.Walls.Num());
        TestEqual(TEXT("One floor per declared region, no invented corridors"), Floors,
                  L.Regions.Num());
        int32 Doors = 0;
        for (const auto &O : L.Openings)
            if (O.Type == TEXT("door"))
                ++Doors;
        TestEqual(TEXT("Open passages have no lintel"), Lintels, Doors);
        if (I == 1)
        {
            TestEqual(TEXT("Single-room geometry-only"), G.FloorPlan.Rooms.Num(), 1);
            TestTrue(TEXT("No fake connection"), G.FloorPlan.Corridors.IsEmpty());
            TestTrue(TEXT("600 x 400 centerline floor"),
                     G.FloorPlan.Rooms[0].Bounds.Max.Equals({600, 400}));
        }
        if (I == 8)
        {
            const auto *Door =
                L.Openings.FindByPredicate([](const auto &O) { return O.Type == TEXT("door"); });
            TestNotNull(TEXT("Data_8 door"), Door);
            if (Door)
            {
                TestEqual(
                    TEXT(
                        "Paper edge offset 300 and clear width 120 rebase to wall-local center 100"),
                    Door->CenterOffsetCm, 100.0);
                const auto *W =
                    L.Walls.FindByPredicate([&](const auto &V) { return V.Id == Door->WallId; });
                const auto *A = L.Vertices.FindByPredicate(
                    [&](const auto &V) { return V.Id == W->StartVertexId; });
                TestEqual(TEXT("Door world center y=360"), A->PositionCm.Y + Door->CenterOffsetCm,
                          360.0);
            }
        }

        const FString Reordered = Modify(Sources.Last(), [](const auto &Root) {
            const auto Data = Root->GetObjectField(TEXT("layout"));
            for (const TCHAR *Key :
                 {TEXT("vertices"), TEXT("walls"), TEXT("rooms"), TEXT("corridors"),
                  TEXT("openings"), TEXT("passages"), TEXT("dimensions")})
            {
                auto A = Data->GetArrayField(Key);
                Algo::Reverse(A);
                Data->SetArrayField(Key, A);
            }
            Root->SetStringField(TEXT("revision_id"), TEXT("another-revision"));
        });
        FPlayableSketchExplicitLayout Other;
        FPlayableSketchExplicitGeometry OtherG;
        TestTrue(TEXT("Reordered canonical layout parses"),
                 FPlayableSketchExplicitLayoutBuilder::Parse(Reordered, Other, Error));
        TestTrue(TEXT("Reordered layout builds"),
                 FPlayableSketchExplicitLayoutBuilder::Build(Other, OtherG, Error));
        TestEqual(TEXT("Array order independent pieces"), OtherG.Specs.Num(), G.Specs.Num());
        for (int32 J = 0; J < FMath::Min(G.Specs.Num(), OtherG.Specs.Num()); ++J)
            TestTrue(TEXT("Stable keys/values across ordering and revision"),
                     G.Specs[J].SameValue(OtherG.Specs[J]));
    }
    FString Error;
    FPlayableSketchExplicitLayout L;
    TestTrue(TEXT("Keep a known valid output"),
             FPlayableSketchExplicitLayoutBuilder::Parse(Sources[2], L, Error));
    const FString KnownId = L.DocumentId;
    TArray<FString> Invalid = {
        Load(9, TEXT("draft")), Load(10, TEXT("draft")),
        TEXT("{\"kind\":\"validated_layout\",\"kind\":\"validated_layout\"}"),
        Sources[2].Replace(TEXT("\"units\": \"cm\""), TEXT("\"units\": \"px\""))};
    Invalid.Add(
        Modify(Sources[2], [](const auto &R) { R->SetBoolField(TEXT("unexpected"), true); }));
    Invalid.Add(
        Modify(Sources[2], [](const auto &R) { R->SetStringField(TEXT("units"), TEXT("CM")); }));
    Invalid.Add(Sources[2].Replace(TEXT("\"units\":"), TEXT("\"Units\":")));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("walls"))[0]
            ->AsObject()
            ->SetStringField(TEXT("start_vertex_id"), TEXT("V001"));
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("walls"))[0]
            ->AsObject()
            ->SetStringField(TEXT("start_vertex_id"), TEXT("missing"));
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("dimensions"))[0]
            ->AsObject()
            ->SetNumberField(TEXT("value_cm"), 450);
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("openings"))[0]
            ->AsObject()
            ->SetNumberField(TEXT("clear_width_cm"), 9999);
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("settings"))->SetBoolField(TEXT("wall_height_cm"), true);
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("vertices"))[0]
            ->AsObject()
            ->SetStringField(TEXT("state"), TEXT("inferred"));
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        auto W = R->GetObjectField(TEXT("layout"))->GetArrayField(TEXT("walls"))[0]->AsObject();
        const auto A = W->GetStringField(TEXT("start_vertex_id"));
        W->SetStringField(TEXT("start_vertex_id"), W->GetStringField(TEXT("end_vertex_id")));
        W->SetStringField(TEXT("end_vertex_id"), A);
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))->SetArrayField(TEXT("passages"), {});
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        R->GetObjectField(TEXT("layout"))
            ->GetArrayField(TEXT("walls"))[1]
            ->AsObject()
            ->SetArrayField(TEXT("region_ids"), {MakeShared<FJsonValueString>(TEXT("rA"))});
    }));
    Invalid.Add(Modify(Sources[2], [](const auto &R) {
        auto Data = R->GetObjectField(TEXT("layout"));
        auto A = Data->GetArrayField(TEXT("openings"));
        TSharedPtr<FJsonObject> Copy;
        FString Text;
        FJsonSerializer::Serialize(A[0]->AsObject().ToSharedRef(),
                                   TJsonWriterFactory<>::Create(&Text));
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Copy);
        Copy->SetStringField(TEXT("id"), TEXT("overlapping"));
        A.Add(MakeShared<FJsonValueObject>(Copy));
        Data->SetArrayField(TEXT("openings"), A);
    }));
    for (const auto &Json : Invalid)
    {
        TestFalse(TEXT("Invalid/unaccepted canonical rejected"),
                  FPlayableSketchExplicitLayoutBuilder::Parse(Json, L, Error));
        TestEqual(TEXT("Parse failure retains previous output"), L.DocumentId, KnownId);
        TestFalse(TEXT("Readable rejection reason"), Error.IsEmpty());
    }

    TestTrue(TEXT("Parse door reference"),
             FPlayableSketchExplicitLayoutBuilder::Parse(Sources[2], L, Error));
    L.Openings[0].ClearWidthCm = 60;
    L.Openings[0].CenterOffsetCm = 100;
    auto Second = L.Openings[0];
    Second.Id = TEXT("secondDoor");
    Second.CenterOffsetCm = 300;
    L.Openings.Add(Second);
    FPlayableSketchExplicitGeometry TwoDoors;
    TestTrue(TEXT("Multiple independent openings"),
             FPlayableSketchExplicitLayoutBuilder::Build(L, TwoDoors, Error));
    L.Openings[0].Id = TEXT("doorA");
    L.Openings[1].Id = TEXT("doora");
    TestTrue(TEXT("Case-sensitive opening IDs build"),
             FPlayableSketchExplicitLayoutBuilder::Build(L, TwoDoors, Error));
    TSet<FName> Keys;
    for (const auto &Spec : TwoDoors.Specs)
        Keys.Add(Spec.Key);
    TestEqual(TEXT("Opening IDs cannot collide through case-insensitive component keys"),
              Keys.Num(), TwoDoors.Specs.Num());
    L.Openings[0].CenterOffsetCm = 30;
    TestFalse(TEXT("Junction cap cannot block claimed clear opening"),
              FPlayableSketchExplicitLayoutBuilder::Build(L, TwoDoors, Error));
    TestTrue(TEXT("Physical opening error is explicit"),
             Error.StartsWith(TEXT("SKETCH_OPENING_BLOCKED")));
    FPlayableSketchExplicitLayout Tiny;
    TestTrue(TEXT("Parse single-room source"),
             FPlayableSketchExplicitLayoutBuilder::Parse(Sources[0], Tiny, Error));
    Tiny.Settings.WallHeightCm = 0.0005;
    Tiny.Settings.DoorHeightCm = 0.00025;
    TestFalse(TEXT("Sub-tolerance settings cannot silently erase wall solids"),
              FPlayableSketchExplicitLayoutBuilder::Build(Tiny, TwoDoors, Error));
    TestTrue(TEXT("Parse corridor reference"),
             FPlayableSketchExplicitLayoutBuilder::Parse(Sources[5], L, Error));
    auto Settings = L.Settings;
    Settings.WallThicknessCm = 30;
    Settings.WallHeightCm = 350;
    Settings.DoorHeightCm = 240;
    Settings.FloorThicknessCm = 25;
    FString Updated;
    FPlayableSketchExplicitLayout Resolved;
    TestFalse(
        TEXT(
            "Changing a clear entrance width cannot silently change a confirmed paper edge offset"),
        FPlayableSketchExplicitLayoutBuilder::ResolveSettings(Sources[5], Settings, Updated,
                                                              Resolved, Error));
    TestTrue(TEXT("Edge-offset settings conflict is explicit"),
             Error.StartsWith(TEXT("SKETCH_DIMENSION_CONFLICT")));
    Settings.WallThicknessCm = 20;
    TestTrue(TEXT("Configured height settings create valid revision"),
             FPlayableSketchExplicitLayoutBuilder::ResolveSettings(Sources[5], Settings, Updated,
                                                                   Resolved, Error));
    TestTrue(TEXT("Settings revision differs"), Resolved.RevisionId != L.RevisionId);
    TestEqual(TEXT("Centerlines retained"), Resolved.Vertices[0].PositionCm,
              L.Vertices[0].PositionCm);
    for (const auto &O : Resolved.Openings)
    {
        TestEqual(TEXT("Clear entrance retained with unchanged thickness"), O.ClearWidthCm, 180.0);
        TestEqual(TEXT("Open passage stays full height"), O.ClearHeightCm, 350.0);
    }
    TestTrue(TEXT("Resolved geometry remains open"),
             FPlayableSketchExplicitLayoutBuilder::Build(Resolved, TwoDoors, Error));
    Settings.DoorHeightCm = 400;
    TestFalse(TEXT("Invalid settings refused"),
              FPlayableSketchExplicitLayoutBuilder::ResolveSettings(Sources[5], Settings, Updated,
                                                                    Resolved, Error));

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
    Actor->ImportedLayoutAsset = NewObject<UPlayableSketchImportedLayoutAsset>(Actor);
    for (int32 I = 0; I < Sources.Num(); ++I)
    {
        if (I == 4)
            TestFalse(TEXT("Actor rejects Data_5 physical junction conflict"),
                      Actor->ImportCanonicalLayoutJsonText(Sources[I], Error));
        else if (!TestTrue(TEXT("Actor imports physically valid photo-reference layouts"),
                           Actor->ImportCanonicalLayoutJsonText(Sources[I], Error)))
            AddError(Error);
    }
    FPlayableSketchExplicitLayout Physical;
    if (FPlayableSketchExplicitLayoutBuilder::Parse(Sources[7], Physical, Error))
    {
        const auto *Door =
            Physical.Openings.FindByPredicate([](const auto &O) { return O.Type == TEXT("door"); });
        const auto *W =
            Physical.Walls.FindByPredicate([&](const auto &V) { return V.Id == Door->WallId; });
        const auto *A = Physical.Vertices.FindByPredicate(
            [&](const auto &V) { return V.Id == W->StartVertexId; });
        FVector2D Center = A->PositionCm;
        Center[W->Axis] += Door->CenterOffsetCm;
        const FVector Normal = W->Axis == 0 ? FVector(0, 50, 0) : FVector(50, 0, 0);
        FVector Point(Center.X, Center.Y, 100);
        TestFalse(TEXT("Actual collision leaves the door opening clear"),
                  World->LineTraceTestByChannel(Point - Normal, Point + Normal, ECC_Visibility));
        Point.Z = Door->ClearHeightCm + 10;
        TestTrue(TEXT("Actual lintel collision exists above the door"),
                 World->LineTraceTestByChannel(Point - Normal, Point + Normal, ECC_Visibility));
        Point.Z = 100;
        Point[W->Axis] += Door->ClearWidthCm / 2 + 10;
        TestTrue(TEXT("Actual jamb collision exists beside the door"),
                 World->LineTraceTestByChannel(Point - Normal, Point + Normal, ECC_Visibility));
    }
    TestTrue(TEXT("Explicit source persisted on actor"),
             Actor->LayoutSource == EPlayableSketchLayoutSource::ImportedExplicitLayout);
    TestNull(TEXT("No legacy GraphAsset required"), Actor->GraphAsset.Get());
    auto *Asset = Actor->ImportedLayoutAsset.Get();
    const FString Stored = Asset->CanonicalJson;
    const auto Before = Actor->ComponentRegistry.Capture();
    const auto Pointers = Actor->ComponentRegistry.GetPointers();
    TestTrue(TEXT("Same revision reimport"), Actor->ImportCanonicalLayoutJsonText(Stored, Error));
    const auto After = Actor->ComponentRegistry.GetPointers();
    TestEqual(TEXT("No duplicate components"), After.Num(), Pointers.Num());
    for (const auto &Pair : Pointers)
        TestTrue(TEXT("No-op reimport retains components"),
                 After.FindChecked(Pair.Key) == Pair.Value);
    TestFalse(TEXT("Rejected import leaves accepted layout intact"),
              Actor->ImportCanonicalLayoutJsonText(Invalid[2], Error));
    TestEqual(TEXT("Accepted source retained"), Asset->CanonicalJson, Stored);
    TestEqual(TEXT("Preview count retained"), Actor->ComponentRegistry.Capture().Num(),
              Before.Num());
    Actor->RebuildLocalGeometry();
    const auto Local = Actor->ComponentRegistry.Capture();
    Actor->RebuildGeometry();
    const auto Full = Actor->ComponentRegistry.Capture();
    TestEqual(TEXT("Local/Full piece counts"), Full.Num(), Local.Num());
    for (const auto &Pair : Local)
        TestEqual(TEXT("Local/Full scene equivalence"), Full.FindChecked(Pair.Key), Pair.Value);
    const auto BeforeSettings = Actor->ComponentRegistry.GetPointers();
    auto *SharedActor = World->SpawnActor<APlayableSketchLevelActor>();
    SharedActor->bAutoRebuildGeometry = false;
    SharedActor->ImportedLayoutAsset = Asset;
    SharedActor->LayoutSource = EPlayableSketchLayoutSource::ImportedExplicitLayout;
    SharedActor->RebuildGeometry();
    Actor->WallThicknessCm = 20;
    Actor->WallHeightCm = 350;
    Actor->RebuildLocalGeometry();
    TestFalse(TEXT("Changed settings publish"), Actor->bPreviewStale);
    TestTrue(TEXT("Resolved source persisted"),
             FPlayableSketchExplicitLayoutBuilder::Parse(Asset->CanonicalJson, Resolved, Error));
    TestEqual(TEXT("Persisted wall thickness"), Resolved.Settings.WallThicknessCm, 20.0);
    const FString SharedSource = Asset->CanonicalJson;
    SharedActor->RebuildLocalGeometry();
    TestEqual(TEXT("Shared asset changes update other actors"), SharedActor->WallThicknessCm,
              20.0f);
    TestEqual(TEXT("Stale actor settings do not overwrite a shared revision"), Asset->CanonicalJson,
              SharedSource);
    TestEqual(TEXT("Confirmed door width retained"), Resolved.Openings[0].ClearWidthCm, 120.0);
    TestEqual(TEXT("Wall-local offset retained"), Resolved.Openings[0].CenterOffsetCm, 100.0);
    const auto ChangedPointers = Actor->ComponentRegistry.GetPointers();
    int32 KeptFloors = 0;
    for (const auto &Pair : ChangedPointers)
        if (Pair.Key.ToString().EndsWith(TEXT("/Floor")) &&
            BeforeSettings.FindChecked(Pair.Key) == Pair.Value)
            ++KeptFloors;
    TestEqual(TEXT("Settings do not invent regions"), KeptFloors, 3);
    const FString GoodJson = Asset->CanonicalJson;
    const auto BeforeDoorEdit = Actor->ComponentRegistry.GetPointers();
    const FString DoorEdit = Modify(GoodJson, [](const auto &Root) {
        Root->SetStringField(TEXT("revision_id"), TEXT("door-width-correction"));
        const auto Data = Root->GetObjectField(TEXT("layout"));
        for (const auto &V : Data->GetArrayField(TEXT("openings")))
            if (V->AsObject()->GetStringField(TEXT("id")) == TEXT("d0"))
            {
                const auto O = V->AsObject();
                O->SetNumberField(TEXT("clear_width_cm"), 100);
                O->SetNumberField(TEXT("center_offset_cm"), 90);
            }
        for (const auto &V : Data->GetArrayField(TEXT("dimensions")))
        {
            const auto D = V->AsObject(), T = D->GetObjectField(TEXT("target"));
            if (T->GetStringField(TEXT("type")) == TEXT("opening_width") &&
                T->GetStringField(TEXT("opening_id")) == TEXT("d0"))
                D->SetNumberField(TEXT("value_cm"), 100);
        }
    });
    TestTrue(TEXT("Single opening correction imports"),
             Actor->ImportCanonicalLayoutJsonText(DoorEdit, Error));
    TestEqual(TEXT("Opening edit dirties one canonical wall"),
              Actor->LastUpdateStats.DirtyWalls.Num(), 1);
    TestEqual(
        TEXT("Opening edit leaves floors unchanged"),
        Actor->LastUpdateStats.DirtyRooms.Num() + Actor->LastUpdateStats.DirtyConnections.Num(), 0);
    const auto AfterDoorEdit = Actor->ComponentRegistry.GetPointers();
    for (const auto &Pair : BeforeDoorEdit)
        TestTrue(TEXT("Stable semantic keys allow in-place opening update"),
                 AfterDoorEdit.FindChecked(Pair.Key) == Pair.Value);
    TestTrue(TEXT("Restore accepted reference after correction test"),
             Actor->ImportCanonicalLayoutJsonText(GoodJson, Error));
    const auto BeforeInvalid = Actor->ComponentRegistry.GetPointers();
    Actor->WallHeightCm = -1;
    Actor->RebuildLocalGeometry();
    TestTrue(TEXT("Invalid rebuild marks old preview stale"), Actor->bPreviewStale);
    TestEqual(TEXT("Invalid settings retain asset"), Asset->CanonicalJson, GoodJson);
    const auto Retained = Actor->ComponentRegistry.GetPointers();
    for (const auto &Pair : BeforeInvalid)
        TestTrue(TEXT("Invalid rebuild retains scene identity"),
                 Retained.FindChecked(Pair.Key) == Pair.Value);
    Actor->WallHeightCm = 350;
    Actor->RebuildGeometry();
    Actor->GenerateLayout();
    TestTrue(TEXT("Generate Layout also preserves explicit source"),
             Actor->LayoutSource == EPlayableSketchLayoutSource::ImportedExplicitLayout);
    TestEqual(TEXT("Generate Layout cannot reroute source"), Asset->CanonicalJson, GoodJson);
    Actor->AnalyzeNavigation();
    TestFalse(TEXT("Explicit geometry not reported as agent-certified"), Actor->bNavigationCurrent);

    TArray<uint8> AssetBytes;
    FMemoryWriter AssetWriter(AssetBytes);
    FObjectAndNameAsStringProxyArchive SaveAsset(AssetWriter, false);
    Asset->Serialize(SaveAsset);
    auto *ReloadedAsset = NewObject<UPlayableSketchImportedLayoutAsset>(Actor);
    FMemoryReader AssetReader(AssetBytes);
    FObjectAndNameAsStringProxyArchive LoadAsset(AssetReader, true);
    ReloadedAsset->Serialize(LoadAsset);
    TestEqual(TEXT("Canonical source survives serialization"), ReloadedAsset->CanonicalJson,
              Asset->CanonicalJson);
    auto *ReloadedActor = World->SpawnActor<APlayableSketchLevelActor>();
    ReloadedActor->bAutoRebuildGeometry = false;
    ReloadedActor->ImportedLayoutAsset = ReloadedAsset;
    ReloadedActor->LayoutSource = EPlayableSketchLayoutSource::ImportedExplicitLayout;
    ReloadedActor->RebuildGeometry();
    TestFalse(TEXT("Fresh actor reconstructs persisted explicit geometry"),
              ReloadedActor->bPreviewStale);
    TestEqual(TEXT("Asset settings restored on fresh actor"), ReloadedActor->WallThicknessCm,
              20.0f);
    TestEqual(TEXT("Reload does not rewrite accepted source"), ReloadedAsset->CanonicalJson,
              GoodJson);
    const auto Reloaded = ReloadedActor->ComponentRegistry.Capture(),
               Published = Actor->ComponentRegistry.Capture();
    TestEqual(TEXT("Reloaded piece counts"), Reloaded.Num(), Published.Num());
    for (const auto &Pair : Published)
        TestEqual(TEXT("Reloaded geometry equivalent"), Reloaded.FindChecked(Pair.Key), Pair.Value);
    UWorld *GameWorld = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true,
                                            ERHIFeatureLevel::Num, &IV);
    if (TestNotNull(TEXT("BeginPlay test world"), GameWorld))
    {
        GEngine->CreateNewWorldContext(GameWorld->WorldType).SetCurrentWorld(GameWorld);
        auto *RuntimeActor = GameWorld->SpawnActor<APlayableSketchLevelActor>();
        if (TestNotNull(TEXT("Runtime explicit actor"), RuntimeActor))
        {
            RuntimeActor->bAutoRebuildGeometry = false;
            auto *RuntimeAsset = NewObject<UPlayableSketchImportedLayoutAsset>(RuntimeActor);
            RuntimeAsset->CanonicalJson =
                PlayableSketchNavigationFixtureRoles(ReloadedAsset->CanonicalJson);
            RuntimeActor->ImportedLayoutAsset = RuntimeAsset;
            RuntimeActor->LayoutSource = EPlayableSketchLayoutSource::ImportedExplicitLayout;
            RuntimeActor->DispatchBeginPlay();
            RuntimeActor->VerifyExplicitPawnTraversal();
            TestEqual(TEXT("BeginPlay actual Pawn crosses door and corridor"),
                      RuntimeActor->ExplicitNavigationResult.Pawn, FString(TEXT("passed")));
            TestTrue(TEXT("BeginPlay ran"), RuntimeActor->HasActorBegunPlay());
            TestTrue(TEXT("BeginPlay rebuilds explicit source"),
                     RuntimeActor->ComponentRegistry.IsHealthy(*RuntimeActor));
            TestEqual(TEXT("BeginPlay preserves region count"),
                      RuntimeActor->GeneratedFloorPlan.Rooms.Num(), 2);
            TestEqual(TEXT("Runtime does not rewrite source asset"), ReloadedAsset->CanonicalJson,
                      GoodJson);
            TestNull(TEXT("BeginPlay does not need legacy graph"), RuntimeActor->GraphAsset.Get());
        }
        GEngine->DestroyWorldContext(GameWorld);
        GameWorld->DestroyWorld(false);
    }
    World->DestroyWorld(false);
    return true;
}
#endif
