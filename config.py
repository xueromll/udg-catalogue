import os
import re
import yaml
from dotenv import load_dotenv
from prompts import EXTRACTION_PROMPT, FILTER_PROMPT, STRICT_SIMULATION_PROMPT

load_dotenv()
API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
SCRIPT_DIR: str = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg: dict = yaml.safe_load(f)

MODEL: str = cfg.get("model", "deepseek-v4-flash")
CSV_FILE: str = os.path.join(SCRIPT_DIR, cfg.get("csv_file", "udg_database.csv"))
SORTED_CSV_FILE: str = os.path.join(SCRIPT_DIR, cfg.get("sorted_csv_file", "udg_database_sorted.csv"))
PROCESSED_FILE: str = os.path.join(SCRIPT_DIR, cfg.get("processed_file", "processed_arxiv_ids.txt"))
HTML_MAP_FILE: str = os.path.join(SCRIPT_DIR, cfg.get("html_map_file", "udg_3d_map.html"))
LOG_FILE: str = os.path.join(SCRIPT_DIR, cfg.get("log_file", "pipeline.log"))

SEARCH_QUERY: str = cfg.get("search_query", 'cat:astro-ph.GA AND abs:ultra-diffuse')
MAX_PAPERS: int = cfg.get("max_papers", 500)
SLEEP_BETWEEN: int = cfg.get("sleep_between", 5)
MAX_RETRIES: int = cfg.get("max_retries", 3)
TIMEOUT: int = cfg.get("timeout", 25)
USER_AGENT: str = cfg.get("user_agent", "UDG-ResearchScript/1.0 (lanhua1122333@gmail.com)")

MAX_DIST_MPC: float = cfg.get("max_dist_mpc", 5.0)
MIN_SAMPLES: int = cfg.get("min_samples", 2)

KEY_FIELDS: list[str] = [
    "ra", "dec", "distance_mpc", "effective_radius_kpc",
    "stellar_mass_solar", "dark_matter_fraction"
]

FORBIDDEN_KEYWORDS = [
    "sim", "simulation", "mock", "synthetic", "toy", "model", "tng", 
    "illustris", "fire", "eagle", "romulus", "nihao", "gadget", "gizmo", 
    "subhalo", "test", "example", "idealized", "artific"
]
FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b|^(" + "|".join(FORBIDDEN_KEYWORDS) + r")[-_0-9]",
    re.IGNORECASE
)