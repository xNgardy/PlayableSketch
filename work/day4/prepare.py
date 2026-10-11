from pathlib import Path
import re
import shutil
import json

root = Path.cwd()
out = root / 'outputs/day4'
files = {}

def save(path, text):
    path = 'Source/PlayableSketch/' + path
    files[path] = text.strip() + '\n'
    target = out / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(files[path], encoding='utf-8')

def original(path):
    return (root / 'Source/PlayableSketch' / path).read_text(encoding='utf-8-sig')

floorplan = original('Public/Layout/PlayableSketchFloorPlan.h')
floorplan = floorplan.replace('#include "Layout/PlayableSketchRect.h"', '#include "Layout/PlayableSketchRect.h"\n#include "PlayableSketchFloorPlan.generated.h"')
floorplan = floorplan.replace('enum class EPlayableSketchWallSide', 'UENUM(BlueprintType)\nenum class EPlayableSketchWallSide')
save('Public/Layout/PlayableSketchFloorPlan.h', floorplan)

room = original('Public/SpatialGraph/PlayableSketchRoom.h')
room = room.replace('USTRUCT(BlueprintType)', '''UENUM(BlueprintType)
enum class EPlayableSketchPositionMode : uint8
{
    Auto,
    Locked
};

USTRUCT(BlueprintType)''')
room = room.replace('    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))\n    int32 WidthCm', '''    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement")
    EPlayableSketchPositionMode PositionMode = EPlayableSketchPositionMode::Auto;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Placement", meta = (EditCondition = "PositionMode == EPlayableSketchPositionMode::Locked"))
    FVector2D PositionCm = FVector2D::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "100"))
    int32 WidthCm''')
save('Public/SpatialGraph/PlayableSketchRoom.h', room)

save('Public/SpatialGraph/PlayableSketchConnection.h', r'''
#pragma once

#include "CoreMinimal.h"
#include "Layout/PlayableSketchFloorPlan.h"
#include "PlayableSketchConnection.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchDoorOverride
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
    bool bManual = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door", meta = (EditCondition = "bManual"))
    EPlayableSketchWallSide WallSide = EPlayableSketchWallSide::East;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door", meta = (EditCondition = "bManual"))
    double OffsetCm = 300.0;
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchConnection
{
    GENERATED_BODY()

public:
    FPlayableSketchConnection() : ConnectionId(FGuid::NewGuid())
    {
    }

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Identity", meta = (IgnoreForMemberInitializationTest))
    FGuid ConnectionId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomAId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rooms")
    FGuid RoomBId = FGuid();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 CorridorWidthCm = 200;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Dimensions", meta = (ClampMin = "1", UIMin = "1"))
    int32 DoorWidthCm = 150;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Doors")
    FPlayableSketchDoorOverride DoorASettings;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Doors")
    FPlayableSketchDoorOverride DoorBSettings;
};
''')

save('Public/SpatialGraph/PlayableSketchGraphAsset.h', r'''
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "PlayableSketchGraphAsset.generated.h"

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedPlacement
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FGuid RoomId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FVector2D MinCm = FVector2D::ZeroVector;
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchSavedLayout
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    TArray<FPlayableSketchSavedPlacement> Rooms;
};

UCLASS(BlueprintType)
class PLAYABLESKETCH_API UPlayableSketchGraphAsset : public UDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Graph")
    FPlayableSketchGraph Graph;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Layout")
    FPlayableSketchSavedLayout SavedLayout;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomAId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid NewConnectionRoomBId;

    UPROPERTY(EditAnywhere, Transient, Category = "Authoring")
    FGuid RoomToRemoveId;

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddRoom();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void AddConnection();

    UFUNCTION(CallInEditor, Category = "Authoring")
    void RemoveRoom();

    FString GetSourceText() const;

#if WITH_EDITOR
    virtual void PreEditChange(FProperty* PropertyAboutToChange) override;
    virtual void PreEditChange(FEditPropertyChain& PropertyAboutToChange) override;
    virtual void PostEditChangeChainProperty(FPropertyChangedChainEvent& PropertyChangedEvent) override;
#endif

private:
    TSet<FGuid> RoomsBeforeEdit;
    void CaptureRoomIds();
    void RemoveDeletedRoomConnections();
    void AssignUniqueIds();
};
''')

save('Private/SpatialGraph/PlayableSketchGraphAsset.cpp', r'''
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
''')

layout = original('Private/Layout/PlayableSketchLayoutGenerator.cpp')
layout = layout.replace('    double NextX = 0.0;', '''    TArray<FPlayableSketchPlacedRoom> Occupied;

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (Room.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        FPlayableSketchPlacedRoom LockedRoom;
        LockedRoom.RoomId = Room.RoomId;
        LockedRoom.Bounds = FPlayableSketchRect(Room.PositionCm, Room.PositionCm + FVector2D(Room.WidthCm, Room.DepthCm));

        if (!LockedRoom.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid Locked position: Room %s."), *Room.RoomId.ToString());
            return false;
        }

        for (const FPlayableSketchPlacedRoom& Existing : Occupied)
        {
            if (!LockedRoom.Bounds.HasRequiredGap(Existing.Bounds, RoomGapCm))
            {
                OutError = FString::Printf(TEXT("Locked Rooms overlap or violate RoomGapCm: %s and %s."), *Room.RoomId.ToString(), *Existing.RoomId.ToString());
                return false;
            }
        }

        Occupied.Add(LockedRoom);
    }

    double NextX = 0.0;''')
layout = layout.replace('''        if (!FPlayableSketchPlacementSearch::FindPlacement(RoomId, SizeCm, PreferredMinCm, Result.Rooms, GridStepCm, RoomGapCm, MaxPlacementAttempts, PlacedRoom, OutError))
        {
            return false;
        }''', '''        if (SourceRoom->PositionMode == EPlayableSketchPositionMode::Locked)
        {
            PlacedRoom.RoomId = RoomId;
            PlacedRoom.Bounds = FPlayableSketchRect(SourceRoom->PositionCm, SourceRoom->PositionCm + SizeCm);
        }
        else
        {
            if (!FPlayableSketchPlacementSearch::FindPlacement(RoomId, SizeCm, PreferredMinCm, Occupied, GridStepCm, RoomGapCm, MaxPlacementAttempts, PlacedRoom, OutError))
            {
                return false;
            }

            Occupied.Add(PlacedRoom);
        }''')
save('Private/Layout/PlayableSketchLayoutGenerator.cpp', layout)

door = original('Private/Layout/PlayableSketchDoorGenerator.cpp')
helper = r'''
namespace
{
    bool ApplyDoorOverride(
        const FPlayableSketchPlacedRoom& Room,
        const FPlayableSketchDoorOverride& Override,
        int32 CornerMarginCm,
        FPlayableSketchDoorEndpoint& Door,
        FString& OutError)
    {
        if (!Override.bManual)
        {
            return true;
        }

        if (!FPlayableSketchDoorGenerator::CreateEndpoint(Room, Override.WallSide, Door.WidthCm, CornerMarginCm, Door, OutError))
        {
            return false;
        }

        const bool bHorizontal = Override.WallSide == EPlayableSketchWallSide::North || Override.WallSide == EPlayableSketchWallSide::South;
        const double LengthCm = bHorizontal ? Room.Bounds.Max.X - Room.Bounds.Min.X : Room.Bounds.Max.Y - Room.Bounds.Min.Y;

        if (!FMath::IsFinite(Override.OffsetCm)
            || Override.OffsetCm - Door.WidthCm * 0.5 < CornerMarginCm
            || Override.OffsetCm + Door.WidthCm * 0.5 > LengthCm - CornerMarginCm)
        {
            OutError = FString::Printf(TEXT("PS-V002: Manual Door offset does not fit Room %s."), *Room.RoomId.ToString());
            return false;
        }

        if (bHorizontal)
        {
            Door.PositionCm.X = Room.Bounds.Min.X + Override.OffsetCm;
        }
        else
        {
            Door.PositionCm.Y = Room.Bounds.Min.Y + Override.OffsetCm;
        }

        return true;
    }
}
'''
door = door.replace('#include "SpatialGraph/PlayableSketchGraphValidator.h"', '#include "SpatialGraph/PlayableSketchGraphValidator.h"\n' + helper)
door = door.replace('CreateEndpoint(*RoomA, SideA,', 'CreateEndpoint(*RoomA, Connection.DoorASettings.bManual ? Connection.DoorASettings.WallSide : SideA,')
door = door.replace('CreateEndpoint(*RoomB, SideB,', 'CreateEndpoint(*RoomB, Connection.DoorBSettings.bManual ? Connection.DoorBSettings.WallSide : SideB,')
door = door.replace('''        for (const FPlayableSketchCorridor& Existing : Result)''', '''        if (!ApplyDoorOverride(*RoomA, Connection.DoorASettings, CornerMarginCm, Corridor.DoorA, OutError)
            || !ApplyDoorOverride(*RoomB, Connection.DoorBSettings, CornerMarginCm, Corridor.DoorB, OutError))
        {
            return false;
        }

        for (const FPlayableSketchCorridor& Existing : Result)''')
save('Private/Layout/PlayableSketchDoorGenerator.cpp', door)

save('PlayableSketch.Build.cs', r'''
using UnrealBuildTool;

public class PlayableSketch : ModuleRules
{
    public PlayableSketch(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore" });

        if (Target.bBuildEditor)
        {
            PrivateDependencyModuleNames.Add("UnrealEd");
        }
    }
}
''')

save('Public/Validation/PlayableSketchValidation.h', r'''
#pragma once

#include "CoreMinimal.h"
#include "SpatialGraph/PlayableSketchGraph.h"
#include "Geometry/PlayableSketchWallGeometry.h"
#include "PlayableSketchValidation.generated.h"

UENUM(BlueprintType)
enum class EPlayableSketchIssueSeverity : uint8
{
    Info,
    Warning,
    Error
};

USTRUCT(BlueprintType)
struct PLAYABLESKETCH_API FPlayableSketchValidationIssue
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FName Code;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    TArray<FGuid> ElementIds;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    EPlayableSketchIssueSeverity Severity = EPlayableSketchIssueSeverity::Error;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FString Message;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    bool bHasPosition = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector PositionCm = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Validation")
    FVector ExtentCm = FVector(25.0, 25.0, 25.0);
};

struct PLAYABLESKETCH_API FPlayableSketchValidationSettings
{
    FPlayableSketchWallSettings Walls;
    int32 GridStepCm = 50;
    double MinCorridorWidthCm = 100.0;
    double PawnRadiusCm = 40.0;
    double PawnHeightCm = 180.0;
    double ClearanceCm = 10.0;

    double RequiredWidthCm() const
    {
        return FMath::Max(MinCorridorWidthCm, 2.0 * (PawnRadiusCm + ClearanceCm));
    }
};

class PLAYABLESKETCH_API FPlayableSketchValidation
{
public:
    static bool HasErrors(const TArray<FPlayableSketchValidationIssue>& Issues);

    static TArray<FPlayableSketchValidationIssue> ValidateInput(
        const FPlayableSketchGraph& Graph,
        const FPlayableSketchValidationSettings& Settings);

    static TArray<FPlayableSketchValidationIssue> ValidatePlan(
        const FPlayableSketchGraph& Graph,
        const FPlayableSketchFloorPlan& Plan,
        const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
        const FPlayableSketchValidationSettings& Settings);
};
''')

save('Private/Validation/PlayableSketchValidation.cpp', r'''
#include "Validation/PlayableSketchValidation.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

namespace
{
    const double ToleranceCm = 0.01;

    void AddIssue(
        TArray<FPlayableSketchValidationIssue>& Issues,
        const TCHAR* Code,
        const FString& Message,
        const TArray<FGuid>& Ids,
        const FVector& Position,
        const FVector& Extent = FVector(25.0, 25.0, 25.0))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = FName(Code);
        Issue.Message = Message;
        Issue.ElementIds = Ids;
        Issue.bHasPosition = !Position.ContainsNaN();
        Issue.PositionCm = Issue.bHasPosition ? Position : FVector::ZeroVector;
        Issue.ExtentCm = Extent;
        Issues.Add(Issue);
    }

    FVector RoomCenter(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Center = (Room.Bounds.Min + Room.Bounds.Max) * 0.5;
        return FVector(Center.X, Center.Y, 25.0);
    }

    FVector RoomExtent(const FPlayableSketchPlacedRoom& Room)
    {
        const FVector2D Half = (Room.Bounds.Max - Room.Bounds.Min) * 0.5;
        return FVector(Half.X, Half.Y, 25.0);
    }

    bool GetWallFrame(
        const FPlayableSketchPlacedRoom& Room,
        EPlayableSketchWallSide Side,
        FVector2D& Origin,
        FVector2D& Tangent,
        FVector2D& Normal,
        double& Length)
    {
        const FVector2D Size = Room.Bounds.Max - Room.Bounds.Min;

        switch (Side)
        {
        case EPlayableSketchWallSide::North:
            Origin = FVector2D(Room.Bounds.Min.X, Room.Bounds.Max.Y);
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, 1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::South:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(1.0, 0.0);
            Normal = FVector2D(0.0, -1.0);
            Length = Size.X;
            return true;

        case EPlayableSketchWallSide::East:
            Origin = FVector2D(Room.Bounds.Max.X, Room.Bounds.Min.Y);
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(1.0, 0.0);
            Length = Size.Y;
            return true;

        case EPlayableSketchWallSide::West:
            Origin = Room.Bounds.Min;
            Tangent = FVector2D(0.0, 1.0);
            Normal = FVector2D(-1.0, 0.0);
            Length = Size.Y;
            return true;
        }

        return false;
    }

    bool FootprintsConnected(const TArray<FPlayableSketchRect>& Rects)
    {
        if (Rects.IsEmpty())
        {
            return false;
        }

        TSet<int32> Visited;
        TArray<int32> Queue;
        Queue.Add(0);
        Visited.Add(0);

        for (int32 Head = 0; Head < Queue.Num(); ++Head)
        {
            const FPlayableSketchRect& A = Rects[Queue[Head]];

            for (int32 Index = 0; Index < Rects.Num(); ++Index)
            {
                if (Visited.Contains(Index))
                {
                    continue;
                }

                const FPlayableSketchRect& B = Rects[Index];
                const double OverlapX = FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X);
                const double OverlapY = FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y);
                const bool bConnected = (OverlapX > ToleranceCm && OverlapY >= -ToleranceCm)
                    || (OverlapY > ToleranceCm && OverlapX >= -ToleranceCm);

                if (bConnected)
                {
                    Visited.Add(Index);
                    Queue.Add(Index);
                }
            }
        }

        return Visited.Num() == Rects.Num();
    }

    bool CoversDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FVector2D& Origin,
        const FVector2D& Tangent,
        const FVector2D& Normal,
        const TArray<FPlayableSketchRect>& Rects)
    {
        const double Center = FVector2D::DotProduct(Door.PositionCm - Origin, Tangent);
        const double Start = Center - Door.WidthCm * 0.5;
        const double End = Center + Door.WidthCm * 0.5;
        TArray<FVector2D> Intervals;

        for (const FPlayableSketchRect& Rect : Rects)
        {
            bool bContact = false;

            if (Normal.X > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.X, Origin.X, ToleranceCm);
            }
            else if (Normal.X < 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.X, Origin.X, ToleranceCm);
            }
            else if (Normal.Y > 0.0)
            {
                bContact = FMath::IsNearlyEqual(Rect.Min.Y, Origin.Y, ToleranceCm);
            }
            else
            {
                bContact = FMath::IsNearlyEqual(Rect.Max.Y, Origin.Y, ToleranceCm);
            }

            if (bContact)
            {
                const double Min = FVector2D::DotProduct(Rect.Min - Origin, Tangent);
                const double Max = FVector2D::DotProduct(Rect.Max - Origin, Tangent);
                Intervals.Add(FVector2D(Min, Max));
            }
        }

        Intervals.Sort([](const FVector2D& A, const FVector2D& B)
        {
            return A.X < B.X;
        });

        double Cursor = Start;

        for (const FVector2D& Interval : Intervals)
        {
            if (Interval.Y < Cursor - ToleranceCm)
            {
                continue;
            }

            if (Interval.X > Cursor + ToleranceCm)
            {
                return false;
            }

            Cursor = FMath::Max(Cursor, Interval.Y);

            if (Cursor >= End - ToleranceCm)
            {
                return true;
            }
        }

        return false;
    }

    bool BoxesOverlap(const FBox& A, const FBox& B)
    {
        return FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X) > ToleranceCm
            && FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y) > ToleranceCm
            && FMath::Min(A.Max.Z, B.Max.Z) - FMath::Max(A.Min.Z, B.Min.Z) > ToleranceCm;
    }

    bool CheckDoor(
        const FPlayableSketchDoorEndpoint& Door,
        const FGuid& ExpectedRoomId,
        const FPlayableSketchConnection& Connection,
        const FPlayableSketchFloorPlan& Plan,
        const TArray<FPlayableSketchRect>& Rects,
        const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
        const FPlayableSketchValidationSettings& Settings,
        TArray<FPlayableSketchValidationIssue>& Issues)
    {
        const FVector Position(Door.PositionCm.X, Door.PositionCm.Y, 40.0);
        const TArray<FGuid> Ids = { Connection.ConnectionId, ExpectedRoomId };
        const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item)
        {
            return Item.RoomId == ExpectedRoomId;
        });

        FVector2D Origin;
        FVector2D Tangent;
        FVector2D Normal;
        double Length = 0.0;

        if (!Room || Door.RoomId != ExpectedRoomId
            || !Room->Bounds.IsValid()
            || !FMath::IsFinite(Door.PositionCm.X) || !FMath::IsFinite(Door.PositionCm.Y)
            || !FMath::IsFinite(Door.WidthCm) || Door.WidthCm <= 0.0
            || !GetWallFrame(*Room, Door.WallSide, Origin, Tangent, Normal, Length))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door ownership, side or coordinates are invalid."), Ids, Position);
            return false;
        }

        const FVector2D Delta = Door.PositionCm - Origin;
        const double Offset = FVector2D::DotProduct(Delta, Tangent);

        if (!FMath::IsNearlyZero(FVector2D::DotProduct(Delta, Normal), ToleranceCm)
            || Offset - Door.WidthCm * 0.5 < Settings.Walls.CornerMarginCm
            || Offset + Door.WidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm
            || !FMath::IsNearlyEqual(Door.WidthCm, static_cast<double>(Connection.DoorWidthCm), ToleranceCm))
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door must lie on its wall, respect corner margin and match DoorWidthCm."), Ids, Position);
            return false;
        }

        if (Door.WidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door is too narrow for the configured Pawn and clearance."), Ids, Position);
            return false;
        }

        if (!CoversDoor(Door, Origin, Tangent, Normal, Rects))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor does not cover the full Door opening."), Ids, Position);
            return false;
        }

        const FVector2D Center2D = Door.PositionCm + Normal * (Settings.Walls.ThicknessCm * 0.5);
        const FVector OpeningCenter(Center2D.X, Center2D.Y, Settings.Walls.DoorHeightCm * 0.5);
        const FVector OpeningSize = Tangent.X != 0.0
            ? FVector(Door.WidthCm, Settings.Walls.ThicknessCm, Settings.Walls.DoorHeightCm)
            : FVector(Settings.Walls.ThicknessCm, Door.WidthCm, Settings.Walls.DoorHeightCm);
        const FBox OpeningBox(OpeningCenter - OpeningSize * 0.5, OpeningCenter + OpeningSize * 0.5);

        bool bBlocked = false;
        bool bHasLintel = Settings.Walls.DoorHeightCm == Settings.Walls.HeightCm;

        for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
        {
            if (Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN())
            {
                continue;
            }

            const FBox Box(Piece.CenterCm - Piece.SizeCm * 0.5, Piece.CenterCm + Piece.SizeCm * 0.5);

            if (BoxesOverlap(OpeningBox, Box))
            {
                bBlocked = true;
                AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated wall or lintel blocks the Door opening."), { Connection.ConnectionId, ExpectedRoomId, Piece.SourceId }, Position);
            }

            if (Piece.bRoom && Piece.SourceId == ExpectedRoomId && Piece.Role == EPlayableSketchGeometryRole::Lintel
                && Box.Min.X <= OpeningBox.Min.X + ToleranceCm && Box.Max.X >= OpeningBox.Max.X - ToleranceCm
                && Box.Min.Y <= OpeningBox.Min.Y + ToleranceCm && Box.Max.Y >= OpeningBox.Max.Y - ToleranceCm
                && FMath::IsNearlyEqual(Box.Min.Z, Settings.Walls.DoorHeightCm, ToleranceCm)
                && FMath::IsNearlyEqual(Box.Max.Z, Settings.Walls.HeightCm, ToleranceCm))
            {
                bHasLintel = true;
            }
        }

        if (!bHasLintel)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Expected Door lintel is missing or has incorrect dimensions."), Ids, Position);
        }

        return !bBlocked && bHasLintel;
    }
}

bool FPlayableSketchValidation::HasErrors(const TArray<FPlayableSketchValidationIssue>& Issues)
{
    return Issues.ContainsByPredicate([](const FPlayableSketchValidationIssue& Issue)
    {
        return Issue.Severity == EPlayableSketchIssueSeverity::Error;
    });
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidateInput(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues;

    for (const FString& Error : FPlayableSketchGraphValidator::Validate(Graph))
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = Error;
        for (const FPlayableSketchRoom& Room : Graph.Rooms)
        {
            if (Error.Contains(Room.RoomId.ToString()))
            {
                Issue.ElementIds.AddUnique(Room.RoomId);
            }
        }
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (Error.Contains(Connection.ConnectionId.ToString()))
            {
                Issue.ElementIds.AddUnique(Connection.ConnectionId);
            }
        }
        if (Error.StartsWith(TEXT("Invalid Start")))
        {
            Issue.ElementIds.AddUnique(Graph.StartRoomId);
        }
        if (Error.StartsWith(TEXT("Invalid Goal")))
        {
            Issue.ElementIds.AddUnique(Graph.GoalRoomId);
        }
        Issues.Add(Issue);
    }

    const bool bSettingsValid = Settings.GridStepCm > 0
        && FMath::IsFinite(Settings.MinCorridorWidthCm) && Settings.MinCorridorWidthCm > 0.0
        && FMath::IsFinite(Settings.PawnRadiusCm) && Settings.PawnRadiusCm > 0.0
        && FMath::IsFinite(Settings.PawnHeightCm) && Settings.PawnHeightCm > 0.0
        && FMath::IsFinite(Settings.ClearanceCm) && Settings.ClearanceCm >= 0.0
        && FMath::IsFinite(Settings.Walls.HeightCm) && Settings.Walls.HeightCm > 0.0
        && FMath::IsFinite(Settings.Walls.ThicknessCm) && Settings.Walls.ThicknessCm > 0.0
        && FMath::IsFinite(Settings.Walls.DoorHeightCm) && Settings.Walls.DoorHeightCm > 0.0
        && Settings.Walls.DoorHeightCm <= Settings.Walls.HeightCm
        && FMath::IsFinite(Settings.Walls.CornerMarginCm) && Settings.Walls.CornerMarginCm >= 0.0;

    if (!bSettingsValid)
    {
        FPlayableSketchValidationIssue Issue;
        Issue.Code = TEXT("PS-I001");
        Issue.Message = TEXT("Invalid validation or wall settings.");
        Issues.Add(Issue);
        return Issues;
    }

    if (Settings.Walls.DoorHeightCm < Settings.PawnHeightCm + Settings.ClearanceCm)
    {
        AddIssue(Issues, TEXT("PS-V002"), TEXT("Door height is too low for the configured Pawn and clearance."), {}, FVector::ZeroVector);
    }

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        if (Connection.CorridorWidthCm < Settings.RequiredWidthCm())
        {
            AddIssue(Issues, TEXT("PS-V003"), FString::Printf(TEXT("Corridor width %d cm is below required %.1f cm."), Connection.CorridorWidthCm, Settings.RequiredWidthCm()), { Connection.ConnectionId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        if (Connection.DoorWidthCm < Settings.RequiredWidthCm() || Connection.DoorWidthCm > Connection.CorridorWidthCm)
        {
            AddIssue(Issues, TEXT("PS-V002"), TEXT("Door width must fit the Corridor and the configured Pawn."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }

        const FPlayableSketchDoorOverride* Overrides[] = { &Connection.DoorASettings, &Connection.DoorBSettings };
        const FGuid RoomIds[] = { Connection.RoomAId, Connection.RoomBId };

        for (int32 Index = 0; Index < 2; ++Index)
        {
            if (!Overrides[Index]->bManual)
            {
                continue;
            }

            const FPlayableSketchRoom* Room = Graph.Rooms.FindByPredicate([&](const FPlayableSketchRoom& Item)
            {
                return Item.RoomId == RoomIds[Index];
            });

            const EPlayableSketchWallSide Side = Overrides[Index]->WallSide;
            const bool bValidSide = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South
                || Side == EPlayableSketchWallSide::East || Side == EPlayableSketchWallSide::West;
            const bool bHorizontal = Side == EPlayableSketchWallSide::North || Side == EPlayableSketchWallSide::South;
            double Length = Room ? (bHorizontal ? Room->WidthCm : Room->DepthCm) : 0.0;
            if (Room && Room->PositionMode == EPlayableSketchPositionMode::Auto)
            {
                Length = FMath::CeilToDouble(Length / Settings.GridStepCm) * Settings.GridStepCm;
            }
            const double Offset = Overrides[Index]->OffsetCm;

            if (!Room || !bValidSide || !FMath::IsFinite(Offset)
                || Offset - Connection.DoorWidthCm * 0.5 < Settings.Walls.CornerMarginCm
                || Offset + Connection.DoorWidthCm * 0.5 > Length - Settings.Walls.CornerMarginCm)
            {
                AddIssue(Issues, TEXT("PS-V002"), TEXT("Manual Door side or offset is invalid."), { Connection.ConnectionId, RoomIds[Index] }, FVector::ZeroVector);
                Issues.Last().bHasPosition = false;
            }
        }
    }

    for (int32 A = 0; A < Graph.Rooms.Num(); ++A)
    {
        const FPlayableSketchRoom& RoomA = Graph.Rooms[A];

        if (RoomA.PositionMode != EPlayableSketchPositionMode::Locked)
        {
            continue;
        }

        const FPlayableSketchRect BoundsA(RoomA.PositionCm, RoomA.PositionCm + FVector2D(RoomA.WidthCm, RoomA.DepthCm));

        if (!BoundsA.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Locked Room coordinates are invalid."), { RoomA.RoomId }, FVector::ZeroVector);
            continue;
        }

        for (int32 B = A + 1; B < Graph.Rooms.Num(); ++B)
        {
            const FPlayableSketchRoom& RoomB = Graph.Rooms[B];
            const FPlayableSketchRect BoundsB(RoomB.PositionCm, RoomB.PositionCm + FVector2D(RoomB.WidthCm, RoomB.DepthCm));

            if (RoomB.PositionMode == EPlayableSketchPositionMode::Locked && BoundsA.OverlapsInterior(BoundsB))
            {
                const FVector2D Center = (BoundsA.Min + BoundsA.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Locked Rooms overlap."), { RoomA.RoomId, RoomB.RoomId }, FVector(Center.X, Center.Y, 25.0), FVector(RoomA.WidthCm * 0.5, RoomA.DepthCm * 0.5, 25.0));
            }
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Queue.Add(Graph.StartRoomId);
    Reachable.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchRoom& Room : Graph.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room is disconnected from Start in the Graph."), { Room.RoomId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
        }
    }

    return Issues;
}

TArray<FPlayableSketchValidationIssue> FPlayableSketchValidation::ValidatePlan(
    const FPlayableSketchGraph& Graph,
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces,
    const FPlayableSketchValidationSettings& Settings)
{
    TArray<FPlayableSketchValidationIssue> Issues = ValidateInput(Graph, Settings);

    for (int32 A = 0; A < Plan.Rooms.Num(); ++A)
    {
        const FPlayableSketchPlacedRoom& Room = Plan.Rooms[A];
        if (!Room.Bounds.IsValid())
        {
            AddIssue(Issues, TEXT("PS-I001"), TEXT("Invalid placed Room bounds."), { Room.RoomId }, FVector::ZeroVector);
            return Issues;
        }
        for (int32 B = A + 1; B < Plan.Rooms.Num(); ++B)
        {
            if (Room.Bounds.OverlapsInterior(Plan.Rooms[B].Bounds))
            {
                AddIssue(Issues, TEXT("PS-V001"), TEXT("Placed Rooms overlap."), { Room.RoomId, Plan.Rooms[B].RoomId }, RoomCenter(Room), RoomExtent(Room));
            }
        }
    }

    TSet<FGuid> ValidConnections;

    for (const FPlayableSketchConnection& Connection : Graph.Connections)
    {
        const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item)
        {
            return Item.ConnectionId == Connection.ConnectionId;
        });

        if (!Corridor)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Connection has no routed Corridor."), { Connection.ConnectionId, Connection.RoomAId, Connection.RoomBId }, FVector::ZeroVector);
            Issues.Last().bHasPosition = false;
            continue;
        }

        bool bValidRects = !Corridor->Footprints.IsEmpty();
        for (const FPlayableSketchRect& Rect : Corridor->Footprints)
        {
            bValidRects &= Rect.IsValid();
            if (Rect.IsValid()
                && (!FMath::IsNearlyEqual(Rect.Max.X - Rect.Min.X, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)
                    && !FMath::IsNearlyEqual(Rect.Max.Y - Rect.Min.Y, static_cast<double>(Connection.CorridorWidthCm), ToleranceCm)))
            {
                const FVector2D Center = (Rect.Min + Rect.Max) * 0.5;
                AddIssue(Issues, TEXT("PS-V003"), TEXT("Corridor footprint width does not match its declared CorridorWidthCm."), { Connection.ConnectionId }, FVector(Center.X, Center.Y, 25.0));
            }
        }

        const FVector Position(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
        const bool bConnected = bValidRects && FootprintsConnected(Corridor->Footprints);

        if (!bConnected)
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Corridor footprints are invalid or physically disconnected."), { Connection.ConnectionId }, Position);
        }

        const bool bDoorAValid = CheckDoor(Corridor->DoorA, Connection.RoomAId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);
        const bool bDoorBValid = CheckDoor(Corridor->DoorB, Connection.RoomBId, Connection, Plan, Corridor->Footprints, Pieces, Settings, Issues);

        if (bConnected && bDoorAValid && bDoorBValid && Connection.CorridorWidthCm >= Settings.RequiredWidthCm())
        {
            ValidConnections.Add(Connection.ConnectionId);
        }
    }

    TSet<FGuid> Reachable;
    TArray<FGuid> Queue;
    Reachable.Add(Graph.StartRoomId);
    Queue.Add(Graph.StartRoomId);

    for (int32 Head = 0; Head < Queue.Num(); ++Head)
    {
        for (const FPlayableSketchConnection& Connection : Graph.Connections)
        {
            if (!ValidConnections.Contains(Connection.ConnectionId)) continue;
            FGuid Neighbor;
            if (Connection.RoomAId == Queue[Head]) Neighbor = Connection.RoomBId;
            else if (Connection.RoomBId == Queue[Head]) Neighbor = Connection.RoomAId;
            if (Neighbor.IsValid() && !Reachable.Contains(Neighbor))
            {
                Reachable.Add(Neighbor);
                Queue.Add(Neighbor);
            }
        }
    }

    for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
    {
        if (!Reachable.Contains(Room.RoomId))
        {
            AddIssue(Issues, TEXT("PS-V004"), TEXT("Room has no validated physical route from Start."), { Room.RoomId }, RoomCenter(Room), RoomExtent(Room));
        }
    }

    for (const FPlayableSketchGeometryDescriptor& Piece : Pieces)
    {
        if (!Piece.SourceId.IsValid() || Piece.CenterCm.ContainsNaN() || Piece.SizeCm.ContainsNaN()
            || Piece.SizeCm.X <= 0.0 || Piece.SizeCm.Y <= 0.0 || Piece.SizeCm.Z <= 0.0)
        {
            AddIssue(Issues, TEXT("PS-V005"), TEXT("Generated geometry descriptor is invalid."), { Piece.SourceId }, FVector::ZeroVector);
            continue;
        }

        if (Piece.CenterCm.Z - Piece.SizeCm.Z * 0.5 >= Settings.PawnHeightCm)
        {
            continue;
        }

        const FPlayableSketchRect WallRect(
            FVector2D(Piece.CenterCm.X - Piece.SizeCm.X * 0.5, Piece.CenterCm.Y - Piece.SizeCm.Y * 0.5),
            FVector2D(Piece.CenterCm.X + Piece.SizeCm.X * 0.5, Piece.CenterCm.Y + Piece.SizeCm.Y * 0.5));

        for (const FPlayableSketchPlacedRoom& Room : Plan.Rooms)
        {
            if (WallRect.OverlapsInterior(Room.Bounds))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Room interior."), { Piece.SourceId, Room.RoomId }, Piece.CenterCm);
            }
        }

        for (const FPlayableSketchCorridor& Corridor : Plan.Corridors)
        {
            if (Piece.bRoom && (Corridor.DoorA.RoomId == Piece.SourceId || Corridor.DoorB.RoomId == Piece.SourceId))
            {
                continue;
            }

            if (Corridor.Footprints.ContainsByPredicate([&](const FPlayableSketchRect& Rect)
                {
                    return WallRect.OverlapsInterior(Rect);
                }))
            {
                AddIssue(Issues, TEXT("PS-V006"), TEXT("Wall thickness intrudes into a Corridor interior."), { Piece.SourceId, Corridor.ConnectionId }, Piece.CenterCm);
            }
        }
    }

    for (FPlayableSketchValidationIssue& Issue : Issues)
    {
        if (Issue.bHasPosition) continue;
        for (const FGuid& Id : Issue.ElementIds)
        {
            const FPlayableSketchPlacedRoom* Room = Plan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Item) { return Item.RoomId == Id; });
            if (Room)
            {
                Issue.PositionCm = RoomCenter(*Room);
                Issue.ExtentCm = RoomExtent(*Room);
                Issue.bHasPosition = true;
                break;
            }
            const FPlayableSketchCorridor* Corridor = Plan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Item) { return Item.ConnectionId == Id; });
            if (Corridor)
            {
                Issue.PositionCm = FVector(Corridor->DoorA.PositionCm.X, Corridor->DoorA.PositionCm.Y, 40.0);
                Issue.bHasPosition = true;
                break;
            }
        }
    }

    return Issues;
}
''')

header = original('PlayableSketchLevelActor.h')
header = header.replace('#include "PlayableSketchLevelActor.generated.h"', '#include "Validation/PlayableSketchValidation.h"\n#include "PlayableSketchLevelActor.generated.h"')
header = header.replace('UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")\n    TArray', 'UPROPERTY()\n    TArray')
header = header.replace('UPROPERTY(EditAnywhere, Category = "PlayableSketch|Graph")\n    FPlayableSketchGraph Graph;', 'UPROPERTY()\n    FPlayableSketchGraph Graph;')
header = header.replace('protected:', r'''
    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring")
    void GenerateLayout();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Authoring", meta = (DisplayName = "Rebuild Geometry (Full)"))
    void RebuildGeometry();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Validation")
    void ValidateCurrentDesign();

    UFUNCTION(CallInEditor, Category = "PlayableSketch|Tests")
    void TestDay4Validation();

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Authoring")
    bool bAutoRebuildGeometry = true;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float MinCorridorWidthCm = 100.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnRadiusCm = 40.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "1.0"))
    float PawnHeightCm = 180.0f;

    UPROPERTY(EditAnywhere, Category = "PlayableSketch|Validation", meta = (ClampMin = "0.0"))
    float ClearanceCm = 10.0f;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    FString PreviewStatus = TEXT("Generate Layout to create the first saved placement.");

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Preview")
    bool bPreviewStale = false;

    UPROPERTY(VisibleAnywhere, Transient, Category = "PlayableSketch|Validation")
    TArray<FPlayableSketchValidationIssue> LastIssues;

    virtual void OnConstruction(const FTransform& Transform) override;

#if WITH_EDITOR
    virtual void PostEditUndo() override;
#endif

protected:''')
header = header.replace('    FPlayableSketchFloorPlan GeneratedFloorPlan;', r'''
    FPlayableSketchFloorPlan GeneratedFloorPlan;
    FString LastAttemptSignature;
    FString PublishedSignature;

    FString GetSourceSignature() const;
    FPlayableSketchValidationSettings GetValidationSettings() const;
    bool ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const;
    bool BuildCandidate(FPlayableSketchFloorPlan& Plan, TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void PublishCandidate(const FPlayableSketchFloorPlan& Plan, const TArray<FPlayableSketchGeometryDescriptor>& Pieces);
    void InvalidatePreview(const TArray<FPlayableSketchValidationIssue>& Issues, const FString& Status);
    void FailStage(const TCHAR* Code, const FString& Message);
    void AnnotateIssues();
    void LogIssues() const;
    void DrawValidationIssues();''')
save('PlayableSketchLevelActor.h', header)

actor = original('PlayableSketchLevelActor.cpp')
actor = actor.replace('#include "Materials/MaterialInterface.h"', '''#include "Materials/MaterialInterface.h"
#include "Validation/Tests/PlayableSketchDay4Tests.h"

#if WITH_EDITOR
#include "ScopedTransaction.h"
#endif''')

def replace_function(text, name, replacement):
    marker = 'void APlayableSketchLevelActor::' + name + '('
    start = text.index(marker)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if text[end] == '{': depth += 1
        elif text[end] == '}': depth -= 1
        end += 1
    return text[:start] + replacement.strip() + text[end:]

actor = replace_function(actor, 'BeginPlay', r'''
void APlayableSketchLevelActor::BeginPlay()
{
    Super::BeginPlay();

    if (bGenerateOnBeginPlay)
    {
        RebuildGeometry();
    }
}
''')

actor = replace_function(actor, 'Tick', r'''
void APlayableSketchLevelActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

#if WITH_EDITOR
    if (GetWorld() && !GetWorld()->IsGameWorld())
    {
        const FString Signature = GetSourceSignature();

        if (Signature != LastAttemptSignature)
        {
            PreviewPathPoints.Reset();
            bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty();
            PreviewStatus = TEXT("Source changed. Preview needs Rebuild Geometry.");
            LastAttemptSignature = Signature;

            if (bAutoRebuildGeometry)
            {
                RebuildGeometry();
            }
        }
    }
#endif

    DrawFloorPathPreview();
    DrawValidationIssues();
}
''')

actor = replace_function(actor, 'GenerateFloors', r'''
void APlayableSketchLevelActor::GenerateFloors()
{
    if (GetWorld() && GetWorld()->IsGameWorld())
    {
        RebuildGeometry();
    }
    else
    {
        GenerateLayout();
    }
}
''')

actor = replace_function(actor, 'ClearFloors', r'''
void APlayableSketchLevelActor::ClearFloors()
{
    FPlayableSketchWallBuilder::Clear(*this);
    FPlayableSketchFloorBuilder::Clear(*this);
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    LastIssues.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = TEXT("Preview cleared. Saved layout is retained.");
}
''')
actor = actor.replace('if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty())', 'if (!GraphAsset || GeneratedFloorPlan.Rooms.IsEmpty() || bPreviewStale || PublishedSignature != GetSourceSignature())')
actor = actor.replace('Assign GraphAsset and run Generate Floors before testing the path.', 'Generate Layout or Rebuild Geometry successfully before testing the current path.')
actor = actor.replace('if (!GetWorld() || PreviewPathPoints.Num() < 2)', 'if (!GetWorld() || PreviewPathPoints.Num() < 2 || bPreviewStale || PublishedSignature != GetSourceSignature())')

actor += r'''

FString APlayableSketchLevelActor::GetSourceSignature() const
{
    if (!GraphAsset)
    {
        return TEXT("NoGraphAsset");
    }

    return GraphAsset->GetPathName() + GraphAsset->GetSourceText()
        + FString::Printf(TEXT("|%d|%d|%d|%d|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g|%.9g"),
            GridStepCm, RoomGapCm, DoorCornerMarginCm, MaxPlacementAttempts,
            FloorThicknessCm, WallHeightCm, WallThicknessCm, DoorHeightCm,
            MinCorridorWidthCm, PawnRadiusCm, PawnHeightCm, ClearanceCm)
        + GetPathNameSafe(WallMaterial.Get()) + GetPathNameSafe(DefaultFloorMaterial.Get())
        + GetPathNameSafe(HubFloorMaterial.Get()) + GetPathNameSafe(StartFloorMaterial.Get())
        + GetPathNameSafe(GoalFloorMaterial.Get());
}

FPlayableSketchValidationSettings APlayableSketchLevelActor::GetValidationSettings() const
{
    FPlayableSketchValidationSettings Settings;
    Settings.GridStepCm = GridStepCm;
    Settings.Walls.HeightCm = WallHeightCm;
    Settings.Walls.ThicknessCm = WallThicknessCm;
    Settings.Walls.DoorHeightCm = DoorHeightCm;
    Settings.Walls.CornerMarginCm = DoorCornerMarginCm;
    Settings.MinCorridorWidthCm = MinCorridorWidthCm;
    Settings.PawnRadiusCm = PawnRadiusCm;
    Settings.PawnHeightCm = PawnHeightCm;
    Settings.ClearanceCm = ClearanceCm;
    return Settings;
}

bool APlayableSketchLevelActor::ReadSavedRooms(FPlayableSketchFloorPlan& OutPlan, FString& OutError) const
{
    OutPlan = FPlayableSketchFloorPlan();
    OutError.Reset();

    if (!GraphAsset)
    {
        OutError = TEXT("GraphAsset is not assigned.");
        return false;
    }

    if (GridStepCm <= 0)
    {
        OutError = TEXT("GridStepCm must be positive.");
        return false;
    }

    for (const FPlayableSketchRoom& Room : GraphAsset->Graph.Rooms)
    {
        FVector2D MinCm = Room.PositionCm;

        if (Room.PositionMode == EPlayableSketchPositionMode::Auto)
        {
            const FPlayableSketchSavedPlacement* Saved = GraphAsset->SavedLayout.Rooms.FindByPredicate(
                [&](const FPlayableSketchSavedPlacement& Placement)
                {
                    return Placement.RoomId == Room.RoomId;
                });

            if (!Saved)
            {
                OutError = FString::Printf(TEXT("Room %s has no saved placement. Run Generate Layout."), *Room.RoomId.ToString());
                return false;
            }

            MinCm = Saved->MinCm;
        }

        FPlayableSketchPlacedRoom Placed;
        Placed.RoomId = Room.RoomId;
        FVector2D SizeCm(Room.WidthCm, Room.DepthCm);
        if (Room.PositionMode == EPlayableSketchPositionMode::Auto)
        {
            SizeCm.X = FMath::CeilToDouble(SizeCm.X / GridStepCm) * GridStepCm;
            SizeCm.Y = FMath::CeilToDouble(SizeCm.Y / GridStepCm) * GridStepCm;
        }
        Placed.Bounds = FPlayableSketchRect(MinCm, MinCm + SizeCm);

        if (!Placed.Bounds.IsValid())
        {
            OutError = FString::Printf(TEXT("Invalid position or dimensions for Room %s."), *Room.RoomId.ToString());
            return false;
        }

        OutPlan.Rooms.Add(Placed);
    }

    return true;
}

bool APlayableSketchLevelActor::BuildCandidate(
    FPlayableSketchFloorPlan& Plan,
    TArray<FPlayableSketchGeometryDescriptor>& Pieces)
{
    for (int32 A = 0; A < Plan.Rooms.Num(); ++A)
    {
        for (int32 B = A + 1; B < Plan.Rooms.Num(); ++B)
        {
            if (Plan.Rooms[A].Bounds.OverlapsInterior(Plan.Rooms[B].Bounds))
            {
                FPlayableSketchValidationIssue Issue;
                Issue.Code = TEXT("PS-V001");
                Issue.ElementIds = { Plan.Rooms[A].RoomId, Plan.Rooms[B].RoomId };
                Issue.Message = TEXT("Room interiors overlap. Move or resize a Room.");
                const FVector2D Center = (Plan.Rooms[A].Bounds.Min + Plan.Rooms[A].Bounds.Max) * 0.5;
                const FVector2D Half = (Plan.Rooms[A].Bounds.Max - Plan.Rooms[A].Bounds.Min) * 0.5;
                Issue.PositionCm = FVector(Center.X, Center.Y, 25.0);
                Issue.ExtentCm = FVector(Half.X, Half.Y, 25.0);
                Issue.bHasPosition = true;
                LastIssues.Add(Issue);
            }
        }
    }

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid Room placement. Preview cleared."));
        return false;
    }

    FString Error;

    if (!FPlayableSketchDoorGenerator::Generate(GraphAsset->Graph, Plan, DoorCornerMarginCm, Error))
    {
        FailStage(TEXT("PS-V002"), Error);
        return false;
    }

    if (!FPlayableSketchCorridorRouting::Generate(GraphAsset->Graph, Plan, GridStepCm, Error))
    {
        FailStage(TEXT("PS-G002"), Error);
        return false;
    }

    if (!FPlayableSketchWallGeometry::Generate(Plan, GetValidationSettings().Walls, Pieces, Error))
    {
        FailStage(TEXT("PS-V005"), Error);
        return false;
    }

    LastIssues = FPlayableSketchValidation::ValidatePlan(GraphAsset->Graph, Plan, Pieces, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Validation failed. Preview cleared."));
        return false;
    }

    return true;
}

void APlayableSketchLevelActor::GenerateLayout()
{
    LastAttemptSignature = GetSourceSignature();

    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    if (GetWorld() && GetWorld()->IsGameWorld())
    {
        UE_LOG(LogTemp, Warning, TEXT("Generate Layout is an Editor authoring action. Use Rebuild Geometry during PIE."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid input. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;

    if (!FPlayableSketchLayoutGenerator::Generate(GraphAsset->Graph, GridStepCm, RoomGapCm, Candidate, Error, MaxPlacementAttempts))
    {
        FailStage(TEXT("PS-G001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;

    if (!BuildCandidate(Candidate, Pieces))
    {
        return;
    }

#if WITH_EDITOR
    {
        const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "GenerateLayout", "Generate PlayableSketch Layout"));
        GraphAsset->Modify();
        GraphAsset->SavedLayout.Rooms.Reset();

        for (const FPlayableSketchPlacedRoom& Room : Candidate.Rooms)
        {
            FPlayableSketchSavedPlacement Saved;
            Saved.RoomId = Room.RoomId;
            Saved.MinCm = Room.Bounds.Min;
            GraphAsset->SavedLayout.Rooms.Add(Saved);
        }

        GraphAsset->MarkPackageDirty();
    }
#endif

    PublishCandidate(Candidate, Pieces);
}

void APlayableSketchLevelActor::RebuildGeometry()
{
    LastAttemptSignature = GetSourceSignature();

    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());

    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Invalid input. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;

    if (!ReadSavedRooms(Candidate, Error))
    {
        FailStage(TEXT("PS-L001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;

    if (BuildCandidate(Candidate, Pieces))
    {
        PublishCandidate(Candidate, Pieces);
    }
}

void APlayableSketchLevelActor::PublishCandidate(
    const FPlayableSketchFloorPlan& Plan,
    const TArray<FPlayableSketchGeometryDescriptor>& Pieces)
{
    FString Error;

    if (!FPlayableSketchFloorBuilder::Build(*this, Plan, FloorThicknessCm, Error)
        || !FPlayableSketchWallBuilder::Build(*this, Pieces, WallMaterial.Get(), Error))
    {
        FailStage(TEXT("PS-G003"), Error);
        return;
    }

    GeneratedFloorPlan = Plan;
    PreviewPathPoints.Reset();
    PublishedSignature = GetSourceSignature();
    LastAttemptSignature = PublishedSignature;
    bPreviewStale = false;
    PreviewStatus = TEXT("Current valid preview. Full geometry rebuild completed.");
    ApplyFloorMaterials();
    LogIssues();
}

void APlayableSketchLevelActor::InvalidatePreview(
    const TArray<FPlayableSketchValidationIssue>& Issues,
    const FString& Status)
{
    LastIssues = Issues;
    AnnotateIssues();
    FPlayableSketchWallBuilder::Clear(*this);
    FPlayableSketchFloorBuilder::Clear(*this);
    GeneratedFloorPlan = FPlayableSketchFloorPlan();
    PreviewPathPoints.Reset();
    PublishedSignature.Reset();
    LastAttemptSignature = GetSourceSignature();
    bPreviewStale = false;
    PreviewStatus = Status;
    LogIssues();
}

void APlayableSketchLevelActor::FailStage(const TCHAR* Code, const FString& Message)
{
    FPlayableSketchValidationIssue Issue;
    Issue.Code = FName(Code);
    Issue.Message = Message;

    if (GraphAsset)
    {
        for (const FPlayableSketchRoom& Room : GraphAsset->Graph.Rooms)
        {
            if (Message.Contains(Room.RoomId.ToString())) Issue.ElementIds.AddUnique(Room.RoomId);
        }
        for (const FPlayableSketchConnection& Connection : GraphAsset->Graph.Connections)
        {
            if (Message.Contains(Connection.ConnectionId.ToString())) Issue.ElementIds.AddUnique(Connection.ConnectionId);
        }
    }

    InvalidatePreview({ Issue }, TEXT("Generation failed. Preview cleared; see Last Issues."));
}

void APlayableSketchLevelActor::AnnotateIssues()
{
    if (!GraphAsset) return;

    for (FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        if (Issue.bHasPosition) continue;

        for (const FGuid& Id : Issue.ElementIds)
        {
            const FPlayableSketchConnection* Connection = GraphAsset->Graph.Connections.FindByPredicate(
                [&](const FPlayableSketchConnection& Item) { return Item.ConnectionId == Id; });
            const FGuid RoomId = Connection ? Connection->RoomAId : Id;
            const FPlayableSketchRoom* Source = GraphAsset->Graph.Rooms.FindByPredicate(
                [&](const FPlayableSketchRoom& Item) { return Item.RoomId == RoomId; });
            const FPlayableSketchSavedPlacement* Saved = GraphAsset->SavedLayout.Rooms.FindByPredicate(
                [&](const FPlayableSketchSavedPlacement& Item) { return Item.RoomId == RoomId; });

            if (Source && (Source->PositionMode == EPlayableSketchPositionMode::Locked || Saved))
            {
                const FVector2D Min = Source->PositionMode == EPlayableSketchPositionMode::Locked ? Source->PositionCm : Saved->MinCm;
                Issue.PositionCm = FVector(Min.X + Source->WidthCm * 0.5, Min.Y + Source->DepthCm * 0.5, 25.0);
                Issue.ExtentCm = FVector(Source->WidthCm * 0.5, Source->DepthCm * 0.5, 25.0);
                Issue.bHasPosition = !Issue.PositionCm.ContainsNaN();
                break;
            }

            const FPlayableSketchPlacedRoom* Previous = GeneratedFloorPlan.Rooms.FindByPredicate(
                [&](const FPlayableSketchPlacedRoom& Item) { return Item.RoomId == RoomId; });
            if (Previous)
            {
                const FVector2D Center = (Previous->Bounds.Min + Previous->Bounds.Max) * 0.5;
                Issue.PositionCm = FVector(Center.X, Center.Y, 25.0);
                Issue.bHasPosition = true;
                break;
            }
        }
    }
}

void APlayableSketchLevelActor::LogIssues() const
{
    for (const FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        FString Ids;
        for (const FGuid& Id : Issue.ElementIds) Ids += Id.ToString() + TEXT(" ");
        UE_LOG(LogTemp, Warning, TEXT("[%s] Severity=%d IDs=%s Position=%s Message=%s"),
            *Issue.Code.ToString(), static_cast<int32>(Issue.Severity), *Ids,
            Issue.bHasPosition ? *Issue.PositionCm.ToString() : TEXT("Unknown"), *Issue.Message);
    }
}

void APlayableSketchLevelActor::DrawValidationIssues()
{
    if (!GetWorld()) return;
    const FTransform Transform = GetActorTransform();
    const FVector Scale = Transform.GetScale3D().GetAbs();

    for (const FPlayableSketchValidationIssue& Issue : LastIssues)
    {
        if (!Issue.bHasPosition) continue;
        const FVector Position = Transform.TransformPosition(Issue.PositionCm);
        const FColor Color = Issue.Severity == EPlayableSketchIssueSeverity::Error ? FColor::Red : FColor::Yellow;
        DrawDebugBox(GetWorld(), Position, Issue.ExtentCm * Scale, Transform.GetRotation(), Color, false, -1.0f, 0, 3.0f);
    }
}

void APlayableSketchLevelActor::ValidateCurrentDesign()
{
    if (!GraphAsset)
    {
        FailStage(TEXT("PS-I001"), TEXT("GraphAsset is not assigned."));
        return;
    }

    LastIssues = FPlayableSketchValidation::ValidateInput(GraphAsset->Graph, GetValidationSettings());
    if (FPlayableSketchValidation::HasErrors(LastIssues))
    {
        InvalidatePreview(LastIssues, TEXT("Validation failed. Preview cleared."));
        return;
    }

    FPlayableSketchFloorPlan Candidate;
    FString Error;
    if (!ReadSavedRooms(Candidate, Error))
    {
        FailStage(TEXT("PS-L001"), Error);
        return;
    }

    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    if (BuildCandidate(Candidate, Pieces))
    {
        bPreviewStale = !GeneratedFloorPlan.Rooms.IsEmpty() && PublishedSignature != GetSourceSignature();
        PreviewStatus = bPreviewStale
            ? TEXT("Design is valid, but displayed preview is stale. Rebuild Geometry.")
            : TEXT("Design validation passed. Validation did not publish new geometry.");
        UE_LOG(LogTemp, Display, TEXT("Current design validation passed."));
    }
}

void APlayableSketchLevelActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);

    if (GraphAsset && GetWorld() && !GetWorld()->IsGameWorld() && bAutoRebuildGeometry)
    {
        RebuildGeometry();
    }
}

#if WITH_EDITOR
void APlayableSketchLevelActor::PostEditUndo()
{
    Super::PostEditUndo();
    LastAttemptSignature.Reset();
    if (bAutoRebuildGeometry) RebuildGeometry();
}
#endif

void APlayableSketchLevelActor::TestDay4Validation()
{
    FPlayableSketchDay4Tests::Run();
}
'''
save('PlayableSketchLevelActor.cpp', actor)

save('Public/Validation/Tests/PlayableSketchDay4Tests.h', r'''
#pragma once

#include "CoreMinimal.h"

class PLAYABLESKETCH_API FPlayableSketchDay4Tests
{
public:
    static bool Run();
};
''')

save('Private/Validation/Tests/PlayableSketchDay4Tests.cpp', r'''
#include "Validation/Tests/PlayableSketchDay4Tests.h"
#include "Validation/PlayableSketchValidation.h"
#include "Layout/PlayableSketchLayoutGenerator.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "SpatialGraph/PlayableSketchGraphAsset.h"
#include "Misc/AutomationTest.h"

#if WITH_EDITOR
#include "Editor.h"
#include "ScopedTransaction.h"
#include "PlayableSketchLevelActor.h"
#include "Components/StaticMeshComponent.h"
#endif

namespace
{
    void MakeFixture(FPlayableSketchGraph& Graph, FPlayableSketchFloorPlan& Plan)
    {
        for (int32 Index = 0; Index < 3; ++Index)
        {
            FPlayableSketchRoom Room;
            Room.RoomId = FGuid(0, 0, 0, Index + 1);
            Room.DisplayName = FString::Printf(TEXT("FixtureRoom%d"), Index);
            Graph.Rooms.Add(Room);

            FPlayableSketchPlacedRoom Placed;
            Placed.RoomId = Room.RoomId;
            Placed.Bounds = FPlayableSketchRect(FVector2D(Index * 1000.0, 0.0), FVector2D(Index * 1000.0 + 600.0, 600.0));
            Plan.Rooms.Add(Placed);
        }

        Graph.StartRoomId = Graph.Rooms[0].RoomId;
        Graph.GoalRoomId = Graph.Rooms[2].RoomId;

        for (int32 Index = 0; Index < 2; ++Index)
        {
            FPlayableSketchConnection Connection;
            Connection.ConnectionId = FGuid(0, 0, 0, 100 + Index);
            Connection.RoomAId = Graph.Rooms[Index].RoomId;
            Connection.RoomBId = Graph.Rooms[Index + 1].RoomId;
            Graph.Connections.Add(Connection);

            FPlayableSketchCorridor Corridor;
            Corridor.ConnectionId = Connection.ConnectionId;
            Corridor.DoorA.RoomId = Connection.RoomAId;
            Corridor.DoorA.WallSide = EPlayableSketchWallSide::East;
            Corridor.DoorA.PositionCm = FVector2D(Index * 1000.0 + 600.0, 300.0);
            Corridor.DoorB.RoomId = Connection.RoomBId;
            Corridor.DoorB.WallSide = EPlayableSketchWallSide::West;
            Corridor.DoorB.PositionCm = FVector2D((Index + 1) * 1000.0, 300.0);
            Corridor.Footprints.Add(FPlayableSketchRect(
                FVector2D(Index * 1000.0 + 600.0, 200.0),
                FVector2D((Index + 1) * 1000.0, 400.0)));
            Plan.Corridors.Add(Corridor);
        }
    }

    bool HasIssue(const TArray<FPlayableSketchValidationIssue>& Issues, const TCHAR* Code, const FGuid& Id)
    {
        return Issues.ContainsByPredicate([&](const FPlayableSketchValidationIssue& Issue)
        {
            return Issue.Code == FName(Code) && Issue.ElementIds.Contains(Id)
                && Issue.Severity == EPlayableSketchIssueSeverity::Error
                && Issue.bHasPosition && !Issue.PositionCm.ContainsNaN() && !Issue.Message.IsEmpty();
        });
    }
}

bool FPlayableSketchDay4Tests::Run()
{
    int32 Failures = 0;
    auto Check = [&](bool bPassed, const TCHAR* Name)
    {
        if (bPassed)
        {
            UE_LOG(LogTemp, Display, TEXT("PASS: %s"), Name);
        }
        else
        {
            ++Failures;
            UE_LOG(LogTemp, Error, TEXT("FAIL: %s"), Name);
        }
    };

    FPlayableSketchGraph Graph;
    FPlayableSketchFloorPlan Plan;
    MakeFixture(Graph, Plan);
    FPlayableSketchValidationSettings Settings;
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    FString Error;

    const bool bGenerated = FPlayableSketchWallGeometry::Generate(Plan, Settings.Walls, Pieces, Error);
    Check(bGenerated, TEXT("Valid fixture wall generation"));
    Check(!FPlayableSketchValidation::HasErrors(FPlayableSketchValidation::ValidatePlan(Graph, Plan, Pieces, Settings)), TEXT("Valid fixture passes independent validation"));

    FPlayableSketchFloorPlan BadPlan = Plan;
    BadPlan.Rooms[1].Bounds = FPlayableSketchRect(FVector2D(400.0, 0.0), FVector2D(1000.0, 600.0));
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V001"), Graph.Rooms[1].RoomId), TEXT("PS-V001 overlap with ID, position, severity and message"));

    BadPlan = Plan;
    BadPlan.Corridors[0].DoorA.PositionCm.X -= 10.0;
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V002"), Graph.Connections[0].ConnectionId), TEXT("PS-V002 invalid Door with metadata"));

    FPlayableSketchGraph BadGraph = Graph;
    BadGraph.Connections[0].CorridorWidthCm = 60;
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(BadGraph, Plan, Pieces, Settings), TEXT("PS-V003"), Graph.Connections[0].ConnectionId), TEXT("PS-V003 narrow Corridor with metadata"));

    BadPlan = Plan;
    BadPlan.Corridors[0].Footprints.Reset();
    BadPlan.Corridors[0].Footprints.Add(FPlayableSketchRect(FVector2D(600.0, 200.0), FVector2D(700.0, 400.0)));
    BadPlan.Corridors[0].Footprints.Add(FPlayableSketchRect(FVector2D(900.0, 200.0), FVector2D(1000.0, 400.0)));
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, BadPlan, Pieces, Settings), TEXT("PS-V004"), Graph.Rooms[1].RoomId), TEXT("PS-V004 physical disconnection with metadata"));

    TArray<FPlayableSketchGeometryDescriptor> BadPieces = Pieces;
    FPlayableSketchGeometryDescriptor BlockingWall;
    BlockingWall.SourceId = Graph.Rooms[0].RoomId;
    BlockingWall.bRoom = true;
    BlockingWall.CenterCm = FVector(610.0, 300.0, 100.0);
    BlockingWall.SizeCm = FVector(20.0, 150.0, 200.0);
    BadPieces.Add(BlockingWall);
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, Plan, BadPieces, Settings), TEXT("PS-V005"), Graph.Connections[0].ConnectionId), TEXT("PS-V005 Door blocked by Wall with metadata"));

    BadPieces = Pieces;
    BadPieces.RemoveAll([](const FPlayableSketchGeometryDescriptor& Piece)
    {
        return Piece.Role == EPlayableSketchGeometryRole::Lintel;
    });
    Check(HasIssue(FPlayableSketchValidation::ValidatePlan(Graph, Plan, BadPieces, Settings), TEXT("PS-V005"), Graph.Connections[0].ConnectionId), TEXT("Missing lintel rejected"));

    BadGraph = Graph;
    BadGraph.Rooms[1].PositionMode = EPlayableSketchPositionMode::Locked;
    BadGraph.Rooms[1].PositionCm = FVector2D(1400.0, 1000.0);
    FPlayableSketchFloorPlan LockedPlan;
    const bool bLockedGenerated = FPlayableSketchLayoutGenerator::Generate(BadGraph, 50, 400, LockedPlan, Error);
    const FPlayableSketchPlacedRoom* LockedRoom = LockedPlan.Rooms.FindByPredicate([&](const FPlayableSketchPlacedRoom& Room)
    {
        return Room.RoomId == BadGraph.Rooms[1].RoomId;
    });
    Check(bLockedGenerated && LockedRoom && LockedRoom->Bounds.Min == BadGraph.Rooms[1].PositionCm, TEXT("Generate Layout preserves Locked position"));

    BadGraph = Graph;
    BadGraph.Connections[0].DoorASettings.bManual = true;
    BadGraph.Connections[0].DoorASettings.WallSide = EPlayableSketchWallSide::East;
    BadGraph.Connections[0].DoorASettings.OffsetCm = 160.0;
    FPlayableSketchFloorPlan DoorPlan = Plan;
    const bool bDoorGenerated = FPlayableSketchDoorGenerator::Generate(BadGraph, DoorPlan, 50, Error);
    const FPlayableSketchCorridor* ManualCorridor = DoorPlan.Corridors.FindByPredicate([&](const FPlayableSketchCorridor& Corridor)
    {
        return Corridor.ConnectionId == BadGraph.Connections[0].ConnectionId;
    });
    Check(bDoorGenerated && ManualCorridor && ManualCorridor->DoorA.PositionCm == FVector2D(600.0, 160.0), TEXT("Manual Door offset applied"));

#if WITH_EDITOR
    UPlayableSketchGraphAsset* Asset = NewObject<UPlayableSketchGraphAsset>(GetTransientPackage(), NAME_None, RF_Transactional);
    Asset->Graph = Graph;
    Asset->RoomToRemoveId = Graph.Rooms[1].RoomId;
    Asset->RemoveRoom();
    Check(Asset->Graph.Rooms.Num() == 2 && Asset->Graph.Connections.IsEmpty(), TEXT("Deleting a Room removes its Connections"));
    Check(Asset->Graph.StartRoomId == Graph.StartRoomId && Asset->Graph.GoalRoomId == Graph.GoalRoomId, TEXT("Deleting a Room does not silently reassign Start or Goal"));
    Asset->RoomToRemoveId = Graph.StartRoomId;
    Asset->RemoveRoom();
    Check(FPlayableSketchValidation::HasErrors(FPlayableSketchValidation::ValidateInput(Asset->Graph, Settings)), TEXT("Deleting Start leaves an explicit validation error"));

    UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
    APlayableSketchLevelActor* Actor = World ? World->SpawnActor<APlayableSketchLevelActor>() : nullptr;
    Check(Actor != nullptr, TEXT("Editor integration fixture created"));

    if (Actor)
    {
        UPlayableSketchGraphAsset* PreviewAsset = NewObject<UPlayableSketchGraphAsset>(GetTransientPackage(), NAME_None, RF_Transactional);
        PreviewAsset->Graph = Graph;
        Actor->GraphAsset = PreviewAsset;
        Actor->GenerateLayout();
        Check(PreviewAsset->SavedLayout.Rooms.Num() == 3 && Actor->LastIssues.IsEmpty(), TEXT("Generate Layout saves valid Room placements"));

        auto GeneratedCount = [&]()
        {
            TArray<UStaticMeshComponent*> Components;
            Actor->GetComponents<UStaticMeshComponent>(Components);
            int32 Count = 0;
            for (UStaticMeshComponent* Component : Components)
            {
                if (Component->ComponentHasTag(TEXT("PlayableSketch.GeneratedFloor"))
                    || Component->ComponentHasTag(TEXT("PlayableSketch.GeneratedWall"))) ++Count;
            }
            return Count;
        };

        const int32 BaselineCount = GeneratedCount();
        const FPlayableSketchSavedLayout Saved = PreviewAsset->SavedLayout;
        Actor->RebuildGeometry();
        Check(BaselineCount > 0 && GeneratedCount() == BaselineCount, TEXT("Repeated full rebuild does not accumulate components"));

        {
            const FScopedTransaction Transaction(NSLOCTEXT("PlayableSketch", "TestResize", "Day 4 test resize"));
            PreviewAsset->Modify();
            PreviewAsset->Graph.Rooms[0].WidthCm = 625;
        }
        Actor->RebuildGeometry();
        Check(Actor->LastIssues.IsEmpty() && PreviewAsset->SavedLayout.Rooms[1].MinCm == Saved.Rooms[1].MinCm, TEXT("Resize and rebuild preserve other Room positions"));

        TArray<UStaticMeshComponent*> Components;
        Actor->GetComponents<UStaticMeshComponent>(Components);
        const FName StartTag(*FString::Printf(TEXT("RoomId=%s"), *Graph.StartRoomId.ToString()));
        UStaticMeshComponent* StartFloor = nullptr;
        for (UStaticMeshComponent* Component : Components)
        {
            if (Component->ComponentHasTag(TEXT("PlayableSketch.RoomFloor")) && Component->ComponentHasTag(StartTag)) StartFloor = Component;
        }
        Check(StartFloor && FMath::IsNearlyEqual(StartFloor->GetRelativeScale3D().X * 100.0, 650.0, 0.01), TEXT("Auto Room dimensions retain grid rounding during rebuild"));

        GEditor->UndoTransaction();
        Actor->Tick(0.016f);
        Check(PreviewAsset->Graph.Rooms[0].WidthCm == 600 && Actor->LastIssues.IsEmpty(), TEXT("Undo restores source and automatically rebuilds preview"));

        GEditor->RedoTransaction();
        Actor->Tick(0.016f);
        Check(PreviewAsset->Graph.Rooms[0].WidthCm == 625 && Actor->LastIssues.IsEmpty(), TEXT("Redo restores edit and automatically rebuilds preview"));

        PreviewAsset->Graph.Rooms[0].WidthCm = 6000;
        Actor->RebuildGeometry();
        Check(GeneratedCount() == 0 && Actor->PreviewPathPoints.IsEmpty()
            && Actor->LastIssues.ContainsByPredicate([](const FPlayableSketchValidationIssue& Issue) { return Issue.Code == FName(TEXT("PS-V001")); }),
            TEXT("Invalid edit clears geometry and old navigation preview"));
        Actor->Destroy();
    }
#endif

    UE_LOG(LogTemp, Display, TEXT("Day 4 tests finished: Failures=%d"), Failures);
    return Failures == 0;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchDay4AutomationTest, "PlayableSketch.Day4.Validation", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPlayableSketchDay4AutomationTest::RunTest(const FString& Parameters)
{
    return FPlayableSketchDay4Tests::Run();
}
#endif
''')

manifest = []
for path in files:
    manifest.append({'path': path, 'action': 'replace' if (root / path).exists() else 'add'})
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

stage = root / 'work/day4/validation-project'
stage.mkdir(parents=True, exist_ok=True)
if not (stage / 'Source').exists():
    shutil.copytree(root / 'Source', stage / 'Source')
    shutil.copy2(root / 'PlayableSketch.uproject', stage / 'PlayableSketch.uproject')
for path, content in files.items():
    target = stage / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding='utf-8') != content:
        target.write_text(content, encoding='utf-8')

print(f'Prepared {len(files)} complete files and an isolated validation project.')
