from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def get_data_path(filename: str) -> Path:
    return DATA_DIR / filename
