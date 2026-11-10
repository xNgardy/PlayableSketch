#include "Runtime/PlayableSketchRuntime.h"
#include "PlayableSketchLevelActor.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Camera/CameraComponent.h"
#include "Kismet/GameplayStatics.h"
#include "SceneView.h"

void APlayableSketchRuntimeController::Smoke()
{
    if (bSmokeFinished)
        return;
    auto J = MakeShared<FJsonObject>();
    J->SetStringField(TEXT("schema_version"), TEXT("runtime-smoke/1.0"));
    J->SetStringField(TEXT("job_id"), JobId);
    J->SetStringField(TEXT("accepted_revision_id"), SelectedRevision);
    J->SetStringField(TEXT("service_url"), ServiceUrl);
    J->SetStringField(TEXT("stage"), Stage);
    J->SetStringField(TEXT("status"), Status);
    J->SetStringField(TEXT("save_prefix"), SavePrefix);
    J->SetStringField(TEXT("saved_directory"), FPaths::ProjectSavedDir());
    J->SetBoolField(TEXT("with_editor"), WITH_EDITOR != 0);
    J->SetBoolField(TEXT("ready"), bReady);
    J->SetBoolField(TEXT("pawn_spawned"), ActivePawn != nullptr);
    J->SetBoolField(TEXT("completed"), false);
    J->SetBoolField(TEXT("source_axes_match_screen"), bScreenAxesMatch);
    J->SetBoolField(TEXT("screen_relative_movement_passed"), bScreenMovementPassed);
    bool Done = false, Success = false;
    if (FParse::Param(FCommandLine::Get(), TEXT("RuntimeOffline")))
    {
        if (Stage == TEXT("failed") && bReady && ActiveLevel && ActivePawn)
        {
            Done = Success = true;
            J->SetBoolField(TEXT("offline_failure_retained_ready_level"), true);
        }
    }
    else if (bReady && Stage == TEXT("ready") && !bSmokeStarted)
    {

        if (++SmokeReadyFrames >= 3)
        {
            const FVector Origin = ActivePawn->GetActorLocation();
            auto *Camera = ActivePawn->FindComponentByClass<UCameraComponent>();
            FMinimalViewInfo View;
            Camera->GetCameraView(0, View);
            FMatrix ViewMatrix, ProjectionMatrix, ViewProjection;
            UGameplayStatics::CalculateViewProjectionMatricesFromMinimalView(
                View, TOptional<FMatrix>(), ViewMatrix, ProjectionMatrix, ViewProjection);
            auto Project = [&](const FVector &Point, FVector2D &Result) {
                return FSceneView::ProjectWorldToScreen(Point, FIntRect(0, 0, 1440, 900),
                                                        ViewProjection, Result);
            };
            FVector2D Screen, Right, Down;
            bScreenAxesMatch = Project(Origin, Screen) &&
                               Project(Origin + FVector(100, 0, 0), Right) &&
                               Project(Origin + FVector(0, 100, 0), Down) && Right.X > Screen.X &&
                               Down.Y > Screen.Y && FMath::Abs(Right.Y - Screen.Y) < .01 &&
                               FMath::Abs(Down.X - Screen.X) < .01;
            bScreenMovementPassed = true;
            for (const FVector2D Input :
                 {FVector2D(0, 1), FVector2D(1, 0), FVector2D(0, -1), FVector2D(-1, 0)})
            {
                ActivePawn->SetActorLocation(Origin);
                ActivePawn->SetScreenInput(Input);
                ActivePawn->Tick(1.0f / 60);
                FVector2D Moved;
                if (!Project(ActivePawn->GetActorLocation(), Moved))
                    bScreenMovementPassed = false;
                const FVector2D Delta = Moved - Screen;
                if (Input.X != 0)
                    bScreenMovementPassed &= Delta.X * Input.X > 0 && FMath::Abs(Delta.Y) < .01;
                else
                    bScreenMovementPassed &= Delta.Y * Input.Y < 0 && FMath::Abs(Delta.X) < .01;
            }
            ActivePawn->SetActorLocation(Origin);
            ActivePawn->SetScreenInput(FVector2D::ZeroVector);
            if (!bScreenAxesMatch || !bScreenMovementPassed)
            {
                Done = true;
                J->SetStringField(
                    TEXT("failure"),
                    TEXT("Image orientation or screen-relative movement check failed."));
            }
            else
            {
                bSmokeStarted = true;
                PlayRoute();
            }
        }
    }
    else if (bSmokeStarted && ActivePawn && ActivePawn->bReachedGoal)
    {
        const FString Json = CurrentJson();
        auto *BeforeLevel = ActiveLevel.Get();
        FString Error;
        const bool Rejected = !PublishAccepted(TEXT("{}"), Error) && ActiveLevel == BeforeLevel &&
                              CurrentJson() == Json;
        const auto BeforePath = ActiveLevel->ExplicitNavigationResult.Path;
        ++ThemeSeed;
        const bool Theme = PublishAccepted(Json, Error) && CurrentJson() == Json &&
                           BeforePath == ActiveLevel->ExplicitNavigationResult.Path;
        const int64 BeforeGeneration = SaveGeneration;
        SaveRuntime();
        const bool Saved = SaveGeneration > BeforeGeneration;
        LoadRuntime();
        const bool Reloaded = CurrentJson() == Json && bReady && ActivePawn;
        J->SetBoolField(TEXT("actual_pawn_reached_goal"), true);
        J->SetBoolField(TEXT("rejected_import_retains_level"), Rejected);
        J->SetBoolField(TEXT("theme_seed_keeps_locked_geometry_and_route"), Theme);
        J->SetBoolField(TEXT("save_verified"), Saved);
        J->SetBoolField(TEXT("runtime_save_reload"), Reloaded);
        J->SetStringField(TEXT("canonical_json"), CurrentJson());
        J->SetNumberField(TEXT("theme_seed"), ThemeSeed);
        J->SetStringField(TEXT("navigation_report"),
                          ActiveLevel ? ActiveLevel->NavigationReport : FString());
        Success =
            Rejected && Theme && Saved && Reloaded && bScreenAxesMatch && bScreenMovementPassed;
        Done = true;
    }

    if (!Done && !bSmokeStarted && !bReady &&
        (Stage == TEXT("validated") || Stage == TEXT("exported")) && !SelectedRevision.IsEmpty())
        ImportAccepted();
    if (!Done && !bReady &&
        (Stage == TEXT("uploaded") || Stage == TEXT("processing") ||
         Stage == TEXT("needs_review")) &&
        FPlatformTime::Seconds() > NextPollAt)
    {
        NextPollAt = FPlatformTime::Seconds() + 1;
        RefreshJob();
    }
    if (FPlatformTime::Seconds() > SmokeDeadline)
    {
        Done = true;
        Success = false;
        J->SetStringField(TEXT("failure"), TEXT("runtime smoke deadline exceeded"));
    }
    J->SetBoolField(TEXT("source_axes_match_screen"), bScreenAxesMatch);
    J->SetBoolField(TEXT("screen_relative_movement_passed"), bScreenMovementPassed);
    J->SetStringField(TEXT("camera_validation_method"),
                      TEXT("Unreal camera view/projection matrix and actual swept Pawn movement"));
    if (Done)
    {
        J->SetBoolField(TEXT("completed"), true);
        J->SetBoolField(TEXT("success"), Success);
        bSmokeFinished = true;
    }
    if (!SmokeReportPath.IsEmpty())
    {
        FString Text;
        FJsonSerializer::Serialize(J, TJsonWriterFactory<>::Create(&Text));
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(SmokeReportPath), true);
        const FString Temp = SmokeReportPath + TEXT(".tmp");
        if (FFileHelper::SaveStringToFile(Text, *Temp))
            IFileManager::Get().Move(*SmokeReportPath, *Temp, true);
    }
    if (Done && FParse::Param(FCommandLine::Get(), TEXT("RuntimeExit")))
        FPlatformMisc::RequestExitWithStatus(false, Success ? 0 : 1);
}
