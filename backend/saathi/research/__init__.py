"""What this system can contribute to cancer research, and what it must not.

See `burden.py`. The short version: travel and cost burden, consented per
patient, with no clinical value in it — because there is no clinical value in
this system to leak.
"""

from .burden import RECIPIENT, BurdenRow, DistanceBand, Release

__all__ = ["RECIPIENT", "BurdenRow", "DistanceBand", "Release"]
