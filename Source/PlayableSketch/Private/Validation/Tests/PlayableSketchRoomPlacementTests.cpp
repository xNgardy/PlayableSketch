#include "Validation/Tests/PlayableSketchRoomPlacementTests.h"
#include "Layout/PlayableSketchLayoutGenerator.h"

void FPlayableSketchRoomPlacementTests::Run(const FPlayableSketchGraph &Graph)
{
    if (Graph.Rooms.Num() < 2)
    {
        UE_LOG(LogTemp, Error, TEXT("Room placement tests require at least two Rooms."));
        return;
    }

    constexpr int32 GridStepCm = 50;
    constexpr int32 RoomGapCm = 100;

    FPlayableSketchFloorPlan Baseline;
    FString Error;

    if (!FPlayableSketchLayoutGenerator::Generate(Graph, GridStepCm, RoomGapCm, Baseline, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), *Error);
        return;
    }

    if (Baseline.Rooms.Num() != Graph.Rooms.Num() ||
        Baseline.Rooms[0].RoomId != Graph.StartRoomId ||
        Baseline.Rooms[0].Bounds.Min != FVector2D::ZeroVector)
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] Room count or Start placement is incorrect."));
        return;
    }

    auto IsOnGrid = [](double ValueCm) { return FMath::IsNearlyZero(FMath::Fmod(ValueCm, 50.0)); };

    for (int32 Index = 0; Index < Baseline.Rooms.Num(); ++Index)
    {
        const FPlayableSketchPlacedRoom &Room = Baseline.Rooms[Index];

        if (!Room.Bounds.IsValid() || !IsOnGrid(Room.Bounds.Min.X) ||
            !IsOnGrid(Room.Bounds.Min.Y) || !IsOnGrid(Room.Bounds.Max.X) ||
            !IsOnGrid(Room.Bounds.Max.Y))
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] Invalid or unaligned bounds: Room %s"),
                   *Room.RoomId.ToString());
            return;
        }

        for (int32 Previous = 0; Previous < Index; ++Previous)
        {
            if (!Room.Bounds.HasRequiredGap(Baseline.Rooms[Previous].Bounds, RoomGapCm))
            {
                UE_LOG(LogTemp, Error, TEXT("[FAIL] Room spacing is insufficient."));
                return;
            }
        }

        UE_LOG(LogTemp, Display, TEXT("Placed Room %s | Min=(%.0f, %.0f) Max=(%.0f, %.0f)"),
               *Room.RoomId.ToString(), Room.Bounds.Min.X, Room.Bounds.Min.Y, Room.Bounds.Max.X,
               Room.Bounds.Max.Y);
    }

    UE_LOG(LogTemp, Display,
           TEXT("[PASS] Start position, Room count, grid alignment and spacing are correct."));

    auto HasSamePlacement = [](const FPlayableSketchFloorPlan &A,
                               const FPlayableSketchFloorPlan &B) {
        if (A.Rooms.Num() != B.Rooms.Num())
        {
            return false;
        }

        for (int32 Index = 0; Index < A.Rooms.Num(); ++Index)
        {
            const FPlayableSketchPlacedRoom &RoomA = A.Rooms[Index];
            const FPlayableSketchPlacedRoom &RoomB = B.Rooms[Index];

            if (RoomA.RoomId != RoomB.RoomId || RoomA.Bounds.Min != RoomB.Bounds.Min ||
                RoomA.Bounds.Max != RoomB.Bounds.Max)
            {
                return false;
            }
        }

        return true;
    };

    for (int32 RunIndex = 0; RunIndex < 10; ++RunIndex)
    {
        FPlayableSketchFloorPlan Repeated;

        if (!FPlayableSketchLayoutGenerator::Generate(Graph, GridStepCm, RoomGapCm, Repeated,
                                                      Error))
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] Repeat generation: %s"), *Error);
            return;
        }

        if (!HasSamePlacement(Baseline, Repeated))
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] Room placement changed on repeat generation."));
            return;
        }
    }

    UE_LOG(LogTemp, Display,
           TEXT("[PASS] 10 repeat generations produced identical Room placements."));

    FPlayableSketchGraph ReorderedGraph = Graph;

    ReorderedGraph.Rooms.Swap(0, ReorderedGraph.Rooms.Num() - 1);

    if (ReorderedGraph.Connections.Num() > 1)
    {
        ReorderedGraph.Connections.Swap(0, ReorderedGraph.Connections.Num() - 1);
    }

    FPlayableSketchFloorPlan ReorderedResult;

    if (!FPlayableSketchLayoutGenerator::Generate(ReorderedGraph, GridStepCm, RoomGapCm,
                                                  ReorderedResult, Error))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] Reordered generation: %s"), *Error);
        return;
    }

    if (!HasSamePlacement(Baseline, ReorderedResult))
    {
        UE_LOG(LogTemp, Error, TEXT("[FAIL] Array order changed Room placement."));
        return;
    }

    UE_LOG(LogTemp, Display,
           TEXT("[PASS] Changing Room and Connection array order preserved placement."));
    UE_LOG(LogTemp, Display, TEXT("Room placement tests passed. Placed Rooms: %d"),
           Baseline.Rooms.Num());
}