#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "Validation/PlayableSketchValidation.h"
#include "PlayableSketchLevelActor.generated.h"

class UMaterialInterface;

UCLASS()
class PLAYABLESKETCH_API APlayableSketchLevelActor : public AActor
{
    GENERATED_BODY()

public:
    APlayableSketchLevelActor();

    UPROPERTY()
    TArray<FPlayableSketchRoom> Rooms;

    UPROPERTY()
    TArray<FPlayableSketchConnection> Connections;

    UPROPERTY()
    FPlayableSketchGraph Graph;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
    TObjectPtr<UPlayableSketchGraphAsset> GraphAsset = nullptr;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateGraph();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestLayoutRect();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestFloorPlan();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestRoomPlacement();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestPlacementSearch();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestDoors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestCorridorCandidates();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestCorridorRouting();
    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1"))
    int32 GridStepCm = 50;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "0"))
    int32 RoomGapCm = 400;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "0"))
    int32 DoorCornerMarginCm = 50;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1"))
    int32 MaxPlacementAttempts = 128;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Generation", meta = (ClampMin = "1.0"))
    float FloorThicknessCm = 20.0f;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Generation")
    void GenerateFloors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Generation")
    void ClearFloors();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestFloorPath();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float WallHeightCm = 300.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float WallThicknessCm = 20.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry", meta = (ClampMin = "1.0"))
    float DoorHeightCm = 220.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Geometry")
    bool bGenerateOnBeginPlay = true;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> WallMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> DefaultFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> HubFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> StartFloorMaterial = nullptr;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Materials")
    TObjectPtr<UMaterialInterface> GoalFloorMaterial = nullptr;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestWallSegments();



    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void GenerateLayout();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring", meta = (DisplayName = "Rebuild Geometry (Full)"))
    void RebuildGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateCurrentDesign();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestAuthoringValidation();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Authoring")
    bool bAutoRebuildGeometry = true;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float MinCorridorWidthCm = 100.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnRadiusCm = 40.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnHeightCm = 180.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "0.0"))
    float ClearanceCm = 10.0f;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    FString PreviewStatus = TEXT("Generate Layout to create the first saved placement.");

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    bool bPreviewStale = false;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Validation")
    TArray<FPlayableSketchValidationIssue> LastIssues;

    virtual void OnConstruction(const FTransform& Transform) override;

#if WITH_EDITOR
    virtual void PostEditUndo() override;
#endif

protected:
    virtual void BeginPlay() override;

public:
    virtual void Tick(float DeltaTime) override;

    TArray<FVector2D> PreviewPathPoints;

    void ApplyFloorMaterials();
    void DrawFloorPathPreview();

#if WITH_EDITOR
    virtual bool ShouldTickIfViewportsOnly() const override;
#endif

private:

    FPlayableSketchFloorPlan GeneratedFloorPlan;
    FString LastAttemptSignature;
    FString PublishedSignature;

    FString GetSourceSignature() const;
    FPlayableSketchValidationSettings GetValidationSettings() const;
    bool ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const;
    bool BuildCandidate(FPlayableSketchFloorPlan& Plan, TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void InvalidatePreview(const TArray<FPlayableSketchValidationIssue>& Issues, const FString& Status);
    void FailStage(const TCHAR* Code, const FString& Message);
    void AnnotateIssues();
    void LogIssues() const;
    void DrawValidationIssues();
};
