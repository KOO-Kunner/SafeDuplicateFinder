#!/usr/bin/env python3
"""Safe Duplicate Finder: find duplicate files and optionally quarantine copies.

The tool never permanently deletes files. Quarantined files can be restored using
the manifest created during the move operation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

CHUNK_SIZE = 1024 * 1024
SAMPLE_SIZE = 64 * 1024
APP_NAME = "Safe Duplicate Finder"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    sha256: str


@dataclass
class ScanResult:
    root: str
    scanned_files: int
    skipped_files: int
    duplicate_groups: list[list[FileRecord]]
    errors: list[str]

    @property
    def duplicate_files(self) -> int:
        return sum(max(0, len(group) - 1) for group in self.duplicate_groups)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(sum(record.size for record in group[1:]) for group in self.duplicate_groups)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def quick_fingerprint(path: Path, size: int) -> str:
    """Hash file size plus the first/last sample to cheaply reject most candidates."""
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    with path.open("rb") as handle:
        first = handle.read(SAMPLE_SIZE)
        digest.update(first)
        if size > SAMPLE_SIZE:
            handle.seek(max(0, size - SAMPLE_SIZE))
            digest.update(handle.read(SAMPLE_SIZE))
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON through a temporary sibling then atomically replace the manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def iter_files(root: Path, excluded: set[Path], errors: list[str]) -> Iterable[Path]:
    """Walk a directory without following symlinks; ignore excluded subtrees."""
    def onerror(exc: OSError) -> None:
        errors.append(f"{getattr(exc, 'filename', '<unknown>')}: {exc}")

    for current, dirs, filenames in os.walk(root, followlinks=False, onerror=onerror):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if not (current_path / name).is_symlink()
            and not any((current_path / name).resolve() == item or item in (current_path / name).resolve().parents
                        for item in excluded)
        ]
        for name in filenames:
            path = current_path / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve()
                if any(resolved == item or item in resolved.parents for item in excluded):
                    continue
                yield path
            except OSError as exc:
                errors.append(f"{path}: {exc}")


def scan(root: str | Path, exclude: Iterable[str | Path] = ()) -> ScanResult:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Scan path is not a directory: {root_path}")

    excluded: set[Path] = set()
    for item in exclude:
        try:
            excluded.add(Path(item).expanduser().resolve())
        except OSError:
            pass

    errors: list[str] = []
    by_size: dict[int, list[Path]] = defaultdict(list)
    scanned = 0
    skipped = 0
    for path in iter_files(root_path, excluded, errors):
        try:
            size = path.stat().st_size
            by_size[size].append(path)
            scanned += 1
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            skipped += 1

    # Stage 1 cheaply compares file size and a small sample. Stage 2 performs the
    # full SHA-256 only for files whose samples match, reducing disk reads on large trees.
    sample_groups: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for path in paths:
            try:
                sample_groups[quick_fingerprint(path, size)].append((size, path))
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                skipped += 1

    groups: dict[str, list[FileRecord]] = defaultdict(list)
    for candidates in sample_groups.values():
        if len(candidates) < 2:
            continue
        for size, path in candidates:
            try:
                digest = sha256_file(path)
                groups[digest].append(
                    FileRecord(path=str(path.resolve()), size=size, sha256=digest)
                )
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                skipped += 1

    duplicate_groups = [
        sorted(group, key=lambda record: (record.path.casefold(), record.path))
        for group in groups.values() if len(group) > 1
    ]
    duplicate_groups.sort(key=lambda group: group[0].path.casefold())
    return ScanResult(str(root_path), scanned, skipped, duplicate_groups, errors)


def save_report(result: ScanResult, destination: str | Path) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "app": APP_NAME,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": result.root,
        "scanned_files": result.scanned_files,
        "skipped_files": result.skipped_files,
        "duplicate_groups": [[asdict(record) for record in group] for group in result.duplicate_groups],
        "duplicate_files": result.duplicate_files,
        "reclaimable_bytes": result.reclaimable_bytes,
        "errors": result.errors,
    }
    atomic_write_json(target, payload)
    return target


def save_csv(result: ScanResult, destination: str | Path) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "keep_candidate", "path", "size_bytes", "sha256"])
        for index, group in enumerate(result.duplicate_groups, start=1):
            for position, record in enumerate(group):
                writer.writerow([index, "yes" if position == 0 else "no", record.path, record.size, record.sha256])
    return target


def quarantine_duplicates(
    groups: list[list[FileRecord]],
    quarantine_dir: str | Path,
    selected_paths: Iterable[str] | None = None,
) -> Path:
    """Move selected duplicates (not the first/keep candidate) into quarantine.

    Existing files are never overwritten. A manifest is written after each move,
    allowing recovery after an interrupted operation.
    """
    qroot = Path(quarantine_dir).expanduser().resolve()
    qroot.mkdir(parents=True, exist_ok=True)
    manifest_path = qroot / MANIFEST_NAME
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"app": APP_NAME, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "moves": []}

    selected = set(selected_paths) if selected_paths is not None else None
    already_moved = {item["original"] for item in manifest["moves"]}
    for group in groups:
        # Deterministic first path is the suggested copy to keep.
        for record in group[1:]:
            original = Path(record.path)
            if selected is not None and str(original) not in selected:
                continue
            if str(original) in already_moved:
                continue
            if not original.exists() or original.is_symlink():
                continue
            # Reports can go stale; verify the candidate still matches the scan.
            try:
                if original.stat().st_size != record.size or sha256_file(original) != record.sha256:
                    raise ValueError(f"File changed since scan; refusing to quarantine: {original}")
            except OSError as exc:
                raise ValueError(f"Cannot re-check file; refusing to quarantine: {original}: {exc}") from exc
            # Preserve the absolute path below a "files" folder; use a stable,
            # collision-resistant name if a path is encountered more than once.
            relative = Path(*original.parts[1:]) if original.is_absolute() else original
            destination = qroot / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination = destination.with_name(f"{destination.name}.{int(time.time())}.duplicate")
            shutil.move(str(original), str(destination))
            manifest["moves"].append({
                "original": str(original),
                "quarantined": str(destination),
                "size": record.size,
                "sha256": record.sha256,
                "moved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            })
            atomic_write_json(manifest_path, manifest)
            already_moved.add(str(original))
    return manifest_path


def restore_quarantine(quarantine_dir: str | Path) -> tuple[int, list[str]]:
    qroot = Path(quarantine_dir).expanduser().resolve()
    manifest_path = qroot / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"No manifest found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = 0
    errors: list[str] = []
    # Reverse order makes nested/related operations safer.
    for item in reversed(manifest.get("moves", [])):
        source = Path(item["quarantined"])
        target = Path(item["original"])
        if not source.exists():
            continue
        if target.exists():
            errors.append(f"Not restored because destination already exists: {target}")
            continue
        try:
            if source.is_symlink() or not source.is_file():
                errors.append(f"Not restored because quarantined item is missing or not a regular file: {source}")
                continue
            if source.stat().st_size != item.get("size") or sha256_file(source) != item.get("sha256"):
                errors.append(f"Not restored because quarantined file failed integrity check: {source}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # shutil.move supports cross-volume restore; the source is retained if a copy fails.
            shutil.move(str(source), str(target))
            restored += 1
        except OSError as exc:
            errors.append(f"{source}: {exc}")
    # Keep manifest for audit/retry; mark restored entries.
    manifest["last_restore_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest["restored_count_last_run"] = restored
    atomic_write_json(manifest_path, manifest)
    return restored, errors


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def print_result(result: ScanResult) -> None:
    print(f"Scan directory : {result.root}")
    print(f"Files scanned  : {result.scanned_files}")
    print(f"Duplicate groups: {len(result.duplicate_groups)}")
    print(f"Extra copies   : {result.duplicate_files}")
    print(f"Potential space: {format_bytes(result.reclaimable_bytes)}")
    for index, group in enumerate(result.duplicate_groups, 1):
        print(f"\nGroup {index} ({format_bytes(group[0].size)} each):")
        for pos, record in enumerate(group):
            print(f"  {'KEEP' if pos == 0 else 'COPY'}  {record.path}")
    if result.errors:
        print(f"\nWarnings/errors: {len(result.errors)}")
        for error in result.errors[:20]:
            print(f"  - {error}")
        if len(result.errors) > 20:
            print(f"  ... and {len(result.errors) - 20} more")


def run_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("Tkinter is not available. Use the CLI or install a Python build with Tk support.", file=sys.stderr)
        return 2

    class App:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title(APP_NAME)
            self.root.geometry("980x650")
            self.result: ScanResult | None = None
            self.groups_by_item: dict[str, FileRecord] = {}
            self.path_var = tk.StringVar()
            self.status_var = tk.StringVar(value="Choose a folder, then click Scan.")
            frame = ttk.Frame(root, padding=12)
            frame.pack(fill="both", expand=True)
            top = ttk.Frame(frame)
            top.pack(fill="x")
            ttk.Label(top, text="Folder to scan:").pack(side="left")
            ttk.Entry(top, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=8)
            ttk.Button(top, text="Browse…", command=self.browse).pack(side="left")
            ttk.Button(top, text="Scan", command=self.do_scan).pack(side="left", padx=(8, 0))
            self.tree = ttk.Treeview(frame, columns=("size", "hash", "role"), show="tree headings", selectmode="extended")
            self.tree.heading("#0", text="File path")
            self.tree.heading("size", text="Size")
            self.tree.heading("hash", text="SHA-256")
            self.tree.heading("role", text="Suggested action")
            self.tree.column("#0", width=480)
            self.tree.column("size", width=90, anchor="e")
            self.tree.column("hash", width=220)
            self.tree.column("role", width=120)
            self.tree.pack(fill="both", expand=True, pady=10)
            buttons = ttk.Frame(frame)
            buttons.pack(fill="x")
            ttk.Button(buttons, text="Export JSON", command=self.export_json).pack(side="left")
            ttk.Button(buttons, text="Export CSV", command=self.export_csv).pack(side="left", padx=8)
            ttk.Button(buttons, text="Quarantine selected copies", command=self.quarantine_selected).pack(side="left")
            ttk.Button(buttons, text="Restore quarantine…", command=self.restore).pack(side="left", padx=8)
            ttk.Label(frame, textvariable=self.status_var).pack(fill="x", pady=(8, 0))
            ttk.Label(frame, text="Safety: scan is read-only. Quarantine moves files; it does not permanently delete them.",
                      wraplength=930).pack(fill="x", pady=(5, 0))

        def browse(self):
            chosen = filedialog.askdirectory()
            if chosen:
                self.path_var.set(chosen)

        def do_scan(self):
            path = self.path_var.get().strip()
            if not path:
                messagebox.showwarning(APP_NAME, "Choose a folder first.")
                return
            self.status_var.set("Scanning… large folders may take time.")
            self.root.update_idletasks()
            try:
                self.result = scan(path)
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc))
                self.status_var.set("Scan failed.")
                return
            self.tree.delete(*self.tree.get_children())
            self.groups_by_item.clear()
            for group_no, group in enumerate(self.result.duplicate_groups, 1):
                parent = self.tree.insert("", "end", text=f"Duplicate group {group_no}", values=("", "", ""))
                for pos, record in enumerate(group):
                    item = self.tree.insert(parent, "end", text=record.path,
                                            values=(format_bytes(record.size), record.sha256[:16] + "…",
                                                    "KEEP" if pos == 0 else "QUARANTINE COPY"))
                    self.groups_by_item[item] = record
            self.status_var.set(
                f"Scanned {self.result.scanned_files} files; {len(self.result.duplicate_groups)} groups; "
                f"{self.result.duplicate_files} extra copies; potential space {format_bytes(self.result.reclaimable_bytes)}."
            )

        def export_json(self):
            if not self.result:
                messagebox.showinfo(APP_NAME, "Scan a folder first.")
                return
            target = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if target:
                save_report(self.result, target)
                messagebox.showinfo(APP_NAME, f"Report saved to:\n{target}")

        def export_csv(self):
            if not self.result:
                messagebox.showinfo(APP_NAME, "Scan a folder first.")
                return
            target = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if target:
                save_csv(self.result, target)
                messagebox.showinfo(APP_NAME, f"CSV saved to:\n{target}")

        def quarantine_selected(self):
            if not self.result:
                messagebox.showinfo(APP_NAME, "Scan a folder first.")
                return
            selected_records = []
            for item in self.tree.selection():
                record = self.groups_by_item.get(item)
                if record:
                    # Refuse the first record in each group (the suggested keep copy).
                    group = next((g for g in self.result.duplicate_groups if record in g), [])
                    if group and record == group[0]:
                        messagebox.showwarning(APP_NAME, f"Will not quarantine the suggested keep copy:\n{record.path}")
                        continue
                    selected_records.append(record.path)
            if not selected_records:
                messagebox.showinfo(APP_NAME, "Select one or more duplicate file rows (not group headings or KEEP rows).")
                return
            if not messagebox.askyesno(APP_NAME,
                f"Move {len(selected_records)} selected file(s) to quarantine?\n"
                "Files will not be permanently deleted. A restore manifest will be created."):
                return
            qdir = filedialog.askdirectory(title="Choose a quarantine folder")
            if not qdir:
                return
            try:
                manifest = quarantine_duplicates(self.result.duplicate_groups, qdir, selected_records)
                messagebox.showinfo(APP_NAME, f"Files moved to quarantine.\nManifest:\n{manifest}\n\nRun a new scan to refresh results.")
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Quarantine operation failed:\n{exc}")

        def restore(self):
            qdir = filedialog.askdirectory(title="Choose the quarantine folder containing manifest.json")
            if not qdir:
                return
            if not messagebox.askyesno(APP_NAME, "Restore quarantined files? Existing destination files will never be overwritten."):
                return
            try:
                count, errors = restore_quarantine(qdir)
                message = f"Restored {count} file(s)."
                if errors:
                    message += "\n\nSome files were not restored:\n" + "\n".join(errors[:10])
                messagebox.showinfo(APP_NAME, message)
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc))

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find duplicate files safely; quarantine instead of deleting.")
    sub = parser.add_subparsers(dest="command")
    scan_parser = sub.add_parser("scan", help="scan a directory for duplicate files")
    scan_parser.add_argument("directory", help="directory to scan")
    scan_parser.add_argument("--json", dest="json_path", help="write a JSON report")
    scan_parser.add_argument("--csv", dest="csv_path", help="write a CSV report")
    quarantine_parser = sub.add_parser("quarantine", help="move extra copies from a saved JSON report")
    quarantine_parser.add_argument("report", help="JSON report generated by scan")
    quarantine_parser.add_argument("directory", help="quarantine directory")
    restore_parser = sub.add_parser("restore", help="restore files from a quarantine manifest")
    restore_parser.add_argument("directory", help="quarantine directory containing manifest.json")
    sub.add_parser("gui", help="launch the graphical interface")
    args = parser.parse_args(argv)

    if args.command in (None, "gui"):
        return run_gui()
    if args.command == "scan":
        result = scan(args.directory)
        print_result(result)
        if args.json_path:
            print(f"\nJSON report: {save_report(result, args.json_path)}")
        if args.csv_path:
            print(f"CSV report : {save_csv(result, args.csv_path)}")
        return 0
    if args.command == "quarantine":
        report_path = Path(args.report).expanduser().resolve()
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        groups = [[FileRecord(**record) for record in group] for group in payload["duplicate_groups"]]
        print_result(ScanResult(payload["root"], payload["scanned_files"], payload["skipped_files"], groups, payload.get("errors", [])))
        confirm = input("\nType QUARANTINE to move the extra copies shown above (no permanent deletion): ").strip()
        if confirm != "QUARANTINE":
            print("Cancelled.")
            return 1
        manifest = quarantine_duplicates(groups, args.directory)
        print(f"Manifest written: {manifest}")
        return 0
    if args.command == "restore":
        count, errors = restore_quarantine(args.directory)
        print(f"Restored {count} file(s).")
        for error in errors:
            print(f"WARNING: {error}")
        return 0 if not errors else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
