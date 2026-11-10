#include "Geometry/PlayableSketchWallBuilder.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"

namespace
{
const FName GeneratedWallTag(TEXT("PlayableSketch.GeneratedWall"));
}

void FPlayableSketchWallBuilder::Clear(AActor &Owner)
{
    TArray<UStaticMeshComponent *> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);

    for (UStaticMeshComponent *Component : Components)
    {
        if (IsValid(Component) && Component->ComponentHasTag(GeneratedWallTag))
        {
            Owner.RemoveInstanceComponent(Component);
            Component->DestroyComponent();
        }
    }
}

bool FPlayableSketchWallBuilder::Build(AActor &Owner,
                                       const TArray<FPlayableSketchGeometryDescriptor> &Pieces,
                                       UMaterialInterface *Material, FString &OutError)
{
    OutError.Reset();

    if (!Owner.GetWorld() || !Owner.GetRootComponent() || Pieces.IsEmpty())
    {
        OutError = TEXT("Invalid wall build input or missing Actor root.");
        return false;
    }

    for (const FPlayableSketchGeometryDescriptor &Piece : Pieces)
    {
        if (!Piece.SourceId.IsValid() || Piece.CenterCm.ContainsNaN() ||
            Piece.SizeCm.ContainsNaN() || Piece.SizeCm.X <= 0.0 || Piece.SizeCm.Y <= 0.0 ||
            Piece.SizeCm.Z <= 0.0)
        {
            OutError = TEXT("Invalid wall descriptor.");
            return false;
        }
    }

    UStaticMesh *CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));

    if (!CubeMesh)
    {
        OutError = TEXT("Engine Cube mesh could not be loaded.");
        return false;
    }

    const FBox MeshBounds = CubeMesh->GetBoundingBox();
    const FVector MeshSize = MeshBounds.GetSize();
    const FVector MeshCenter = MeshBounds.GetCenter();

    if (MeshSize.X <= 0.0 || MeshSize.Y <= 0.0 || MeshSize.Z <= 0.0)
    {
        OutError = TEXT("Engine Cube mesh has invalid dimensions.");
        return false;
    }

    Clear(Owner);

    int32 WallCount = 0;
    int32 LintelCount = 0;

    for (const FPlayableSketchGeometryDescriptor &Piece : Pieces)
    {
        const FVector Scale(Piece.SizeCm.X / MeshSize.X, Piece.SizeCm.Y / MeshSize.Y,
                            Piece.SizeCm.Z / MeshSize.Z);

        const FVector Location = Piece.CenterCm - MeshCenter * Scale;

        UStaticMeshComponent *Component =
            NewObject<UStaticMeshComponent>(&Owner, NAME_None, RF_Transient);

        if (!Component)
        {
            Clear(Owner);
            OutError = TEXT("Wall component creation failed.");
            return false;
        }

        const bool bLintel = Piece.Role == EPlayableSketchGeometryRole::Lintel;

        Component->SetMobility(EComponentMobility::Movable);
        Component->SetStaticMesh(CubeMesh);
        Component->SetupAttachment(Owner.GetRootComponent());
        Component->SetRelativeLocation(Location);
        Component->SetRelativeScale3D(Scale);
        Component->SetCollisionProfileName(TEXT("BlockAllDynamic"));
        Component->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        Component->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
        Component->SetGenerateOverlapEvents(false);
        Component->SetCanEverAffectNavigation(false);
        Component->CanCharacterStepUpOn = ECB_No;

        if (Material)
        {
            Component->SetMaterial(0, Material);
        }

        Component->ComponentTags.Add(GeneratedWallTag);
        Component->ComponentTags.Add(
            FName(bLintel ? TEXT("PlayableSketch.Lintel") : TEXT("PlayableSketch.Wall")));

        Component->ComponentTags.Add(FName(
            *FString::Printf(TEXT("%s=%s"), Piece.bRoom ? TEXT("RoomId") : TEXT("ConnectionId"),
                             *Piece.SourceId.ToString())));

        Owner.AddInstanceComponent(Component);
        Component->RegisterComponent();

        if (bLintel)
        {
            ++LintelCount;
        }
        else
        {
            ++WallCount;
        }
    }

    UE_LOG(LogTemp, Display, TEXT("Walls generated: Walls=%d Lintels=%d MeshComponents=%d"),
           WallCount, LintelCount, Pieces.Num());

    return true;
}