#include "ExplicitLayout/PlayableSketchExplicitLayout.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayableSketchTabletReferenceTests,
                                 "PlayableSketch.Import.TabletReferences",
                                 EAutomationTestFlags::EditorContext |
                                     EAutomationTestFlags::EngineFilter)

bool FPlayableSketchTabletReferenceTests::RunTest(const FString &Parameters)
{
    FString TwoDoors;
    for (int32 I = 11; I <= 50; ++I)
    {
        FString Json, Error;
        const bool bComplete = I <= 18 || (I >= 21 && I <= 28) || (I >= 32 && I <= 36) || I == 38 ||
                               (I >= 41 && I <= 48);
        const FString Kind = bComplete ? TEXT("validated") : TEXT("draft");
        if (!TestTrue(TEXT("Tablet reference exists"),
                      FFileHelper::LoadFileToString(
                          Json, *(FPaths::ProjectDir() /
                                  FString::Printf(TEXT("Data/ground_truth/v1/Data_%d.%s.json"), I,
                                                  *Kind)))))
            return false;
        FPlayableSketchExplicitLayout L;
        if (!bComplete)
        {
            TestFalse(TEXT("Conflicting/incomplete tablet input cannot import"),
                      FPlayableSketchExplicitLayoutBuilder::Parse(Json, L, Error));
            continue;
        }
        if (!TestTrue(FString::Printf(TEXT("Data_%d parses"), I),
                      FPlayableSketchExplicitLayoutBuilder::Parse(Json, L, Error)))
        {
            AddError(Error);
            return false;
        }
        FPlayableSketchExplicitGeometry G;
        if (!TestTrue(FString::Printf(TEXT("Data_%d preserves clear openings"), I),
                      FPlayableSketchExplicitLayoutBuilder::Build(L, G, Error)))
        {
            AddError(Error);
            return false;
        }
        if (I == 15)
        {
            TwoDoors = Json;
            TestEqual(TEXT("Both shared-wall doors remain distinct"), L.Openings.Num(), 2);
        }
        if (I == 47)
        {
            auto Settings = L.Settings;
            Settings.WallThicknessCm = 40;
            FString Updated;
            FPlayableSketchExplicitLayout Resolved;
            if (!TestTrue(TEXT("Side-branch passages resolve settings by shared span"),
                          FPlayableSketchExplicitLayoutBuilder::ResolveSettings(
                              Json, Settings, Updated, Resolved, Error)))
            {
                AddError(Error);
                return false;
            }
            for (const auto &Opening : Resolved.Openings)
            {
                if (Opening.Type == TEXT("open_passage"))
                {
                    const bool bSideBranch = Opening.RegionIds.Contains(TEXT("rC")) ||
                                             Opening.RegionIds.Contains(TEXT("rD"));
                    TestEqual(TEXT("End and side interfaces retain distinct clear widths"),
                              Opening.ClearWidthCm, bSideBranch ? 360.0 : 160.0);
                }
                else
                    TestEqual(TEXT("Door clear width survives thickness change"),
                              Opening.ClearWidthCm, 120.0);
            }
            TestTrue(TEXT("Revised branching corridor geometry builds"),
                     FPlayableSketchExplicitLayoutBuilder::Build(Resolved, G, Error));
        }
    }
    TSharedPtr<FJsonObject> Root;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(TwoDoors), Root);
    for (const auto &Value :
         Root->GetObjectField(TEXT("layout"))->GetArrayField(TEXT("dimensions")))
    {
        const auto D = Value->AsObject();
        if (D->GetObjectField(TEXT("target"))->GetStringField(TEXT("type")) ==
            TEXT("opening_separation"))
            D->SetNumberField(TEXT("value_cm"), 380);
    }
    FString Invalid, Error;
    FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Invalid));
    FPlayableSketchExplicitLayout L;
    TestFalse(TEXT("Door-to-door separation cannot masquerade as a corner offset"),
              FPlayableSketchExplicitLayoutBuilder::Parse(Invalid, L, Error));
    TestTrue(TEXT("Wrong separation reports dimension conflict"),
             Error.StartsWith(TEXT("SKETCH_DIMENSION_CONFLICT")));
    return !HasAnyErrors();
}
#endif
