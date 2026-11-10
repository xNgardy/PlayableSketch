#pragma once
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

inline FString PlayableSketchNavigationFixtureRoles(const FString &Json)
{
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root))
        return Json;
    const auto Rooms = Root->GetObjectField(TEXT("layout"))->GetArrayField(TEXT("rooms"));
    if (Rooms.Num() < 2)
        return Json;
    Root->SetStringField(TEXT("validation_mode"), TEXT("gameplay"));
    Root->SetStringField(TEXT("start_room_id"), Rooms[0]->AsObject()->GetStringField(TEXT("id")));
    Root->SetStringField(TEXT("goal_room_id"),
                         Rooms.Last()->AsObject()->GetStringField(TEXT("id")));
    for (int32 I = 0; I < Rooms.Num(); ++I)
        Rooms[I]->AsObject()->SetStringField(TEXT("role"), I == 0                 ? TEXT("start")
                                                           : I == Rooms.Num() - 1 ? TEXT("goal")
                                                                                  : TEXT("none"));
    Root->SetStringField(TEXT("revision_id"), TEXT("step12-controlled-navigation-fixture"));
    FString Result;
    FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Result));
    return Result;
}
