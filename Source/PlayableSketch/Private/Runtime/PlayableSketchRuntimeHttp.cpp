#include "Runtime/PlayableSketchRuntime.h"
#include "PlayableSketchLevelActor.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "GenericPlatform/GenericPlatformHttp.h"
#include "HAL/PlatformProcess.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Internationalization/Regex.h"

namespace
{
bool RevisionId(const FString &Id)
{
    FRegexMatcher M(FRegexPattern(TEXT("^metric-[0-9TZ]+-[a-f0-9]{12}$")), Id);
    return M.FindNext();
}
auto Request(const FString &Url, const FString &Verb = TEXT("GET"))
{
    auto R = FHttpModule::Get().CreateRequest();
    R->SetURL(Url);
    R->SetVerb(Verb);
    R->SetTimeout(15);
    R->SetDelegateThreadPolicy(EHttpRequestDelegateThreadPolicy::CompleteOnGameThread);
    return R;
}
bool Response(FHttpResponsePtr R, bool Connected, TSharedPtr<FJsonObject> &J, FString &Error)
{
    if (!Connected || !R)
    {
        Error = TEXT(
            "Local service unavailable or timed out. Start the sidecar, then retry; previous level retained.");
        return false;
    }
    if (R->GetContent().Num() > 2 * 1024 * 1024 ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(R->GetContentAsString()), J) ||
        !J)
    {
        Error = TEXT("Invalid or oversized service response.");
        return false;
    }
    if (R->GetResponseCode() < 200 || R->GetResponseCode() >= 300)
    {
        if (!J->TryGetStringField(TEXT("error"), Error))
            Error = TEXT("Service request rejected.");
        return false;
    }
    return true;
}
void Append(TArray<uint8> &Bytes, const FString &Text)
{
    FTCHARToUTF8 Utf8(*Text);
    Bytes.Append(reinterpret_cast<const uint8 *>(Utf8.Get()), Utf8.Length());
}
}
void APlayableSketchRuntimeController::OpenReview()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl))
    {
        Status = TEXT("Choose an explicit loopback service URL.");
        return;
    }
    const FString Url =
        ServiceUrl +
        (APlayableSketchLevelActor::IsPipelineJobId(JobId) ? TEXT("/?job=") + JobId : TEXT("/"));
    FPlatformProcess::LaunchURL(*Url, nullptr, nullptr);
    Status = TEXT(
        "In Review plan, choose Playable level, select Start and Goal, then confirm and export. Come back and choose Open latest plan.");
}
void APlayableSketchRuntimeController::UploadImage()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl))
    {
        Status = TEXT("Use http://127.0.0.1:PORT or localhost:PORT.");
        return;
    }
    const FString Path = FPaths::ConvertRelativePathToFull(ImagePath);
    const FString Extension = FPaths::GetExtension(Path).ToLower();
    TArray<uint8> Image;
    const int64 Size = IFileManager::Get().FileSize(*Path);
    if ((Extension != TEXT("png") && Extension != TEXT("jpg") && Extension != TEXT("jpeg")) ||
        Size <= 0 || Size > 20 * 1024 * 1024 || !FFileHelper::LoadFileToArray(Image, *Path))
    {
        Status =
            TEXT("Choose a readable local PNG/JPEG up to 20 MB, or use the browser file picker.");
        return;
    }
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Bootstrap = Request(Service + TEXT("/api/bootstrap"));
    Bootstrap->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job, Revision,
                                                      Image = MoveTemp(Image),
                                                      Extension](FHttpRequestPtr,
                                                                 FHttpResponsePtr R, bool Ok) {
        if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
            return;
        TSharedPtr<FJsonObject> J;
        FString Error, Token;
        if (!Response(R, Ok, J, Error) || !J->TryGetStringField(TEXT("token"), Token))
        {
            Weak->Stage = TEXT("failed");
            Weak->Status = Error;
            return;
        }
        const FString Boundary =
            TEXT("SketchRuntime") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
        TArray<uint8> Body;
        Append(
            Body,
            TEXT("--") + Boundary +
                TEXT(
                    "\r\nContent-Disposition: form-data; name=\"config\"\r\n\r\n{\"mode\":\"inference\"}\r\n--") +
                Boundary +
                TEXT("\r\nContent-Disposition: form-data; name=\"image\"; filename=\"sketch.") +
                Extension + TEXT("\"\r\nContent-Type: image/") +
                (Extension == TEXT("png") ? TEXT("png") : TEXT("jpeg")) + TEXT("\r\n\r\n"));
        Body.Append(Image);
        Append(Body, TEXT("\r\n--") + Boundary + TEXT("--\r\n"));
        auto Upload = Request(Service + TEXT("/jobs"), TEXT("POST"));
        Upload->SetHeader(TEXT("Content-Type"), TEXT("multipart/form-data; boundary=") + Boundary);
        Upload->SetHeader(TEXT("X-Review-Token"), Token);
        Upload->SetContent(MoveTemp(Body));
        Upload->OnProcessRequestComplete().BindLambda(
            [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr R2,
                                                     bool Ok2) {
                if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                    return;
                TSharedPtr<FJsonObject> J2;
                FString Error2, Id;
                if (!Response(R2, Ok2, J2, Error2) || !J2->TryGetStringField(TEXT("job_id"), Id) ||
                    !APlayableSketchLevelActor::IsPipelineJobId(Id))
                {
                    Weak->Status = Error2;
                    Weak->Stage = TEXT("failed");
                    return;
                }
                Weak->JobId = Id;
                Weak->SelectedRevision.Reset();
                Weak->Stage = TEXT("uploaded");
                Weak->Status = TEXT("Upload acknowledged: ") + Id +
                               TEXT(". Processing asynchronously; open review when ready.");
            });
        if (!Upload->ProcessRequest())
        {
            Weak->Stage = TEXT("failed");
            Weak->Status = TEXT("Could not dispatch upload.");
        }
    });
    Stage = TEXT("uploading");
    Status = TEXT("Uploading image to local sidecar…");
    if (!Bootstrap->ProcessRequest())
    {
        Stage = TEXT("failed");
        Status = TEXT("Could not dispatch local service request.");
    }
}
void APlayableSketchRuntimeController::RefreshJob()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl) ||
        !APlayableSketchLevelActor::IsPipelineJobId(JobId))
    {
        Status = TEXT("Choose a loopback service and valid Job ID.");
        return;
    }
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Poll = Request(Service + TEXT("/jobs/") + Job);
    Poll->OnProcessRequestComplete().BindLambda(
        [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr R, bool Ok) {
            if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                return;
            TSharedPtr<FJsonObject> J;
            FString Error, State, StageName, Accepted;
            if (!Response(R, Ok, J, Error) || !J->TryGetStringField(TEXT("state"), State))
            {
                Weak->Status = Error;
                Weak->Stage = TEXT("failed");
                return;
            }
            J->TryGetStringField(TEXT("stage"), StageName);
            J->TryGetStringField(TEXT("error"), Error);
            if (J->TryGetStringField(TEXT("accepted_revision_id"), Accepted) &&
                Weak->SelectedRevision.IsEmpty())
                Weak->SelectedRevision = Accepted;
            Weak->Stage = State;
            Weak->Status =
                State + TEXT(" / ") + StageName + (Error.IsEmpty() ? TEXT("") : TEXT(": ") + Error);
        });
    Stage = TEXT("checking");
    Status = TEXT("Checking local job…");
    if (!Poll->ProcessRequest())
    {
        Stage = TEXT("failed");
        Status = TEXT("Could not dispatch job status request.");
    }
}
void APlayableSketchRuntimeController::ImportAccepted()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl) ||
        !APlayableSketchLevelActor::IsPipelineJobId(JobId) || !RevisionId(SelectedRevision))
    {
        Status = TEXT(
            "Select a local service, Job ID and accepted metric revision. Refresh after browser acceptance.");
        return;
    }
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Fetch = Request(Service + TEXT("/jobs/") + Job + TEXT("/layout?revision_id=") +
                         FGenericPlatformHttp::UrlEncode(Revision));
    Fetch->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job, Revision](
                                                     FHttpRequestPtr, FHttpResponsePtr R, bool Ok) {
        if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
            return;
        TSharedPtr<FJsonObject> J;
        FString Error, Returned;
        if (!Response(R, Ok, J, Error) || !J->TryGetStringField(TEXT("revision_id"), Returned) ||
            !Returned.Equals(Revision + TEXT("-accepted"), ESearchCase::CaseSensitive))
        {
            Weak->Status = TEXT("Import rejected; previous level retained: ") + Error;
            Weak->Stage = TEXT("failed");
            return;
        }
        Weak->Stage = TEXT("building");
        if (!Weak->PublishAccepted(R->GetContentAsString(), Error))
        {
            Weak->Status = TEXT("Runtime readiness rejected; previous level retained: ") + Error;
            Weak->Stage = TEXT("failed");
        }
    });
    Stage = TEXT("importing");
    Status = TEXT("Fetching the explicitly selected accepted revision…");
    if (!Fetch->ProcessRequest())
    {
        Stage = TEXT("failed");
        Status = TEXT("Could not dispatch accepted import.");
    }
}

void APlayableSketchRuntimeController::CancelJob()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl) ||
        !APlayableSketchLevelActor::IsPipelineJobId(JobId))
        return;
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Bootstrap = Request(Service + TEXT("/api/bootstrap"));
    Bootstrap->OnProcessRequestComplete().BindLambda(
        [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr R, bool Ok) {
            if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                return;
            TSharedPtr<FJsonObject> J;
            FString Error, Token;
            if (!Response(R, Ok, J, Error) || !J->TryGetStringField(TEXT("token"), Token))
            {
                Weak->Status = Error;
                return;
            }
            auto Cancel = Request(Service + TEXT("/jobs/") + Job + TEXT("/cancel"), TEXT("POST"));
            Cancel->SetHeader(TEXT("X-Review-Token"), Token);
            Cancel->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
            Cancel->SetContentAsString(TEXT("{}"));
            Cancel->OnProcessRequestComplete().BindLambda(
                [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr R2,
                                                         bool Ok2) {
                    if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                        return;
                    TSharedPtr<FJsonObject> J2;
                    FString Error2;
                    if (!Response(R2, Ok2, J2, Error2))
                    {
                        Weak->Status = Error2;
                        return;
                    }
                    Weak->Stage = TEXT("cancelled");
                    Weak->Status = TEXT("Server job cancelled; previous playable level retained.");
                });
            Cancel->ProcessRequest();
        });
    Bootstrap->ProcessRequest();
}
void APlayableSketchRuntimeController::RetryJob()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl) ||
        !APlayableSketchLevelActor::IsPipelineJobId(JobId))
        return;
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Bootstrap = Request(Service + TEXT("/api/bootstrap"));
    Bootstrap->OnProcessRequestComplete().BindLambda(
        [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr R, bool Ok) {
            if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                return;
            TSharedPtr<FJsonObject> J;
            FString Error, Token;
            if (!Response(R, Ok, J, Error) || !J->TryGetStringField(TEXT("token"), Token))
            {
                Weak->Status = Error;
                return;
            }
            auto Retry = Request(Service + TEXT("/jobs/") + Job + TEXT("/retry"), TEXT("POST"));
            Retry->SetHeader(TEXT("X-Review-Token"), Token);
            Retry->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
            Retry->SetContentAsString(TEXT("{}"));
            Retry->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job,
                                                          Revision](FHttpRequestPtr,
                                                                    FHttpResponsePtr R2, bool Ok2) {
                if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
                    return;
                TSharedPtr<FJsonObject> J2;
                FString Error2, Id;
                if (!Response(R2, Ok2, J2, Error2) || !J2->TryGetStringField(TEXT("job_id"), Id))
                {
                    Weak->Status = Error2;
                    return;
                }
                Weak->JobId = Id;
                Weak->SelectedRevision.Reset();
                Weak->Stage = TEXT("uploaded");
                Weak->Status = TEXT("Retry started as a new job: ") + Id;
            });
            Retry->ProcessRequest();
        });
    Bootstrap->ProcessRequest();
}

void APlayableSketchRuntimeController::OpenLatestPlan()
{
    if (!APlayableSketchLevelActor::IsLocalPipelineUrl(ServiceUrl))
    {
        Status = TEXT("Open the local workspace first, then try again.");
        return;
    }
    const auto Sequence = ++RequestSequence;
    const FString Service = ServiceUrl, Job = JobId, Revision = SelectedRevision;
    TWeakObjectPtr<APlayableSketchRuntimeController> Weak(this);
    auto Selection = Request(Service + TEXT("/runtime/selection"));
    Selection->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job,
                                                      Revision](FHttpRequestPtr,
                                                                FHttpResponsePtr ResponsePtr,
                                                                bool Connected) {
        if (!Weak.IsValid() || !Weak->IsCurrent(Sequence, Service, Job, Revision))
            return;
        TSharedPtr<FJsonObject> Json;
        FString Error, Mode, NewJob, NewRevision;
        if (!Response(ResponsePtr, Connected, Json, Error))
        {
            Weak->Stage = TEXT("failed");
            Weak->Status =
                TEXT(
                    "Export your current plan in the workspace, then try Open latest plan again. ") +
                Error;
            return;
        }
        if (!Json->TryGetStringField(TEXT("validation_mode"), Mode) || Mode != TEXT("gameplay"))
        {
            Weak->Stage = TEXT("failed");
            Weak->Status = TEXT(
                "This export is geometry only. In Review plan, choose Playable level and select Start and Goal, then confirm and export again.");
            return;
        }
        if (!Json->TryGetStringField(TEXT("runtime_job_id"), NewJob) ||
            !APlayableSketchLevelActor::IsPipelineJobId(NewJob) ||
            !Json->TryGetStringField(TEXT("revision_id"), NewRevision) || !RevisionId(NewRevision))
        {
            Weak->Stage = TEXT("failed");
            Weak->Status = TEXT(
                "The exported plan could not be selected. Export it again from the workspace.");
            return;
        }
        Weak->JobId = NewJob;
        Weak->SelectedRevision = NewRevision;
        Weak->ImportAccepted();
    });
    Stage = TEXT("checking");
    Status = TEXT("Finding your latest confirmed plan...");
    if (!Selection->ProcessRequest())
    {
        Stage = TEXT("failed");
        Status = TEXT("The local workspace is unavailable. Start it and try again.");
    }
}
