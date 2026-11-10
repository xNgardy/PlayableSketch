#pragma once
#include "CoreMinimal.h"
#include "ExplicitLayout/PlayableSketchExplicitLayout.h"

class AActor;

struct PLAYABLESKETCH_API FPlayableSketchExplicitAgent
{
    double RadiusCm = 40, HalfHeightCm = 90, ClearanceCm = 10;
    double StepHeightCm = 0;
    double CellSizeCm = 25;
    FVector2D GridOffsetCm = FVector2D::ZeroVector;
    int32 MaxCells = 250000;
    int32 MaxQueries = 2000000;
};

struct PLAYABLESKETCH_API FPlayableSketchExplicitNavigationReport
{
    bool bAnalysisCompleted = false, bReachable = false;
    FString DocumentId, RevisionId;
    FString Topology = TEXT("not_run"), Geometry = TEXT("not_run"), Grid = TEXT("not_run");
    FString NavMesh = TEXT("not_applicable"), Pawn = TEXT("not_run");
    FString Reason;
    TArray<FString> Issues;
    TMap<FString, double> CorridorClearWidthsCm;
    TArray<FVector2D> Path;
    FVector2D OriginCm = FVector2D::ZeroVector;
    FIntPoint Dimensions = FIntPoint::ZeroValue;
    int32 Queries = 0, WalkableCells = 0, MovementSteps = 0;
    double AnalysisMs = 0, PawnMs = 0;
    FTransform ActorTransform;
    FPlayableSketchExplicitAgent Agent;
    FString Json() const;
    FString Summary() const;
};

class PLAYABLESKETCH_API FPlayableSketchExplicitNavigation
{
  public:
    static FPlayableSketchExplicitNavigationReport Analyze(
        AActor &Owner, const FPlayableSketchExplicitLayout &Layout,
        const FPlayableSketchExplicitAgent &Agent);
    static bool CanMove(AActor &Owner, const FVector2D &From, const FVector2D &To,
                        const FPlayableSketchExplicitAgent &Agent, const AActor *Ignore = nullptr);

    static bool TraversePawn(AActor &Owner, const TArray<FVector2D> &Route,
                             FPlayableSketchExplicitNavigationReport &Report);
};
