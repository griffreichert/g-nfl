#!/usr/bin/env python3
"""Push or pull the source documents that cannot be regenerated (issue #96).

    make push-data          # local -> Supabase Storage
    make pull-data          # Supabase Storage -> local
    make pull-data ARGS=--force

The bucket has to exist first. Create it once in the Supabase dashboard,
private, named as ``g_nfl.utils.storage.BUCKET`` — the publishable key cannot
create buckets and neither laptop carries the service key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "src"))

from g_nfl.utils.storage import (  # noqa: E402
    BUCKET,
    BucketMissing,
    pull_data,
    push_data,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("direction", choices=["push", "pull"])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Pull only: overwrite a local file that is newer than the remote copy.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would move, move nothing."
    )
    args = parser.parse_args()

    try:
        if args.direction == "push":
            result = push_data(dry_run=args.dry_run)
            for key in result.uploaded:
                print(f"  {'would upload' if args.dry_run else 'uploaded'} {key}")
        else:
            result = pull_data(force=args.force, dry_run=args.dry_run)
            for key in result.downloaded:
                print(f"  {'would download' if args.dry_run else 'downloaded'} {key}")
            for key in result.refused:
                print(f"  refused {key}: local file is newer (--force to overwrite)")
    except BucketMissing as e:
        sys.exit(str(e))

    print(f"{BUCKET}: {result.summary()}")


if __name__ == "__main__":
    main()
