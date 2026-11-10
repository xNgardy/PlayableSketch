#include "Runtime/PlayableSketchRuntime.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/SBoxPanel.h"
#include "Framework/Application/SlateApplication.h"
#include "Misc/ConfigCacheIni.h"

void APlayableSketchRuntimeController::ToggleAppearance()
{
    bDarkMode = !bDarkMode;
    GConfig->SetBool(TEXT("PlayableSketch.Appearance"), TEXT("DarkMode"), bDarkMode,
                     GGameUserSettingsIni);
    GConfig->Flush(false, GGameUserSettingsIni);
}
void APlayableSketchRuntimeController::CreatePanel()
{
    if (!GEngine || !GEngine->GameViewport || !FSlateApplication::IsInitialized())
        return;
    auto Button = [](const TCHAR *Label, TFunction<void()> Action) {
        return SNew(SButton)
            .Text(FText::FromString(Label))
            .IsFocusable(true)
            .ContentPadding(FMargin(10, 8))
            .OnClicked_Lambda([Action]() {
                Action();
                return FReply::Handled();
            });
    };
    auto Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0,
                                         8)[SNew(STextBlock)
                                                .Text(FText::FromString(TEXT("PlayableSketch")))
                                                .Font(FCoreStyle::GetDefaultFontStyle("Bold", 22))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)
        [SNew(STextBlock)
             .AutoWrapText(true)
             .Text(FText::FromString(TEXT(
                 "Sketch. Shape. Explore.\nPrepare your plan in the workspace, then open it here.")))];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 8)[Button(TEXT("1   Open workspace"), [this] { OpenReview(); })];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 14)[Button(TEXT("2   Open latest plan"), [this] { OpenLatestPlan(); })];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 7)[SNew(STextBlock)
                        .AutoWrapText(true)
                        .Text_Lambda([this] {
                            return FText::FromString(
                                bReady                    ? TEXT("Ready to explore")
                                : Stage == TEXT("failed") ? TEXT("Your plan needs attention")
                                : Stage == TEXT("idle")   ? TEXT("Start in the workspace")
                                                          : TEXT("Opening your plan..."));
                        })
                        .Font(FCoreStyle::GetDefaultFontStyle("Bold", 13))];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 14)[SNew(STextBlock).AutoWrapText(true).Text_Lambda([this] {
        if (Stage == TEXT("failed") && Status.Contains(TEXT("Runtime readiness rejected")))
            return FText::FromString(TEXT(
                "The player cannot safely cross this plan. Widen the route in the workspace, confirm and export again. Your previous level is kept."));
        return FText::FromString(Status);
    })];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 8)[SNew(SButton)
                        .Text(FText::FromString(TEXT("Follow route to Goal")))
                        .IsEnabled_Lambda([this] { return bReady; })
                        .OnClicked_Lambda([this] {
                            PlayRoute();
                            FSlateApplication::Get().SetAllUserFocusToGameViewport();
                            return FReply::Handled();
                        })];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)
        [SNew(STextBlock)
             .AutoWrapText(true)
             .Text(FText::FromString(TEXT(
                 "Click the level, then use WASD or arrow keys.\nMovement follows the directions on your screen.")))];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 8)[SNew(SHorizontalBox) +
                    SHorizontalBox::Slot().FillWidth(
                        1)[Button(TEXT("Save level"), [this] { SaveRuntime(); })] +
                    SHorizontalBox::Slot().FillWidth(
                        1)[Button(TEXT("Load saved level"), [this] { LoadRuntime(); })]];
    Rows->AddSlot().AutoHeight().Padding(
        0, 0, 0, 10)[SNew(SButton)
                         .Text_Lambda([this] {
                             return FText::FromString(bDarkMode ? TEXT("Switch to light mode")
                                                                : TEXT("Switch to night mode"));
                         })
                         .OnClicked_Lambda([this] {
                             ToggleAppearance();
                             return FReply::Handled();
                         })];
    Rows->AddSlot().AutoHeight()[SNew(SButton)
                                     .Text_Lambda([this] {
                                         return FText::FromString(
                                             bShowAdvanced ? TEXT("Hide advanced options")
                                                           : TEXT("Advanced options"));
                                     })
                                     .OnClicked_Lambda([this] {
                                         bShowAdvanced = !bShowAdvanced;
                                         return FReply::Handled();
                                     })];
    auto Advanced = SNew(SVerticalBox);
    Advanced->AddSlot().AutoHeight().Padding(
        0, 10, 0, 4)[SNew(STextBlock).Text(FText::FromString(TEXT("Local service")))];
    Advanced->AddSlot()
        .AutoHeight()[SNew(SEditableTextBox)
                          .Text_Lambda([this] { return FText::FromString(ServiceUrl); })
                          .OnTextChanged_Lambda([this](const FText &T) {
                              ++RequestSequence;
                              ServiceUrl = T.ToString();
                              SelectedRevision.Reset();
                          })];
    Advanced->AddSlot().AutoHeight().Padding(
        0, 8, 0, 4)[SNew(STextBlock).Text(FText::FromString(TEXT("Job ID")))];
    Advanced->AddSlot().AutoHeight()[SNew(SEditableTextBox)
                                         .Text_Lambda([this] { return FText::FromString(JobId); })
                                         .OnTextChanged_Lambda([this](const FText &T) {
                                             ++RequestSequence;
                                             JobId = T.ToString();
                                             SelectedRevision.Reset();
                                         })];
    Advanced->AddSlot().AutoHeight().Padding(
        0, 8, 0, 4)[SNew(STextBlock).Text(FText::FromString(TEXT("Export revision")))];
    Advanced->AddSlot()
        .AutoHeight()[SNew(SEditableTextBox)
                          .Text_Lambda([this] { return FText::FromString(SelectedRevision); })
                          .OnTextChanged_Lambda([this](const FText &T) {
                              ++RequestSequence;
                              SelectedRevision = T.ToString();
                          })];
    Advanced->AddSlot().AutoHeight().Padding(
        0, 5, 0, 5)[Button(TEXT("Open selected revision"), [this] { ImportAccepted(); })];
    Advanced->AddSlot().AutoHeight()[Button(TEXT("Cancel loading"), [this] { CancelRequest(); })];
    Advanced->AddSlot().AutoHeight().Padding(
        0, 10, 0, 0)[SNew(STextBlock).AutoWrapText(true).Text_Lambda([this] {
        return FText::FromString(Stage + TEXT("\n") + Status);
    })];
    Rows->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this] {
        return bShowAdvanced ? EVisibility::Visible : EVisibility::Collapsed;
    })[Advanced]];
    Panel = SNew(SOverlay) +
            SOverlay::Slot()
                .HAlign(HAlign_Left)
                .VAlign(VAlign_Fill)
                .Padding(14)[SNew(SBox).WidthOverride(
                    320)[SNew(SBorder)
                             .Padding(16)
                             .BorderBackgroundColor_Lambda([this] {
                                 return bDarkMode ? FLinearColor(.045, .06, .05, .97)
                                                  : FLinearColor(.94, .95, .90, .98);
                             })
                             .ForegroundColor_Lambda([this] {
                                 return bDarkMode ? FSlateColor(FLinearColor(.92, .95, .87))
                                                  : FSlateColor(FLinearColor(.09, .14, .10));
                             })[SNew(SScrollBox) + SScrollBox::Slot()[Rows]]]];
    Panel->ForceVolatile(true);
    GEngine->GameViewport->AddViewportWidgetContent(Panel.ToSharedRef(), 10);
    FInputModeGameAndUI Input;
    Input.SetHideCursorDuringCapture(false);
    SetInputMode(Input);
}
