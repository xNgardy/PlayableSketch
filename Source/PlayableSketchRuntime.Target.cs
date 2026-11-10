using UnrealBuildTool;
public class PlayableSketchRuntimeTarget : TargetRules
{
    public PlayableSketchRuntimeTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        ExtraModuleNames.Add("PlayableSketch");
    }
}
