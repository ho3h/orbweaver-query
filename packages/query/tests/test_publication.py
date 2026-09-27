"""A publication export must fail closed on nested confidential text and unsafe paths."""

import gzip
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

path = Path(__file__).parents[1] / "tools/prepare_publication.py"
spec = importlib.util.spec_from_file_location("publication_tool", path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_scans_nested_zip_gzip_tar_without_printing_private_term():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("note.md", "A Hidden-Project detail")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo("nested.zip")
        member.size = len(payload.getvalue())
        archive.addfile(member, io.BytesIO(payload.getvalue()))
    with pytest.raises(ValueError, match="Confidential term") as error:
        tool.ExclusionScan(["Hidden Project"]).check(
            gzip.compress(stream.getvalue()), "evidence.tar.gz"
        )
    assert "Hidden" not in str(error.value)


def test_safe_payload_deduplication_and_unsafe_archive_member():
    scan = tool.ExclusionScan(["Hidden Project"])
    scan.check(b"public content", "one")
    scan.check(b"public content", "two")
    assert scan.payloads == 1
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.md", "public content")
    with pytest.raises(ValueError, match="Unsafe"):
        scan.check(stream.getvalue(), "bad.zip")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://name:password@github.com/a/b",
        "https://github.com/a/b?token=example",
        "https://example.org/a/b",
    ],
)
def test_repository_url_cannot_embed_credentials_or_other_destinations(url):
    with pytest.raises(ValueError):
        tool.repository_url(url)


def test_plain_repository_url():
    assert (
        tool.repository_url("https://github.com/example/query")
        == "https://github.com/example/query"
    )
