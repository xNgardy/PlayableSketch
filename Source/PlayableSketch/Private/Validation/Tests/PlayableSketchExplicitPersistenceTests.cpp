#include "PlayableSketchLevelActor.h"
#include "PlayableSketchNavigationTestFixtures.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "PackageTools.h"
#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/PackageName.h"
#include "Misc/ScopeExit.h"
#include "HAL/FileManager.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchExplicitPersistenceTests,
                                 "PlayableSketch.Import.ExplicitPersistence",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchExplicitPersistenceTests::RunTest(const FString &Parameters)
{

    if (!FApp::IsUnattended())
    {
        AddInfo(TEXT("Disk save/reopen check requires -unattended; no open user map was changed."));
        return true;
    }
    const FString Run = FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Mount = TEXT("/PSStep05_") + Run + TEXT("/");
    const FString Directory = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() /
                                                                TEXT("Step05/Persistence") / Run) +
                              TEXT("/");
    IFileManager::Get().MakeDirectory(*Directory, true);
    FPackageName::RegisterMountPoint(Mount, Directory);
    ON_SCOPE_EXIT
    {
        UEditorLoadingAndSavingUtils::NewBlankMap(false);
    };
    UWorld *World = UEditorLoadingAndSavingUtils::NewBlankMap(false);
    if (!TestNotNull(TEXT("Fresh Editor map"), World))
        return false;
    UPackage *AssetPackage = CreatePackage(*(Mount + TEXT("LayoutSource")));
    auto *Asset = NewObject<UPlayableSketchImportedLayoutAsset>(
        AssetPackage, TEXT("LayoutSource"), RF_Public | RF_Standalone | RF_Transactional);
    auto *Actor = World->SpawnActor<APlayableSketchLevelActor>();
    if (!TestNotNull(TEXT("Persistent actor"), Actor))
        return false;
    Actor->bAutoRebuildGeometry = false;
    Actor->ImportedLayoutAsset = Asset;
    const FVector Position(1000, -500, 50);
    Actor->SetActorLocationAndRotation(Position, FRotator(0, 90, 0));
    FString Json, Error;
    if (!TestTrue(TEXT("Data_8 reference exists"),
                  FFileHelper::LoadFileToString(
                      Json, *(FPaths::ProjectDir() /
                              TEXT("Data/ground_truth/v1/Data_8.validated.json")))))
        return false;
    if (!TestTrue(TEXT("Canonical import before saving"),
                  Actor->ImportCanonicalLayoutJsonText(PlayableSketchNavigationFixtureRoles(Json),
                                                       Error)))
    {
        AddError(Error);
        return false;
    }
    Actor->WallThicknessCm = 20;
    Actor->WallHeightCm = 350;
    Actor->RebuildLocalGeometry();
    if (!TestFalse(TEXT("Configured source is valid"), Actor->bPreviewStale))
        return false;
    Actor->bAutoRebuildGeometry = true;
    Actor->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Pre-save actual Pawn"), Actor->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    const FString SavedJson = Asset->CanonicalJson;
    const auto Before = Actor->ComponentRegistry.Capture();
    FSavePackageArgs Args;
    Args.TopLevelFlags = RF_Public | RF_Standalone;
    Args.SaveFlags = SAVE_NoError;
    if (!TestTrue(TEXT("Real Data Asset saved"),
                  UPackage::SavePackage(AssetPackage, Asset,
                                        *(Directory + TEXT("LayoutSource.uasset")), Args)))
        return false;
    if (!TestTrue(TEXT("Real map saved"),
                  UEditorLoadingAndSavingUtils::SaveMap(World, Mount + TEXT("ExplicitLevel"))))
        return false;
    UEditorLoadingAndSavingUtils::NewBlankMap(false);
    FText UnloadError;
    if (!TestTrue(TEXT("Source package unloaded before reopening"),
                  UPackageTools::UnloadPackages({AssetPackage}, UnloadError)))
    {
        AddError(UnloadError.ToString());
        return false;
    }
    UWorld *Reopened =
        UEditorLoadingAndSavingUtils::LoadMap(Directory + TEXT("ExplicitLevel.umap"));
    if (!TestNotNull(TEXT("Map reopened from disk"), Reopened))
        return false;
    APlayableSketchLevelActor *Loaded = nullptr;
    for (TActorIterator<APlayableSketchLevelActor> It(Reopened); It; ++It)
    {
        Loaded = *It;
        break;
    }
    if (!TestNotNull(TEXT("Actor reference persisted"), Loaded) ||
        !TestNotNull(TEXT("Data Asset reference persisted"), Loaded->ImportedLayoutAsset.Get()))
        return false;
    TestTrue(TEXT("Explicit source mode survived map save"),
             Loaded->LayoutSource == EPlayableSketchLayoutSource::ImportedExplicitLayout);
    TestTrue(TEXT("Actor transform survived map save"),
             Loaded->GetActorLocation().Equals(Position) &&
                 Loaded->GetActorRotation().Equals(FRotator(0, 90, 0)));
    TestEqual(TEXT("Canonical source loaded from disk"), Loaded->ImportedLayoutAsset->CanonicalJson,
              SavedJson);
    TestEqual(TEXT("Wall thickness survived save/reopen"), Loaded->WallThicknessCm, 20.0f);
    TestEqual(TEXT("Wall height survived save/reopen"), Loaded->WallHeightCm, 350.0f);
    Loaded->RebuildGeometry();
    TestFalse(TEXT("Reopened source rebuilds"), Loaded->bPreviewStale);
    const auto After = Loaded->ComponentRegistry.Capture();
    TestEqual(TEXT("Reopened geometry piece count"), After.Num(), Before.Num());
    for (const auto &Pair : Before)
    {
        const FString *Value = After.Find(Pair.Key);
        TestTrue(TEXT("Reopened transforms, materials and collision match"),
                 Value && *Value == Pair.Value);
    }
    Loaded->VerifyExplicitPawnTraversal();
    TestEqual(TEXT("Disk reopened actual Pawn"), Loaded->ExplicitNavigationResult.Pawn,
              FString(TEXT("passed")));
    const FString Manifest = FPaths::ProjectSavedDir() / TEXT("Step12/lifecycle-map.txt");
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Manifest), true);
    FFileHelper::SaveStringToFile(Mount + TEXT("\n") + Directory + TEXT("\n"), *Manifest);
    return !HasAnyErrors();
}
#endif
