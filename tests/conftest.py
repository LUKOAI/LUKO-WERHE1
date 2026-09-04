import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLES = ROOT / "samples"
SAMPLE_CSV = SAMPLES / "taxReport_sample.csv"
SAMPLE_PDF_DIR = SAMPLES / "faktury"
