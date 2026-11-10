

using UnrealBuildTool;
using System.Collections.Generic;

public class PlayableSketchEditorTarget : TargetRules
{
    public PlayableSketchEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V6;

        ExtraModuleNames.AddRange(new string[] { "PlayableSketch" });
    }
}
