"""Verify retained preparation bytes; optionally restore them without executing code."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root, output=None):
    metadata = json.loads((root/"ARCHIVE.json").read_text())
    raw = (root/"evidence.tar.gz").read_bytes()
    if digest(raw) != metadata["archive_sha256"]:
        raise ValueError("Archive checksum mismatch")
    files = {}
    with tarfile.open(root/"evidence.tar.gz") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or ".." in name.parts or member.name in files:
                raise ValueError("Unsafe or duplicate archive member")
            data = archive.extractfile(member).read()
            if digest(data) != metadata["files"].get(member.name):
                raise ValueError(f"Member checksum mismatch: {member.name}")
            files[member.name] = data
    if set(files) != set(metadata["files"]):
        raise ValueError("Incomplete archive")
    manifest = json.loads(files["manifest.json"])
    for name, expected in manifest["files"].items():
        if digest(files[name]) != expected:
            raise ValueError(f"Frozen input checksum mismatch: {name}")
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            path = output/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return dict(verified_files=len(files), manifest_sha256=digest(files["manifest.json"]),
                cuda_executed=False, inference_quality_measured=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent, args.output), indent=2))
