#include "Import/PlayableSketchLayoutImporter.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/SecureHash.h"
#include "Layout/PlayableSketchDoorGenerator.h"
#include "Layout/PlayableSketchCorridorRouting.h"

namespace
{
bool Fields(const TSharedPtr<FJsonObject> &O, std::initializer_list<const TCHAR *> Names)
{
    if (!O || O->Values.Num() != static_cast<int32>(Names.size()))
        return false;
    for (const TCHAR *Name : Names)
        if (!O->HasField(Name))
            return false;
    return true;
}

bool String(const TSharedPtr<FJsonObject> &O, const TCHAR *Name, FString &Value)
{
    const TSharedPtr<FJsonValue> *Field = O ? O->Values.Find(Name) : nullptr;
    return Field && (*Field)->Type == EJson::String && O->TryGetStringField(Name, Value) &&
           !Value.IsEmpty() && Value.Len() <= 256;
}

bool Number(const TSharedPtr<FJsonObject> &O, const TCHAR *Name, double &Value)
{
    const TSharedPtr<FJsonValue> *Field = O ? O->Values.Find(Name) : nullptr;
    if (!Field || (*Field)->Type != EJson::Number)
        return false;
    Value = (*Field)->AsNumber();
    return FMath::IsFinite(Value) && FMath::Abs(Value) <= 10000000.0;
}

bool Positive(const TSharedPtr<FJsonObject> &O, const TCHAR *Name, double &Value)
{
    return Number(O, Name, Value) && Value > 0.0;
}

bool Integer(const TSharedPtr<FJsonObject> &O, const TCHAR *Name, int32 &Value)
{
    double NumberValue;
    if (!Positive(O, Name, NumberValue) || NumberValue != FMath::FloorToDouble(NumberValue))
        return false;
    Value = static_cast<int32>(NumberValue);
    return true;
}

bool ReadPoint(const TSharedPtr<FJsonObject> &O, const TCHAR *Name, FVector2D &Value)
{
    const TArray<TSharedPtr<FJsonValue>> *Array;
    if (!O->TryGetArrayField(Name, Array) || Array->Num() != 2)
        return false;
    for (const auto &V : *Array)
        if (!V || V->Type != EJson::Number || !FMath::IsFinite(V->AsNumber()) ||
            FMath::Abs(V->AsNumber()) > 10000000.0)
            return false;
    Value = FVector2D((*Array)[0]->AsNumber(), (*Array)[1]->AsNumber());
    return true;
}

bool Id(const FString &Value)
{
    if (Value.IsEmpty() || Value.Len() > 128 || !FChar::IsAlpha(Value[0]))
        return false;
    for (TCHAR C : Value)
        if (!FChar::IsAlnum(C) && C != TEXT('_') && C != TEXT('-') && C != TEXT('.') &&
            C != TEXT(':'))
            return false;
    return true;
}

FGuid StableId(const FString &Document, const TCHAR *Kind, const FString &ExternalId)
{
    const FString Identity = Document + TEXT("|") + Kind + TEXT("|") + ExternalId;
    FTCHARToUTF8 Bytes(*Identity);
    FMD5 Hash;
    Hash.Update(reinterpret_cast<const uint8 *>(Bytes.Get()), Bytes.Length());
    uint8 Digest[16];
    Hash.Final(Digest);
    FGuid Result;
    FGuid::ParseExact(BytesToHex(Digest, 16), EGuidFormats::Digits, Result);
    return Result;
}

bool Door(const TSharedPtr<FJsonObject> &O, FPlayableSketchDoorOverride &Out)
{
    FString Side;
    if (!Fields(O, {TEXT("side"), TEXT("offset_cm")}) || !String(O, TEXT("side"), Side) ||
        !Number(O, TEXT("offset_cm"), Out.OffsetCm) || Out.OffsetCm < 0.0)
        return false;
    if (Side == TEXT("north"))
        Out.WallSide = EPlayableSketchWallSide::North;
    else if (Side == TEXT("south"))
        Out.WallSide = EPlayableSketchWallSide::South;
    else if (Side == TEXT("east"))
        Out.WallSide = EPlayableSketchWallSide::East;
    else if (Side == TEXT("west"))
        Out.WallSide = EPlayableSketchWallSide::West;
    else
        return false;
    Out.bManual = true;
    return true;
}

bool UniqueKeys(const FString &Json)
{
    auto Reader = TJsonReaderFactory<>::Create(Json);
    EJsonNotation Notation;
    struct FScope
    {
        bool bObject;
        TSet<FString> Keys;
    };
    TArray<FScope> Stack;
    while (Reader->ReadNext(Notation))
    {
        if (Notation == EJsonNotation::Error)
            return false;
        if (Notation == EJsonNotation::ObjectEnd || Notation == EJsonNotation::ArrayEnd)
        {
            if (Stack.IsEmpty())
                return false;
            Stack.Pop();
            continue;
        }
        if (!Stack.IsEmpty() && Stack.Last().bObject)
        {
            const FString Key = Reader->GetIdentifier();
            if (Stack.Last().Keys.Contains(Key))
                return false;
            Stack.Last().Keys.Add(Key);
        }
        if (Notation == EJsonNotation::ObjectStart || Notation == EJsonNotation::ArrayStart)
        {
            if (Stack.Num() >= 32)
                return false;
            Stack.Add({Notation == EJsonNotation::ObjectStart, {}});
        }
    }
    return Stack.IsEmpty() && Reader->GetErrorMessage().IsEmpty();
}
}

bool FPlayableSketchLayoutImporter::Parse(const FString &Json,
                                          FPlayableSketchLegacyImport &OutImport, FString &Error)
{
    Error = TEXT(
        "PS-I004: Invalid legacy import JSON. Export a supported validated layout with export_legacy.py; canonical layouts require Step 05.");
    if (Json.Len() > 2 * 1024 * 1024 || !UniqueKeys(Json))
        return false;
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root)
        return false;
    if (!Fields(Root, {TEXT("schema_version"), TEXT("units"), TEXT("dimension_basis"),
                       TEXT("source_document_id"), TEXT("source_revision_id"),
                       TEXT("source_layout_sha256"), TEXT("start_room_id"), TEXT("goal_room_id"),
                       TEXT("settings"), TEXT("rooms"), TEXT("connections")}))
        return false;
    FString Version, Units, Basis, Start, Goal;
    FPlayableSketchLegacyImport Candidate;
    if (!String(Root, TEXT("schema_version"), Version) ||
        Version != TEXT("playablesketch-legacy-import/1.0") ||
        !String(Root, TEXT("units"), Units) || Units != TEXT("cm") ||
        !String(Root, TEXT("dimension_basis"), Basis) || Basis != TEXT("clear_inside") ||
        !String(Root, TEXT("source_document_id"), Candidate.DocumentId) ||
        !Id(Candidate.DocumentId) ||
        !String(Root, TEXT("source_revision_id"), Candidate.RevisionId) ||
        !String(Root, TEXT("source_layout_sha256"), Candidate.SourceHash) ||
        Candidate.SourceHash.Len() != 64 || !String(Root, TEXT("start_room_id"), Start) ||
        !String(Root, TEXT("goal_room_id"), Goal) || Start == Goal)
        return false;
    for (TCHAR C : Candidate.SourceHash)
        if (!FChar::IsHexDigit(C))
            return false;
    const TSharedPtr<FJsonObject> *Settings;
    if (!Root->TryGetObjectField(TEXT("settings"), Settings) ||
        !Fields(*Settings, {TEXT("wall_thickness_cm"), TEXT("wall_height_cm"),
                            TEXT("door_height_cm"), TEXT("floor_thickness_cm")}) ||
        !Positive(*Settings, TEXT("wall_thickness_cm"), Candidate.Walls.ThicknessCm) ||
        !Positive(*Settings, TEXT("wall_height_cm"), Candidate.Walls.HeightCm) ||
        !Positive(*Settings, TEXT("door_height_cm"), Candidate.Walls.DoorHeightCm) ||
        !Positive(*Settings, TEXT("floor_thickness_cm"), Candidate.FloorThicknessCm) ||
        Candidate.Walls.DoorHeightCm > Candidate.Walls.HeightCm)
        return false;
    const TArray<TSharedPtr<FJsonValue>> *Rooms;
    if (!Root->TryGetArrayField(TEXT("rooms"), Rooms) || Rooms->Num() != 2)
        return false;
    TMap<FString, FGuid> RoomIds;
    for (const auto &Value : *Rooms)
    {
        if (!Value || Value->Type != EJson::Object)
            return false;
        const auto O = Value->AsObject();
        FString External;
        FPlayableSketchRoom Room;
        if (!Fields(O, {TEXT("id"), TEXT("name"), TEXT("min_cm"), TEXT("width_cm"),
                        TEXT("depth_cm")}) ||
            !String(O, TEXT("id"), External) || !Id(External) || RoomIds.Contains(External) ||
            !String(O, TEXT("name"), Room.DisplayName) ||
            !ReadPoint(O, TEXT("min_cm"), Room.PositionCm) ||
            !Integer(O, TEXT("width_cm"), Room.WidthCm) ||
            !Integer(O, TEXT("depth_cm"), Room.DepthCm))
            return false;
        Room.RoomId = StableId(Candidate.DocumentId, TEXT("room"), External);
        RoomIds.Add(External, Room.RoomId);
        Room.PositionMode = EPlayableSketchPositionMode::Locked;
        Room.RoomRole = External == Start  ? EPlayableSketchRoomRole::Start
                        : External == Goal ? EPlayableSketchRoomRole::Goal
                                           : EPlayableSketchRoomRole::None;
        Candidate.Graph.Rooms.Add(Room);
    }
    if (!RoomIds.Contains(Start) || !RoomIds.Contains(Goal))
        return false;
    Candidate.Graph.StartRoomId = RoomIds[Start];
    Candidate.Graph.GoalRoomId = RoomIds[Goal];
    const TArray<TSharedPtr<FJsonValue>> *Connections;
    if (!Root->TryGetArrayField(TEXT("connections"), Connections) || Connections->Num() != 1 ||
        !(*Connections)[0] || (*Connections)[0]->Type != EJson::Object)
        return false;
    const auto C = (*Connections)[0]->AsObject();
    FString External, A, B;
    FPlayableSketchConnection Connection;
    FVector2D Min, Max;
    const TSharedPtr<FJsonObject> *DoorA;
    const TSharedPtr<FJsonObject> *DoorB;
    if (!Fields(C, {TEXT("id"), TEXT("room_a_id"), TEXT("room_b_id"), TEXT("corridor_width_cm"),
                    TEXT("door_width_cm"), TEXT("door_a"), TEXT("door_b"),
                    TEXT("expected_corridor_min_cm"), TEXT("expected_corridor_max_cm")}) ||
        !String(C, TEXT("id"), External) || !Id(External) || RoomIds.Contains(External) ||
        !String(C, TEXT("room_a_id"), A) || !String(C, TEXT("room_b_id"), B) || A == B ||
        !RoomIds.Contains(A) || !RoomIds.Contains(B) ||
        !Integer(C, TEXT("corridor_width_cm"), Connection.CorridorWidthCm) ||
        !Integer(C, TEXT("door_width_cm"), Connection.DoorWidthCm) ||
        !C->TryGetObjectField(TEXT("door_a"), DoorA) || !Door(*DoorA, Connection.DoorASettings) ||
        !C->TryGetObjectField(TEXT("door_b"), DoorB) || !Door(*DoorB, Connection.DoorBSettings) ||
        !ReadPoint(C, TEXT("expected_corridor_min_cm"), Min) ||
        !ReadPoint(C, TEXT("expected_corridor_max_cm"), Max))
        return false;
    Candidate.ExpectedCorridor = FPlayableSketchRect(Min, Max);
    if (!Candidate.ExpectedCorridor.IsValid())
        return false;
    Connection.ConnectionId = StableId(Candidate.DocumentId, TEXT("corridor"), External);
    Connection.RoomAId = RoomIds[A];
    Connection.RoomBId = RoomIds[B];
    Candidate.Graph.Connections.Add(Connection);
    OutImport = MoveTemp(Candidate);
    Error.Reset();
    return true;
}

bool FPlayableSketchLayoutImporter::Prepare(const FPlayableSketchLegacyImport &Import,
                                            const FPlayableSketchValidationSettings &ActorSettings,
                                            FPlayableSketchFloorPlan &OutPlan,
                                            TArray<FPlayableSketchGeometryDescriptor> &OutPieces,
                                            FString &Error)
{
    FPlayableSketchValidationSettings Settings = ActorSettings;
    Settings.Walls.HeightCm = Import.Walls.HeightCm;
    Settings.Walls.ThicknessCm = Import.Walls.ThicknessCm;
    Settings.Walls.DoorHeightCm = Import.Walls.DoorHeightCm;
    auto Issues = FPlayableSketchValidation::ValidateInput(Import.Graph, Settings);
    if (FPlayableSketchValidation::HasErrors(Issues))
    {
        Error = TEXT("PS-I004: Import input validation failed: ") + Issues[0].Message;
        return false;
    }
    FPlayableSketchFloorPlan Plan;
    for (const auto &Room : Import.Graph.Rooms)
        Plan.Rooms.Add({Room.RoomId, FPlayableSketchRect(
                                         Room.PositionCm,
                                         Room.PositionCm + FVector2D(Room.WidthCm, Room.DepthCm))});
    if (!FPlayableSketchDoorGenerator::Generate(Import.Graph, Plan, Settings.Walls.CornerMarginCm,
                                                Error) ||
        !FPlayableSketchCorridorRouting::Generate(Import.Graph, Plan, Settings.GridStepCm, Error))
        return false;
    if (Plan.Corridors.Num() != 1 || Plan.Corridors[0].Footprints.Num() != 1 ||
        !Plan.Corridors[0].Footprints[0].Min.Equals(Import.ExpectedCorridor.Min, 0.001) ||
        !Plan.Corridors[0].Footprints[0].Max.Equals(Import.ExpectedCorridor.Max, 0.001))
    {
        Error = TEXT(
            "PS-I004: Legacy routing does not preserve the supplied straight corridor. Use the explicit builder.");
        return false;
    }
    TArray<FPlayableSketchGeometryDescriptor> Pieces;
    if (!FPlayableSketchWallGeometry::Generate(Plan, Settings.Walls, Pieces, Error))
        return false;
    Issues = FPlayableSketchValidation::ValidatePlan(Import.Graph, Plan, Pieces, Settings);
    if (FPlayableSketchValidation::HasErrors(Issues))
    {
        Error = TEXT("PS-I004: Import geometry validation failed: ") + Issues[0].Message;
        return false;
    }
    OutPlan = MoveTemp(Plan);
    OutPieces = MoveTemp(Pieces);
    Error.Reset();
    return true;
}
