from pathlib import Path
import os

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT.parent.parent / "data"

DB_PATH = DATA_DIR / "courses_metcs.sqlite"
TABLE_NAME = "public_classes"

NER_PATH = PACKAGE_ROOT.parent.parent / "models" / "ner" / "course_ner_model"
API_KEY = os.environ.get("OPENAI_API_KEY")