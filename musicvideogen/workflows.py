from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowPaths:
    promptgen: Path
    avatar_description: Path
    image: Path
    image_aliases: tuple[Path, ...]
    image_reference: Path
    avatar_image: Path
    video: Path
    video_aliases: tuple[Path, ...]
    chorus: Path

    @classmethod
    def defaults(cls, project_root: Path | None = None) -> "WorkflowPaths":
        root = project_root or Path.cwd()
        directory = root / "workflows"
        return cls(
            promptgen=directory / "promptgen.json",
            avatar_description=directory / "avatar_description.json",
            image=directory / "image.json",
            image_aliases=(directory / "image_z_image_turbo.json",),
            image_reference=directory / "image_reference.json",
            avatar_image=directory / "avatartoimage_flux.json",
            video=directory / "video.json",
            video_aliases=(directory / "imageaudiotovideo.json",),
            chorus=directory / "chorus.json",
        )

    def optional_promptgen(self) -> Path | None:
        return self.promptgen if self.promptgen.exists() else None

    def optional_avatar_description(self) -> Path | None:
        return self.avatar_description if self.avatar_description.exists() else None

    def require_image(self) -> Path:
        if self.image.exists():
            return self.image
        for alias in self.image_aliases:
            if alias.exists():
                return alias
        return self._require(self.image, "workflows.image")

    def image_for_reference(self, use_reference: bool) -> Path:
        if use_reference and self.image_reference.exists():
            return self.image_reference
        return self.require_image()

    def require_avatar_image(self) -> Path:
        return self._require(self.avatar_image, "workflows.avatartoimage_flux")

    def require_video(self) -> Path:
        if self.video.exists():
            return self.video
        for alias in self.video_aliases:
            if alias.exists():
                return alias
        return self._require(self.video, "workflows.video")

    def require_chorus(self) -> Path:
        return self._require(self.chorus, "workflows.chorus")

    @staticmethod
    def _require(path: Path, label: str) -> Path:
        if not path.exists():
            raise FileNotFoundError(f"Missing {label}: put the exported ComfyUI workflow at {path}")
        return path
