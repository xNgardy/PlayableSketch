#pragma once

#include "CoreMinimal.h"

struct PLAYABLESKETCH_API FPlayableSketchRect
{
    FVector2D Min = FVector2D::ZeroVector;
    FVector2D Max = FVector2D::ZeroVector;

    FPlayableSketchRect() = default;

    FPlayableSketchRect(const FVector2D& InMin, const FVector2D& InMax) : Min(InMin), Max(InMax)
    {
    }

    bool IsValid() const
    {
        return FMath::IsFinite(Min.X) && FMath::IsFinite(Min.Y) && FMath::IsFinite(Max.X) && FMath::IsFinite(Max.Y) && Max.X > Min.X && Max.Y > Min.Y;
    }

    bool OverlapsInterior(const FPlayableSketchRect& Other) const
    {
        if (!IsValid() || !Other.IsValid())
        {
            return false;
        }

        const bool bOverlapsX = Min.X < Other.Max.X && Max.X > Other.Min.X;
        const bool bOverlapsY = Min.Y < Other.Max.Y && Max.Y > Other.Min.Y;

        return bOverlapsX && bOverlapsY;
    }

    bool HasRequiredGap(const FPlayableSketchRect& Other, double RequiredGapCm) const
    {
        if (!IsValid() || !Other.IsValid() || !FMath::IsFinite(RequiredGapCm) || RequiredGapCm < 0.0)
        {
            return false;
        }

        const FVector2D Padding(RequiredGapCm, RequiredGapCm);
        const FPlayableSketchRect Expanded(Min - Padding, Max + Padding);

        if (!Expanded.IsValid())
        {
            return false;
        }

        return !Expanded.OverlapsInterior(Other);
    }
};