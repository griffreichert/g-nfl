"""Source-document sync (issue #96). No network, no Supabase."""

from datetime import UTC, datetime, timedelta

import pytest

from g_nfl.utils import storage


class FakeBucket:
    """The three storage methods the sync uses, over an in-memory dict."""

    def __init__(self, objects: dict[str, tuple[bytes, datetime]] | None = None):
        self.objects = objects or {}
        self.uploads: list[str] = []

    def list(self, prefix: str):
        out = []
        for key, (body, modified) in self.objects.items():
            head, _, name = key.partition("/")
            if head == prefix:
                out.append(
                    {
                        "name": name,
                        "updated_at": modified.isoformat(),
                        "metadata": {"size": len(body)},
                    }
                )
        return out

    def upload(self, key: str, body: bytes, options: dict):
        self.uploads.append(key)
        self.objects[key] = (body, datetime.now(UTC))

    def download(self, key: str) -> bytes:
        return self.objects[key][0]


class FakeClient:
    def __init__(self, bucket: FakeBucket):
        self._bucket = bucket
        self.storage = self

    def from_(self, name: str):
        return self._bucket


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    """Point SOURCE_DOCUMENTS at a temp directory instead of data/pool."""
    directory = tmp_path / "pool"
    directory.mkdir()
    monkeypatch.setattr(
        storage, "SOURCE_DOCUMENTS", {"pool": (directory, "*.xlsx")}, raising=True
    )
    return directory


def test_push_uploads_new_files_and_skips_matching_ones(pool_dir):
    (pool_dir / "standings_2025.xlsx").write_bytes(b"workbook")
    (pool_dir / "standings_2024.xlsx").write_bytes(b"new one")
    bucket = FakeBucket({"pool/standings_2025.xlsx": (b"workbook", datetime.now(UTC))})

    result = storage.push_data(client=FakeClient(bucket))

    assert result.uploaded == ("pool/standings_2024.xlsx",)
    assert result.skipped == ("pool/standings_2025.xlsx",)
    assert bucket.uploads == ["pool/standings_2024.xlsx"]


def test_push_reuploads_when_the_size_changed(pool_dir):
    (pool_dir / "standings_2025.xlsx").write_bytes(b"workbook, now longer")
    bucket = FakeBucket({"pool/standings_2025.xlsx": (b"workbook", datetime.now(UTC))})

    assert storage.push_data(client=FakeClient(bucket)).uploaded == (
        "pool/standings_2025.xlsx",
    )


def test_pull_fetches_files_the_clone_does_not_have(pool_dir):
    bucket = FakeBucket({"pool/standings_2025.xlsx": (b"workbook", datetime.now(UTC))})

    result = storage.pull_data(client=FakeClient(bucket))

    assert result.downloaded == ("pool/standings_2025.xlsx",)
    assert (pool_dir / "standings_2025.xlsx").read_bytes() == b"workbook"


def test_pull_refuses_to_clobber_a_newer_local_file(pool_dir):
    """The case that would lose an irreplaceable workbook: both laptops edited."""
    local = pool_dir / "standings_2025.xlsx"
    local.write_bytes(b"edited here, longer than remote")
    stale = datetime.now(UTC) - timedelta(days=2)
    bucket = FakeBucket({"pool/standings_2025.xlsx": (b"older", stale)})

    result = storage.pull_data(client=FakeClient(bucket))

    assert result.refused == ("pool/standings_2025.xlsx",)
    assert local.read_bytes() == b"edited here, longer than remote"

    forced = storage.pull_data(client=FakeClient(bucket), force=True)
    assert forced.downloaded == ("pool/standings_2025.xlsx",)
    assert local.read_bytes() == b"older"


def test_dry_run_moves_nothing(pool_dir):
    (pool_dir / "standings_2024.xlsx").write_bytes(b"new one")
    bucket = FakeBucket()

    result = storage.push_data(client=FakeClient(bucket), dry_run=True)

    assert result.uploaded == ("pool/standings_2024.xlsx",)
    assert bucket.uploads == []


def test_a_missing_bucket_is_an_error_not_an_empty_sync(pool_dir):
    """`list()` returns [] for a bucket that does not exist, so check first."""

    class NoBucketClient(FakeClient):
        def get_bucket(self, name):
            raise RuntimeError("Bucket not found")

    with pytest.raises(storage.BucketMissing, match="not found"):
        storage.pull_data(client=NoBucketClient(FakeBucket()))
