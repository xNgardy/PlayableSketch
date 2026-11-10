#include "Layout/PlayableSketchCorridorRouting.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

bool FPlayableSketchCorridorRouting::ValidateCandidate(
    const FPlayableSketchCorridorCandidate &Candidate,
    const TArray<FPlayableSketchPlacedRoom> &Rooms,
    const TArray<FPlayableSketchCorridor> &AcceptedCorridors, FString &OutError)
{
    OutError.Reset();

    if (Candidate.Footprints.IsEmpty())
    {
        OutError = TEXT("Candidate has no footprints.");
        return false;
    }

    for (const FPlayableSketchPlacedRoom &Room : Rooms)
    {
        if (!Room.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid Room bounds: %s."), *Room.RoomId.ToString());
            return false;
        }
    }

    for (const FPlayableSketchRect &Footprint : Candidate.Footprints)
    {
        if (!Footprint.IsValid())
        {
            OutError = TEXT("Candidate has an invalid footprint.");
            return false;
        }

        for (const FPlayableSketchPlacedRoom &Room : Rooms)
        {
            if (Footprint.OverlapsInterior(Room.Bounds))
            {
                OutError =
                    FString::Printf(TEXT("Candidate overlaps Room %s."), *Room.RoomId.ToString());
                return false;
            }
        }

        for (const FPlayableSketchCorridor &Accepted : AcceptedCorridors)
        {
            for (const FPlayableSketchRect &ExistingFootprint : Accepted.Footprints)
            {
                if (!ExistingFootprint.IsValid())
                {
                    OutError =
                        FString::Printf(TEXT("Invalid accepted corridor footprint: Connection %s."),
                                        *Accepted.ConnectionId.ToString());
                    return false;
                }

                if (Footprint.OverlapsInterior(ExistingFootprint))
                {
                    OutError =
                        FString::Printf(TEXT("Candidate overlaps corridor of Connection %s."),
                                        *Accepted.ConnectionId.ToString());
                    return false;
                }
            }
        }
    }

    return true;
}

bool FPlayableSketchCorridorRouting::Generate(const FPlayableSketchGraph &Graph,
                                              FPlayableSketchFloorPlan &FloorPlan, int32 GridStepCm,
                                              FString &OutError)
{
    OutError.Reset();

    for (FPlayableSketchCorridor &Corridor : FloorPlan.Corridors)
    {
        Corridor.Footprints.Reset();
    }

    if (GridStepCm <= 0)
    {
        OutError = TEXT("GridStepCm must be positive.");
        return false;
    }

    const TArray<FString> ValidationErrors = FPlayableSketchGraphValidator::Validate(Graph);

    if (!ValidationErrors.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Graph validation failed: %s"), *ValidationErrors[0]);
        return false;
    }

    if (FloorPlan.Corridors.Num() != Graph.Connections.Num())
    {
        OutError = TEXT("Routing failed: endpoint pair count does not match Connection count.");
        return false;
    }

    TArray<FPlayableSketchCorridor> Pending = FloorPlan.Corridors;

    Pending.Sort([](const FPlayableSketchCorridor &A, const FPlayableSketchCorridor &B) {
        return A.ConnectionId.ToString() < B.ConnectionId.ToString();
    });

    TArray<FPlayableSketchCorridor> Accepted;
    TSet<FGuid> RoutedConnectionIds;

    for (FPlayableSketchCorridor &Corridor : Pending)
    {
        if (RoutedConnectionIds.Contains(Corridor.ConnectionId))
        {
            OutError = FString::Printf(TEXT("Routing failed: duplicate Connection %s."),
                                       *Corridor.ConnectionId.ToString());
            return false;
        }

        const FPlayableSketchConnection *Connection =
            Graph.Connections.FindByPredicate([&Corridor](const FPlayableSketchConnection &Item) {
                return Item.ConnectionId == Corridor.ConnectionId;
            });

        if (!Connection || Corridor.DoorA.RoomId != Connection->RoomAId ||
            Corridor.DoorB.RoomId != Connection->RoomBId)
        {
            OutError = FString::Printf(
                TEXT("Routing failed: invalid endpoint ownership for Connection %s."),
                *Corridor.ConnectionId.ToString());
            return false;
        }

        TArray<FPlayableSketchCorridorCandidate> Candidates;
        FString CandidateError;

        if (!FPlayableSketchCorridorRouter::BuildCandidates(Corridor, Connection->CorridorWidthCm,
                                                            GridStepCm, Candidates, CandidateError))
        {
            OutError = FString::Printf(TEXT("Routing failed: Connection %s. %s"),
                                       *Corridor.ConnectionId.ToString(), *CandidateError);
            return false;
        }

        bool bFoundRoute = false;

        for (const FPlayableSketchCorridorCandidate &Candidate : Candidates)
        {
            if (ValidateCandidate(Candidate, FloorPlan.Rooms, Accepted, CandidateError))
            {
                Corridor.Footprints = Candidate.Footprints;
                bFoundRoute = true;
                break;
            }
        }

        if (!bFoundRoute)
        {
            OutError = FString::Printf(
                TEXT("Routing failed: Connection %s, all %d candidates rejected. Last reason: %s"),
                *Corridor.ConnectionId.ToString(), Candidates.Num(), *CandidateError);
            return false;
        }

        RoutedConnectionIds.Add(Corridor.ConnectionId);
        Accepted.Add(Corridor);
    }

    FloorPlan.Corridors = MoveTemp(Accepted);

    return true;
}