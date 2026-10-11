#pragma once

#include "CoreMinimal.h"

class AActor;
class UStaticMeshComponent;
class UMaterialInterface;

enum class EPlayableSketchPieceKind : uint8 { Floor, Wall, Lintel };

// Same owner + kind + canonical ordinal identifies the same output slot.
struct PLAYABLESKETCH_API FPlayableSketchComponentSpec
{
    FName Key;
    FGuid SourceId;
    bool bRoom = false;
    EPlayableSketchPieceKind Kind = EPlayableSketchPieceKind::Floor;
    FVector CenterCm = FVector::ZeroVector;
    FVector SizeCm = FVector::OneVector;
    TWeakObjectPtr<UMaterialInterface> Material;

    bool SameValue(const FPlayableSketchComponentSpec& Other) const;
};

struct PLAYABLESKETCH_API FPlayableSketchUpdateStats
{
    TSet<FGuid> DirtyRooms;
    TSet<FGuid> DirtyConnections;
    int32 Created = 0;
    int32 Updated = 0;
    int32 Removed = 0;
    int32 Kept = 0;
    double DirtyMs = 0.0;
    double ApplyMs = 0.0;
};

class PLAYABLESKETCH_API FPlayableSketchComponentRegistry
{
public:
    static void AssignKeys(TArray<FPlayableSketchComponentSpec>& Specs);
    bool IsHealthy(const AActor& Owner) const;
    void Clear(AActor& Owner);
    bool Apply(AActor& Owner, const TArray<FPlayableSketchComponentSpec>& Specs,
        bool bFull, FPlayableSketchUpdateStats& Stats, FString& Error);
    bool Verify(FString& Error) const;
    TMap<FName, FString> Capture() const;
    TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> GetPointers() const;

private:
    struct FEntry
    {
        FPlayableSketchComponentSpec Spec;
        TWeakObjectPtr<UStaticMeshComponent> Component;
    };
    TMap<FName, FEntry> Entries;
};
