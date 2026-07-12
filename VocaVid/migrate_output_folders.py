from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .paths import slug_folder_name


PATH_COLUMNS = {
    "projects": ["final_video_path"],
    "lyric_lines": ["image_path", "avatar_image_path", "clip_path"],
    "render_segments": ["image_path", "avatar_image_path", "clip_path", "audio_path"],
}


def migrate(app_root: Path, apply: bool = False) -> list[str]:
    app_root = app_root.resolve()
    db_path = app_root / "VocaVid.sqlite3"
    outputs = app_root / "outputs"
    messages: list[str] = []
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        projects = list(con.execute("SELECT id, name FROM projects ORDER BY id"))
        mappings = [
            {
                "project_id": int(project["id"]),
                "name": str(project["name"]),
                "old_name": f"project-{int(project['id'])}",
                "new_name": slug_folder_name(str(project["name"])),
            }
            for project in projects
        ]
        mappings = [item for item in mappings if item["old_name"] != item["new_name"]]
        _check_destination_conflicts(outputs, mappings)

        changes = _collect_db_changes(con, app_root, mappings)
        moves = [
            (outputs / item["old_name"], outputs / item["new_name"])
            for item in mappings
            if (outputs / item["old_name"]).exists()
        ]
        kdenlive_files = list(outputs.rglob("*.kdenlive")) if outputs.exists() else []

        messages.extend(_format_plan(mappings, moves, changes, kdenlive_files))
        if not apply:
            messages.append("Dry run only. Re-run with --apply to migrate.")
            return messages

        backup = _backup_db(db_path)
        messages.append(f"DB backup: {backup}")
        for source, target in moves:
            _merge_or_move_dir(source, target)
            messages.append(f"Moved {source.name} -> {target.name}")
        changed_files = _rewrite_kdenlive_files(outputs, app_root, mappings)
        if changed_files:
            messages.append(f"Updated kdenlive files: {len(changed_files)}")
        _apply_db_changes(con, changes)
        messages.append(f"Updated DB values: {len(changes)}")
        return messages
    finally:
        con.close()


def _collect_db_changes(con: sqlite3.Connection, app_root: Path, mappings: list[dict[str, object]]) -> list[tuple[str, str, int, str]]:
    changes: list[tuple[str, str, int, str]] = []
    for table, columns in PATH_COLUMNS.items():
        for column in columns:
            rows = con.execute(f"SELECT rowid AS _rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
            for row in rows:
                current = str(row[column])
                updated = _replace_output_refs(current, app_root, mappings)
                if updated != current:
                    changes.append((table, column, int(row["_rowid"]), updated))
    return changes


def _apply_db_changes(con: sqlite3.Connection, changes: list[tuple[str, str, int, str]]) -> None:
    with con:
        for table, column, rowid, value in changes:
            con.execute(f"UPDATE {table} SET {column} = ? WHERE rowid = ?", (value, rowid))


def _replace_output_refs(value: str, app_root: Path, mappings: list[dict[str, object]]) -> str:
    updated = value
    for item in mappings:
        old_name = str(item["old_name"])
        new_name = str(item["new_name"])
        old_abs = app_root / "outputs" / old_name
        new_abs = app_root / "outputs" / new_name
        replacements = [
            (str(old_abs), str(new_abs)),
            (old_abs.as_posix(), new_abs.as_posix()),
            (f".VocaVid\\outputs\\{old_name}", f".VocaVid\\outputs\\{new_name}"),
            (f".VocaVid/outputs/{old_name}", f".VocaVid/outputs/{new_name}"),
            (f"outputs\\{old_name}", f"outputs\\{new_name}"),
            (f"outputs/{old_name}", f"outputs/{new_name}"),
        ]
        for old, new in replacements:
            updated = updated.replace(old, new)
    return updated


def _rewrite_kdenlive_files(outputs: Path, app_root: Path, mappings: list[dict[str, object]]) -> list[Path]:
    changed: list[Path] = []
    if not outputs.exists():
        return changed
    for path in outputs.rglob("*.kdenlive"):
        text = path.read_text(encoding="utf-8")
        updated = _replace_output_refs(text, app_root, mappings)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path)
    return changed


def _check_destination_conflicts(outputs: Path, mappings: list[dict[str, object]]) -> None:
    for item in mappings:
        source = outputs / str(item["old_name"])
        target = outputs / str(item["new_name"])
        if not source.exists() or not target.exists():
            continue
        conflicts = [
            source_file.relative_to(source)
            for source_file in source.rglob("*")
            if source_file.is_file() and (target / source_file.relative_to(source)).exists()
        ]
        if conflicts:
            names = ", ".join(str(conflict) for conflict in conflicts[:5])
            raise RuntimeError(f"Destination conflicts for {target}: {names}")


def _merge_or_move_dir(source: Path, target: Path) -> None:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return
    for child in source.iterdir():
        shutil.move(str(child), str(target / child.name))
    source.rmdir()


def _backup_db(db_path: Path) -> Path:
    backup = db_path.with_name(f"{db_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(db_path, backup)
    return backup


def _format_plan(
    mappings: list[dict[str, object]],
    moves: list[tuple[Path, Path]],
    changes: list[tuple[str, str, int, str]],
    kdenlive_files: list[Path],
) -> list[str]:
    messages = [f"Project mappings: {len(mappings)}", f"Output folders to move: {len(moves)}", f"DB values to update: {len(changes)}"]
    for source, target in moves:
        messages.append(f"Move {source.name} -> {target.name}")
    messages.append(f"Kdenlive files to scan: {len(kdenlive_files)}")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=Path.cwd() / ".VocaVid")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    for message in migrate(args.app_root, apply=args.apply):
        print(message)


if __name__ == "__main__":
    main()
