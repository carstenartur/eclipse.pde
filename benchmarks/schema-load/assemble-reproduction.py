#!/usr/bin/env python3
# SPDX-License-Identifier: EPL-2.0
"""Join the two adjacent archive parts and verify their exact recorded hashes."""
import hashlib
from pathlib import Path
import tempfile

PARTS = (
    ("reproduction.zip.part1", 7500000,
     "ffd289f36b9cd6fb74692ce0ffd52ee886611b3ea60ff5e16437932d3b6a2962"),
    ("reproduction.zip.part2", 7867548,
     "f470fca259b4e9c20b9153299e60d564b34be5f62fc496ef7dffca60b30c58e4"),
)
ARCHIVE_SIZE = 15367548
ARCHIVE_SHA256 = "9c558850d36959a7ed899dcdcf2375ae58a612aee60b550b744869e98cc12355"


def assemble():
    directory = Path(__file__).resolve().parent
    output = directory / "reproduction.zip"
    if output.exists():
        if (output.stat().st_size != ARCHIVE_SIZE or
                hashlib.sha256(output.read_bytes()).hexdigest() != ARCHIVE_SHA256):
            raise ValueError("Existing reproduction.zip has a different checksum; move it aside first.")
        print("Existing reproduction.zip verified: " + ARCHIVE_SHA256)
        return
    temporary = None
    try:
        total_hash = hashlib.sha256()
        total_size = 0
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".reproduction-", delete=False) as target:
            temporary = Path(target.name)
            for name, expected_size, expected_hash in PARTS:
                part_hash = hashlib.sha256()
                part_size = 0
                with (directory / name).open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        part_hash.update(chunk)
                        total_hash.update(chunk)
                        part_size += len(chunk)
                        target.write(chunk)
                if part_size != expected_size or part_hash.hexdigest() != expected_hash:
                    raise ValueError(name + " failed size/checksum verification.")
                total_size += part_size
        if total_size != ARCHIVE_SIZE or total_hash.hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Assembled archive failed size/checksum verification.")
        temporary.replace(output)
        print("Created reproduction.zip: " + ARCHIVE_SHA256)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        assemble()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
