from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR  = BASE_DIR / "output"
DB_PATH     = BASE_DIR / "applications.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL      = "claude-sonnet-4-6"
