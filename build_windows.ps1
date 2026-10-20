# Build a standalone Windows GUI executable. Run in PowerShell from this folder.
$ErrorActionPreference = "Stop"
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --upgrade pip
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-build\Scripts\pyinstaller.exe --clean --noconfirm safe_duplicate_finder.spec
Write-Host "Build complete: dist\SafeDuplicateFinder.exe"
Write-Host "Test it on a temporary folder before scanning important files."
