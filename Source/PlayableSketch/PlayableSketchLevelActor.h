#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "Validation/PlayableSketchValidation.h"
#include "Geometry/PlayableSketchComponentRegistry.h"
#include "Navigation/PlayableSketchNavigation.h"
#include "ExplicitLayout/PlayableSketchImportedLayoutAsset.h"
#include "ExplicitLayout/PlayableSketchExplicitLayout.h"
#include "ExplicitLayout/PlayableSketchExplicitNavigation.h"
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

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Import")
    EPlayableSketchLayoutSource LayoutSource = EPlayableSketchLayoutSource::ProceduralGraph;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Import")
    TObjectPtr<UPlayableSketchImportedLayoutAsset> ImportedLayoutAsset = nullptr;

    UPROPERTY(Transient)
    bool bUseSketchViewCoordinates = false;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Import")
    FString ImportLayoutJsonPath;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Import")
    FString LastImportReport;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Import")
    void ImportLayoutJson();

    bool ImportLayoutJsonText(const FString &Json, FString &OutError);

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Import",
              meta = (DisplayName = "Import Canonical Layout Json"))
    void ImportCanonicalLayoutJson();

    bool ImportCanonicalLayoutJsonText(const FString &Json, FString &OutError);

    bool ImportRuntimeCanonicalJsonText(const FString &Json, FString &OutError);

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Pipeline")
    FString PipelineServiceUrl = TEXT("http://127.0.0.1:8768");

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Pipeline",
              meta = (FilePathFilter = "png,jpg,jpeg"))
    FString PipelineImagePath;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Pipeline")
    FString PipelineJobId;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Pipeline")
    FString PipelineAcceptedRevisionId;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Pipeline")
    FString LastPipelineStatus;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Pipeline")
    void UploadPipelineImage();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Pipeline")
    void RefreshPipelineJob();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Pipeline")
    void OpenPipelineReview();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Pipeline")
    void ImportPipelineAcceptedLayout();

    static bool IsLocalPipelineUrl(const FString &Url);
    static bool IsPipelineJobId(const FString &Id);
    bool IsPipelineRequestCurrent(uint64 Sequence, const FString &Service, const FString &Job,
                                  const FString &SelectedRevision) const;

  private:
    uint64 PipelineRequestSequence = 0;

  public:
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

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring",
              meta = (DisplayName = "Rebuild Geometry (Full)"))
    void RebuildGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void RebuildLocalGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestRebuildEquivalence();

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Rebuild")
    FString LastRebuildReport;

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

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Navigation",
              meta = (ClampMin = "1", ClampMax = "1000000"))
    int32 NavigationMaxCells = 250000;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Navigation")
    bool bShowNavigationGrid = false;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Navigation")
    bool bShowBlockedNavigationCells = false;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Navigation")
    FString NavigationReport = TEXT("No current navigation analysis.");

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Navigation")
    FString NavigationExportPath;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Navigation")
    void AnalyzeNavigation();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Navigation")
    void ExportNavigationReport();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Navigation")
    void VerifyExplicitPawnTraversal();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Navigation")
    FVector2D NavigationGridOffsetCm = FVector2D::ZeroVector;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Navigation",
              meta = (ClampMin = "1", ClampMax = "1000000"))
    float ExplicitNavigationCellSizeCm = 25.0f;

    FPlayableSketchExplicitNavigationReport ExplicitNavigationResult;

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Navigation")
    void RunNavigationExamples();

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    FString PreviewStatus = TEXT("Generate Layout to create the first saved placement.");

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    bool bPreviewStale = false;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Validation")
    TArray<FPlayableSketchValidationIssue> LastIssues;

    virtual void OnConstruction(const FTransform &Transform) override;

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
    UPROPERTY(Transient)
    TObjectPtr<UPlayableSketchImportedLayoutAsset> ExplicitSettingsAsset = nullptr;
    FString ExplicitSettingsSourceJson;

    void UpdateExplicitGeometry(bool bForceFull);
    void ValidateExplicitDesign();
    void ReportExplicitNavigation();
    void ApplyRuntimeCoordinates(FPlayableSketchExplicitLayout &Layout) const;
    bool BuildExplicitGeometry(FPlayableSketchExplicitLayout &Layout,
                               FPlayableSketchExplicitGeometry &Geometry, FString &Error) const;
    bool PublishExplicitLayout(const FPlayableSketchExplicitLayout &Layout,
                               const FPlayableSketchExplicitGeometry &Geometry, const FString &Json,
                               bool bFull, FString &Error);

    FPlayableSketchFloorPlan GeneratedFloorPlan;
    FString LastAttemptSignature;
    friend class FPlayableSketchLocalRebuildTests;
    friend class FPlayableSketchExplicitImportTests;
    friend class FPlayableSketchExplicitPersistenceTests;
    friend class FPlayableSketchNavigationIntegrationTests;
    friend class FPlayableSketchExperimentRunner;
    FString PublishedSignature;
    FString PublishedGlobalSignature;
    FPlayableSketchComponentRegistry ComponentRegistry;
    FPlayableSketchUpdateStats LastUpdateStats;
    double RebuildStartSeconds = 0.0;
    double ValidationMs = 0.0;
    double PlanMs = 0.0;
    FPlayableSketchNavigationResult NavigationResult;
    bool bNavigationCurrent = false;
    FPlayableSketchNavigationSettings GetNavigationSettings() const;
    void RefreshNavigation(const TArray<FPlayableSketchGeometryDescriptor> &Pieces);
    void ResetNavigation();
    void DrawNavigationGrid();

    FString GetGlobalRebuildSignature() const;
    void UpdateGeometry(bool bForceFull);

    FString GetSourceSignature() const;
    FPlayableSketchValidationSettings GetValidationSettings() const;
    bool ReadSavedRooms(FPlayableSketchFloorPlan &OutPlan, FString &OutError) const;
    bool BuildCandidate(FPlayableSketchFloorPlan &Plan,
                        TArray<FPlayableSketchGeometryDescriptor> &Pieces);
    bool PublishCandidate(const FPlayableSketchFloorPlan &Plan,
                          const TArray<FPlayableSketchGeometryDescriptor> &Pieces,
                          bool bFull = true, const FString &Reason = TEXT("Explicit full rebuild"));
    void InvalidatePreview(const TArray<FPlayableSketchValidationIssue> &Issues,
                           const FString &Status);
    void FailStage(const TCHAR *Code, const FString &Message);
    void AnnotateIssues();
    void LogIssues() const;
    void DrawValidationIssues();
};
