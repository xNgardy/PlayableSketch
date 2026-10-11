#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "UObject/UnrealType.h"

#if WITH_EDITOR
#include "ScopedTransaction.h"
#endif

FString UPlayableSketchGraphAsset::GetSourceText() const
{
    FString GraphText;
    FString LayoutText;
    FPlayableSketchGraph::StaticStruct()->ExportText(GraphText, &Graph, nullptr, nullptr, PPF_None, nullptr);
    FPlayableSketchSavedLayout::StaticStruct()->ExportText(LayoutText, &SavedLayout, nullptr, nullptr, PPF_None, nullptr);
    return GraphText + TEXT("|Layout|") + LayoutText;
}

void UPlayableSketchGraphAsset::CaptureRoomIds()
{
    RoomsBeforeEdit.Reset();

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        RoomsBeforeEdit.Add(Room.RoomId);
    }
}

void UPlayableSketchGraphAsset::RemoveDeletedRoomConnections()
{
    TSet<FGuid> CurrentIds;

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        CurrentIds.Add(Room.RoomId);
    }

    TSet<FGuid> DeletedIds;

    for (const FGuid& Id : RoomsBeforeEdit)
    {
        if (!CurrentIds.Contains(Id))
        {
            DeletedIds.Add(Id);
        }
    }

    Graph.Connections.RemoveAll([&](const FPlayableSketchConnection& Connection)
        {
            return DeletedIds.Contains(Connection.RoomAId) || DeletedIds.Contains(Connection.RoomBId);
        });

    SavedLayout.Rooms.RemoveAll([&](const FPlayableSketchSavedPlacement& Placement)
        {
            return DeletedIds.Contains(Placement.RoomId);
        });
}

void UPlayableSketchGraphAsset::AssignUniqueIds()
{
    TSet<FGuid> RoomIds;
    TSet<FGuid> ConnectionIds;

    for (FPlayableSketchRoom& Room : Graph.Rooms)
    {
        while (!Room.RoomId.IsValid() || RoomIds.Contains(Room.RoomId))
        {
            Room.RoomId = FGuid::NewGuid();
        }

        RoomIds.Add(Room.RoomId);
    }

    for (FPlayableSketchConnection& Connection : Graph.Connections)
    {
        while (!Connection.ConnectionId.IsValid() || ConnectionIds.Contains(Connection.ConnectionId))
        {
            Connection.ConnectionId = FGuid::NewGuid();
        }

        ConnectionIds.Add(Connection.ConnectionId);
    }
}

void UPlayableSketchGraphAsset::AddRoom()
{
#if WITH_EDITOR
    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "AddRoom", "Add PlayableSketch Room"));
    Modify();

    FPlayableSketchRoom Room;
    Room.DisplayName = FString::Printf(TEXT("Room_%d"), Graph.Rooms.Num() + 1);
    Graph.Rooms.Add(Room);
    MarkPackageDirty();
#endif
}

void UPlayableSketchGraphAsset::AddConnection()
{
#if WITH_EDITOR
    auto Exists = [&](const FGuid& Id)
        {
            return Graph.Rooms.ContainsByPredicate([&](const FPlayableSketchRoom& Room)
                {
                    return Room.RoomId == Id;
                });
        };

    const bool bDuplicate = Graph.Connections.ContainsByPredicate([&](const FPlayableSketchConnection& Connection)
        {
            return (Connection.RoomAId == NewConnectionRoomAId && Connection.RoomBId == NewConnectionRoomBId)
                || (Connection.RoomAId == NewConnectionRoomBId && Connection.RoomBId == NewConnectionRoomAId);
        });

    if (!Exists(NewConnectionRoomAId) || !Exists(NewConnectionRoomBId)
        || NewConnectionRoomAId == NewConnectionRoomBId || bDuplicate)
    {
        UE_LOG(LogTemp, Error, TEXT("PS-I001: Select two existing, different Rooms without an existing Connection."));
        return;
    }

    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "AddConnection", "Add PlayableSketch Connection"));
    Modify();

    FPlayableSketchConnection Connection;
    Connection.RoomAId = NewConnectionRoomAId;
    Connection.RoomBId = NewConnectionRoomBId;
    Graph.Connections.Add(Connection);
    MarkPackageDirty();
#endif
}

void UPlayableSketchGraphAsset::RemoveRoom()
{
#if WITH_EDITOR
    if (!Graph.Rooms.ContainsByPredicate([&](const FPlayableSketchRoom& Room)
        {
            return Room.RoomId == RoomToRemoveId;
        }))
    {
        UE_LOG(LogTemp, Error, TEXT("PS-I001: RoomToRemoveId does not identify an existing Room."));
        return;
    }

    const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "RemoveRoom", "Remove PlayableSketch Room"));
    Modify();
    CaptureRoomIds();

    Graph.Rooms.RemoveAll([&](const FPlayableSketchRoom& Room)
        {
            return Room.RoomId == RoomToRemoveId;
        });

    RemoveDeletedRoomConnections();
    MarkPackageDirty();
#endif
}

#if WITH_EDITOR
void UPlayableSketchGraphAsset::PreEditChange(FProperty* PropertyAboutToChange)
{
    CaptureRoomIds();
    Super::PreEditChange(PropertyAboutToChange);
}

void UPlayableSketchGraphAsset::PreEditChange(FEditPropertyChain& PropertyAboutToChange)
{
    CaptureRoomIds();
    Super::PreEditChange(PropertyAboutToChange);
}

void UPlayableSketchGraphAsset::PostEditChangeChainProperty(FPropertyChangedChainEvent& Event)
{
    if ((Event.ChangeType & EPropertyChangeType::Duplicate) != 0)
    {
        const int32 RoomIndex = Event.GetArrayIndex(TEXT("Rooms"));
        const int32 ConnectionIndex = Event.GetArrayIndex(TEXT("Connections"));
        if (Graph.Rooms.IsValidIndex(RoomIndex)) Graph.Rooms[RoomIndex].RoomId = FGuid::NewGuid();
        if (Graph.Connections.IsValidIndex(ConnectionIndex)) Graph.Connections[ConnectionIndex].ConnectionId = FGuid::NewGuid();
    }

    if ((Event.ChangeType & (EPropertyChangeType::ArrayAdd | EPropertyChangeType::Duplicate)) != 0)
    {
        AssignUniqueIds();
    }

    if ((Event.ChangeType & (EPropertyChangeType::ArrayRemove | EPropertyChangeType::ArrayClear)) != 0)
    {
        RemoveDeletedRoomConnections();
    }

    MarkPackageDirty();
    Super::PostEditChangeChainProperty(Event);
}
#endif