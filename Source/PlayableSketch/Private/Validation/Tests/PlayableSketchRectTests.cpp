#include "Validation/Tests/PlayableSketchRectTests.h"
#include "Layout/PlayableSketchRect.h"

void FPlayableSketchRectTests::Run()
{
    const FPlayableSketchRect A(FVector2D(0, 0), FVector2D(600, 600));

    constexpr double RequiredGapCm = 100.0;

    int32 PassedCount = 0;
    int32 TotalCount = 0;

    auto Check = [&PassedCount, &TotalCount](const TCHAR *Name, bool bPassed) {
        ++TotalCount;

        if (bPassed)
        {
            ++PassedCount;

            UE_LOG(LogTemp, Display, TEXT("[PASS] %s"), Name);
        }
        else
        {
            UE_LOG(LogTemp, Error, TEXT("[FAIL] %s"), Name);
        }
    };

    auto TestCase = [&](const TCHAR *Name, const FPlayableSketchRect &B, bool bExpectedOverlap,
                        bool bExpectedGap) {
        const bool bOverlapAB = A.OverlapsInterior(B);
        const bool bOverlapBA = B.OverlapsInterior(A);

        const bool bGapAB = A.HasRequiredGap(B, RequiredGapCm);
        const bool bGapBA = B.HasRequiredGap(A, RequiredGapCm);

        const bool bPassed = bOverlapAB == bExpectedOverlap && bOverlapBA == bExpectedOverlap &&
                             bGapAB == bExpectedGap && bGapBA == bExpectedGap;

        Check(Name, bPassed);

        UE_LOG(LogTemp, Display,
               TEXT("  Overlap AB/BA=%d/%d expected=%d | Gap AB/BA=%d/%d expected=%d"), bOverlapAB,
               bOverlapBA, bExpectedOverlap, bGapAB, bGapBA, bExpectedGap);
    };

    TestCase(TEXT("Separated on X"), FPlayableSketchRect(FVector2D(800, 0), FVector2D(1400, 600)),
             false, true);

    TestCase(TEXT("Touching edges"), FPlayableSketchRect(FVector2D(600, 0), FVector2D(1200, 600)),
             false, false);

    TestCase(TEXT("Interior overlap"), FPlayableSketchRect(FVector2D(550, 0), FVector2D(1150, 600)),
             true, false);

    TestCase(TEXT("Separated on Y"), FPlayableSketchRect(FVector2D(0, 800), FVector2D(600, 1400)),
             false, true);

    TestCase(TEXT("Only 50 cm gap"), FPlayableSketchRect(FVector2D(650, 0), FVector2D(1250, 600)),
             false, false);

    TestCase(TEXT("Exactly 100 cm gap"),
             FPlayableSketchRect(FVector2D(700, 0), FVector2D(1300, 600)), false, true);

    const FPlayableSketchRect InvalidRect(FVector2D(0, 0), FVector2D(0, 600));

    Check(TEXT("Zero width is invalid"), !InvalidRect.IsValid());

    Check(TEXT("Invalid rectangle cannot satisfy gap"),
          !A.HasRequiredGap(InvalidRect, RequiredGapCm));

    Check(TEXT("Negative gap is rejected"), !A.HasRequiredGap(A, -100.0));

    UE_LOG(LogTemp, Display, TEXT("Layout rectangle tests: %d/%d passed."), PassedCount,
           TotalCount);
}
