"""Fail the build when py.typed is missing from the sdist or wheel.

The marker lives at a different path in each artifact: a wheel uses the
installable layout (``ticko/py.typed``), while an sdist preserves the source
tree (``<name>-<version>/src/ticko/py.typed``). Each is checked accordingly.
"""

import sys
import tarfile
import zipfile
from pathlib import Path


def _find_one(dist: Path, pattern: str) -> Path:
    matches = sorted(dist.glob(pattern))
    if len(matches) != 1:
        print(
            f"expected exactly one {pattern} in {dist}, found {len(matches)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return matches[0]


def _require_member(
    archive_name: str, members: list[str], expected: str
) -> None:
    if expected not in members:
        print(f"{expected} missing from {archive_name}", file=sys.stderr)
        print("\n".join(sorted(members)), file=sys.stderr)
        sys.exit(1)
    print(f"OK: {expected} found in {archive_name}")


def main() -> None:
    """Check that both built artifacts ship the py.typed marker."""
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")

    wheel = _find_one(dist, "*.whl")
    with zipfile.ZipFile(wheel) as archive:
        wheel_members = archive.namelist()
    _require_member(wheel.name, wheel_members, "ticko/py.typed")

    sdist = _find_one(dist, "*.tar.gz")
    sdist_root = sdist.name.removesuffix(".tar.gz")
    with tarfile.open(sdist) as archive:
        sdist_members = archive.getnames()
    _require_member(
        sdist.name, sdist_members, f"{sdist_root}/src/ticko/py.typed"
    )


if __name__ == "__main__":
    main()
