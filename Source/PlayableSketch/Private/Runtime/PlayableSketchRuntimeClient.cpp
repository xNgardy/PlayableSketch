#include "Runtime/PlayableSketchRuntime.h"
#include "PlayableSketchLevelActor.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/DirectionalLight.h"
#include "Camera/CameraActor.h"
#include "Misc/ConfigCacheIni.h"
#include "Framework/Application/SlateApplication.h"
#include "Components/DirectionalLightComponent.h"
#include "Engine/GameViewportClient.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Hash/Blake3.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
FString SaveHash(const UPlayableSketchRuntimeSave &Save)
{
    auto J = MakeShared<FJsonObject>();
    J->SetStringField(TEXT("canonical"), Save.CanonicalJson);
    J->SetStringField(TEXT("service"), Save.ServiceUrl);
    J->SetStringField(TEXT("job"), Save.JobId);
    J->SetStringField(TEXT("revision"), Save.SelectedRevision);
    J->SetNumberField(TEXT("seed"), Save.ThemeSeed);
    J->SetStringField(TEXT("generation"), LexToString(Save.Generation));
    FString Text;
    FJsonSerializer::Serialize(J, TJsonWriterFactory<>::Create(&Text));
    FTCHARToUTF8 Bytes(*Text);
    return LexToString(FBlake3::HashBuffer(Bytes.Get(), Bytes.Length()));
}
bool ValidPrefix(const FString &Prefix)
{
    if (Prefix.IsEmpty() || Prefix.Len() > 80)
        return false;
    for (TCHAR C : Prefix)
        if (!FChar::IsAlnum(C) && C != TEXT('_'))
            return false;
    return true;
}
}
APlayableSketchRuntimeController::APlayableSketchRuntimeController()
{
    PrimaryActorTick.bCanEverTick = true;
    bShowMouseCursor = true;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(
        TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Material(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    CookedCube = Cube.Object;
    CookedMaterial = Material.Object;
}
void APlayableSketchRuntimeController::BeginPlay()
{
    Super::BeginPlay();
    FParse::Value(FCommandLine::Get(), TEXT("RuntimeService="), ServiceUrl);
    FParse::Value(FCommandLine::Get(), TEXT("RuntimeJob="), JobId);
    FParse::Value(FCommandLine::Get(), TEXT("RuntimeRevision="), SelectedRevision);
    FParse::Value(FCommandLine::Get(), TEXT("RuntimeImage="), ImagePath);
    FParse::Value(FCommandLine::Get(), TEXT("RuntimeSavePrefix="), SavePrefix);
    if (!ValidPrefix(SavePrefix))
        SavePrefix = TEXT("PlayableSketchRuntime");
    auto *Light =
        GetWorld()->SpawnActor<ADirectionalLight>(FVector(0, 0, 1200), FRotator(-55, -30, 0));
    if (Light)
    {
        Light->SetOwner(this);
        Light->GetLightComponent()->SetIntensity(5);
    }

    if (auto *IdleCamera =
            GetWorld()->SpawnActor<ACameraActor>(FVector(0, 0, 1500), FRotator(-90, 0, 0)))
    {
        IdleCamera->SetOwner(this);
        SetViewTarget(IdleCamera);
    }
    GConfig->GetBool(TEXT("PlayableSketch.Appearance"), TEXT("DarkMode"), bDarkMode,
                     GGameUserSettingsIni);
    CreatePanel();
    if (FParse::Param(FCommandLine::Get(), TEXT("RuntimeSmoke")))
    {
        SmokeDeadline = FPlatformTime::Seconds() + 180;
        FParse::Value(FCommandLine::Get(), TEXT("RuntimeReport="), SmokeReportPath);
        if (FParse::Param(FCommandLine::Get(), TEXT("RuntimeLoadSave")))
        {
            LoadRuntime();
            if (FParse::Param(FCommandLine::Get(), TEXT("RuntimeOffline")))
            {
                ServiceUrl = TEXT("http://127.0.0.1:1");
                ImportAccepted();
            }
        }
        else if (!JobId.IsEmpty() && !SelectedRevision.IsEmpty())
            ImportAccepted();
        else if (!ImagePath.IsEmpty())
            UploadImage();
    }
}
void APlayableSketchRuntimeController::EndPlay(const EEndPlayReason::Type Reason)
{
    bStopped = true;
    ++RequestSequence;
    if (Panel && GEngine && GEngine->GameViewport)
        GEngine->GameViewport->RemoveViewportWidgetContent(Panel.ToSharedRef());
    Panel.Reset();
    Super::EndPlay(Reason);
}
bool APlayableSketchRuntimeController::IsCurrent(uint64 Id, const FString &Service,
                                                 const FString &Job, const FString &Revision) const
{
    return !bStopped && !IsActorBeingDestroyed() && RequestSequence == Id &&
           ServiceUrl.Equals(Service, ESearchCase::CaseSensitive) &&
           JobId.Equals(Job, ESearchCase::CaseSensitive) &&
           SelectedRevision.Equals(Revision, ESearchCase::CaseSensitive);
}
FString APlayableSketchRuntimeController::CurrentJson() const
{
    return ActiveLevel && ActiveLevel->ImportedLayoutAsset
               ? ActiveLevel->ImportedLayoutAsset->CanonicalJson
               : FString();
}
void APlayableSketchRuntimeController::ApplyTheme(APlayableSketchLevelActor &Level, int32 Seed)
{
    FRandomStream Rng(Seed);
    auto Material = [&](FLinearColor Color) -> UMaterialInterface * {
        auto *Result = UMaterialInstanceDynamic::Create(CookedMaterial, &Level);
        if (Result)
            Result->SetVectorParameterValue(TEXT("Color"), Color);
        return Result;
    };
    const float Hue = Rng.FRandRange(.12f, .32f);
    Level.WallMaterial = Material(FLinearColor(.7f + Hue / 2, .72f, .75f));
    Level.DefaultFloorMaterial = Material(FLinearColor(.2f + Hue, .28f, .32f));
    Level.StartFloorMaterial = Material(FLinearColor(.15f, .55f, .3f));
    Level.GoalFloorMaterial = Material(FLinearColor(.8f, .5f, .12f));
}
bool APlayableSketchRuntimeController::PublishAccepted(const FString &Json, FString &Error)
{
    if (!GetWorld() || !GetWorld()->IsGameWorld() || Json.Len() > 2 * 1024 * 1024 || !CookedCube ||
        !CookedMaterial)
    {
        Error = TEXT(
            "Runtime world or cooked Cube/BasicShapeMaterial unavailable; previous level retained.");
        return false;
    }
    FPlayableSketchExplicitLayout Layout;
    if (!FPlayableSketchExplicitLayoutBuilder::Parse(Json, Layout, Error))
        return false;
    if (Layout.ValidationMode != TEXT("gameplay"))
    {
        Error = TEXT(
            "Choose distinct Start/Goal and gameplay mode in metric review before playing. Previous level retained.");
        return false;
    }

    const FTransform Staging(FRotator::ZeroRotator, FVector(1000000, 0, 0));
    auto *Candidate = GetWorld()->SpawnActorDeferred<APlayableSketchLevelActor>(
        APlayableSketchLevelActor::StaticClass(), Staging);
    if (!Candidate)
    {
        Error = TEXT("Could not stage a runtime level.");
        return false;
    }
    Candidate->bUseSketchViewCoordinates = true;
    Candidate->bGenerateOnBeginPlay = false;
    Candidate->bAutoRebuildGeometry = false;
    Candidate->SetActorHiddenInGame(true);
    Candidate->FinishSpawning(Staging);
    ApplyTheme(*Candidate, ThemeSeed);
    auto Reject = [&](const FString &Message) {
        Error = Message;
        Candidate->Destroy();
        return false;
    };
    if (!Candidate->ImportRuntimeCanonicalJsonText(Json, Error))
    {
        Candidate->Destroy();
        return false;
    }
    Candidate->VerifyExplicitPawnTraversal();
    if (Candidate->ExplicitNavigationResult.Pawn != TEXT("passed"))
        return Reject(Candidate->NavigationReport);
    auto *Previous = ActiveLevel.Get();
    auto *PreviousPawn = ActivePawn.Get();
    if (Previous)
        Previous->SetActorEnableCollision(false);
    if (PreviousPawn)
        PreviousPawn->SetActorEnableCollision(false);
    auto Restore = [&]() {
        if (Previous)
            Previous->SetActorEnableCollision(true);
        if (PreviousPawn)
            PreviousPawn->SetActorEnableCollision(true);
    };
    Candidate->SetActorLocation(FVector::ZeroVector);
    Candidate->AnalyzeNavigation();
    if (!Candidate->ExplicitNavigationResult.bReachable)
    {
        Restore();
        return Reject(TEXT("Destination collision check failed: ") + Candidate->NavigationReport);
    }

    const auto &Nav = Candidate->ExplicitNavigationResult;
    const FVector Start(Nav.Path[0].X, Nav.Path[0].Y,
                        Nav.Agent.HalfHeightCm + Nav.Agent.ClearanceCm / 2 + .5);
    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto *Pawn =
        GetWorld()->SpawnActor<APlayableSketchRuntimePawn>(Start, FRotator::ZeroRotator, Params);
    if (!Pawn)
    {
        Restore();
        return Reject(TEXT("Pawn spawn failed; previous level retained."));
    }
    Pawn->Configure(*Candidate);
    ActiveLevel = Candidate;
    ActivePawn = Pawn;
    Candidate->SetActorHiddenInGame(false);
    Possess(Pawn);
    SetViewTarget(Pawn);
    if (PreviousPawn)
        PreviousPawn->Destroy();
    if (Previous)
        Previous->Destroy();
    PublishedService = ServiceUrl;
    PublishedJob = JobId;
    PublishedRevision = SelectedRevision;
    PublishedSeed = ThemeSeed;
    bGoalReported = false;
    bReady = true;
    Stage = TEXT("ready");
    Status = TEXT(
        "Your level is ready. Click the view to explore with WASD or arrow keys, or choose Follow route.");
    Error.Reset();
    return true;
}
void APlayableSketchRuntimeController::CancelRequest()
{
    ++RequestSequence;
    Stage = ActiveLevel ? TEXT("ready") : TEXT("idle");
    Status = TEXT(
        "Request cancelled locally. Previous level retained. Cancel job separately to stop server work.");
}
void APlayableSketchRuntimeController::SaveRuntime()
{
    if (!bReady || CurrentJson().IsEmpty() || !ValidPrefix(SavePrefix))
    {
        Status = TEXT("No ready runtime layout to save.");
        return;
    }
    auto *Save = Cast<UPlayableSketchRuntimeSave>(
        UGameplayStatics::CreateSaveGameObject(UPlayableSketchRuntimeSave::StaticClass()));
    Save->CanonicalJson = CurrentJson();
    Save->ThemeSeed = PublishedSeed;
    Save->ServiceUrl = PublishedService;
    Save->JobId = PublishedJob;
    Save->SelectedRevision = PublishedRevision;

    for (const TCHAR *Suffix : {TEXT("_A"), TEXT("_B")})
    {
        auto *Existing = Cast<UPlayableSketchRuntimeSave>(
            UGameplayStatics::LoadGameFromSlot(SavePrefix + Suffix, 0));
        if (Existing && Existing->Generation > 0 && Existing->Generation < MAX_int32 &&
            !Existing->ContentHash.IsEmpty() && Existing->ContentHash == SaveHash(*Existing))
            SaveGeneration = FMath::Max(SaveGeneration, Existing->Generation);
    }
    Save->Generation = SaveGeneration + 1;
    Save->ContentHash = SaveHash(*Save);
    if (Save->ContentHash.IsEmpty() ||
        !APlayableSketchLevelActor::IsLocalPipelineUrl(Save->ServiceUrl))
    {
        Status = TEXT("Save rejected: checksum/service unavailable.");
        return;
    }
    const FString Slot = SavePrefix + (Save->Generation % 2 ? TEXT("_A") : TEXT("_B"));
    if (!UGameplayStatics::SaveGameToSlot(Save, Slot, 0))
    {
        Status = TEXT("Save failed. Previous bank retained.");
        return;
    }
    auto *Check = Cast<UPlayableSketchRuntimeSave>(UGameplayStatics::LoadGameFromSlot(Slot, 0));
    if (!Check || Check->ContentHash != SaveHash(*Check))
    {
        Status = TEXT("Save verification failed. Previous bank retained.");
        return;
    }
    SaveGeneration = Save->Generation;
    Status = TEXT("Saved runtime layout to bank ") + Slot;
}
void APlayableSketchRuntimeController::LoadRuntime()
{
    ++RequestSequence;
    if (!ValidPrefix(SavePrefix))
    {
        Status = TEXT("Invalid save prefix.");
        return;
    }
    UPlayableSketchRuntimeSave *Best = nullptr;
    for (const TCHAR *Suffix : {TEXT("_A"), TEXT("_B")})
    {
        auto *Save = Cast<UPlayableSketchRuntimeSave>(
            UGameplayStatics::LoadGameFromSlot(SavePrefix + Suffix, 0));
        if (Save && Save->Generation > 0 && Save->Generation < MAX_int32 &&
            !Save->ContentHash.IsEmpty() && Save->ContentHash == SaveHash(*Save) &&
            APlayableSketchLevelActor::IsLocalPipelineUrl(Save->ServiceUrl) &&
            (!Best || Save->Generation > Best->Generation))
            Best = Save;
    }
    if (!Best)
    {
        Status = TEXT("No intact runtime save. Previous level retained.");
        return;
    }
    const int32 OldSeed = ThemeSeed;
    ThemeSeed = Best->ThemeSeed;
    FString Error;
    if (!PublishAccepted(Best->CanonicalJson, Error))
    {
        ThemeSeed = OldSeed;
        Status = TEXT("Saved layout rejected: ") + Error;
        return;
    }
    SaveGeneration = Best->Generation;
    ServiceUrl = Best->ServiceUrl;
    JobId = Best->JobId;
    SelectedRevision = Best->SelectedRevision;
    PublishedService = ServiceUrl;
    PublishedJob = JobId;
    PublishedRevision = SelectedRevision;
    Status = TEXT("Runtime save restored; source, revision, settings and theme seed preserved.");
}
void APlayableSketchRuntimeController::PlayRoute()
{
    if (!bReady || !ActivePawn || !ActiveLevel)
    {
        Status = TEXT("Import a gameplay layout and wait for navigation readiness.");
        return;
    }
    const auto &R = ActiveLevel->ExplicitNavigationResult;

    ActivePawn->SetActorLocation(
        FVector(R.Path[0].X, R.Path[0].Y, R.Agent.HalfHeightCm + R.Agent.ClearanceCm / 2 + .5));
    bGoalReported = false;
    ActivePawn->Follow(R.Path);
    Status = TEXT("Pawn moving through the accepted layout to Goal.");
}
void APlayableSketchRuntimeController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    if (Panel.IsValid() && FSlateApplication::IsInitialized() &&
        FSlateApplication::Get().GetPressedMouseButtons().IsEmpty())
        FSlateApplication::Get().InvalidateAllWidgets(false);
    if (SmokeDeadline > 0)
        Smoke();
    else if ((Stage == TEXT("processing") || Stage == TEXT("uploaded")) &&
             FPlatformTime::Seconds() > NextPollAt)
    {
        NextPollAt = FPlatformTime::Seconds() + 1;
        RefreshJob();
    }
    if (Stage == TEXT("ready") && ActivePawn && ActivePawn->bReachedGoal && !bGoalReported)
    {
        bGoalReported = true;
        Status = TEXT(
            "Goal reached by actual capsule Pawn. Use WASD to explore or play the route again.");
    }
}
