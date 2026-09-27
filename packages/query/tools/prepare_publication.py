"""Create an allowlisted, history-free local publication candidate; never publish it."""

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

SOURCE_PATHS = (
    "packages/query",
    ".github/workflows/query.yml",
    "LICENSE",
    "docs/QUERY_ENGINE_RELEASE.md",
    "docs/QUERY_ENGINE_RELEASE_VALIDATION.json",
)
# Retained JSONL evidence includes individual streams of about 726 MiB.
# Bound decoding, but do not silently omit those adverse historical results.
LIMIT = 1024 * 2**20


class ExclusionScan:
    """Term values never appear in reports/errors. This is not a credential scanner."""

    def __init__(self, terms):
        patterns = []
        for term in terms:
            words = re.findall(r"\w+", unicodedata.normalize("NFKC", term).casefold())
            if len("".join(words)) < 4:
                raise ValueError("Exclusion terms must contain at least four word characters")
            patterns.append(r"[\W_]*".join(re.escape(word) for word in words))
        if not patterns:
            raise ValueError("At least one private exclusion term is required")
        self.pattern = re.compile("|".join(patterns), re.IGNORECASE)
        self.seen = set()
        self.payloads = self.archive_members = 0

    def check(self, data, location, depth=0):
        if len(data) > LIMIT or depth > 8:
            raise ValueError(f"Scan size/nesting limit reached: {location}")
        if self.pattern.search(unicodedata.normalize("NFKC", str(location))):
            raise ValueError("Confidential term found in a publication path")
        digest = hashlib.sha256(data).digest()
        if digest in self.seen:
            return
        self.seen.add(digest)
        self.payloads += 1
        # Check container contents after decoding too; never assume compressed
        # evidence is safe merely because the outer bytes have no text match.
        if data.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                self.check(stream.read(LIMIT + 1), location + "::gzip", depth + 1)
        elif data.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    self._safe_name(member.filename)
                    if not member.is_dir():
                        if member.file_size > LIMIT:
                            raise ValueError("Archive member exceeds scan size limit")
                        self.archive_members += 1
                        self.check(
                            archive.read(member), location + "::" + member.filename, depth + 1
                        )
        elif len(data) > 265 and data[257:262] == b"ustar":
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
                for member in archive:
                    self._safe_name(member.name)
                    if member.isfile():
                        if member.size > LIMIT:
                            raise ValueError("Archive member exceeds scan size limit")
                        self.archive_members += 1
                        self.check(
                            archive.extractfile(member).read(),
                            location + "::" + member.name,
                            depth + 1,
                        )
                    elif not member.isdir():
                        raise ValueError("Links/special archive members require explicit review")
        else:
            text = unicodedata.normalize("NFKC", data.decode("utf-8", errors="ignore"))
            if self.pattern.search(text):
                raise ValueError(f"Confidential term found in publication content: {location}")

    @staticmethod
    def _safe_name(name):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive member name")


def repository_url(value):
    url = urlparse(value)
    if (
        url.scheme != "https"
        or url.netloc != "github.com"
        or url.query
        or url.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url.path)
    ):
        raise ValueError(
            "Expected https://github.com/OWNER/REPOSITORY without credentials or query"
        )
    return value


def prepare(destination, repository, exclusions, ref="HEAD"):
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=root, text=True
    ).strip()
    if destination.exists():
        raise ValueError("Choose a new destination; existing files are never overwritten")
    repository = repository_url(repository)
    scan = ExclusionScan(
        [line.strip() for line in exclusions.read_text().splitlines() if line.strip()]
    )
    raw = subprocess.check_output(
        ["git", "archive", "--format=tar", revision, *SOURCE_PATHS], cwd=root
    )
    destination.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                scan._safe_name(member.name)
                if not (member.isfile() or member.isdir()):
                    raise ValueError("Export contains a link or special file")
            archive.extractall(destination, filter="data")
        package = destination / "packages/query"
        templates = package / "publication"
        (destination / "README.md").write_bytes((templates / "README.md").read_bytes())
        (destination / "CONTRIBUTING.md").write_text(
            "# Contributing\n\nSee the [package contribution guide](packages/query/CONTRIBUTING.md).\n"
        )
        (destination / "SECURITY.md").write_bytes((package / "SECURITY.md").read_bytes())
        (destination / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n.venv*/\n.pytest_cache/\n.ruff_cache/\n.DS_Store\npackages/query/dist/\npackages/query/runs/\n.env\n.env.*\n"
        )
        target = destination / ".github/ISSUE_TEMPLATE"
        target.mkdir(parents=True)
        for file in sorted((templates / "ISSUE_TEMPLATE").glob("*.yml")):
            (target / file.name).write_bytes(file.read_bytes())
        (destination / ".github/PULL_REQUEST_TEMPLATE.md").write_bytes(
            (templates / "PULL_REQUEST_TEMPLATE.md").read_bytes()
        )
        project = package / "pyproject.toml"
        metadata, replacements = re.subn(
            r'^Repository = "[^"\n]+"$',
            f'Repository = "{repository}"',
            project.read_text(),
            flags=re.M,
        )
        if replacements != 1:
            raise ValueError("Expected one repository metadata field")
        project.write_text(metadata)
        files = {}
        for file in sorted(destination.rglob("*")):
            if not file.is_file():
                continue
            relative = str(file.relative_to(destination))
            if ".git" in file.relative_to(destination).parts:
                raise ValueError("Git history unexpectedly included")
            contents = file.read_bytes()
            scan.check(contents, relative)
            files[relative] = hashlib.sha256(contents).hexdigest()
        manifest = {
            "source_revision": revision,
            "source_paths": SOURCE_PATHS,
            "proposed_public_repository": repository,
            "git_history_included": False,
            "status": "Local review candidate only; no repository creation/upload/publication performed",
            "files": files,
            "file_count": len(files),
            "exclusion_scan": {
                "matching_payloads": 0,
                "unique_payloads_checked": scan.payloads,
                "archive_members_checked": scan.archive_members,
                "scope": "Names and readable nested contents; not secret detection or image OCR",
            },
        }
        (destination / "PUBLICATION_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
    except Exception:
        # Retain the failed candidate for investigation, visibly unsuitable for release.
        (destination / "PUBLICATION_BLOCKED.txt").write_text(
            "Preparation failed. Do not publish this directory.\n"
        )
        raise
    return {k: v for k, v in manifest.items() if k != "files"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--deny-terms-file", type=Path, required=True)
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(args.destination.resolve(), args.repository, args.deny_terms_file, args.ref),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
