#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"

class PLAYABLESKETCH_API FPlayableSketchGraphValidator
{
public:
    static TArray<FString> Validate(const FPlayableSketchGraph& Graph)
    {
        TArray<FString> Errors;
        TSet<FGuid> RoomIds;
        TSet<FGuid> ConnectionIds;

        for (const FPlayableSketchRoom& Room : Graph.Rooms)
        {
            if (!Room.RoomId.IsValid())
            {
                Errors.Add(TEXT("Invalid Room ID."));
            }

            if (RoomIds.Contains(Room.RoomId))
            {
                Errors.Add(FString::Printf(TEXT("Duplicate Room ID: %s"), *Room.RoomId.ToString()));
            }

            RoomIds.Add(Room.RoomId);

            if (Room.WidthCm <= 0 || Room.DepthCm <= 0)
            {
                Errors.Add(FString::Printf(TEXT("Invalid dimension: Room %s, Width=%d, Depth=%d"), *Room.RoomId.ToString(), Room.WidthCm, Room.DepthCm));
            }
        }

        auto RoomExists = [&RoomIds](const FGuid& RoomId)
            {
                return RoomId.IsValid() && RoomIds.Contains(RoomId);
            };

        if (!RoomExists(Graph.StartRoomId))
        {
            Errors.Add(TEXT("Invalid Start: Room does not exist."));
        }

        if (!RoomExists(Graph.GoalRoomId))
        {
            Errors.Add(TEXT("Invalid Goal: Room does not exist."));
        }

        if (Graph.StartRoomId == Graph.GoalRoomId)
        {
            Errors.Add(TEXT("Start and Goal must be different Rooms."));
        }

        for (int32 Index = 0; Index < Graph.Connections.Num(); ++Index)
        {
            const FPlayableSketchConnection& Connection = Graph.Connections[Index];

            const FString Id = Connection.ConnectionId.ToString();

            if (!Connection.ConnectionId.IsValid())
            {
                Errors.Add(TEXT("Invalid Connection ID."));
            }

            if (ConnectionIds.Contains(Connection.ConnectionId))
            {
                Errors.Add(FString::Printf(TEXT("Duplicate Connection ID: %s"), *Id));
            }

            ConnectionIds.Add(Connection.ConnectionId);

            if (!RoomExists(Connection.RoomAId))
            {
                Errors.Add(FString::Printf(TEXT("Missing endpoint: Connection %s, RoomAId %s"), *Id, *Connection.RoomAId.ToString()));
            }

            if (!RoomExists(Connection.RoomBId))
            {
                Errors.Add(FString::Printf(TEXT("Missing endpoint: Connection %s, RoomBId %s"), *Id, *Connection.RoomBId.ToString()));
            }

            if (Connection.RoomAId == Connection.RoomBId)
            {
                Errors.Add(FString::Printf(TEXT("Self connection: %s"), *Id));
            }

            if (Connection.CorridorWidthCm <= 0 || Connection.DoorWidthCm <= 0)
            {
                Errors.Add(FString::Printf(TEXT("Invalid connection dimension: %s"), *Id));
            }

            for (int32 Previous = 0; Previous < Index; ++Previous)
            {
                const FPlayableSketchConnection& Other = Graph.Connections[Previous];

                const bool SameOrder =Connection.RoomAId == Other.RoomAId && Connection.RoomBId == Other.RoomBId;

                const bool ReverseOrder =Connection.RoomAId == Other.RoomBId && Connection.RoomBId == Other.RoomAId;

                if (SameOrder || ReverseOrder)
                {
                    Errors.Add(FString::Printf(TEXT("Duplicate Room pair: Connections %s and %s"), *Other.ConnectionId.ToString(), *Id));

                    break;
                }
            }
        }

        return Errors;
    }
};