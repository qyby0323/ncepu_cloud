$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $scriptDir "build_exe.py") --onedir
