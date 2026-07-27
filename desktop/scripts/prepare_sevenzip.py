from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path


EXECUTABLE_URL = "https://www.7-zip.org/a/7zr.exe"
EXECUTABLE_SHA256 = "56b8cc9f4971cef253644fafe54063ed7fdca551d4dee0f8c6baa81b855acd72"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "VocaVid-build/1.1"})
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output)
    partial.replace(target)


def prepare(output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file() and sha256_file(output) == EXECUTABLE_SHA256:
        print(f"Using cached {output}")
        return
    output.unlink(missing_ok=True)
    download(EXECUTABLE_URL, output)
    actual_executable_hash = sha256_file(output)
    if actual_executable_hash != EXECUTABLE_SHA256:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"7zr.exe SHA-256 mismatch: {actual_executable_hash}")
    print(f"Prepared {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.output)


if __name__ == "__main__":
    main()
