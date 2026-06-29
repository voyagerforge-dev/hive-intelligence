"""Configure pytest environment for okfserve tests."""
from pathlib import Path
import sys

# Add okfgen to path for proper import resolution
okf_gen_dir = Path(__file__).parent.parent.parent / "okf-gen"
if okf_gen_dir.exists() and str(okf_gen_dir) not in sys.path:
    sys.path.insert(0, str(okf_gen_dir))
