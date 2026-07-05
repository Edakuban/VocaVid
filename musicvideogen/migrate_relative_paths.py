from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .paths import storage_relative_path


PATH_COLUMNS = {
    "projects": ["audio_path", "lyrics_path", "final_video_path"],
    "lyric_lines": ["image_path", "avatar_image_path", "clip_path"],
    "render_segments": ["image_path", "avatar_image_path", "clip_path", "audio_path"],
}


def migrate(app_root: Path) -> int:
    app_root = app_root.resolve()
    db_path = app_root / "musicvideogen.sqlite3"
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    changed = 0
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        with con:
            for table, columns in PATH_COLUMNS.items():
                for column in columns:
                    changed += _normalize_column(con, app_root, table, column)
            changed += _normalize_reference_image_paths(con, app_root)
    finally:
        con.close()
    return changed


def _normalize_column(con: sqlite3.Connection, app_root: Path, table: str, column: str) -> int:
    changed = 0
    rows = con.execute(f"SELECT rowid AS _rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
    for row in rows:
        current = str(row[column])
        updated = storage_relative_path(app_root, current)
        if updated == current:
            continue
        con.execute(f"UPDATE {table} SET {column} = ? WHERE rowid = ?", (updated, int(row["_rowid"])))
        changed += 1
    return changed


def _normalize_reference_image_paths(con: sqlite3.Connection, app_root: Path) -> int:
    changed = 0
    rows = con.execute("SELECT rowid AS _rowid, reference_image_paths FROM projects").fetchall()
    for row in rows:
        current = str(row["reference_image_paths"] or "[]")
        try:
            parsed = json.loads(current)
        except json.JSONDecodeError:
            parsed = [line.strip() for line in current.splitlines() if line.strip()]
        if not isinstance(parsed, list):
            continue
        updated_list = [storage_relative_path(app_root, item) for item in parsed]
        updated = json.dumps(updated_list)
        if updated == current:
            continue
        con.execute("UPDATE projects SET reference_image_paths = ? WHERE rowid = ?", (updated, int(row["_rowid"])))
        changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=Path.cwd() / ".musicvideogen")
    args = parser.parse_args()
    changed = migrate(args.app_root)
    print(f"Updated DB values: {changed}")


if __name__ == "__main__":
    main()
