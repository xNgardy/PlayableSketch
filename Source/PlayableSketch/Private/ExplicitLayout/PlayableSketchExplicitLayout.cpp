#include "ExplicitLayout/PlayableSketchExplicitLayout.h"
#include "Dom/JsonObject.h"
#include "Misc/SecureHash.h"
#include "Misc/Crc.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
constexpr double Tolerance = 0.001;
constexpr double MaxNumber = 10000000.0;
constexpr int32 MaxEntities = 2048;
using FObject = TSharedPtr<FJsonObject>;

bool Exact(const FString &A, const FString &B)
{
    return A.Equals(B, ESearchCase::CaseSensitive);
}
bool HasExactField(const FObject &Object, const TCHAR *Key)
{
    for (const auto &Pair : Object->Values)
        if (Exact(Pair.Key, Key))
            return true;
    return false;
}
struct FExactSetKeys : DefaultKeyFuncs<FString>
{
    static bool Matches(KeyInitType A, KeyInitType B)
    {
        return Exact(A, B);
    }
    static uint32 GetKeyHash(KeyInitType Key)
    {
        return FCrc::StrCrc32(*Key);
    }
};
using FStringSet = TSet<FString, FExactSetKeys>;
template <typename ValueType> struct TExactMapKeys : TDefaultMapKeyFuncs<FString, ValueType, false>
{
    using KeyInitType = typename TDefaultMapKeyFuncs<FString, ValueType, false>::KeyInitType;
    static bool Matches(KeyInitType A, KeyInitType B)
    {
        return Exact(A, B);
    }
    static uint32 GetKeyHash(KeyInitType Key)
    {
        return FCrc::StrCrc32(*Key);
    }
};
template <typename ValueType>
using TStringMap = TMap<FString, ValueType, FDefaultSetAllocator, TExactMapKeys<ValueType>>;
bool ContainsExact(const TArray<FString> &Values, const FString &Value)
{
    return Values.ContainsByPredicate([&](const FString &Item) { return Exact(Item, Value); });
}
bool ArraysExact(const TArray<FString> &A, const TArray<FString> &B)
{
    if (A.Num() != B.Num())
        return false;
    for (int32 I = 0; I < A.Num(); ++I)
        if (!Exact(A[I], B[I]))
            return false;
    return true;
}

bool IsId(const FString &S)
{
    auto Alpha = [](TCHAR C) { return (C >= 'A' && C <= 'Z') || (C >= 'a' && C <= 'z'); };
    if (S.IsEmpty() || S.Len() > 128 || !Alpha(S[0]))
        return false;
    for (TCHAR C : S)
        if (!Alpha(C) && !(C >= '0' && C <= '9') && C != '_' && C != '.' && C != ':' && C != '-')
            return false;
    return true;
}

bool Finite(double N)
{
    return FMath::IsFinite(N) && FMath::Abs(N) <= MaxNumber;
}
bool Near(double A, double B)
{
    return FMath::Abs(A - B) <= Tolerance;
}
FString TextValue(const FObject &O, const TCHAR *Key)
{
    return O->GetStringField(Key);
}
double NumberValue(const FObject &O, const TCHAR *Key)
{
    return O->GetNumberField(Key);
}

bool UniqueKeys(const FString &Json)
{
    auto Reader = TJsonReaderFactory<>::Create(Json);
    struct FScope
    {
        bool bObject;
        FStringSet Keys;
    };
    TArray<FScope> Stack;
    EJsonNotation Token;
    while (Reader->ReadNext(Token))
    {
        if (Token == EJsonNotation::Error)
            return false;
        if (Token == EJsonNotation::ObjectEnd || Token == EJsonNotation::ArrayEnd)
        {
            if (Stack.IsEmpty())
                return false;
            Stack.Pop();
            continue;
        }
        if (!Stack.IsEmpty() && Stack.Last().bObject)
        {

            const FString Key = Reader->GetIdentifier().ToLower();
            if (Stack.Last().Keys.Contains(Key))
                return false;
            Stack.Last().Keys.Add(Key);
        }
        if (Token == EJsonNotation::ObjectStart || Token == EJsonNotation::ArrayStart)
        {
            if (Stack.Num() >= 32)
                return false;
            Stack.Add({Token == EJsonNotation::ObjectStart, {}});
        }
    }
    return Stack.IsEmpty() && Reader->GetErrorMessage().IsEmpty();
}

struct FReader
{
    FString &Error;
    FStringSet Ids;

    bool Fail(const FString &Message)
    {
        Error = TEXT("SKETCH_IMPORT_INVALID: ") + Message;
        return false;
    }
    bool Fields(const FObject &O, std::initializer_list<const TCHAR *> Keys)
    {
        if (!O || O->Values.Num() != static_cast<int32>(Keys.size()))
            return Fail(TEXT("Missing or unknown object fields."));
        for (const TCHAR *K : Keys)
            if (!HasExactField(O, K))
                return Fail(FString(TEXT("Missing field: ")) + K);
        return true;
    }
    bool Text(const FObject &O, const TCHAR *K, bool bId = false, bool bNullable = false,
              bool bEmpty = false)
    {
        const auto *V = O->Values.Find(K);
        if (V && (*V)->Type == EJson::Null && bNullable)
            return true;
        if (!V || (*V)->Type != EJson::String)
            return Fail(FString(TEXT("Expected string: ")) + K);
        const FString Value = (*V)->AsString();
        return ((bEmpty || !Value.IsEmpty()) && (!bId || IsId(Value))) ||
               Fail(FString(TEXT("Invalid string: ")) + K);
    }
    bool Number(const FObject &O, const TCHAR *K, double Minimum = -MaxNumber, bool bStrict = false)
    {
        const auto *V = O->Values.Find(K);
        return (V && (*V)->Type == EJson::Number && Finite((*V)->AsNumber()) &&
                (bStrict ? (*V)->AsNumber() > Minimum : (*V)->AsNumber() >= Minimum)) ||
               Fail(FString(TEXT("Invalid/bounded numeric field: ")) + K);
    }
    bool Eq(const FObject &O, const TCHAR *K, const TCHAR *Value)
    {
        return (Text(O, K) && Exact(TextValue(O, K), Value)) ||
               Fail(FString(TEXT("Unsupported value: ")) + K);
    }
    bool Enum(const FObject &O, const TCHAR *K, std::initializer_list<const TCHAR *> Values)
    {
        if (!Text(O, K))
            return false;
        for (const TCHAR *V : Values)
            if (Exact(TextValue(O, K), V))
                return true;
        return Fail(FString(TEXT("Unsupported value: ")) + K);
    }
    FObject Object(const FObject &O, const TCHAR *K)
    {
        const auto *V = O->Values.Find(K);
        if (!V || (*V)->Type != EJson::Object)
        {
            Fail(FString(TEXT("Expected object: ")) + K);
            return nullptr;
        }
        return (*V)->AsObject();
    }
    const TArray<TSharedPtr<FJsonValue>> *Array(const FObject &O, const TCHAR *K, int32 Minimum = 0,
                                                int32 Maximum = MaxEntities)
    {
        const TArray<TSharedPtr<FJsonValue>> *A = nullptr;
        if (!O->TryGetArrayField(K, A) || A->Num() < Minimum || A->Num() > Maximum)
        {
            Fail(FString(TEXT("Invalid/bounded array: ")) + K);
            return nullptr;
        }
        return A;
    }
    bool Strings(const FObject &O, const TCHAR *K, TArray<FString> &Out, int32 Minimum = 0,
                 int32 Maximum = MaxEntities, bool bIds = true)
    {
        const auto *A = Array(O, K, Minimum, Maximum);
        if (!A)
            return false;
        for (const auto &V : *A)
        {
            if (V->Type != EJson::String ||
                (bIds && (!IsId(V->AsString()) || ContainsExact(Out, V->AsString()))))
                return Fail(FString(TEXT("Invalid/duplicate array item: ")) + K);
            Out.Add(V->AsString());
        }
        return true;
    }
    bool Provenance(const FObject &O)
    {
        const FObject P = Object(O, TEXT("provenance"));
        TArray<FString> Evidence;
        return Fields(P, {TEXT("method"), TEXT("evidence_ids"), TEXT("note")}) &&
               Enum(P, TEXT("method"),
                    {TEXT("manual_annotation"), TEXT("derived"), TEXT("configured"),
                     TEXT("user_correction"), TEXT("ocr"), TEXT("line_detection")}) &&
               Strings(P, TEXT("evidence_ids"), Evidence) &&
               Text(P, TEXT("note"), false, false, true);
    }
    bool Entity(const FObject &O, FString &Id)
    {
        if (!Text(O, TEXT("id"), true))
            return false;
        Id = TextValue(O, TEXT("id"));
        if (Ids.Contains(Id) || Ids.Num() >= MaxEntities)
            return Fail(TEXT("Duplicate ID or entity limit exceeded: ") + Id);
        Ids.Add(Id);
        return Provenance(O);
    }
    bool Connections(const FObject &O, const FPlayableSketchExplicitLayout &L, TArray<FString> &Out)
    {
        const auto *A = Array(O, TEXT("connected_entities"), 2, 2);
        if (!A)
            return false;
        for (const auto &V : *A)
        {
            const auto C = V->Type == EJson::Object ? V->AsObject() : nullptr;
            if (!Fields(C, {TEXT("type"), TEXT("id")}) || !Text(C, TEXT("id"), true) ||
                !Enum(C, TEXT("type"), {TEXT("room"), TEXT("corridor")}))
                return false;
            const FString Id = TextValue(C, TEXT("id"));
            const auto *Region =
                L.Regions.FindByPredicate([&](const auto &R) { return Exact(R.Id, Id); });
            if (!Region ||
                Region->bCorridor != (Exact(TextValue(C, TEXT("type")), TEXT("corridor"))) ||
                ContainsExact(Out, Id))
                return Fail(TEXT("Unknown/mistyped connected region: ") + Id);
            Out.Add(Id);
        }
        Out.Sort([](const FString &A, const FString &B) {
            return A.Compare(B, ESearchCase::CaseSensitive) < 0;
        });
        return true;
    }
};

const FPlayableSketchExplicitVertex *Vertex(const FPlayableSketchExplicitLayout &L,
                                            const FString &Id)
{
    return L.Vertices.FindByPredicate([&](const auto &V) { return Exact(V.Id, Id); });
}
const FPlayableSketchExplicitWall *Wall(const FPlayableSketchExplicitLayout &L, const FString &Id)
{
    return L.Walls.FindByPredicate([&](const auto &W) { return Exact(W.Id, Id); });
}
const FPlayableSketchExplicitRegion *Region(const FPlayableSketchExplicitLayout &L,
                                            const FString &Id)
{
    return L.Regions.FindByPredicate([&](const auto &R) { return Exact(R.Id, Id); });
}
const FPlayableSketchExplicitOpening *Opening(const FPlayableSketchExplicitLayout &L,
                                              const FString &Id)
{
    return L.Openings.FindByPredicate([&](const auto &O) { return Exact(O.Id, Id); });
}

bool Geometry(FPlayableSketchExplicitLayout &L, FString &Error)
{
    auto Fail = [&](const TCHAR *Code, const FString &Message) {
        Error = FString(Code) + TEXT(": ") + Message;
        return false;
    };
    if (!IsId(L.DocumentId) || !IsId(L.RevisionId))
        return Fail(TEXT("SKETCH_IMPORT_INVALID"), TEXT("Invalid document/revision ID."));
    const auto &Settings = L.Settings;
    for (double Value : {Settings.WallThicknessCm, Settings.WallHeightCm, Settings.DoorHeightCm,
                         Settings.FloorThicknessCm})
        if (!Finite(Value) || Value <= Tolerance)
            return Fail(TEXT("SKETCH_SETTINGS_CONFLICT"), TEXT("Invalid settings."));
    if (Settings.DoorHeightCm > Settings.WallHeightCm)
        return Fail(TEXT("SKETCH_SETTINGS_CONFLICT"), TEXT("Door height exceeds wall height."));
    FStringSet Ids;
    auto AddId = [&](const FString &Id) {
        if (!IsId(Id) || Ids.Contains(Id) || Ids.Num() >= MaxEntities)
            return false;
        Ids.Add(Id);
        return true;
    };
    if (L.Vertices.Num() < 4 || L.Walls.Num() < 4 || L.Regions.IsEmpty())
        return Fail(TEXT("SKETCH_GEOMETRY_INCOMPLETE"), TEXT("A rectangular room is required."));
    for (int32 I = 0; I < L.Vertices.Num(); ++I)
    {
        const auto &V = L.Vertices[I];
        if (!AddId(V.Id) || !Finite(V.PositionCm.X) || !Finite(V.PositionCm.Y))
            return Fail(TEXT("SKETCH_VERTEX_INVALID"), V.Id);
        for (int32 J = 0; J < I; ++J)
            if (L.Vertices[J].PositionCm == V.PositionCm)
                return Fail(TEXT("SKETCH_TOPOLOGY_UNNODED"),
                            TEXT("Coincident vertices must share one ID: ") + V.Id);
    }
    for (const auto &W : L.Walls)
    {
        const auto *A = Vertex(L, W.StartVertexId);
        const auto *B = Vertex(L, W.EndVertexId);
        if (!AddId(W.Id) || !A || !B || (W.Axis != 0 && W.Axis != 1) ||
            A->PositionCm[1 - W.Axis] != B->PositionCm[1 - W.Axis] ||
            B->PositionCm[W.Axis] - A->PositionCm[W.Axis] <= Tolerance)
            return Fail(TEXT("SKETCH_WALL_INVALID"), W.Id);
    }
    TStringMap<FStringSet> Owners;
    int32 RoomCount = 0;
    for (auto &R : L.Regions)
    {
        if (!AddId(R.Id) || R.VertexIds.Num() < 4 || R.VertexIds.Num() != R.WallIds.Num() ||
            (!Exact(R.Role, TEXT("none")) && !Exact(R.Role, TEXT("start")) &&
             !Exact(R.Role, TEXT("goal"))) ||
            (R.bCorridor && !Exact(R.Role, TEXT("none"))))
            return Fail(TEXT("SKETCH_BOUNDARY_INVALID"), R.Id);
        if (!R.bCorridor)
            ++RoomCount;
        TArray<FVector2D> P;
        FStringSet VIds, WIds;
        for (int32 I = 0; I < R.VertexIds.Num(); ++I)
        {
            const auto *V = Vertex(L, R.VertexIds[I]);
            const auto *W = Wall(L, R.WallIds[I]);
            const FString &Next = R.VertexIds[(I + 1) % R.VertexIds.Num()];
            if (!V || !W || VIds.Contains(V->Id) || WIds.Contains(W->Id) ||
                !((Exact(W->StartVertexId, V->Id) && Exact(W->EndVertexId, Next)) ||
                  (Exact(W->EndVertexId, V->Id) && Exact(W->StartVertexId, Next))))
                return Fail(TEXT("SKETCH_BOUNDARY_INVALID"), R.Id);
            VIds.Add(V->Id);
            WIds.Add(W->Id);
            P.Add(V->PositionCm);
            Owners.FindOrAdd(W->Id).Add(R.Id);
        }
        FVector2D Lo = P[0], Hi = P[0];
        for (const auto &V : P)
        {
            Lo.X = FMath::Min(Lo.X, V.X);
            Lo.Y = FMath::Min(Lo.Y, V.Y);
            Hi.X = FMath::Max(Hi.X, V.X);
            Hi.Y = FMath::Max(Hi.Y, V.Y);
        }
        double Area = 0;
        for (int32 I = 0; I < P.Num(); ++I)
        {
            const auto A = P[I], B = P[(I + 1) % P.Num()], C = P[(I + 2) % P.Num()];
            const auto AB = B - A, BC = C - B;
            Area += FVector2D::CrossProduct(A - P[0], B - P[0]) * 0.5;
            if ((A.X != Lo.X && A.X != Hi.X && A.Y != Lo.Y && A.Y != Hi.Y) ||
                FVector2D::CrossProduct(AB, BC) < 0 || FVector2D::DotProduct(AB, BC) < 0)
                return Fail(TEXT("SKETCH_UNSUPPORTED_GEOMETRY"),
                            R.Id + TEXT(" must be a CCW rectangle."));
        }
        R.Bounds = FPlayableSketchRect(Lo, Hi);
        if (!R.Bounds.IsValid() || !Near(Area, (Hi.X - Lo.X) * (Hi.Y - Lo.Y)) ||
            (Hi.X - Lo.X) <= Settings.WallThicknessCm || (Hi.Y - Lo.Y) <= Settings.WallThicknessCm)
            return Fail(TEXT("SKETCH_UNSUPPORTED_GEOMETRY"),
                        R.Id + TEXT(" has no rectangular clear interior."));
    }
    if (RoomCount == 0)
        return Fail(TEXT("SKETCH_GEOMETRY_INCOMPLETE"), TEXT("At least one room is required."));
    for (int32 I = 0; I < L.Regions.Num(); ++I)
        for (int32 J = 0; J < I; ++J)
            if (L.Regions[I].Bounds.OverlapsInterior(L.Regions[J].Bounds))
                return Fail(TEXT("SKETCH_REGION_OVERLAP"),
                            L.Regions[I].Id + TEXT(" / ") + L.Regions[J].Id);
    for (const auto &W : L.Walls)
    {
        const auto *Expected = Owners.Find(W.Id);
        FStringSet Actual;
        for (const auto &Id : W.RegionIds)
        {
            if (!Region(L, Id) || Actual.Contains(Id))
                return Fail(TEXT("SKETCH_WALL_OWNERSHIP"), W.Id);
            Actual.Add(Id);
        }
        if (!Expected || Actual.Num() < 1 || Actual.Num() > 2 || Actual.Num() != Expected->Num())
            return Fail(TEXT("SKETCH_WALL_OWNERSHIP"), W.Id);
        for (const auto &Id : Actual)
            if (!Expected->Contains(Id))
                return Fail(TEXT("SKETCH_WALL_OWNERSHIP"), W.Id);
    }
    for (int32 I = 0; I < L.Walls.Num(); ++I)
    {
        const auto &W = L.Walls[I];
        const auto A = Vertex(L, W.StartVertexId)->PositionCm,
                   B = Vertex(L, W.EndVertexId)->PositionCm;
        for (int32 J = 0; J < I; ++J)
        {
            const auto &Other = L.Walls[J];
            const auto C = Vertex(L, Other.StartVertexId)->PositionCm,
                       D = Vertex(L, Other.EndVertexId)->PositionCm;
            if (W.Axis == Other.Axis)
            {
                if (A[1 - W.Axis] == C[1 - W.Axis] &&
                    FMath::Min(B[W.Axis], D[W.Axis]) - FMath::Max(A[W.Axis], C[W.Axis]) > Tolerance)
                    return Fail(TEXT("SKETCH_WALL_DUPLICATE"), W.Id + TEXT(" / ") + Other.Id);
            }
            else
            {
                const FVector2D P = W.Axis == 0 ? FVector2D(C.X, A.Y) : FVector2D(A.X, C.Y);
                const bool bInside = P.X >= A.X && P.X <= B.X && P.Y >= A.Y && P.Y <= B.Y &&
                                     P.X >= C.X && P.X <= D.X && P.Y >= C.Y && P.Y <= D.Y;
                const bool bShared = Exact(W.StartVertexId, Other.StartVertexId) ||
                                     Exact(W.StartVertexId, Other.EndVertexId) ||
                                     Exact(W.EndVertexId, Other.StartVertexId) ||
                                     Exact(W.EndVertexId, Other.EndVertexId);
                if (bInside && !bShared)
                    return Fail(TEXT("SKETCH_TOPOLOGY_UNNODED"), W.Id + TEXT(" / ") + Other.Id);
            }
        }
    }
    for (int32 I = 0; I < L.Openings.Num(); ++I)
    {
        const auto &O = L.Openings[I];
        const auto *W = Wall(L, O.WallId);
        if (!AddId(O.Id) || !W || O.RegionIds.Num() != 2 || W->RegionIds.Num() != 2 ||
            Exact(O.RegionIds[0], O.RegionIds[1]) ||
            (!Exact(O.Type, TEXT("door")) && !Exact(O.Type, TEXT("open_passage"))))
            return Fail(TEXT("SKETCH_OPENING_CONNECTION"), O.Id);
        for (const auto &Id : O.RegionIds)
            if (!ContainsExact(W->RegionIds, Id))
                return Fail(TEXT("SKETCH_OPENING_CONNECTION"), O.Id);
        const double Length = Vertex(L, W->EndVertexId)->PositionCm[W->Axis] -
                              Vertex(L, W->StartVertexId)->PositionCm[W->Axis];
        const double H =
            Exact(O.Type, TEXT("door")) ? Settings.DoorHeightCm : Settings.WallHeightCm;
        if (!Finite(O.CenterOffsetCm) || !Finite(O.ClearWidthCm) || !Finite(O.ClearHeightCm) ||
            O.ClearWidthCm <= Tolerance || O.ClearHeightCm <= Tolerance ||
            !Near(O.ClearHeightCm, H) || O.CenterOffsetCm - O.ClearWidthCm / 2 < -Tolerance ||
            O.CenterOffsetCm + O.ClearWidthCm / 2 > Length + Tolerance)
            return Fail(TEXT("SKETCH_OPENING_OUT_OF_BOUNDS"), O.Id);
        for (int32 J = 0; J < I; ++J)
        {
            const auto &Old = L.Openings[J];
            if (Exact(O.WallId, Old.WallId) &&
                FMath::Min(O.CenterOffsetCm + O.ClearWidthCm / 2,
                           Old.CenterOffsetCm + Old.ClearWidthCm / 2) -
                        FMath::Max(O.CenterOffsetCm - O.ClearWidthCm / 2,
                                   Old.CenterOffsetCm - Old.ClearWidthCm / 2) >
                    Tolerance)
                return Fail(TEXT("SKETCH_OPENING_OVERLAP"), O.Id + TEXT(" / ") + Old.Id);
        }
    }
    for (const auto &R : L.Regions)
    {
        const FString Expected = Exact(R.Id, L.StartRoomId)  ? TEXT("start")
                                 : Exact(R.Id, L.GoalRoomId) ? TEXT("goal")
                                                             : TEXT("none");
        if (!Exact(R.Role, Expected))
            return Fail(TEXT("SKETCH_ROLE_INVALID"), R.Id);
    }
    for (const auto &Id : {L.StartRoomId, L.GoalRoomId})
        if (!Id.IsEmpty() && (!Region(L, Id) || Region(L, Id)->bCorridor))
            return Fail(TEXT("SKETCH_ROLE_INVALID"), Id);
    if (!L.StartRoomId.IsEmpty() && Exact(L.StartRoomId, L.GoalRoomId))
        return Fail(TEXT("SKETCH_ROLE_INVALID"), TEXT("Start/Goal must differ."));
    if (Exact(L.ValidationMode, TEXT("gameplay")))
    {
        if (L.StartRoomId.IsEmpty() || L.GoalRoomId.IsEmpty())
            return Fail(TEXT("SKETCH_ROLE_INVALID"), TEXT("Gameplay requires Start/Goal."));
        FStringSet Seen;
        Seen.Add(L.StartRoomId);
        bool Changed = true;
        while (Changed)
        {
            const int32 Before = Seen.Num();
            for (const auto &O : L.Openings)
                if (Seen.Contains(O.RegionIds[0]) || Seen.Contains(O.RegionIds[1]))
                {
                    Seen.Add(O.RegionIds[0]);
                    Seen.Add(O.RegionIds[1]);
                }
            Changed = Before != Seen.Num();
        }
        for (const auto &R : L.Regions)
            if (!R.bCorridor && !Seen.Contains(R.Id))
                return Fail(TEXT("SKETCH_CONNECTIVITY_INVALID"), R.Id);
    }
    else if (!Exact(L.ValidationMode, TEXT("geometry_only")))
        return Fail(TEXT("SKETCH_ROLE_INVALID"), TEXT("Unknown validation mode."));
    return true;
}
}

bool FPlayableSketchExplicitSettings::operator==(const FPlayableSketchExplicitSettings &O) const
{
    return WallThicknessCm == O.WallThicknessCm && WallHeightCm == O.WallHeightCm &&
           DoorHeightCm == O.DoorHeightCm && FloorThicknessCm == O.FloorThicknessCm;
}

FGuid FPlayableSketchExplicitLayoutBuilder::StableId(const FString &Document, const TCHAR *Kind,
                                                     const FString &External)
{
    const FString Identity = Document + TEXT("|") + Kind + TEXT("|") + External;
    FTCHARToUTF8 Bytes(*Identity);
    FMD5 Hash;
    Hash.Update(reinterpret_cast<const uint8 *>(Bytes.Get()), Bytes.Length());
    uint8 Digest[16];
    Hash.Final(Digest);
    FGuid Result;
    FGuid::ParseExact(BytesToHex(Digest, 16), EGuidFormats::Digits, Result);
    return Result;
}

bool FPlayableSketchExplicitLayoutBuilder::Parse(const FString &Json,
                                                 FPlayableSketchExplicitLayout &OutLayout,
                                                 FString &Error)
{
    Error = TEXT(
        "SKETCH_IMPORT_INVALID: Expected an accepted canonical v1 layout (maximum 2 MB, 2048 entities, "
        "coordinates/settings within 10,000,000 cm).");
    if (Json.Len() > 2 * 1024 * 1024 || !UniqueKeys(Json))
        return false;
    FObject Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root)
        return false;
    FReader R{Error, {}};
    if (!R.Fields(Root, {TEXT("schema_version"),
                         TEXT("kind"),
                         TEXT("status"),
                         TEXT("document_id"),
                         TEXT("revision_id"),
                         TEXT("parent_revision_id"),
                         TEXT("algorithm_version"),
                         TEXT("observation_document_id"),
                         TEXT("source"),
                         TEXT("units"),
                         TEXT("coordinate_system"),
                         TEXT("dimension_basis"),
                         TEXT("validation_mode"),
                         TEXT("start_room_id"),
                         TEXT("goal_room_id"),
                         TEXT("settings"),
                         TEXT("review"),
                         TEXT("layout"),
                         TEXT("issues"),
                         TEXT("validation"),
                         TEXT("notes")}) ||
        !R.Eq(Root, TEXT("schema_version"), TEXT("playablesketch-layout/1.0")) ||
        !R.Eq(Root, TEXT("kind"), TEXT("validated_layout")) ||
        !R.Eq(Root, TEXT("status"), TEXT("validated")) || !R.Eq(Root, TEXT("units"), TEXT("cm")) ||
        !R.Eq(Root, TEXT("coordinate_system"), TEXT("local_x_right_y_up_z_up")) ||
        !R.Eq(Root, TEXT("dimension_basis"), TEXT("wall_centerline")) ||
        !R.Text(Root, TEXT("document_id"), true) || !R.Text(Root, TEXT("revision_id"), true) ||
        !R.Text(Root, TEXT("parent_revision_id"), true, true) ||
        !R.Text(Root, TEXT("observation_document_id"), true) ||
        !R.Text(Root, TEXT("algorithm_version")) ||
        !R.Text(Root, TEXT("start_room_id"), true, true) ||
        !R.Text(Root, TEXT("goal_room_id"), true, true) ||
        !R.Enum(Root, TEXT("validation_mode"), {TEXT("geometry_only"), TEXT("gameplay")}))
        return false;
    FPlayableSketchExplicitLayout L;
    L.DocumentId = TextValue(Root, TEXT("document_id"));
    L.RevisionId = TextValue(Root, TEXT("revision_id"));
    L.ValidationMode = TextValue(Root, TEXT("validation_mode"));
    if (Root->Values[TEXT("start_room_id")]->Type != EJson::Null)
        L.StartRoomId = TextValue(Root, TEXT("start_room_id"));
    if (Root->Values[TEXT("goal_room_id")]->Type != EJson::Null)
        L.GoalRoomId = TextValue(Root, TEXT("goal_room_id"));
    const auto Source = R.Object(Root, TEXT("source")), Review = R.Object(Root, TEXT("review")),
               Validation = R.Object(Root, TEXT("validation"));
    if (!R.Fields(Source, {TEXT("image_path"), TEXT("image_sha256"), TEXT("legacy_draft_path")}) ||
        !R.Text(Source, TEXT("image_path")) || !R.Text(Source, TEXT("image_sha256")) ||
        !R.Text(Source, TEXT("legacy_draft_path"), false, true) ||
        !R.Fields(Review, {TEXT("status"), TEXT("reviewer")}) ||
        !R.Eq(Review, TEXT("status"), TEXT("accepted")) || !R.Text(Review, TEXT("reviewer")) ||
        !R.Fields(Validation, {TEXT("metric"), TEXT("validator_version"), TEXT("tolerance_cm"),
                               TEXT("engine_geometry"), TEXT("navigation")}) ||
        !R.Eq(Validation, TEXT("metric"), TEXT("passed")) ||
        !R.Text(Validation, TEXT("validator_version")) ||
        !R.Number(Validation, TEXT("tolerance_cm"), 0, true) ||
        !R.Eq(Validation, TEXT("engine_geometry"), TEXT("not_run")) ||
        !R.Eq(Validation, TEXT("navigation"), TEXT("not_run")) ||
        !R.Array(Root, TEXT("issues"), 0, 0))
        return false;
    L.ImageHash = TextValue(Source, TEXT("image_sha256"));
    if (L.ImageHash.Len() != 64)
        return R.Fail(TEXT("Invalid image SHA-256."));
    for (TCHAR C : L.ImageHash)
        if (!(C >= '0' && C <= '9') && !(C >= 'a' && C <= 'f'))
            return R.Fail(TEXT("Invalid image SHA-256."));
    TArray<FString> Notes;
    if (!R.Strings(Root, TEXT("notes"), Notes, 0, MaxEntities, false))
        return false;
    const auto Settings = R.Object(Root, TEXT("settings"));
    if (!R.Fields(Settings, {TEXT("wall_thickness_cm"), TEXT("wall_height_cm"),
                             TEXT("door_height_cm"), TEXT("floor_thickness_cm"), TEXT("source")}) ||
        !R.Eq(Settings, TEXT("source"), TEXT("configured")))
        return false;
    for (const TCHAR *K : {TEXT("wall_thickness_cm"), TEXT("wall_height_cm"),
                           TEXT("door_height_cm"), TEXT("floor_thickness_cm")})
        if (!R.Number(Settings, K, 0, true))
            return false;
    L.Settings = {NumberValue(Settings, TEXT("wall_thickness_cm")),
                  NumberValue(Settings, TEXT("wall_height_cm")),
                  NumberValue(Settings, TEXT("door_height_cm")),
                  NumberValue(Settings, TEXT("floor_thickness_cm"))};
    const auto Layout = R.Object(Root, TEXT("layout"));
    if (!R.Fields(Layout, {TEXT("vertices"), TEXT("walls"), TEXT("rooms"), TEXT("corridors"),
                           TEXT("openings"), TEXT("passages"), TEXT("dimensions")}))
        return false;
    for (const TCHAR *Key : {TEXT("vertices"), TEXT("walls"), TEXT("rooms"), TEXT("corridors"),
                             TEXT("openings"), TEXT("passages"), TEXT("dimensions")})
    {
        const auto *A = R.Array(Layout, Key);
        if (!A)
            return false;
        for (const auto &Value : *A)
        {
            if (Value->Type != EJson::Object)
                return R.Fail(TEXT("Expected entity object."));
            const auto O = Value->AsObject();
            FString Id;
            const FString Kind(Key);
            if (Exact(Kind, TEXT("vertices")))
            {
                if (!R.Fields(
                        O, {TEXT("id"), TEXT("position_cm"), TEXT("state"), TEXT("provenance")}) ||
                    !R.Entity(O, Id) ||
                    !R.Enum(O, TEXT("state"), {TEXT("confirmed"), TEXT("derived")}))
                    return false;
                const auto *P = R.Array(O, TEXT("position_cm"), 2, 2);
                if (!P)
                    return false;
                for (const auto &V : *P)
                    if (V->Type != EJson::Number || !Finite(V->AsNumber()))
                        return R.Fail(TEXT("Missing/invalid vertex coordinate: ") + Id);
                L.Vertices.Add({Id, {(*P)[0]->AsNumber(), (*P)[1]->AsNumber()}});
            }
            else if (Exact(Kind, TEXT("walls")))
            {
                if (!R.Fields(O, {TEXT("id"), TEXT("start_vertex_id"), TEXT("end_vertex_id"),
                                  TEXT("axis"), TEXT("thickness_cm"), TEXT("height_cm"),
                                  TEXT("region_ids"), TEXT("provenance")}) ||
                    !R.Entity(O, Id) || !R.Text(O, TEXT("start_vertex_id"), true) ||
                    !R.Text(O, TEXT("end_vertex_id"), true) ||
                    !R.Enum(O, TEXT("axis"), {TEXT("x"), TEXT("y")}) ||
                    !R.Number(O, TEXT("thickness_cm"), 0, true) ||
                    !R.Number(O, TEXT("height_cm"), 0, true))
                    return false;
                if (NumberValue(O, TEXT("thickness_cm")) != L.Settings.WallThicknessCm ||
                    NumberValue(O, TEXT("height_cm")) != L.Settings.WallHeightCm)
                    return R.Fail(TEXT("Wall/settings mismatch: ") + Id);
                FPlayableSketchExplicitWall W;
                W.Id = Id;
                W.StartVertexId = TextValue(O, TEXT("start_vertex_id"));
                W.EndVertexId = TextValue(O, TEXT("end_vertex_id"));
                W.Axis = Exact(TextValue(O, TEXT("axis")), TEXT("x")) ? 0 : 1;
                if (!R.Strings(O, TEXT("region_ids"), W.RegionIds, 1, 2))
                    return false;
                L.Walls.Add(MoveTemp(W));
            }
            else if (Exact(Kind, TEXT("rooms")) || Exact(Kind, TEXT("corridors")))
            {
                if (!R.Fields(O, {TEXT("id"), TEXT("name"), TEXT("boundary_vertex_ids"),
                                  TEXT("boundary_wall_ids"), TEXT("role"), TEXT("provenance")}) ||
                    !R.Entity(O, Id) || !R.Text(O, TEXT("name")) ||
                    !R.Enum(O, TEXT("role"), {TEXT("none"), TEXT("start"), TEXT("goal")}))
                    return false;
                FPlayableSketchExplicitRegion RegionValue;
                RegionValue.Id = Id;
                RegionValue.Name = TextValue(O, TEXT("name"));
                RegionValue.Role = TextValue(O, TEXT("role"));
                RegionValue.bCorridor = Exact(Kind, TEXT("corridors"));
                if (!R.Strings(O, TEXT("boundary_vertex_ids"), RegionValue.VertexIds, 4) ||
                    !R.Strings(O, TEXT("boundary_wall_ids"), RegionValue.WallIds, 4))
                    return false;
                L.Regions.Add(MoveTemp(RegionValue));
            }
            else if (Exact(Kind, TEXT("openings")))
            {
                if (!R.Fields(O,
                              {TEXT("id"), TEXT("wall_id"), TEXT("type"), TEXT("center_offset_cm"),
                               TEXT("clear_width_cm"), TEXT("clear_height_cm"),
                               TEXT("connected_entities"), TEXT("state"), TEXT("provenance")}) ||
                    !R.Entity(O, Id) || !R.Text(O, TEXT("wall_id"), true) ||
                    !R.Enum(O, TEXT("type"), {TEXT("door"), TEXT("open_passage")}) ||
                    !R.Number(O, TEXT("center_offset_cm"), 0) ||
                    !R.Number(O, TEXT("clear_width_cm"), 0, true) ||
                    !R.Number(O, TEXT("clear_height_cm"), 0, true) ||
                    !R.Enum(O, TEXT("state"), {TEXT("confirmed"), TEXT("derived")}))
                    return false;
                FPlayableSketchExplicitOpening Open;
                Open.Id = Id;
                Open.WallId = TextValue(O, TEXT("wall_id"));
                Open.Type = TextValue(O, TEXT("type"));
                Open.CenterOffsetCm = NumberValue(O, TEXT("center_offset_cm"));
                Open.ClearWidthCm = NumberValue(O, TEXT("clear_width_cm"));
                Open.ClearHeightCm = NumberValue(O, TEXT("clear_height_cm"));
                if (!R.Connections(O, L, Open.RegionIds))
                    return false;
                L.Openings.Add(MoveTemp(Open));
            }
        }
    }
    if (!Geometry(L, Error))
        return false;
    const auto *RawOpenings = R.Array(Layout, TEXT("openings"));
    for (const auto &V : *RawOpenings)
    {
        const auto O = V->AsObject();
        const auto *Open = Opening(L, TextValue(O, TEXT("id")));
        const auto *W = Wall(L, Open->WallId);
        if (Exact(Open->Type, TEXT("open_passage")) &&
            Exact(TextValue(O, TEXT("state")), TEXT("derived")))
            for (const auto &E : O->GetArrayField(TEXT("connected_entities")))
            {
                const auto C = E->AsObject();
                if (Exact(TextValue(C, TEXT("type")), TEXT("corridor")))
                {
                    const double InterfaceSpan = Vertex(L, W->EndVertexId)->PositionCm[W->Axis] -
                                                 Vertex(L, W->StartVertexId)->PositionCm[W->Axis];
                    if (!Near(Open->ClearWidthCm, InterfaceSpan - L.Settings.WallThicknessCm))
                        return R.Fail(TEXT("Derived entrance width/settings mismatch: ") +
                                      Open->Id);
                    break;
                }
            }
    }
    TStringMap<int32> PassageCounts;
    const auto *Passages = R.Array(Layout, TEXT("passages"));
    for (const auto &Value : *Passages)
    {
        const auto O = Value->AsObject();
        FString Id;
        TArray<FString> Connected;
        if (!R.Fields(O, {TEXT("id"), TEXT("opening_id"), TEXT("connected_entities"), TEXT("type"),
                          TEXT("provenance")}) ||
            !R.Entity(O, Id) || !R.Text(O, TEXT("opening_id"), true) || !R.Text(O, TEXT("type")) ||
            !R.Connections(O, L, Connected))
            return false;
        const auto *Open = Opening(L, TextValue(O, TEXT("opening_id")));
        if (!Open || !Exact(Open->Type, TextValue(O, TEXT("type"))) ||
            !ArraysExact(Open->RegionIds, Connected))
            return R.Fail(TEXT("Passage must match its opening: ") + Id);
        ++PassageCounts.FindOrAdd(Open->Id);
    }
    for (const auto &Open : L.Openings)
        if (PassageCounts.FindRef(Open.Id) != 1)
            return R.Fail(TEXT("Exactly one passage per opening is required: ") + Open.Id);
    TStringMap<double> MeasuredTargets;
    const auto *Dimensions = R.Array(Layout, TEXT("dimensions"));
    for (const auto &Value : *Dimensions)
    {
        const auto O = Value->AsObject();
        FString Id;
        if (!R.Fields(O, {TEXT("id"), TEXT("value_cm"), TEXT("basis"), TEXT("target"),
                          TEXT("state"), TEXT("span_label"), TEXT("provenance")}) ||
            !R.Entity(O, Id) || !R.Number(O, TEXT("value_cm"), 0, true) ||
            !R.Text(O, TEXT("basis")) || !R.Text(O, TEXT("span_label")) ||
            !R.Enum(O, TEXT("state"), {TEXT("confirmed"), TEXT("derived")}))
            return false;
        const auto T = R.Object(O, TEXT("target"));
        if (!T || !R.Text(T, TEXT("type")))
            return false;
        const FString Type = TextValue(T, TEXT("type"));
        FString Signature = Type + TEXT("/") + TextValue(O, TEXT("basis"));
        double Measured = 0;
        if (Exact(Type, TEXT("opening_offset")))
        {
            if (!R.Enum(O, TEXT("basis"), {TEXT("center_offset"), TEXT("edge_offset")}))
                return false;
        }
        else if (Exact(Type, TEXT("opening_separation")))
        {
            if (!R.Eq(O, TEXT("basis"), TEXT("edge_offset")))
                return false;
        }
        else if (!R.Eq(O, TEXT("basis"),
                       Exact(Type, TEXT("opening_width")) ? TEXT("clear_opening")
                                                          : TEXT("wall_centerline")))
            return false;
        if (Exact(Type, TEXT("region_span")))
        {
            if (!R.Fields(T, {TEXT("type"), TEXT("region_id"), TEXT("axis")}) ||
                !R.Text(T, TEXT("region_id"), true) ||
                !R.Enum(T, TEXT("axis"), {TEXT("x"), TEXT("y")}))
                return false;
            const auto *Reg = Region(L, TextValue(T, TEXT("region_id")));
            const int32 Axis = Exact(TextValue(T, TEXT("axis")), TEXT("x")) ? 0 : 1;
            if (!Reg)
                return R.Fail(TEXT("Unknown dimension region: ") + Id);
            Measured = Reg->Bounds.Max[Axis] - Reg->Bounds.Min[Axis];
            Signature += TEXT("/") + Reg->Id + TEXT("/") + TextValue(T, TEXT("axis"));
        }
        else if (Exact(Type, TEXT("opening_separation")))
        {
            if (!R.Fields(T, {TEXT("type"), TEXT("from_opening_id"), TEXT("to_opening_id")}) ||
                !R.Text(T, TEXT("from_opening_id"), true) ||
                !R.Text(T, TEXT("to_opening_id"), true))
                return false;
            const auto *First = Opening(L, TextValue(T, TEXT("from_opening_id")));
            const auto *Second = Opening(L, TextValue(T, TEXT("to_opening_id")));
            if (!First || !Second || Exact(First->Id, Second->Id) ||
                !Exact(First->WallId, Second->WallId))
                return R.Fail(
                    TEXT("Opening separation requires two distinct openings on the same wall: ") +
                    Id);
            Measured = Second->CenterOffsetCm - Second->ClearWidthCm / 2 - First->CenterOffsetCm -
                       First->ClearWidthCm / 2;
            if (Measured < 0)
                return R.Fail(TEXT("Opening separation must follow the positive wall direction: ") +
                              Id);
            Signature += TEXT("/") + First->Id + TEXT("/") + Second->Id;
        }
        else if (Exact(Type, TEXT("wall_chain")))
        {
            TArray<FString> Chain;
            if (!R.Fields(T, {TEXT("type"), TEXT("wall_ids")}) ||
                !R.Strings(T, TEXT("wall_ids"), Chain, 1))
                return false;
            const FPlayableSketchExplicitWall *Previous = nullptr;
            for (const auto &WallId : Chain)
            {
                const auto *W = Wall(L, WallId);
                if (!W || (Previous && (Previous->Axis != W->Axis ||
                                        !Exact(Previous->EndVertexId, W->StartVertexId))))
                    return R.Fail(TEXT("Invalid ordered collinear chain: ") + Id);
                Measured += Vertex(L, W->EndVertexId)->PositionCm[W->Axis] -
                            Vertex(L, W->StartVertexId)->PositionCm[W->Axis];
                Signature += TEXT("/") + WallId;
                Previous = W;
            }
        }
        else if (Exact(Type, TEXT("opening_width")) || Exact(Type, TEXT("opening_offset")))
        {
            if (Exact(Type, TEXT("opening_width")))
            {
                if (!R.Fields(T, {TEXT("type"), TEXT("opening_id")}))
                    return false;
            }
            else if (!R.Fields(T, {TEXT("type"), TEXT("opening_id"), TEXT("region_id"),
                                   TEXT("side"), TEXT("reference")}) ||
                     !R.Text(T, TEXT("region_id"), true) ||
                     !R.Enum(T, TEXT("side"),
                             {TEXT("north"), TEXT("south"), TEXT("east"), TEXT("west")}) ||
                     !R.Enum(T, TEXT("reference"), {TEXT("min_corner"), TEXT("max_corner")}))
                return false;
            if (!R.Text(T, TEXT("opening_id"), true))
                return false;
            const auto *Open = Opening(L, TextValue(T, TEXT("opening_id")));
            if (!Open)
                return R.Fail(TEXT("Unknown dimension opening: ") + Id);
            Signature += TEXT("/") + Open->Id;
            if (Exact(Type, TEXT("opening_width")))
                Measured = Open->ClearWidthCm;
            else
            {
                const auto *Reg = Region(L, TextValue(T, TEXT("region_id")));
                if (!Reg || !ContainsExact(Open->RegionIds, Reg->Id))
                    return R.Fail(TEXT("Offset region is not connected: ") + Id);
                const auto *W = Wall(L, Open->WallId);
                FVector2D Center = Vertex(L, W->StartVertexId)->PositionCm;
                Center[W->Axis] += Open->CenterOffsetCm;
                const FString Side = TextValue(T, TEXT("side"));
                const int32 Axis =
                    (Exact(Side, TEXT("north")) || Exact(Side, TEXT("south"))) ? 0 : 1;
                const double Boundary = (Exact(Side, TEXT("north")) || Exact(Side, TEXT("east")))
                                            ? Reg->Bounds.Max[1 - Axis]
                                            : Reg->Bounds.Min[1 - Axis];
                if (!Near(Center[1 - Axis], Boundary))
                    return R.Fail(TEXT("Offset refers to the wrong room side: ") + Id);
                const FString Reference = TextValue(T, TEXT("reference"));
                Measured = Exact(Reference, TEXT("max_corner"))
                               ? Reg->Bounds.Max[Axis] - Center[Axis]
                               : Center[Axis] - Reg->Bounds.Min[Axis];
                if (Exact(TextValue(O, TEXT("basis")), TEXT("edge_offset")))
                    Measured -= Open->ClearWidthCm / 2;
                Signature += TEXT("/") + Reg->Id + TEXT("/") + Side + TEXT("/") + Reference;
            }
        }
        else
            return R.Fail(TEXT("Unassigned/unsupported dimension target: ") + Id);
        const double ValueCm = NumberValue(O, TEXT("value_cm"));
        if (!Near(ValueCm, Measured) ||
            (MeasuredTargets.Contains(Signature) && !Near(MeasuredTargets[Signature], ValueCm)))
        {
            Error = TEXT("SKETCH_DIMENSION_CONFLICT: ") + Id;
            return false;
        }
        MeasuredTargets.Add(Signature, ValueCm);
    }
    OutLayout = MoveTemp(L);
    Error.Reset();
    return true;
}

bool FPlayableSketchExplicitLayoutBuilder::Build(const FPlayableSketchExplicitLayout &Layout,
                                                 FPlayableSketchExplicitGeometry &OutGeometry,
                                                 FString &Error)
{
    auto L = Layout;
    if (!Geometry(L, Error))
        return false;
    FPlayableSketchExplicitGeometry G;
    for (const auto &R : L.Regions)
    {
        const FGuid Id =
            StableId(L.DocumentId, R.bCorridor ? TEXT("corridor") : TEXT("room"), R.Id);
        FPlayableSketchComponentSpec Spec;
        Spec.Key = FName(*(TEXT("Explicit/") + Id.ToString() + TEXT("/Floor")));
        Spec.SourceId = Id;
        Spec.bRoom = !R.bCorridor;
        Spec.Kind = EPlayableSketchPieceKind::Floor;
        if (R.bCorridor)
            Spec.OwnerKind = TEXT("Corridor");
        const auto Center = (R.Bounds.Min + R.Bounds.Max) * 0.5, Size = R.Bounds.Max - R.Bounds.Min;
        Spec.CenterCm = {Center.X, Center.Y, -L.Settings.FloorThicknessCm / 2};
        Spec.SizeCm = {Size.X, Size.Y, L.Settings.FloorThicknessCm};
        G.Specs.Add(Spec);
        if (R.bCorridor)
        {
            FPlayableSketchCorridor C;
            C.ConnectionId = Id;
            C.Footprints.Add(R.Bounds);
            G.FloorPlan.Corridors.Add(C);
        }
        else
            G.FloorPlan.Rooms.Add({Id, R.Bounds});
    }
    for (const auto &W : L.Walls)
    {
        const auto A = Vertex(L, W.StartVertexId)->PositionCm,
                   B = Vertex(L, W.EndVertexId)->PositionCm;
        const double Length = B[W.Axis] - A[W.Axis], Half = L.Settings.WallThicknessCm / 2;
        const FGuid Id = StableId(L.DocumentId, TEXT("wall"), W.Id);
        TArray<FPlayableSketchExplicitOpening> Openings;
        for (const auto &O : L.Openings)
            if (Exact(O.WallId, W.Id))
                Openings.Add(O);
        Openings.Sort(
            [](const auto &X, const auto &Y) { return X.CenterOffsetCm < Y.CenterOffsetCm; });
        auto Add = [&](double Lo, double Hi, double Bottom, double Top,
                       EPlayableSketchPieceKind Kind, const FString &Role) {
            if (Hi - Lo <= Tolerance || Top - Bottom <= Tolerance)
                return;
            FPlayableSketchComponentSpec Spec;
            Spec.Key = FName(*(TEXT("Explicit/") + Id.ToString() + TEXT("/") + Role));
            Spec.SourceId = Id;
            Spec.OwnerKind = TEXT("Wall");
            Spec.Kind = Kind;
            FVector2D Center = A;
            Center[W.Axis] += (Lo + Hi) * 0.5;
            Spec.CenterCm = {Center.X, Center.Y, (Bottom + Top) * 0.5};
            Spec.SizeCm = W.Axis == 0 ? FVector(Hi - Lo, L.Settings.WallThicknessCm, Top - Bottom)
                                      : FVector(L.Settings.WallThicknessCm, Hi - Lo, Top - Bottom);
            G.Specs.Add(Spec);
        };
        double Cursor = -Half;
        FString Left = TEXT("start");
        for (const auto &O : Openings)
        {

            const FString OpeningKey =
                StableId(L.DocumentId, TEXT("opening"), O.Id).ToString(EGuidFormats::Digits);
            const double Lo = FMath::Clamp(O.CenterOffsetCm - O.ClearWidthCm / 2, 0.0, Length),
                         Hi = FMath::Clamp(O.CenterOffsetCm + O.ClearWidthCm / 2, 0.0, Length);

            Add(Cursor, Lo, 0, L.Settings.WallHeightCm, EPlayableSketchPieceKind::Wall,
                TEXT("solid/") + Left + TEXT("/") + OpeningKey);
            if (Exact(O.Type, TEXT("door")))
                Add(Lo, Hi, O.ClearHeightCm, L.Settings.WallHeightCm,
                    EPlayableSketchPieceKind::Lintel, TEXT("lintel/") + OpeningKey);
            Cursor = Hi;
            Left = OpeningKey;
        }
        Add(Cursor, Length + Half, 0, L.Settings.WallHeightCm, EPlayableSketchPieceKind::Wall,
            TEXT("solid/") + Left + TEXT("/end"));
    }

    for (const auto &O : L.Openings)
    {
        const auto *W = Wall(L, O.WallId);
        FVector2D Center = Vertex(L, W->StartVertexId)->PositionCm;
        Center[W->Axis] += O.CenterOffsetCm;
        const FVector Size =
            W->Axis == 0 ? FVector(O.ClearWidthCm, L.Settings.WallThicknessCm, O.ClearHeightCm)
                         : FVector(L.Settings.WallThicknessCm, O.ClearWidthCm, O.ClearHeightCm);
        const FVector C(Center.X, Center.Y, O.ClearHeightCm / 2), Lo = C - Size / 2,
                                                                  Hi = C + Size / 2;
        for (const auto &Spec : G.Specs)
        {
            if (Spec.Kind == EPlayableSketchPieceKind::Floor)
                continue;
            const auto SLo = Spec.CenterCm - Spec.SizeCm / 2, SHi = Spec.CenterCm + Spec.SizeCm / 2;
            if (FMath::Min(Hi.X, SHi.X) - FMath::Max(Lo.X, SLo.X) > Tolerance &&
                FMath::Min(Hi.Y, SHi.Y) - FMath::Max(Lo.Y, SLo.Y) > Tolerance &&
                FMath::Min(Hi.Z, SHi.Z) - FMath::Max(Lo.Z, SLo.Z) > Tolerance)
            {
                Error = TEXT("SKETCH_OPENING_BLOCKED: ") + O.Id + TEXT(" intersects ") +
                        Spec.Key.ToString();
                return false;
            }
        }
    }
    G.Specs.Sort([](const auto &A, const auto &B) { return A.Key.ToString() < B.Key.ToString(); });
    OutGeometry = MoveTemp(G);
    Error.Reset();
    return true;
}

bool FPlayableSketchExplicitLayoutBuilder::ResolveSettings(
    const FString &Json, const FPlayableSketchExplicitSettings &Settings, FString &OutJson,
    FPlayableSketchExplicitLayout &OutLayout, FString &Error)
{
    FPlayableSketchExplicitLayout L;
    if (!Parse(Json, L, Error))
        return false;
    if (L.Settings == Settings)
    {
        OutJson = Json;
        OutLayout = MoveTemp(L);
        return true;
    }
    for (double V : {Settings.WallThicknessCm, Settings.WallHeightCm, Settings.DoorHeightCm,
                     Settings.FloorThicknessCm})
        if (!Finite(V) || V <= 0)
        {
            Error = TEXT("SKETCH_SETTINGS_CONFLICT: Invalid explicit settings.");
            return false;
        }
    FObject Root;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root);
    const auto Config = Root->GetObjectField(TEXT("settings")),
               Data = Root->GetObjectField(TEXT("layout"));
    Config->SetNumberField(TEXT("wall_thickness_cm"), Settings.WallThicknessCm);
    Config->SetNumberField(TEXT("wall_height_cm"), Settings.WallHeightCm);
    Config->SetNumberField(TEXT("door_height_cm"), Settings.DoorHeightCm);
    Config->SetNumberField(TEXT("floor_thickness_cm"), Settings.FloorThicknessCm);
    for (const auto &V : Data->GetArrayField(TEXT("walls")))
    {
        V->AsObject()->SetNumberField(TEXT("thickness_cm"), Settings.WallThicknessCm);
        V->AsObject()->SetNumberField(TEXT("height_cm"), Settings.WallHeightCm);
    }
    TStringMap<double> DerivedWidths;
    for (const auto &V : Data->GetArrayField(TEXT("openings")))
    {
        const auto O = V->AsObject();
        const bool bDoor = Exact(TextValue(O, TEXT("type")), TEXT("door"));
        O->SetNumberField(TEXT("clear_height_cm"),
                          bDoor ? Settings.DoorHeightCm : Settings.WallHeightCm);
        if (!bDoor && Exact(TextValue(O, TEXT("state")), TEXT("derived")))
            for (const auto &E : O->GetArrayField(TEXT("connected_entities")))
            {
                const auto C = E->AsObject();
                if (Exact(TextValue(C, TEXT("type")), TEXT("corridor")))
                {
                    const auto *W = Wall(L, TextValue(O, TEXT("wall_id")));
                    const double InterfaceSpan = Vertex(L, W->EndVertexId)->PositionCm[W->Axis] -
                                                 Vertex(L, W->StartVertexId)->PositionCm[W->Axis];
                    const double Width = InterfaceSpan - Settings.WallThicknessCm;
                    O->SetNumberField(TEXT("clear_width_cm"), Width);
                    DerivedWidths.Add(TextValue(O, TEXT("id")), Width);
                    break;
                }
            }
    }
    for (const auto &V : Data->GetArrayField(TEXT("dimensions")))
    {
        const auto D = V->AsObject(), Target = D->GetObjectField(TEXT("target"));
        if (Exact(TextValue(D, TEXT("state")), TEXT("derived")) &&
            Exact(TextValue(Target, TEXT("type")), TEXT("opening_width")))
            if (const double *Width = DerivedWidths.Find(TextValue(Target, TEXT("opening_id"))))
                D->SetNumberField(TEXT("value_cm"), *Width);
    }
    Root->SetStringField(TEXT("parent_revision_id"), L.RevisionId);
    const FString ConfigIdentity =
        FString::Printf(TEXT("%.17g|%.17g|%.17g|%.17g"), Settings.WallThicknessCm,
                        Settings.WallHeightCm, Settings.DoorHeightCm, Settings.FloorThicknessCm);
    const FString Hash =
        StableId(L.DocumentId, TEXT("settings"), L.RevisionId + TEXT("|") + ConfigIdentity)
            .ToString(EGuidFormats::Digits);
    Root->SetStringField(TEXT("revision_id"), TEXT("unreal-settings-") + Hash);
    Root->SetStringField(TEXT("algorithm_version"), TEXT("unreal-explicit-settings/1.0"));
    Root->GetObjectField(TEXT("review"))
        ->SetStringField(TEXT("reviewer"), TEXT("UnrealEditor-configured-settings"));
    FString Candidate;
    FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Candidate));
    FPlayableSketchExplicitLayout Resolved;
    if (!Parse(Candidate, Resolved, Error))
        return false;
    OutJson = MoveTemp(Candidate);
    OutLayout = MoveTemp(Resolved);
    return true;
}
