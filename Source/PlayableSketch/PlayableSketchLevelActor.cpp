#include "PlayableSketchLevelActor.h"
#include "SpatialGraph/PlayableSketchGraphValidator.h"

APlayableSketchLevelActor::APlayableSketchLevelActor()
{
	PrimaryActorTick.bCanEverTick = true;

}

void APlayableSketchLevelActor::BeginPlay()
{
	Super::BeginPlay();
	
}

void APlayableSketchLevelActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

}

void APlayableSketchLevelActor::ValidateGraph()
{
    if (!GraphAsset)
    {
        UE_LOG(LogTemp, Error, TEXT("GraphAsset is not assigned."));
        return;
    }

    const TArray<FString> Errors =
        FPlayableSketchGraphValidator::Validate(GraphAsset->Graph);

    if (Errors.IsEmpty())
    {
        UE_LOG(LogTemp, Display, TEXT("Graph validation passed."));
        return;
    }

    UE_LOG(LogTemp, Error,TEXT("Graph validation failed: %d error(s)."), Errors.Num());

    for (const FString& Error : Errors)
    {
        UE_LOG(LogTemp, Error, TEXT("%s"), *Error);
    }
}
