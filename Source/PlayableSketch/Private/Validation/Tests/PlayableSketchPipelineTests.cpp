#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchPipelineGuards,
                                 "PlayableSketch.Pipeline.RequestGuards",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchPipelineGuards::RunTest(const FString &Parameters)
{
    TestTrue(TEXT("Loopback accepted"),
             APlayableSketchLevelActor::IsLocalPipelineUrl(TEXT("http://127.0.0.1:8768")));
    TestTrue(TEXT("localhost accepted"),
             APlayableSketchLevelActor::IsLocalPipelineUrl(TEXT("http://localhost:8768")));
    for (const FString Url : {TEXT("http://example.com:8768"), TEXT("http://localhost:0"),
                              TEXT("http://localhost:65536"), TEXT("http://localhost:8768/path"),
                              TEXT("http://localhost:8768@evil.com")})
        TestFalse(TEXT("Non-loopback/invalid URL rejected"),
                  APlayableSketchLevelActor::IsLocalPipelineUrl(Url));
    TestTrue(TEXT("Job ID accepted"),
             APlayableSketchLevelActor::IsPipelineJobId(TEXT("Job_20261021T120000Z_123456789a")));
    TestFalse(TEXT("Path injection rejected"),
              APlayableSketchLevelActor::IsPipelineJobId(TEXT("../Data_1")));
    UWorld *GuardWorld = UWorld::CreateWorld(EWorldType::Editor, false);
    if (!TestNotNull(TEXT("Guard world"), GuardWorld))
        return false;
    auto *Actor = GuardWorld->SpawnActor<APlayableSketchLevelActor>();
    if (!Actor)
    {
        GuardWorld->DestroyWorld(false);
        return false;
    }
    TestTrue(TEXT("Matching initial token"),
             Actor->IsPipelineRequestCurrent(0, Actor->PipelineServiceUrl, Actor->PipelineJobId,
                                             Actor->PipelineAcceptedRevisionId));
    TestFalse(TEXT("Stale sequence"),
              Actor->IsPipelineRequestCurrent(1, Actor->PipelineServiceUrl, Actor->PipelineJobId,
                                              Actor->PipelineAcceptedRevisionId));
    TestFalse(TEXT("Stale job"),
              Actor->IsPipelineRequestCurrent(0, Actor->PipelineServiceUrl, TEXT("different"),
                                              Actor->PipelineAcceptedRevisionId));
    TestFalse(TEXT("Stale selected revision"),
              Actor->IsPipelineRequestCurrent(0, Actor->PipelineServiceUrl, Actor->PipelineJobId,
                                              TEXT("different")));
    GuardWorld->DestroyWorld(false);
    return true;
}

namespace
{
class FPipelineLiveImport : public IAutomationLatentCommand
{
  public:
    FPipelineLiveImport(FAutomationTestBase *InTest, UWorld *InWorld,
                        APlayableSketchLevelActor *InActor, FString InRevision)
        : Test(InTest), World(InWorld), Actor(InActor), Revision(MoveTemp(InRevision)),
          Start(FPlatformTime::Seconds())
    {
    }
    virtual bool Update() override
    {
        if (!Actor.IsValid() || FPlatformTime::Seconds() - Start > 45)
        {
            Test->AddError(TEXT("Live pipeline import timed out or actor was destroyed."));
            Cleanup();
            return true;
        }
        auto *A = Actor.Get();
        if (Phase == 0)
        {
            if (A->LastPipelineStatus.StartsWith(TEXT("Checking")))
                return false;
            if (!Test->TestEqual(TEXT("Status selected the accepted metric revision"),
                                 A->PipelineAcceptedRevisionId, Revision))
            {
                Cleanup();
                return true;
            }
            A->ImportPipelineAcceptedLayout();
            Phase = 1;
            return false;
        }
        if (A->LastPipelineStatus.StartsWith(TEXT("Fetching")))
            return false;
        TArray<UStaticMeshComponent *> Components;
        A->GetComponents(Components);
        if (Phase == 1)
        {
            if (!Test->TestTrue(TEXT("Accepted HTTP snapshot imported through canonical builder"),
                                A->LastPipelineStatus.StartsWith(TEXT("Imported selected"))))
            {
                Test->AddError(A->LastPipelineStatus);
                Cleanup();
                return true;
            }
            Test->TestTrue(TEXT("Explicit geometry components published"), Components.Num() > 0);
            Canonical = A->ImportedLayoutAsset->CanonicalJson;
            Count = Components.Num();
            A->ImportPipelineAcceptedLayout();
            Phase = 2;
            return false;
        }
        if (Phase == 2)
        {
            Test->TestTrue(TEXT("Repeat import succeeds"),
                           A->LastPipelineStatus.StartsWith(TEXT("Imported selected")));
            Test->TestEqual(TEXT("Repeated request does not accumulate components"),
                            Components.Num(), Count);
            A->PipelineAcceptedRevisionId = TEXT("metric-20000101T000000Z-123456789abc");
            A->ImportPipelineAcceptedLayout();
            Phase = 3;
            return false;
        }
        Test->TestTrue(TEXT("Nonselected/stale revision rejected by service"),
                       A->LastPipelineStatus.StartsWith(TEXT("Import rejected")));
        Test->TestEqual(TEXT("Rejected request preserves accepted asset"),
                        A->ImportedLayoutAsset->CanonicalJson, Canonical);
        Test->TestEqual(TEXT("Rejected request preserves components"), Components.Num(), Count);
        Cleanup();
        return true;
    }

  private:
    void Cleanup()
    {
        if (World)
        {
            World->DestroyWorld(false);
            World = nullptr;
        }
    }
    FAutomationTestBase *Test;
    UWorld *World;
    TWeakObjectPtr<APlayableSketchLevelActor> Actor;
    FString Revision, Canonical;
    double Start;
    int32 Phase = 0, Count = 0;
};
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchPipelineLive,
                                 "PlayableSketch.Pipeline.LocalJobImport",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchPipelineLive::RunTest(const FString &Parameters)
{
    FString Text;
    TSharedPtr<FJsonObject> Fixture;
    if (!FFileHelper::LoadFileToString(
            Text, *(FPaths::ProjectDir() / TEXT("Saved/Step11/e2e/service.json"))) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Fixture) || !Fixture)
    {
        AddError(TEXT(
            "Prepare the controlled local job fixture and running service in Saved/Step11/e2e/service.json first."));
        return false;
    }
    FString Service, Job, Revision;
    if (!Fixture->TryGetStringField(TEXT("service_url"), Service) ||
        !Fixture->TryGetStringField(TEXT("job_id"), Job) ||
        !Fixture->TryGetStringField(TEXT("accepted_revision_id"), Revision))
    {
        AddError(TEXT("Invalid local pipeline fixture."));
        return false;
    }
    UWorld::InitializationValues IV = UWorld::InitializationValues()
                                          .InitializeScenes(false)
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
    if (!TestNotNull(TEXT("Pipeline Editor test world"), World))
        return false;
    auto *Actor = World->SpawnActor<APlayableSketchLevelActor>();
    if (!Actor)
    {
        World->DestroyWorld(false);
        AddError(TEXT("Could not create pipeline actor"));
        return false;
    }
    Actor->bAutoRebuildGeometry = false;
    Actor->ImportedLayoutAsset = NewObject<UPlayableSketchImportedLayoutAsset>(Actor);
    Actor->PipelineServiceUrl = Service;
    Actor->PipelineJobId = Job;
    Actor->RefreshPipelineJob();
    ADD_LATENT_AUTOMATION_COMMAND(FPipelineLiveImport(this, World, Actor, Revision));
    return true;
}
#endif
