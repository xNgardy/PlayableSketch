#include "Geometry/PlayableSketchFloorBuilder.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"

namespace
{
    const FName GeneratedFloorTag(TEXT("PlayableSketch.GeneratedFloor"));

    struct FFloorPiece
    {
        FPlayableSketchRect Bounds;
        FGuid SourceId;
        bool bRoom = false;
    };
}

void FPlayableSketchFloorBuilder::Clear(AActor& Owner)
{
    TArray<UStaticMeshComponent*> Components;
    Owner.GetComponents<UStaticMeshComponent>(Components);

    for (UStaticMeshComponent* Component : Components)
    {
        if (IsValid(Component) && Component->ComponentHasTag(GeneratedFloorTag))
        {
            Owner.RemoveInstanceComponent(Component);
            Component->DestroyComponent();
        }
    }
}

TArray<FPlayableSketchRect> FPlayableSketchFloorBuilder::BuildCorridorFloorRects(const TArray<FPlayableSketchRect>& Footprints)
{
    TArray<double> XEdges;
    TArray<double> YEdges;

    for (const FPlayableSketchRect& Footprint : Footprints)
    {
        XEdges.AddUnique(Footprint.Min.X);
        XEdges.AddUnique(Footprint.Max.X);
        YEdges.AddUnique(Footprint.Min.Y);
        YEdges.AddUnique(Footprint.Max.Y);
    }

    XEdges.Sort();
    YEdges.Sort();

    TArray<FPlayableSketchRect> Result;

    for (int32 YIndex = 0; YIndex + 1 < YEdges.Num(); ++YIndex)
    {
        int32 RunStart = INDEX_NONE;

        auto AddRun = [&](int32 RunEnd)
            {
                const FPlayableSketchRect Rect(FVector2D(XEdges[RunStart], YEdges[YIndex]), FVector2D(XEdges[RunEnd], YEdges[YIndex + 1]));

                for (FPlayableSketchRect& Existing : Result)
                {
                    if (Existing.Min.X == Rect.Min.X && Existing.Max.X == Rect.Max.X && Existing.Max.Y == Rect.Min.Y)
                    {
                        Existing.Max.Y = Rect.Max.Y;
                        return;
                    }
                }

                Result.Add(Rect);
            };

        for (int32 XIndex = 0; XIndex + 1 < XEdges.Num(); ++XIndex)
        {
            const FVector2D Center(XEdges[XIndex] + (XEdges[XIndex + 1] - XEdges[XIndex]) * 0.5, YEdges[YIndex] + (YEdges[YIndex + 1] - YEdges[YIndex]) * 0.5);

            bool bCovered = false;

            for (const FPlayableSketchRect& Footprint : Footprints)
            {
                if (Center.X > Footprint.Min.X && Center.X < Footprint.Max.X && Center.Y > Footprint.Min.Y && Center.Y < Footprint.Max.Y)
                {
                    bCovered = true;
                    break;
                }
            }

            if (bCovered && RunStart == INDEX_NONE)
            {
                RunStart = XIndex;
            }

            if (!bCovered && RunStart != INDEX_NONE)
            {
                AddRun(XIndex);
                RunStart = INDEX_NONE;
            }
        }

        if (RunStart != INDEX_NONE)
        {
            AddRun(XEdges.Num() - 1);
        }
    }

    return Result;
}

bool FPlayableSketchFloorBuilder::Build(AActor& Owner, const FPlayableSketchFloorPlan& FloorPlan, double ThicknessCm, FString& OutError)
{
    OutError.Reset();

    if (!Owner.GetWorld() || !Owner.GetRootComponent() || !FMath::IsFinite(ThicknessCm) || ThicknessCm <= 0.0 || FloorPlan.Rooms.IsEmpty())
    {
        OutError = TEXT("Invalid floor build input or missing Actor root.");
        return false;
    }

    TArray<FFloorPiece> Pieces;

    for (const FPlayableSketchPlacedRoom& Room : FloorPlan.Rooms)
    {
        if (!Room.RoomId.IsValid() || !Room.Bounds.IsValid())
        {
            OutError = TEXT("Invalid Room floor input.");
            return false;
        }

        FFloorPiece Piece;
        Piece.Bounds = Room.Bounds;
        Piece.SourceId = Room.RoomId;
        Piece.bRoom = true;

        Pieces.Add(Piece);
    }

    for (const FPlayableSketchCorridor& Corridor : FloorPlan.Corridors)
    {
        if (!Corridor.ConnectionId.IsValid() || Corridor.Footprints.IsEmpty())
        {
            OutError = TEXT("Invalid or unrouted corridor floor input.");
            return false;
        }

        for (const FPlayableSketchRect& Footprint : Corridor.Footprints)
        {
            if (!Footprint.IsValid())
            {
                OutError = TEXT("Invalid corridor floor footprint.");
                return false;
            }
        }

        const TArray<FPlayableSketchRect> FloorRects = BuildCorridorFloorRects(Corridor.Footprints);

        for (const FPlayableSketchRect& Rect : FloorRects)
        {
            FFloorPiece Piece;
            Piece.Bounds = Rect;
            Piece.SourceId = Corridor.ConnectionId;

            Pieces.Add(Piece);
        }
    }

    UStaticMesh* CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));

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

    for (const FFloorPiece& Piece : Pieces)
    {
        const FVector2D SizeCm = Piece.Bounds.Max - Piece.Bounds.Min;
        const FVector2D CenterCm = Piece.Bounds.Min + SizeCm * 0.5;

        const FVector Scale(SizeCm.X / MeshSize.X, SizeCm.Y / MeshSize.Y, ThicknessCm / MeshSize.Z);
        const FVector CenterLocation(CenterCm.X, CenterCm.Y, -ThicknessCm * 0.5);
        const FVector Location = CenterLocation - MeshCenter * Scale;

        UStaticMeshComponent* Component = NewObject<UStaticMeshComponent>(&Owner, NAME_None, RF_Transient);

        if (!Component)
        {
            Clear(Owner);
            OutError = TEXT("Floor component creation failed.");
            return false;
        }

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

        Component->ComponentTags.Add(GeneratedFloorTag);
        Component->ComponentTags.Add(FName(Piece.bRoom ? TEXT("PlayableSketch.RoomFloor") : TEXT("PlayableSketch.CorridorFloor")));
        Component->ComponentTags.Add(FName(*FString::Printf(TEXT("%s=%s"), Piece.bRoom ? TEXT("RoomId") : TEXT("ConnectionId"), *Piece.SourceId.ToString())));

        Owner.AddInstanceComponent(Component);
        Component->RegisterComponent();
    }

    UE_LOG(LogTemp, Display, TEXT("Floors generated: Rooms=%d Connections=%d MeshComponents=%d"), FloorPlan.Rooms.Num(), FloorPlan.Corridors.Num(), Pieces.Num());

    return true;
}