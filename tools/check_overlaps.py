"""Interference gate — cadkit/AGENTS.md's standard gate, run standalone.

The component list and the whitelist live in `src/build.py`, not here, so the
build and this script cannot disagree about what the design IS. This is the
thin wrapper AGENTS.md describes; the build calls the same `overlap_check.run`
with the components it already has in memory.

    py -3.12 -m tools.check_overlaps          # exit code = unintended pairs
    py -3.12 -m tools.check_overlaps --all    # also list intended contacts

Know what this costs. The scan is seconds; everything before it is a COMPLETE
model build, the same one `src.build` does. So gate-then-build pays for two
full builds. Prefer `py -3.12 -m src.build`, which gates as part of building.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cadkit import overlap_check              # noqa: E402

from src import build as B                    # noqa: E402


def collect_components():
    return [(n, s.val()) for n, s in B.components()]


def intended(a, b):
    return B.intended(a, b)


def main(argv):
    return overlap_check.run(collect_components(), intended,
                             show_all="--all" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
