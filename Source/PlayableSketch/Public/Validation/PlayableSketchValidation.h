#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Geometry/PlayableSketchWallGeometry.h"
#include "PlayableSketchValidation.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchIssueSeverity : uint8
{
    Info,
    Warning,
    Error
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchValidationIssue
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FName Code;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    TArray<FGuid> ElementIds;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    EPlayableSketchIssueSeverity Severity = EPlayableSketchIssueSeverity::Error;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FString Message;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    bool bHasPosition = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector PositionCm = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector ExtentCm = FVector(25.0, 25.0, 25.0);
};

struct PLAYABLESKETCH_API FPlayableSketchValidationSettings
{
    FPlayableSketchWallSettings Walls;
    int32 GridStepCm = 50;
    double MinCorridorWidthCm = 100.0;
    double PawnRadiusCm = 40.0;
    double PawnHeightCm = 180.0;
    double ClearanceCm = 10.0;

    double RequiredWidthCm() const
    {
        return FMath::Max(MinCorridorWidthCm, 2.0 * (PawnRadiusCm + ClearanceCm));
    }
};

class PLAYABLESKETCH_API FPlayableSketchValidation
{
  public:
    static bool HasErrors(const TArray<FPlayableSketchValidationIssue> &Issues);

    static TArray<FPlayableSketchValidationIssue> ValidateInput(
        const FPlayableSketchGraph &Graph, const FPlayableSketchValidationSettings &Settings);

    static TArray<FPlayableSketchValidationIssue> ValidatePlan(
        const FPlayableSketchGraph &Graph, const FPlayableSketchFloorPlan &Plan,
        const TArray<FPlayableSketchGeometryDescriptor> &Pieces,
        const FPlayableSketchValidationSettings &Settings);
};
