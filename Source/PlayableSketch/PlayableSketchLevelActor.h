#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpatialGraph/PlayableSketchRoom.h"
#include "SpatialGraph/PlayableSketchConnection.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "PlayableSketchLevelActor.generated.h"

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


protected:
    virtual void BeginPlay() override;

public:
    virtual void Tick(float DeltaTime) override;

private:
    FPlayableSketchFloorPlan GeneratedFloorPlan;
};