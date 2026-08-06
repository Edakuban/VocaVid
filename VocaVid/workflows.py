from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_AVATAR_IMAGE_PROFILE = "flux2-klein-4b-distilled"
DEFAULT_CLIP_GENERATION_PROFILE = "ltx23-quality"
AVATAR_IMAGE_PROFILES = (
    "flux2-klein-9b-base",
    "flux2-klein-4b-base",
    "flux2-klein-4b-distilled",
)
CLIP_GENERATION_PROFILES = ("ltx23-quality", "ltx23-fast")


def normalize_avatar_image_profile(value: str | None) -> str:
    profile = str(value or "").strip().lower()
    if profile == "legacy":
        return "flux2-klein-9b-base"
    return profile if profile in AVATAR_IMAGE_PROFILES else DEFAULT_AVATAR_IMAGE_PROFILE


def normalize_clip_generation_profile(value: str | None) -> str:
    profile = str(value or "").strip().lower()
    return profile if profile in CLIP_GENERATION_PROFILES else DEFAULT_CLIP_GENERATION_PROFILE


@dataclass(frozen=True)
class WorkflowPaths:
    promptgen: Path
    avatar_description: Path
    qwen35_promptgen: Path
    qwen35_avatar_description: Path
    image: Path
    image_aliases: tuple[Path, ...]
    image_reference: Path
    avatar_image: Path
    avatar_image_flux2_klein_4b_base: Path
    avatar_image_flux2_klein_4b_distilled: Path
    video: Path
    video_aliases: tuple[Path, ...]
    video_ltx23_fast: Path
    chorus: Path

    @classmethod
    def defaults(cls, project_root: Path | None = None) -> "WorkflowPaths":
        root = project_root or Path.cwd()
        directory = root / "workflows"
        return cls(
            promptgen=directory / "promptgen.json",
            avatar_description=directory / "avatar_description.json",
            qwen35_promptgen=directory / "qwen35_text_promptgen.json",
            qwen35_avatar_description=directory / "qwen35_avatar_description.json",
            image=directory / "image.json",
            image_aliases=(directory / "image_z_image_turbo.json",),
            image_reference=directory / "image_reference.json",
            avatar_image=directory / "avatartoimage_flux.json",
            avatar_image_flux2_klein_4b_base=directory / "image_flux2_klein_image_edit_4b_base.json",
            avatar_image_flux2_klein_4b_distilled=directory / "image_flux2_klein_image_edit_4b_distilled.json",
            video=directory / "video.json",
            video_aliases=(directory / "imageaudiotovideo.json",),
            video_ltx23_fast=directory / "imageaudiotovideo_ltx23_fast.json",
            chorus=directory / "chorus.json",
        )

    def optional_promptgen(self) -> Path | None:
        return self.promptgen if self.promptgen.exists() else None

    def optional_promptgen_for_profile(self, profile: str) -> Path | None:
        path = self.qwen35_promptgen if profile == "qwen35" and self.qwen35_promptgen.exists() else self.promptgen
        return path if path.exists() else None

    def optional_avatar_description(self) -> Path | None:
        return self.avatar_description if self.avatar_description.exists() else None

    def optional_avatar_description_for_profile(self, profile: str) -> Path | None:
        path = self.qwen35_avatar_description if profile == "qwen35" and self.qwen35_avatar_description.exists() else self.avatar_description
        return path if path.exists() else None

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

    def require_avatar_image(self, profile: str | None = None) -> Path:
        selected = normalize_avatar_image_profile(profile)
        paths = {
            "flux2-klein-9b-base": (self.avatar_image, "workflows.avatartoimage_flux"),
            "flux2-klein-4b-base": (
                self.avatar_image_flux2_klein_4b_base,
                "workflows.image_flux2_klein_image_edit_4b_base",
            ),
            "flux2-klein-4b-distilled": (
                self.avatar_image_flux2_klein_4b_distilled,
                "workflows.image_flux2_klein_image_edit_4b_distilled",
            ),
        }
        path, label = paths[selected]
        if selected == DEFAULT_AVATAR_IMAGE_PROFILE and not path.exists() and self.avatar_image.exists():
            # Existing installations keep working until the new default
            # workflow has been copied into their workflows directory.
            return self.avatar_image
        return self._require(path, label)

    def avatar_output_targets(self, workflow_path: Path) -> list[str] | None:
        # The official distilled template also includes a one-image example.
        # Target its two-image SaveImage node so avatar replacement runs only
        # once with the scene image plus the avatar reference.
        if workflow_path == self.avatar_image_flux2_klein_4b_distilled:
            return ["94"]
        return None

    def require_video(self) -> Path:
        if self.video.exists():
            return self.video
        for alias in self.video_aliases:
            if alias.exists():
                return alias
        return self._require(self.video, "workflows.video")

    def require_video_for_profile(self, profile: str | None = None) -> Path:
        if normalize_clip_generation_profile(profile) == "ltx23-fast":
            return self._require(self.video_ltx23_fast, "workflows.imageaudiotovideo_ltx23_fast")
        return self.require_video()

    def require_chorus(self) -> Path:
        return self._require(self.chorus, "workflows.chorus")

    @staticmethod
    def _require(path: Path, label: str) -> Path:
        if not path.exists():
            raise FileNotFoundError(f"Missing {label}: put the exported ComfyUI workflow at {path}")
        return path
