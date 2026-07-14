from __future__ import annotations

from pathlib import Path

from ..paths import project_output_file_stem, slug_folder_name, storage_relative_path


def project_reels_dir(app_root: Path, project) -> Path:
    return app_root / "outputs" / slug_folder_name(str(project["name"])) / "reels"


def project_finished_video_path(app_root: Path, project) -> Path:
    return app_root / "outputs" / slug_folder_name(str(project["name"])) / f"{project_output_file_stem(str(project['name']))}.mp4"


def project_finished_video_path_candidates(app_root: Path, project) -> list[Path]:
    output_dir = app_root / "outputs" / slug_folder_name(str(project["name"]))
    primary = project_finished_video_path(app_root, project)
    old_pipeline_default = output_dir / "final.mp4"
    legacy = output_dir / "finished.mp4"
    return list(dict.fromkeys([primary, old_pipeline_default, legacy]))


def ensure_reels_dirs(app_root: Path, project) -> dict[str, Path]:
    root = project_reels_dir(app_root, project)
    paths = {
        "root": root,
        "cache": root / "cache",
        "previews": root / "previews",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def reels_storage_path(app_root: Path, value: str | Path) -> str:
    return storage_relative_path(app_root, value)
