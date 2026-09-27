"""Verify all retained VeriSci comparator evidence and replay the completed summary."""

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "ARCHIVE.json").read_text())
bundle = root / "evidence.tar.gz"
if hashlib.sha256(bundle.read_bytes()).hexdigest() != manifest["bundle_sha256"]:
    raise ValueError("Evidence bundle checksum mismatch")

with tempfile.TemporaryDirectory(prefix="orbweaver-verisci-replay-") as folder:
    target = Path(folder)
    with tarfile.open(bundle, "r:gz") as archive:
        names = archive.getnames()
        if len(names) != len(set(names)) or set(names) != set(manifest["files"]):
            raise ValueError("Wrong bundle members")
        for member in archive:
            relative = Path(member.name)
            if not member.isfile() or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive member")
            data = archive.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != manifest["files"][member.name]:
                raise ValueError(f"Archive checksum mismatch: {member.name}")
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    run = target / manifest["completed_run"]
    expected = (run / "results.json").read_bytes()
    (run / "results.json").unlink()
    subprocess.run([sys.executable, str(run / "verisci_reference.py"), "evaluate", str(run)],
                   stdout=subprocess.DEVNULL, check=True)
    if (run / "results.json").read_bytes() != expected:
        raise ValueError("Frozen summary replay differs")

print(json.dumps({"verified_files": len(manifest["files"]), "byte_identical_replay": True}))
