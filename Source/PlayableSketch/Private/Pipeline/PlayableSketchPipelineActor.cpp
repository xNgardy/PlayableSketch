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
bool Match(const FString &Value, const TCHAR *Pattern)
{
    FRegexMatcher Matcher(FRegexPattern(Pattern), Value);
    return Matcher.FindNext();
}
bool EditorActor(const APlayableSketchLevelActor &Actor)
{
#if WITH_EDITOR
    return Actor.GetWorld() && (Actor.GetWorld()->WorldType == EWorldType::Editor ||
                                Actor.GetWorld()->WorldType == EWorldType::EditorPreview);
#else
    return false;
#endif
}
TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request(const FString &Url, const FString &Verb)
{
    auto Result = FHttpModule::Get().CreateRequest();
    Result->SetURL(Url);
    Result->SetVerb(Verb);
    Result->SetTimeout(15.0f);
    Result->SetDelegateThreadPolicy(EHttpRequestDelegateThreadPolicy::CompleteOnGameThread);
    return Result;
}
bool ResponseJson(FHttpResponsePtr Response, bool bConnected, TSharedPtr<FJsonObject> &Object,
                  FString &Error)
{
    if (!bConnected || !Response.IsValid())
    {
        Error = TEXT("Local pipeline service unavailable or request timed out.");
        return false;
    }
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()),
                                      Object) ||
        !Object)
    {
        Error = TEXT("Pipeline returned invalid JSON.");
        return false;
    }
    if (Response->GetResponseCode() < 200 || Response->GetResponseCode() >= 300)
    {
        if (!Object->TryGetStringField(TEXT("error"), Error))
            Error = FString::Printf(TEXT("Pipeline HTTP error %d"), Response->GetResponseCode());
        return false;
    }
    return true;
}
void AppendUtf8(TArray<uint8> &Data, const FString &Text)
{
    FTCHARToUTF8 Utf8(*Text);
    Data.Append(reinterpret_cast<const uint8 *>(Utf8.Get()), Utf8.Length());
}
}

bool APlayableSketchLevelActor::IsLocalPipelineUrl(const FString &Url)
{

    if (!Match(Url, TEXT("^http://(127\\.0\\.0\\.1|localhost):[0-9]{1,5}$")))
        return false;
    int32 Colon = INDEX_NONE;
    Url.FindLastChar(TEXT(':'), Colon);
    const int32 Port = FCString::Atoi(*Url.Mid(Colon + 1));
    return Port > 0 && Port <= 65535;
}

bool APlayableSketchLevelActor::IsPipelineJobId(const FString &Id)
{
    return Match(Id, TEXT("^Job_[0-9TZ]+_[a-f0-9]{10}$"));
}

bool APlayableSketchLevelActor::IsPipelineRequestCurrent(uint64 Sequence, const FString &Service,
                                                         const FString &Job,
                                                         const FString &SelectedRevision) const
{
    return PipelineRequestSequence == Sequence && PipelineServiceUrl == Service &&
           PipelineJobId == Job && PipelineAcceptedRevisionId == SelectedRevision;
}

void APlayableSketchLevelActor::UploadPipelineImage()
{
    if (!EditorActor(*this) || !IsLocalPipelineUrl(PipelineServiceUrl))
    {
        LastPipelineStatus = TEXT(
            "Use an Editor actor and an explicit http://127.0.0.1:PORT or localhost:PORT service.");
        return;
    }
    const FString Path =
        FPaths::IsRelative(PipelineImagePath)
            ? FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), PipelineImagePath)
            : PipelineImagePath;
    const FString Ext = FPaths::GetExtension(Path).ToLower();
    TArray<uint8> Image;
    if (!(Ext == TEXT("png") || Ext == TEXT("jpg") || Ext == TEXT("jpeg")) ||
        IFileManager::Get().FileSize(*Path) > 20000000 ||
        !FFileHelper::LoadFileToArray(Image, *Path) || Image.IsEmpty())
    {
        LastPipelineStatus = TEXT("Choose a readable PNG/JPEG up to 20 MB.");
        return;
    }
    const uint64 Sequence = ++PipelineRequestSequence;
    const FString Service = PipelineServiceUrl, Job = PipelineJobId,
                  Revision = PipelineAcceptedRevisionId;
    const FString Boundary =
        TEXT("PlayableSketch-") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Config = FString::Printf(
        TEXT(
            "{\"settings\":{\"wall_thickness_cm\":%.9g,\"wall_height_cm\":%.9g,\"door_height_cm\":%.9g,\"floor_thickness_cm\":%.9g}}"),
        WallThicknessCm, WallHeightCm, DoorHeightCm, FloorThicknessCm);
    TArray<uint8> Body;
    AppendUtf8(Body, TEXT("--") + Boundary +
                         TEXT("\r\nContent-Disposition: form-data; name=\"config\"\r\n\r\n") +
                         Config + TEXT("\r\n"));
    AppendUtf8(Body,
               TEXT("--") + Boundary +
                   TEXT("\r\nContent-Disposition: form-data; name=\"image\"; filename=\"drawing.") +
                   Ext + TEXT("\"\r\nContent-Type: application/octet-stream\r\n\r\n"));
    Body.Append(Image);
    AppendUtf8(Body, TEXT("\r\n--") + Boundary + TEXT("--\r\n"));
    TWeakObjectPtr<APlayableSketchLevelActor> Weak(this);
    auto Bootstrap = Request(Service + TEXT("/api/bootstrap"), TEXT("GET"));
    Bootstrap->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job, Revision,
                                                      Boundary, Body = MoveTemp(Body)](
                                                         FHttpRequestPtr, FHttpResponsePtr Response,
                                                         bool bOk) mutable {
        if (!Weak.IsValid() || !Weak->IsPipelineRequestCurrent(Sequence, Service, Job, Revision))
            return;
        TSharedPtr<FJsonObject> Object;
        FString Error, Token;
        if (!ResponseJson(Response, bOk, Object, Error) ||
            !Object->TryGetStringField(TEXT("token"), Token))
        {
            Weak->LastPipelineStatus =
                Error.IsEmpty() ? TEXT("Missing local session token.") : Error;
            return;
        }
        auto Upload = Request(Service + TEXT("/jobs"), TEXT("POST"));
        Upload->SetHeader(TEXT("X-Review-Token"), Token);
        Upload->SetHeader(TEXT("Content-Type"), TEXT("multipart/form-data; boundary=") + Boundary);
        Upload->SetContent(MoveTemp(Body));
        Upload->OnProcessRequestComplete().BindLambda(
            [Weak, Sequence, Service, Job, Revision](FHttpRequestPtr, FHttpResponsePtr Result,
                                                     bool bConnected) {
                if (!Weak.IsValid() ||
                    !Weak->IsPipelineRequestCurrent(Sequence, Service, Job, Revision))
                    return;
                TSharedPtr<FJsonObject> Json;
                FString Error, Id;
                if (!ResponseJson(Result, bConnected, Json, Error) ||
                    !Json->TryGetStringField(TEXT("job_id"), Id) || !IsPipelineJobId(Id))
                {
                    Weak->LastPipelineStatus =
                        Error.IsEmpty() ? TEXT("Invalid pipeline job acknowledgement.") : Error;
                    return;
                }
                Weak->Modify();
                Weak->PipelineJobId = Id;
                Weak->PipelineAcceptedRevisionId.Reset();
                Weak->LastPipelineStatus =
                    TEXT("Uploaded: ") + Id +
                    TEXT(". Refresh job for stage progress; open review when ready.");
            });
        if (!Upload->ProcessRequest())
            Weak->LastPipelineStatus = TEXT("Could not dispatch upload request.");
    });
    LastPipelineStatus = TEXT("Uploading to the local pipeline…");
    if (!Bootstrap->ProcessRequest())
        LastPipelineStatus = TEXT("Could not contact the local pipeline service.");
}

void APlayableSketchLevelActor::RefreshPipelineJob()
{
    if (!EditorActor(*this) || !IsLocalPipelineUrl(PipelineServiceUrl) ||
        !IsPipelineJobId(PipelineJobId))
    {
        LastPipelineStatus = TEXT("Select a valid local pipeline service and Job ID.");
        return;
    }
    const uint64 Sequence = ++PipelineRequestSequence;
    const FString Service = PipelineServiceUrl, Job = PipelineJobId,
                  Revision = PipelineAcceptedRevisionId;
    TWeakObjectPtr<APlayableSketchLevelActor> Weak(this);
    auto Poll = Request(Service + TEXT("/jobs/") + Job, TEXT("GET"));
    Poll->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job,
                                                 Revision](FHttpRequestPtr,
                                                           FHttpResponsePtr Response, bool bOk) {
        if (!Weak.IsValid() || !Weak->IsPipelineRequestCurrent(Sequence, Service, Job, Revision))
            return;
        TSharedPtr<FJsonObject> Object;
        FString Error, State, Stage, Accepted;
        if (!ResponseJson(Response, bOk, Object, Error) ||
            !Object->TryGetStringField(TEXT("state"), State))
        {
            Weak->LastPipelineStatus = Error.IsEmpty() ? TEXT("Malformed job status.") : Error;
            return;
        }
        Object->TryGetStringField(TEXT("stage"), Stage);
        Object->TryGetStringField(TEXT("error"), Error);
        if (Object->TryGetStringField(TEXT("accepted_revision_id"), Accepted) &&
            Weak->PipelineAcceptedRevisionId.IsEmpty())
        {
            Weak->Modify();
            Weak->PipelineAcceptedRevisionId = Accepted;
        }
        Weak->LastPipelineStatus =
            State + TEXT(" / ") + Stage + (Error.IsEmpty() ? TEXT("") : TEXT(": ") + Error);
    });
    LastPipelineStatus = TEXT("Checking job asynchronously…");
    if (!Poll->ProcessRequest())
        LastPipelineStatus = TEXT("Could not dispatch job status request.");
}

void APlayableSketchLevelActor::OpenPipelineReview()
{
    if (!EditorActor(*this) || !IsLocalPipelineUrl(PipelineServiceUrl) ||
        !IsPipelineJobId(PipelineJobId))
    {
        LastPipelineStatus = TEXT("Select a valid local service and Job ID before opening review.");
        return;
    }
    const FString Url = PipelineServiceUrl + TEXT("/?job=") + PipelineJobId;
    FPlatformProcess::LaunchURL(*Url, nullptr, nullptr);
    LastPipelineStatus = TEXT(
        "Review opened. Approve topology, continue to metric review, then explicitly accept a metric revision.");
}

void APlayableSketchLevelActor::ImportPipelineAcceptedLayout()
{
    if (!EditorActor(*this) || !ImportedLayoutAsset || !IsLocalPipelineUrl(PipelineServiceUrl) ||
        !IsPipelineJobId(PipelineJobId) ||
        !Match(PipelineAcceptedRevisionId, TEXT("^metric-[0-9TZ]+-[a-f0-9]{12}$")))
    {
        LastPipelineStatus = TEXT(
            "Assign ImportedLayoutAsset, local service, Job ID and selected accepted metric revision.");
        return;
    }
    const uint64 Sequence = ++PipelineRequestSequence;
    const FString Service = PipelineServiceUrl, Job = PipelineJobId,
                  Revision = PipelineAcceptedRevisionId;
    TWeakObjectPtr<APlayableSketchLevelActor> Weak(this);
    TWeakObjectPtr<UPlayableSketchImportedLayoutAsset> TargetAsset(ImportedLayoutAsset);
    const FString PreviousAssetRevision = ImportedLayoutAsset->RevisionId;
    auto Fetch = Request(Service + TEXT("/jobs/") + Job + TEXT("/layout?revision_id=") +
                             FGenericPlatformHttp::UrlEncode(Revision),
                         TEXT("GET"));
    Fetch->OnProcessRequestComplete().BindLambda([Weak, Sequence, Service, Job, Revision,
                                                  TargetAsset, PreviousAssetRevision](
                                                     FHttpRequestPtr, FHttpResponsePtr Response,
                                                     bool bOk) {
        if (!Weak.IsValid() || !Weak->IsPipelineRequestCurrent(Sequence, Service, Job, Revision))
            return;
        if (!TargetAsset.IsValid() || Weak->ImportedLayoutAsset != TargetAsset.Get() ||
            TargetAsset->RevisionId != PreviousAssetRevision)
        {
            Weak->LastPipelineStatus =
                TEXT("Import response is stale: the target asset changed. Request import again.");
            return;
        }
        TSharedPtr<FJsonObject> Object;
        FString Error, Kind, ReturnedRevision;
        if (!ResponseJson(Response, bOk, Object, Error) ||
            Response->GetContent().Num() > 2 * 1024 * 1024 ||
            !Object->TryGetStringField(TEXT("kind"), Kind) || Kind != TEXT("validated_layout") ||
            !Object->TryGetStringField(TEXT("revision_id"), ReturnedRevision) ||
            ReturnedRevision != Revision + TEXT("-accepted"))
        {
            Weak->LastPipelineStatus =
                TEXT("Import rejected: ") +
                (Error.IsEmpty() ? TEXT("Response is not the selected accepted canonical revision.")
                                 : Error);
            return;
        }
        if (!Weak->ImportCanonicalLayoutJsonText(Response->GetContentAsString(), Error))
        {
            Weak->LastPipelineStatus =
                TEXT("Canonical import rejected; existing asset retained: ") + Error;
            return;
        }
        Weak->LastPipelineStatus = TEXT("Imported selected pipeline revision: ") + Revision +
                                   TEXT(". Save asset/map explicitly; navigation is separate.");
    });
    LastPipelineStatus = TEXT("Fetching selected accepted revision asynchronously…");
    if (!Fetch->ProcessRequest())
        LastPipelineStatus = TEXT("Could not dispatch selected-layout request.");
}
