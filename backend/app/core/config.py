from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FT_PER_METER = 3.28084
DEFAULT_WALL_THICKNESS_M = 0.15
DEFAULT_CEILING_HEIGHT_M = 2.7
