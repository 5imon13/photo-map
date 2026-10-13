' Starts daily.ps1 with no visible window (used by Task Scheduler).
Set shell = CreateObject("WScript.Shell")
script = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\" & WScript.Arguments(0)
WScript.Quit shell.Run("pwsh.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """", 0, True)
