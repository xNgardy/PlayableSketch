#include "PlayableSketchLevelActor.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "Misc/AutomationTest.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/PackageName.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchNavigationRestartTests,
                                 "PlayableSketch.Navigation.RestartedProcess",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)
bool FPlayableSketchNavigationRestartTests::RunTest(const FString &Parameters)
{
    if (!FApp::IsUnattended() || !FParse::Param(FCommandLine::Get(), TEXT("Step12Restart")))
    {
        AddInfo(TEXT(
            "Separate-process verification requires -unattended -Step12Restart after ExplicitPersistence."));
        return true;
    }
    FString Manifest;
    TArray<FString> Lines;
    if (!TestTrue(TEXT("Previous process saved lifecycle map"),
                  FFileHelper::LoadFileToString(
                      Manifest, *(FPaths::ProjectSavedDir() / TEXT("Step12/lifecycle-map.txt")))))
        return false;
    Manifest.ParseIntoArrayLines(Lines);
    if (!TestEqual(TEXT("Lifecycle mount and directory"), Lines.Num(), 2))
        return false;
    FPackageName::RegisterMountPoint(Lines[0], Lines[1]);
    UWorld *World = UEditorLoadingAndSavingUtils::LoadMap(Lines[1] + TEXT("ExplicitLevel.umap"));
    if (!TestNotNull(TEXT("Fresh process opens saved map"), World))
        return false;
    APlayableSketchLevelActor *Actor = nullptr;
    for (TActorIterator<APlayableSketchLevelActor> It(World); It; ++It)
    {
        Actor = *It;
        break;
    }
    if (!TestNotNull(TEXT("Persistent actor"), Actor))
        return false;
    const FString Source = Actor->ImportedLayoutAsset->CanonicalJson;

    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Restart collision actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->RebuildLocalGeometry();
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Restart Local actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->RebuildGeometry();
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Restart Full actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    Actor->DispatchBeginPlay();
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Restart BeginPlay actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    TestEqual(TEXT("Restart preserves canonical coordinates/openings"),
              Actor->ImportedLayoutAsset->CanonicalJson, Source);
    FFileHelper::SaveStringToFile(
        Actor->ExplicitNavigationResult.Json(),
        *(FPaths::ProjectSavedDir() / TEXT("Step12/restarted-pawn.json")));
    UEditorLoadingAndSavingUtils::NewBlankMap(false);
    return !HasAnyErrors();
}
#endif
