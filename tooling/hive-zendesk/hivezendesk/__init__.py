# Read from the installed distribution, never a literal here. This value is stamped into every
# card as `distilled_by: hive-zendesk@<version>` and committed as provenance in the corpus
# repository, so a hand-kept copy that drifts from the released version writes permanent bad
# data with no error to notice it - which is what the literal `0.1.0` this replaced would have
# stamped into every card emitted by a wheel cut at 0.6.0. No fallback: a missing distribution
# must fail loudly rather than stamp a plausible guess.
from importlib.metadata import version

__version__ = version("vf-hive-zendesk")
