"""Supabase Storage for the files that cannot be regenerated (issue #96).

Almost everything under ``data/`` rebuilds from code: 163M of nflverse parquet
re-downloads, the Sleeper cache re-fetches, board CSVs take 30 seconds. The
exception is the pool workbooks, which came out of Griffin's inbox and exist
nowhere else. Those are what this syncs, and #56 wants more of them.

**Why Supabase and not S3.** Supabase is already provisioned, already in
``.env``, and already holds the tables these workbooks produced. S3 would mean
a new account, IAM keys on two laptops and a fetch layer, to move 452K. S3
earns its place when large point-in-time scrapes appear (paywalled PFF pulls,
historical odds snapshots) — Supabase Storage gets expensive per GB first.

**Idempotent in both directions.** Uploads skip files whose size already
matches, and downloads refuse to clobber a local file that is newer than the
remote copy unless told to. Losing an irreplaceable workbook to a careless
sync would defeat the point of syncing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .supabase_client import get_supabase

#: Private bucket. Create it once in the Supabase dashboard: the publishable
#: key cannot create buckets, and this repo has no service key on either laptop.
BUCKET = "source-documents"

# repo root: src/g_nfl/utils/storage.py -> utils -> g_nfl -> src -> root
_ROOT = Path(__file__).parents[3]

#: Local directories whose contents are irreplaceable, and the glob that
#: catches them. Keyed by the prefix used inside the bucket.
SOURCE_DOCUMENTS: dict[str, tuple[Path, str]] = {
    "pool": (_ROOT / "data" / "pool", "*.xlsx"),
}


@dataclass(frozen=True)
class SyncResult:
    """What a push or pull did, so the caller can print it honestly."""

    uploaded: tuple[str, ...] = ()
    downloaded: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()

    def summary(self) -> str:
        parts = [
            f"{len(self.uploaded)} uploaded",
            f"{len(self.downloaded)} downloaded",
            f"{len(self.skipped)} unchanged",
        ]
        if self.refused:
            parts.append(f"{len(self.refused)} refused (local file is newer)")
        return ", ".join(parts)


class BucketMissing(RuntimeError):
    """The bucket has not been created yet, and listing it lies about that."""


def _bucket(client=None):
    storage = (client or get_supabase()).storage
    # `from_(...).list()` on a bucket that does not exist returns [] rather than
    # raising, which would turn `make pull-data` into a silent no-op on a fresh
    # clone — the one moment it has to work. get_bucket 404s honestly.
    get_bucket = getattr(storage, "get_bucket", None)
    if get_bucket is not None:
        try:
            get_bucket(BUCKET)
        except Exception as e:  # noqa: BLE001 — storage errors are not typed usefully
            raise BucketMissing(
                f"Supabase Storage bucket {BUCKET!r} not found ({e}). Create it once "
                "in the dashboard (Storage → New bucket, private). The publishable "
                "key cannot create buckets."
            ) from e
    return storage.from_(BUCKET)


def _remote_index(bucket, prefix: str) -> dict[str, dict]:
    """``{name: object}`` for one prefix. An empty prefix lists nothing, not an error."""
    return {obj["name"]: obj for obj in bucket.list(prefix)}


def _remote_size(obj: dict) -> int | None:
    return (obj.get("metadata") or {}).get("size")


def _remote_modified(obj: dict) -> datetime | None:
    stamp = obj.get("updated_at") or obj.get("created_at")
    if not stamp:
        return None
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def push_data(client=None, dry_run: bool = False) -> SyncResult:
    """Upload local source documents, skipping ones already there at the same size.

    Size rather than a hash: Supabase's listing gives size for free, and these
    are append-only workbooks — a changed workbook changes length. A hash would
    mean downloading every remote file to compare, which is the cost this is
    trying to avoid.
    """
    bucket = _bucket(client)
    uploaded, skipped = [], []

    for prefix, (directory, pattern) in SOURCE_DOCUMENTS.items():
        if not directory.exists():
            continue
        remote = _remote_index(bucket, prefix)
        for path in sorted(directory.glob(pattern)):
            key = f"{prefix}/{path.name}"
            existing = remote.get(path.name)
            if existing and _remote_size(existing) == path.stat().st_size:
                skipped.append(key)
                continue
            if not dry_run:
                bucket.upload(
                    key,
                    path.read_bytes(),
                    {"upsert": "true", "content-type": "application/octet-stream"},
                )
            uploaded.append(key)

    return SyncResult(uploaded=tuple(uploaded), skipped=tuple(skipped))


def pull_data(client=None, force: bool = False, dry_run: bool = False) -> SyncResult:
    """Fetch source documents into their local directories.

    Refuses to overwrite a local file modified more recently than the remote
    object unless ``force``. That case means the two laptops both edited a
    workbook, and silently picking one is how the irreplaceable copy is lost.
    """
    bucket = _bucket(client)
    downloaded, skipped, refused = [], [], []

    for prefix, (directory, _) in SOURCE_DOCUMENTS.items():
        for name, obj in _remote_index(bucket, prefix).items():
            key = f"{prefix}/{name}"
            local = directory / name

            if local.exists():
                if _remote_size(obj) == local.stat().st_size:
                    skipped.append(key)
                    continue
                remote_time = _remote_modified(obj)
                local_time = datetime.fromtimestamp(local.stat().st_mtime, UTC)
                if not force and remote_time and local_time > remote_time:
                    refused.append(key)
                    continue

            if not dry_run:
                directory.mkdir(parents=True, exist_ok=True)
                local.write_bytes(bucket.download(key))
            downloaded.append(key)

    return SyncResult(
        downloaded=tuple(downloaded), skipped=tuple(skipped), refused=tuple(refused)
    )
