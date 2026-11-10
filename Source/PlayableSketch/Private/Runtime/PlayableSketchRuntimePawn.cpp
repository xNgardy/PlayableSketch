#include "Runtime/PlayableSketchRuntime.h"
#include "PlayableSketchLevelActor.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"
#include "Components/InputComponent.h"
#include "GameFramework/FloatingPawnMovement.h"
#include "InputCoreTypes.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"

APlayableSketchRuntimePawn::APlayableSketchRuntimePawn()
{
    PrimaryActorTick.bCanEverTick = true;
    Capsule = CreateDefaultSubobject<UCapsuleComponent>(TEXT("AgentCapsule"));
    SetRootComponent(Capsule);
    Capsule->InitCapsuleSize(50, 95);
    Capsule->SetCollisionProfileName(TEXT("Pawn"));
    Capsule->SetGenerateOverlapEvents(false);
    auto *Marker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PawnMarker"));
    Marker->SetupAttachment(Capsule);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(
        TEXT("/Engine/BasicShapes/Cube.Cube"));
    Marker->SetStaticMesh(Cube.Object);
    Marker->SetRelativeScale3D(FVector(.5, .5, 1.5));
    Marker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Movement = CreateDefaultSubobject<UFloatingPawnMovement>(TEXT("FlatMovement"));
    Movement->SetUpdatedComponent(Capsule);

    Movement->PrimaryComponentTick.bCanEverTick = false;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("PlanCamera"));
    Camera->SetupAttachment(Capsule);
    Camera->SetRelativeLocation(FVector(0, 0, 1800));
    Camera->SetAbsolute(true, true, false);
    Camera->SetWorldRotation(FRotator(-90, -90, 0));
    Camera->FieldOfView = 80;
    Camera->bUsePawnControlRotation = false;
}
void APlayableSketchRuntimePawn::Configure(APlayableSketchLevelActor &Level)
{
    Layout = &Level;
    Capsule->SetCapsuleSize(Level.PawnRadiusCm + Level.ClearanceCm,
                            Level.PawnHeightCm / 2 + Level.ClearanceCm / 2);
    FitCamera();
}
void APlayableSketchRuntimePawn::Follow(const TArray<FVector2D> &Route)
{
    Path = Route;
    PathIndex = 0;
    bReachedGoal = false;
}
void APlayableSketchRuntimePawn::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!Layout || !Layout->ExplicitNavigationResult.bReachable)
        return;
    FitCamera();
    const FVector Local = Layout->GetActorTransform().InverseTransformPosition(GetActorLocation());
    FVector2D From(Local.X, Local.Y), Target = From;
    const double Step = FMath::Clamp(static_cast<double>(DeltaSeconds), 0.0, 0.1) * 200;
    if (PathIndex < Path.Num())
    {
        if (FVector2D::Distance(From, Path[PathIndex]) < .2)
            ++PathIndex;
        if (PathIndex < Path.Num())
        {
            const auto Delta = Path[PathIndex] - From;
            Target = From + Delta.GetSafeNormal() * FMath::Min(Step, Delta.Size());
        }
        else
            bReachedGoal = true;
    }
    else
        Target += ScreenMovement(Keys).GetSafeNormal() * Step;
    if (Target.Equals(From))
        return;
    if (!FPlayableSketchExplicitNavigation::CanMove(*Layout, From, Target,
                                                    Layout->ExplicitNavigationResult.Agent, this))
        return;
    const FVector Goal =
        Layout->GetActorTransform().TransformPosition(FVector(Target.X, Target.Y, Local.Z));
    FHitResult Hit;
    Movement->SafeMoveUpdatedComponent(Goal - GetActorLocation(), GetActorQuat(), true, Hit);
}
void APlayableSketchRuntimePawn::ForwardDown()
{
    Keys.Y = 1;
    Path.Reset();
}
void APlayableSketchRuntimePawn::ForwardUp()
{
    if (Keys.Y > 0)
        Keys.Y = 0;
}
void APlayableSketchRuntimePawn::BackDown()
{
    Keys.Y = -1;
    Path.Reset();
}
void APlayableSketchRuntimePawn::BackUp()
{
    if (Keys.Y < 0)
        Keys.Y = 0;
}
void APlayableSketchRuntimePawn::RightDown()
{
    Keys.X = 1;
    Path.Reset();
}
void APlayableSketchRuntimePawn::RightUp()
{
    if (Keys.X > 0)
        Keys.X = 0;
}
void APlayableSketchRuntimePawn::LeftDown()
{
    Keys.X = -1;
    Path.Reset();
}
void APlayableSketchRuntimePawn::LeftUp()
{
    if (Keys.X < 0)
        Keys.X = 0;
}
void APlayableSketchRuntimePawn::SetupPlayerInputComponent(UInputComponent *Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindKey(EKeys::Up, IE_Pressed, this, &APlayableSketchRuntimePawn::ForwardDown);
    Input->BindKey(EKeys::Up, IE_Released, this, &APlayableSketchRuntimePawn::ForwardUp);
    Input->BindKey(EKeys::Down, IE_Pressed, this, &APlayableSketchRuntimePawn::BackDown);
    Input->BindKey(EKeys::Down, IE_Released, this, &APlayableSketchRuntimePawn::BackUp);
    Input->BindKey(EKeys::Right, IE_Pressed, this, &APlayableSketchRuntimePawn::RightDown);
    Input->BindKey(EKeys::Right, IE_Released, this, &APlayableSketchRuntimePawn::RightUp);
    Input->BindKey(EKeys::Left, IE_Pressed, this, &APlayableSketchRuntimePawn::LeftDown);
    Input->BindKey(EKeys::Left, IE_Released, this, &APlayableSketchRuntimePawn::LeftUp);
    Input->BindKey(EKeys::W, IE_Pressed, this, &APlayableSketchRuntimePawn::ForwardDown);
    Input->BindKey(EKeys::W, IE_Released, this, &APlayableSketchRuntimePawn::ForwardUp);
    Input->BindKey(EKeys::S, IE_Pressed, this, &APlayableSketchRuntimePawn::BackDown);
    Input->BindKey(EKeys::S, IE_Released, this, &APlayableSketchRuntimePawn::BackUp);
    Input->BindKey(EKeys::D, IE_Pressed, this, &APlayableSketchRuntimePawn::RightDown);
    Input->BindKey(EKeys::D, IE_Released, this, &APlayableSketchRuntimePawn::RightUp);
    Input->BindKey(EKeys::A, IE_Pressed, this, &APlayableSketchRuntimePawn::LeftDown);
    Input->BindKey(EKeys::A, IE_Released, this, &APlayableSketchRuntimePawn::LeftUp);
}
APlayableSketchRuntimeGameMode::APlayableSketchRuntimeGameMode()
{
    DefaultPawnClass = nullptr;
    PlayerControllerClass = APlayableSketchRuntimeController::StaticClass();
}

FVector2D APlayableSketchRuntimePawn::ScreenMovement(const FVector2D &Input) const
{
    if (!Layout)
        return FVector2D::ZeroVector;
    const FVector World = Camera->GetRightVector() * Input.X + Camera->GetUpVector() * Input.Y;
    const FVector Local = Layout->GetActorTransform().InverseTransformVectorNoScale(World);
    return FVector2D(Local.X, Local.Y);
}
void APlayableSketchRuntimePawn::FitCamera()
{
    if (!Layout)
        return;
    FVector2D Viewport(1440, 900);
    if (GEngine && GEngine->GameViewport)
        GEngine->GameViewport->GetViewportSize(Viewport);
    if (Viewport.X < 1 || Viewport.Y < 1)
        return;
    if (Viewport.Equals(CameraViewportSize))
        return;
    CameraViewportSize = Viewport;
    const FBox Bounds = Layout->GetComponentsBoundingBox(true);
    const double Aspect = Viewport.X / Viewport.Y;
    const double Panel = FMath::Min(360.0, Viewport.X * .32);
    const double Available = FMath::Max(.4, 1.0 - Panel / Viewport.X);
    const double Tangent = FMath::Tan(FMath::DegreesToRadians(Camera->FieldOfView / 2.0));
    const double Height = FMath::Max(Bounds.GetSize().X / Available, Bounds.GetSize().Y * Aspect) /
                              (2 * Tangent) * 1.18 +
                          Bounds.GetSize().Z;
    const double Offset = Panel / Viewport.X * Height * Tangent;
    Camera->SetWorldLocation(Bounds.GetCenter() - Camera->GetRightVector() * Offset +
                             FVector(0, 0, Height));
}

void APlayableSketchRuntimePawn::SetScreenInput(const FVector2D &Input)
{
    Keys = Input;
    Path.Reset();
}
