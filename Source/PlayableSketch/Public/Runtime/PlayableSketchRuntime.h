#pragma once
#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/SaveGame.h"
#include "PlayableSketchRuntime.generated.h"

class APlayableSketchLevelActor;
class UStaticMesh;
class UMaterialInterface;
class UCapsuleComponent;
class UFloatingPawnMovement;
class UCameraComponent;
class SWidget;
class APlayerStart;

UCLASS()
class PLAYABLESKETCH_API UPlayableSketchRuntimeSave : public USaveGame
{
    GENERATED_BODY()
  public:
    UPROPERTY() FString CanonicalJson;
    UPROPERTY() FString ContentHash;
    UPROPERTY() FString ServiceUrl;
    UPROPERTY() FString JobId;
    UPROPERTY() FString SelectedRevision;
    UPROPERTY() int32 ThemeSeed = 42;
    UPROPERTY() int64 Generation = 0;
};

UCLASS()
class PLAYABLESKETCH_API APlayableSketchRuntimePawn : public APawn
{
    GENERATED_BODY()
  public:
    APlayableSketchRuntimePawn();
    virtual void SetupPlayerInputComponent(UInputComponent *Input) override;
    virtual void Tick(float DeltaSeconds) override;
    void Configure(APlayableSketchLevelActor &Level);
    void Follow(const TArray<FVector2D> &Route);
    bool bReachedGoal = false;
    FVector2D ScreenMovement(const FVector2D &Input) const;
    void FitCamera();
    void SetScreenInput(const FVector2D &Input);

  private:
    UPROPERTY() TObjectPtr<UCapsuleComponent> Capsule;
    UPROPERTY() TObjectPtr<UFloatingPawnMovement> Movement;
    UPROPERTY() TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<APlayableSketchLevelActor> Layout;
    TArray<FVector2D> Path;
    int32 PathIndex = 0;
    FVector2D CameraViewportSize = FVector2D::ZeroVector;
    FVector2D Keys = FVector2D::ZeroVector;
    void ForwardDown();
    void ForwardUp();
    void BackDown();
    void BackUp();
    void RightDown();
    void RightUp();
    void LeftDown();
    void LeftUp();
};

UCLASS()
class PLAYABLESKETCH_API APlayableSketchRuntimeController : public APlayerController
{
    GENERATED_BODY()
  public:
    APlayableSketchRuntimeController();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void Tick(float DeltaSeconds) override;
    FString ServiceUrl = TEXT("http://127.0.0.1:8772");
    FString JobId, SelectedRevision, ImagePath;
    FString Status =
        TEXT("Finish and export a playable plan in the workspace, then choose Open latest plan.");
    FString Stage = TEXT("idle");
    int32 ThemeSeed = 42;
    bool bReady = false;
    bool bDarkMode = true;
    bool bShowAdvanced = false;
    FString SavePrefix = TEXT("PlayableSketchRuntime");
    void OpenReview();
    void OpenLatestPlan();
    void ToggleAppearance();
    void UploadImage();
    void RefreshJob();
    void ImportAccepted();
    void CancelRequest();
    void CancelJob();
    void RetryJob();
    void SaveRuntime();
    void LoadRuntime();
    void PlayRoute();
    bool PublishAccepted(const FString &Json, FString &Error);
    bool IsCurrent(uint64 Id, const FString &Service, const FString &Job,
                   const FString &Revision) const;
    APlayableSketchLevelActor *CurrentLevel() const
    {
        return ActiveLevel;
    }
    APlayableSketchRuntimePawn *CurrentPawn() const
    {
        return ActivePawn;
    }
    FString CurrentJson() const;

  private:
    UPROPERTY() TObjectPtr<APlayableSketchLevelActor> ActiveLevel;
    UPROPERTY() TObjectPtr<APlayableSketchRuntimePawn> ActivePawn;

    UPROPERTY() TObjectPtr<UStaticMesh> CookedCube;
    UPROPERTY() TObjectPtr<UMaterialInterface> CookedMaterial;
    uint64 RequestSequence = 0;
    int64 SaveGeneration = 0;
    FString PublishedService, PublishedJob, PublishedRevision;
    int32 PublishedSeed = 42;
    bool bGoalReported = false;
    TSharedPtr<SWidget> Panel;
    bool bSmokeStarted = false;
    int32 SmokeReadyFrames = 0;
    bool bScreenAxesMatch = false;
    bool bScreenMovementPassed = false;
    bool bStopped = false;
    double NextPollAt = 0;
    bool bSmokeFinished = false;
    double SmokeDeadline = 0;
    FString SmokeReportPath;
    void CreatePanel();
    void ApplyTheme(APlayableSketchLevelActor &Level, int32 Seed);
    void Smoke();
};

UCLASS()
class PLAYABLESKETCH_API APlayableSketchRuntimeGameMode : public AGameModeBase
{
    GENERATED_BODY()
  public:
    APlayableSketchRuntimeGameMode();
};
