#include "Geometry/PlayableSketchComponentRegistry.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"

namespace
{
const FName RegistryTag(TEXT("PlayableSketch.RegistryPiece"));
const FName FloorTag(TEXT("PlayableSketch.GeneratedFloor"));
const FName WallTag(TEXT("PlayableSketch.GeneratedWall"));

bool IsGenerated(const UStaticMeshComponent &C)
{
    return C.ComponentHasTag(RegistryTag) || C.ComponentHasTag(FloorTag) ||
           C.ComponentHasTag(WallTag);
}

void Destroy(AActor &Owner, UStaticMeshComponent *C)
{
    if (IsValid(C))
    {
        C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Owner.RemoveInstanceComponent(C);
        C->DestroyComponent();
    }
}

FVector ScaleFor(const FPlayableSketchComponentSpec &S, const UStaticMesh &Mesh)
{
    const FVector M = Mesh.GetBoundingBox().GetSize();
    return FVector(S.SizeCm.X / M.X, S.SizeCm.Y / M.Y, S.SizeCm.Z / M.Z);
}

void Configure(UStaticMeshComponent &C, const FPlayableSketchComponentSpec &S, UStaticMesh &Mesh,
               bool bActive)
{
    const bool bFloor = S.Kind == EPlayableSketchPieceKind::Floor;
    const FVector Scale = ScaleFor(S, Mesh);
    C.SetStaticMesh(&Mesh);
    C.SetRelativeTransform(
        FTransform(FQuat::Identity, S.CenterCm - Mesh.GetBoundingBox().GetCenter() * Scale, Scale));

    C.SetMaterial(0, S.Material.Get());
    C.SetCollisionProfileName(TEXT("BlockAllDynamic"));
    C.SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
    C.SetGenerateOverlapEvents(false);
    C.SetCanEverAffectNavigation(false);
    C.CanCharacterStepUpOn = bFloor ? ECB_Yes : ECB_No;
    C.SetCollisionEnabled(bActive ? ECollisionEnabled::QueryAndPhysics
                                  : ECollisionEnabled::NoCollision);
    C.SetVisibility(bActive);
    C.SetHiddenInGame(!bActive);

    if (bActive)
    {
        C.ComponentTags.Reset();
        C.ComponentTags.Add(RegistryTag);
        C.ComponentTags.Add(bFloor ? FloorTag : WallTag);
        C.ComponentTags.Add(FName(*FString::Printf(TEXT("ComponentKey=%s"), *S.Key.ToString())));
        C.ComponentTags.Add(FName(*FString::Printf(
            TEXT("%s=%s"),
            S.OwnerKind == TEXT("Wall") ? TEXT("WallId")
                                        : (S.OwnerKind == TEXT("Corridor")
                                               ? TEXT("CorridorId")
                                               : (S.bRoom ? TEXT("RoomId") : TEXT("ConnectionId"))),
            *S.SourceId.ToString())));
        C.ComponentTags.Add(FName(bFloor ? (S.bRoom ? TEXT("PlayableSketch.RoomFloor")
                                                    : TEXT("PlayableSketch.CorridorFloor"))
                                         : (S.Kind == EPlayableSketchPieceKind::Lintel
                                                ? TEXT("PlayableSketch.Lintel")
                                                : TEXT("PlayableSketch.Wall"))));
    }
}
}

bool FPlayableSketchComponentSpec::SameValue(const FPlayableSketchComponentSpec &O) const
{
    return Key == O.Key && SourceId == O.SourceId && OwnerKind == O.OwnerKind && bRoom == O.bRoom &&
           Kind == O.Kind && CenterCm == O.CenterCm && SizeCm == O.SizeCm &&
           Material.Get() == O.Material.Get();
}

void FPlayableSketchComponentRegistry::AssignKeys(TArray<FPlayableSketchComponentSpec> &Specs)
{
    Specs.Sort([](const FPlayableSketchComponentSpec &A, const FPlayableSketchComponentSpec &B) {
        if (A.bRoom != B.bRoom)
            return A.bRoom;
        if (A.SourceId != B.SourceId)
            return A.SourceId.ToString() < B.SourceId.ToString();
        if (A.Kind != B.Kind)
            return static_cast<uint8>(A.Kind) < static_cast<uint8>(B.Kind);
        if (A.CenterCm.X != B.CenterCm.X)
            return A.CenterCm.X < B.CenterCm.X;
        if (A.CenterCm.Y != B.CenterCm.Y)
            return A.CenterCm.Y < B.CenterCm.Y;
        if (A.CenterCm.Z != B.CenterCm.Z)
            return A.CenterCm.Z < B.CenterCm.Z;
        if (A.SizeCm.X != B.SizeCm.X)
            return A.SizeCm.X < B.SizeCm.X;
        if (A.SizeCm.Y != B.SizeCm.Y)
            return A.SizeCm.Y < B.SizeCm.Y;
        return A.SizeCm.Z < B.SizeCm.Z;
    });
    TMap<FString, int32> Counts;
    for (FPlayableSketchComponentSpec &S : Specs)
    {
        const FString Prefix =
            FString::Printf(TEXT("%s/%s/%d"), S.bRoom ? TEXT("Room") : TEXT("Connection"),
                            *S.SourceId.ToString(), static_cast<int32>(S.Kind));
        int32 &Index = Counts.FindOrAdd(Prefix);
        S.Key = FName(*FString::Printf(TEXT("%s/%d"), *Prefix, Index++));
    }
}

bool FPlayableSketchComponentRegistry::IsHealthy(const AActor &Owner) const
{
    int32 SceneCount = 0;
    TArray<UStaticMeshComponent *> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);
    for (const UStaticMeshComponent *C : Components)
        if (IsValid(C) && IsGenerated(*C))
            ++SceneCount;
    if (SceneCount != Entries.Num())
        return false;
    for (const auto &Pair : Entries)
    {
        const UStaticMeshComponent *C = Pair.Value.Component.Get();
        if (!C || C->GetOwner() != &Owner || !C->IsRegistered() || !IsGenerated(*C))
            return false;
    }
    FString Error;
    return Verify(Error);
}

void FPlayableSketchComponentRegistry::Clear(AActor &Owner)
{
    TArray<UStaticMeshComponent *> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);
    for (UStaticMeshComponent *C : Components)
        if (IsValid(C) && IsGenerated(*C))
            Destroy(Owner, C);
    Entries.Reset();
}

bool FPlayableSketchComponentRegistry::Apply(AActor &Owner,
                                             const TArray<FPlayableSketchComponentSpec> &Specs,
                                             bool bFull, FPlayableSketchUpdateStats &Stats,
                                             FString &Error)
{
    Stats = FPlayableSketchUpdateStats();
    Error.Reset();
    if (!Owner.GetWorld() || !Owner.GetRootComponent())
    {
        Error = TEXT("Missing world or root component.");
        return false;
    }
    UStaticMesh *Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Mesh || Mesh->GetBoundingBox().GetSize().GetMin() <= 0.0)
    {
        Error = TEXT("Invalid Engine Cube mesh.");
        return false;
    }
    TMap<FName, FPlayableSketchComponentSpec> Desired;
    for (const FPlayableSketchComponentSpec &S : Specs)
    {
        if (S.Key.IsNone() || !S.SourceId.IsValid() || S.CenterCm.ContainsNaN() ||
            S.SizeCm.ContainsNaN() || S.SizeCm.GetMin() <= 0.0 || Desired.Contains(S.Key))
        {
            Error = TEXT("Invalid or duplicate component descriptor.");
            return false;
        }
        Desired.Add(S.Key, S);
    }
    if (!bFull && !IsHealthy(Owner))
    {
        Error = TEXT("Registry is stale. A full geometry rebuild is required.");
        return false;
    }
    const double DirtyStart = FPlatformTime::Seconds();
    TSet<FName> Changed;
    TArray<FName> Removed;
    auto MarkOwner = [&](const FPlayableSketchComponentSpec &S) {
        if (S.OwnerKind == TEXT("Wall"))
        {
            Stats.DirtyWalls.Add(S.SourceId);
            return;
        }
        (S.bRoom ? Stats.DirtyRooms : Stats.DirtyConnections).Add(S.SourceId);
    };
    for (const auto &Pair : Desired)
    {
        const FEntry *Old = Entries.Find(Pair.Key);
        if (bFull || !Old || !Old->Spec.SameValue(Pair.Value))
        {
            Changed.Add(Pair.Key);
            MarkOwner(Pair.Value);
        }
        else
            ++Stats.Kept;
    }
    for (const auto &Pair : Entries)
    {
        if (bFull || !Desired.Contains(Pair.Key))
        {
            Removed.Add(Pair.Key);
            MarkOwner(Pair.Value.Spec);
        }
    }
    Stats.DirtyMs = (FPlatformTime::Seconds() - DirtyStart) * 1000.0;
    const double ApplyStart = FPlatformTime::Seconds();

    TMap<FName, UStaticMeshComponent *> Staged;
    auto Rollback = [&]() {
        for (const auto &Pair : Staged)
            Destroy(Owner, Pair.Value);
    };
    for (const FName Key : Changed)
    {
        if (!bFull && Entries.Contains(Key))
            continue;
        UStaticMeshComponent *C = NewObject<UStaticMeshComponent>(&Owner, NAME_None, RF_Transient);
        if (!C)
        {
            Rollback();
            Error = TEXT("Component allocation failed.");
            return false;
        }
        Staged.Add(Key, C);
        C->SetMobility(EComponentMobility::Movable);
        C->SetupAttachment(Owner.GetRootComponent());
        Configure(*C, Desired.FindChecked(Key), *Mesh, false);
        Owner.AddInstanceComponent(C);
        C->RegisterComponent();
        if (!C->IsRegistered())
        {
            Rollback();
            Error = TEXT("Component registration failed.");
            return false;
        }
    }

    if (bFull)
    {
        Stats.Removed = Entries.Num();
        Clear(Owner);
    }
    else
    {
        for (const FName Key : Removed)
        {
            Destroy(Owner, Entries.FindChecked(Key).Component.Get());
            Entries.Remove(Key);
            ++Stats.Removed;
        }
    }
    for (const FName Key : Changed)
    {
        UStaticMeshComponent *C = nullptr;
        if (UStaticMeshComponent **NewComponent = Staged.Find(Key))
        {
            C = *NewComponent;
            ++Stats.Created;
        }
        else
        {
            C = Entries.FindChecked(Key).Component.Get();
            ++Stats.Updated;
        }
        const FPlayableSketchComponentSpec &S = Desired.FindChecked(Key);
        Configure(*C, S, *Mesh, true);
        FEntry Entry;
        Entry.Spec = S;
        Entry.Component = C;
        Entries.Add(Key, Entry);
    }
    Stats.ApplyMs = (FPlatformTime::Seconds() - ApplyStart) * 1000.0;
    return true;
}

bool FPlayableSketchComponentRegistry::Verify(FString &Error) const
{
    Error.Reset();
    UStaticMesh *Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Mesh)
    {
        Error = TEXT("Engine Cube missing.");
        return false;
    }
    for (const auto &Pair : Entries)
    {
        const FPlayableSketchComponentSpec &S = Pair.Value.Spec;
        const UStaticMeshComponent *C = Pair.Value.Component.Get();
        const FVector Scale = ScaleFor(S, *Mesh);
        UMaterialInterface *ExpectedMaterial =
            S.Material.IsValid() ? S.Material.Get() : Mesh->GetMaterial(0);
        if (!C || !C->IsRegistered() || C->GetStaticMesh() != Mesh ||
            !C->GetRelativeLocation().Equals(
                S.CenterCm - Mesh->GetBoundingBox().GetCenter() * Scale, 0.001) ||
            !C->GetRelativeScale3D().Equals(Scale, 0.000001) ||
            !C->GetRelativeRotation().IsNearlyZero(0.001) ||
            C->GetMaterial(0) != ExpectedMaterial ||
            C->GetCollisionEnabled() != ECollisionEnabled::QueryAndPhysics ||
            C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block ||
            C->GetCollisionProfileName() != FName(TEXT("BlockAllDynamic")) ||
            C->CanCharacterStepUpOn !=
                (S.Kind == EPlayableSketchPieceKind::Floor ? ECB_Yes : ECB_No) ||
            !C->IsVisible())
        {
            Error = FString::Printf(TEXT("Scene mismatch: %s"), *Pair.Key.ToString());
            return false;
        }
    }
    return true;
}

TMap<FName, FString> FPlayableSketchComponentRegistry::Capture() const
{
    TMap<FName, FString> Result;
    for (const auto &Pair : Entries)
    {
        const UStaticMeshComponent *C = Pair.Value.Component.Get();
        if (!C)
        {
            Result.Add(Pair.Key, TEXT("Missing"));
            continue;
        }
        const FVector L = C->GetRelativeLocation();
        const FVector S = C->GetRelativeScale3D();
        const FRotator R = C->GetRelativeRotation();
        Result.Add(
            Pair.Key,
            FString::Printf(
                TEXT("%.17g,%.17g,%.17g|%.17g,%.17g,%.17g|%.17g,%.17g,%.17g|%s|%s|%d|%d|%d|%s"),
                L.X, L.Y, L.Z, S.X, S.Y, S.Z, R.Pitch, R.Yaw, R.Roll,
                *GetPathNameSafe(C->GetStaticMesh()), *GetPathNameSafe(C->GetMaterial(0)),
                static_cast<int32>(C->GetCollisionEnabled()),
                static_cast<int32>(C->GetCollisionResponseToChannel(ECC_Pawn)),
                static_cast<int32>(C->CanCharacterStepUpOn),
                *C->GetCollisionProfileName().ToString()));
    }
    return Result;
}

TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> FPlayableSketchComponentRegistry::GetPointers()
    const
{
    TMap<FName, TWeakObjectPtr<UStaticMeshComponent>> Result;
    for (const auto &Pair : Entries)
        Result.Add(Pair.Key, Pair.Value.Component);
    return Result;
}
