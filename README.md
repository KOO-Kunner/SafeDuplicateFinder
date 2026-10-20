# Safe Duplicate Finder

A practical, cross-platform duplicate-file finder for Windows and Linux. It finds byte-identical files by size and SHA-256, lets you review candidates, exports reports, and can move selected copies into a quarantine folder instead of permanently deleting them.

- **Python 3.10+**
- **No third-party dependencies**
- **Windows GUI and CLI; Linux CLI and GUI when Tkinter is installed**
- **MIT license**
- **Two-stage hashing** to avoid full-file hashing when quick samples differ
- **Atomic manifest writes** and integrity checks during quarantine/restore

## Why use it?

Duplicate photos, downloads, archives, and document copies can consume storage and make folders hard to manage. This tool identifies exact duplicates and estimates reclaimable space. It deliberately avoids automatic deletion.

## Safety model

1. Scanning is read-only.
2. Symlinks are skipped; directory symlinks are not followed.
3. The tool compares file size first, then SHA-256 for files with matching sizes.
4. The first path in each sorted group is only a **suggested** keep candidate, not a claim that it is the best copy. Review paths before moving anything.
5. Quarantine uses file moves, not permanent deletion. It writes `manifest.json` after each move.
6. Restore refuses to overwrite an existing destination.
7. Always keep a backup of important data. A move can still be interrupted by hardware or permission errors.

## Quick start on Windows

Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). During setup, enable **Add Python to PATH**.

Open PowerShell in the extracted project folder:

```powershell
python --version
python safe_duplicate_finder.py
```

The GUI opens. Choose a folder and click **Scan**.

CLI examples:

```powershell
python safe_duplicate_finder.py scan "$env:USERPROFILE\Downloads"
python safe_duplicate_finder.py scan "D:\Photos" --json report.json --csv report.csv
python safe_duplicate_finder.py restore "D:\DuplicateQuarantine"
```

## Build a Windows executable

On Windows, open PowerShell in the extracted project folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The executable will be created at `dist\SafeDuplicateFinder.exe`. The build uses PyInstaller and downloads its build dependency into a local virtual environment. The resulting executable is for Windows; build it on Windows for best compatibility. The app is not code-signed, so Windows SmartScreen may show a warning. Review the source and build it yourself rather than trusting an executable from an unknown publisher.

## Recovery and performance improvements

- A small first/last-block fingerprint filters most same-size files before full SHA-256 hashing.
- JSON reports and quarantine manifests are written via a temporary file and atomic replacement.
- Before moving a duplicate, the tool rechecks its size and full hash to detect stale reports.
- Before restoring, it checks the quarantined file's size and SHA-256. It never overwrites an existing destination.
- If an operation is interrupted, re-run restore using the same quarantine folder; review any warnings. Keep the quarantine folder and `manifest.json` together.

These protections reduce common risks but do not replace a backup. Sudden power loss, storage failure, antivirus locks, or filesystem errors can still interrupt file operations.

## Quick start on Linux

```bash
python3 --version
python3 safe_duplicate_finder.py
```

If the GUI cannot start because Tkinter is missing, use the CLI:

```bash
python3 safe_duplicate_finder.py scan ~/Downloads --json report.json --csv report.csv
```

On Debian/Ubuntu, Tkinter is usually available from the `python3-tk` package.

## CLI workflow

### 1. Scan and review

```bash
python safe_duplicate_finder.py scan "/path/to/folder" --json report.json --csv report.csv
```

The report groups files with identical SHA-256 hashes. In each group, the first sorted path is marked `KEEP`; remaining entries are marked as extra copies. Review the paths yourself before taking action.

### 2. Quarantine extra copies

```bash
python safe_duplicate_finder.py quarantine report.json "/path/to/quarantine"
```

The command prints the candidates and requires you to type `QUARANTINE`. Extra copies are moved under the quarantine folder, and `manifest.json` records their original paths.

**Important:** the CLI quarantine command moves all extra copies from the supplied report. Do not run it until you have reviewed the report. For selecting individual files, use the GUI.

### 3. Restore

```bash
python safe_duplicate_finder.py restore "/path/to/quarantine"
```

If a file's original path is occupied, that file is skipped and a warning is printed. Nothing is overwritten.

## Limitations

- Only byte-identical files count as duplicates; visually similar photos and files with different metadata are not merged.
- Hashing large files takes time and disk reads.
- The tool does not scan cloud-only placeholders reliably and does not bypass file permissions.
- The suggested keep candidate is based on a stable path sort, not file quality or recency.
- If files are moved between volumes, the operating system may implement a move as copy-then-remove; ensure the destination has sufficient space.

## Development

```bash
python -m unittest discover -s tests -v
```

Contributions should include tests for safety-sensitive changes. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Please see [SECURITY.md](SECURITY.md). Do not report private files or personal data in public issues.
