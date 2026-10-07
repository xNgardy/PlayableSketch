#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "PlayableSketchLevelActor.generated.h"

class UMaterialInterface;

UCLASS()
class PLAYABLESKETCH_API APlayableSketchLevelActor : public AActor
{
    GENERATED_BODY()

public:
    APlayableSketchLevelActor();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
    TArray<FPlayableSketchRoom> Rooms;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
    TArray<FPlayableSketchConnection> Connections;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")
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
};