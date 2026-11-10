#include "Validation/Tests/PlayableSketchFloorPlanTests.h"
#include "Layout/PlayableSketchFloorPlan.h"

void FPlayableSketchFloorPlanTests::Run(const FPlayableSketchGraph &Graph)
{
    if (Graph.Rooms.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("FloorPlan test requires at least one Room."));
        return;
    }

    const FPlayableSketchRoom &SourceRoom = Graph.Rooms[0];

    const int32 OriginalWidthCm = SourceRoom.WidthCm;
    const int32 OriginalDepthCm = SourceRoom.DepthCm;
    const FGuid OriginalRoomId = SourceRoom.RoomId;

    FPlayableSketchPlacedRoom PlacedRoom;
    PlacedRoom.RoomId = SourceRoom.RoomId;
    PlacedRoom.Bounds = FPlayableSketchRect(
        FVector2D(100, 200), FVector2D(100 + SourceRoom.WidthCm, 200 + SourceRoom.DepthCm));

    FPlayableSketchFloorPlan FloorPlan;
    FloorPlan.Rooms.Add(PlacedRoom);

    FloorPlan.Rooms[0].Bounds.Min += FVector2D(50, 50);
    FloorPlan.Rooms[0].Bounds.Max += FVector2D(50, 50);

    const bool bCorrectRoomCount = FloorPlan.Rooms.Num() == 1;
    const bool bSameRoomId = FloorPlan.Rooms[0].RoomId == OriginalRoomId;
    const bool bValidBounds = FloorPlan.Rooms[0].Bounds.IsValid();
    const bool bCorrectPosition = FloorPlan.Rooms[0].Bounds.Min == FVector2D(150, 250);
    const bool bCorrectSize = FloorPlan.Rooms[0].Bounds.Max - FloorPlan.Rooms[0].Bounds.Min ==
                              FVector2D(OriginalWidthCm, OriginalDepthCm);
    const bool bSourceUnchanged = SourceRoom.RoomId == OriginalRoomId &&
                                  SourceRoom.WidthCm == OriginalWidthCm &&
                                  SourceRoom.DepthCm == OriginalDepthCm;

    const bool bPassed = bCorrectRoomCount && bSameRoomId && bValidBounds && bCorrectPosition &&
                         bCorrectSize && bSourceUnchanged;

    if (bPassed)
    {
        UE_LOG(
            LogTemp, Display,
            TEXT(
                "[PASS] FloorPlan stores a placed Room with its source ID. Moving the result preserves size and leaves Graph unchanged."));
    }
    else
    {
        UE_LOG(LogTemp, Error,
               TEXT("[FAIL] Count=%d ID=%d Bounds=%d Position=%d Size=%d SourceUnchanged=%d"),
               bCorrectRoomCount, bSameRoomId, bValidBounds, bCorrectPosition, bCorrectSize,
               bSourceUnchanged);
    }
}
