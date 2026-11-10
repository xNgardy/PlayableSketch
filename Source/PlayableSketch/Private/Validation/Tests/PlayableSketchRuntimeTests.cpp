#include "Runtime/PlayableSketchRuntime.h"
#include "PlayableSketchLevelActor.h"
#include "PlayableSketchNavigationTestFixtures.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Components/StaticMeshComponent.h"
#include "Kismet/GameplayStatics.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchRuntimeTests,
                                 "PlayableSketch.Runtime.AtomicReadySaveAndPlay",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)
bool FPlayableSketchRuntimeTests::RunTest(const FString &Parameters)
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
    auto *W = UWorld::CreateWorld(EWorldType::Game, false, NAME_None, nullptr, true,
                                  ERHIFeatureLevel::Num, &IV);
    if (!TestNotNull(TEXT("Runtime game world"), W))
        return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(W);
    auto *Client = W->SpawnActor<APlayableSketchRuntimeController>();
    FString Json, Error;
    FFileHelper::LoadFileToString(
        Json, *(FPaths::ProjectDir() / TEXT("Data/ground_truth/v1/Data_3.validated.json")));
    Json = PlayableSketchNavigationFixtureRoles(Json);
    TestTrue(TEXT("Initial request identity"),
             Client->IsCurrent(0, Client->ServiceUrl, Client->JobId, Client->SelectedRevision));
    Client->CancelRequest();
    TestFalse(TEXT("Cancelled response stale"),
              Client->IsCurrent(0, Client->ServiceUrl, Client->JobId, Client->SelectedRevision));
    TestTrue(TEXT("Runtime candidate becomes ready"), Client->PublishAccepted(Json, Error));
    if (!TestTrue(TEXT("Runtime ready and Pawn published"),
                  Client->bReady && Client->CurrentPawn() != nullptr))
    {
        AddError(Error);
        GEngine->DestroyWorldContext(W);
        W->DestroyWorld(false);
        return false;
    }
    TestTrue(TEXT("Runtime drawing coordinate basis enabled"),
             Client->CurrentLevel()->bUseSketchViewCoordinates);
    const FVector2D Up = Client->CurrentPawn()->ScreenMovement(FVector2D(0, 1));
    const FVector2D Right = Client->CurrentPawn()->ScreenMovement(FVector2D(1, 0));
    TestTrue(TEXT("Screen up follows image-up world direction"),
             Up.Y < -.99 && FMath::Abs(Up.X) < .01);
    TestTrue(TEXT("Screen right follows image-right world direction"),
             Right.X > .99 && FMath::Abs(Right.Y) < .01);
    TestNull(TEXT("No procedural source asset required"), Client->CurrentLevel()->GraphAsset.Get());
    TestTrue(TEXT("Runtime source transient"),
             Client->CurrentLevel()->ImportedLayoutAsset->HasAnyFlags(RF_Transient));
    const auto *Previous = Client->CurrentLevel();
    const auto *PreviousPawn = Client->CurrentPawn();
    TestFalse(TEXT("Invalid canonical fails"), Client->PublishAccepted(TEXT("{}"), Error));
    TestTrue(TEXT("Rejected import preserves ready actor and Pawn"),
             Client->CurrentLevel() == Previous && Client->CurrentPawn() == PreviousPawn &&
                 Client->bReady);
    FString GeometryOnly;
    FFileHelper::LoadFileToString(
        GeometryOnly, *(FPaths::ProjectDir() / TEXT("Data/ground_truth/v1/Data_1.validated.json")));
    TestFalse(TEXT("Geometry-only cannot masquerade as gameplay ready"),
              Client->PublishAccepted(GeometryOnly, Error));
    TestTrue(TEXT("Geometry-only rejection preserves source"), Client->CurrentJson() == Json);

    Client->PlayRoute();
    for (int32 I = 0; I < 2000 && !Client->CurrentPawn()->bReachedGoal; ++I)
        Client->CurrentPawn()->Tick(1.0f / 60);
    TestTrue(TEXT("Runtime controlled Pawn reaches Goal"), Client->CurrentPawn()->bReachedGoal);
    const auto Path = Client->CurrentLevel()->ExplicitNavigationResult.Path;
    Client->ThemeSeed = 123;
    TestTrue(TEXT("Different seed accepted with locked source"),
             Client->PublishAccepted(Json, Error));
    TestEqual(TEXT("Seed cannot change canonical geometry"), Client->CurrentJson(), Json);
    TestTrue(TEXT("Seed cannot change route"),
             Client->CurrentLevel()->ExplicitNavigationResult.Path == Path);
    Client->SavePrefix = TEXT("Step14_Test_") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
    Client->SaveRuntime();
    TestTrue(TEXT("Save first bank exists"),
             UGameplayStatics::DoesSaveGameExist(Client->SavePrefix + TEXT("_A"), 0));
    Client->ThemeSeed = 456;
    Client->PublishAccepted(Json, Error);
    Client->SaveRuntime();
    auto *Corrupt = Cast<UPlayableSketchRuntimeSave>(
        UGameplayStatics::LoadGameFromSlot(Client->SavePrefix + TEXT("_B"), 0));
    if (TestNotNull(TEXT("Second bank exists"), Corrupt))
    {
        Corrupt->ContentHash = TEXT("tampered");
        UGameplayStatics::SaveGameToSlot(Corrupt, Client->SavePrefix + TEXT("_B"), 0);
    }
    Client->LoadRuntime();
    TestEqual(TEXT("Corrupt newest bank falls back to verified first"), Client->ThemeSeed, 123);
    TestEqual(TEXT("Runtime restore retains source/revision/settings"), Client->CurrentJson(),
              Json);
    Client->SaveRuntime();
    const FString SharedPrefix = Client->SavePrefix;
    Client->CurrentPawn()->Destroy();
    Client->CurrentLevel()->Destroy();
    auto *Fresh = W->SpawnActor<APlayableSketchRuntimeController>();
    Fresh->SavePrefix = SharedPrefix;
    Fresh->ThemeSeed = 789;
    TestTrue(TEXT("Fresh session import before Load"), Fresh->PublishAccepted(Json, Error));
    Fresh->SaveRuntime();
    Fresh->LoadRuntime();
    TestEqual(TEXT("Fresh save outranks existing higher-generation banks"), Fresh->ThemeSeed, 789);

    auto *Direct = W->SpawnActorDeferred<APlayableSketchLevelActor>(
        APlayableSketchLevelActor::StaticClass(), FTransform(FVector(20000, 0, 0)));
    Direct->bGenerateOnBeginPlay = false;
    Direct->bAutoRebuildGeometry = false;
    Direct->FinishSpawning(FTransform(FVector(20000, 0, 0)));
    Direct->PawnRadiusCm = 70;
    TestTrue(TEXT("Runtime API builds valid metric geometry"),
             Direct->ImportRuntimeCanonicalJsonText(Json, Error));
    Direct->AnalyzeNavigation();
    TestFalse(TEXT("Large agent geometry is not navigation ready"),
              Direct->ExplicitNavigationResult.bReachable);
    TestEqual(TEXT("Accepted dimensions still unchanged"),
              Direct->ImportedLayoutAsset->CanonicalJson, Json);
    UGameplayStatics::DeleteGameInSlot(Client->SavePrefix + TEXT("_A"), 0);
    UGameplayStatics::DeleteGameInSlot(Client->SavePrefix + TEXT("_B"), 0);
    GEngine->DestroyWorldContext(W);
    W->DestroyWorld(false);
    return !HasAnyErrors();
}
#endif
