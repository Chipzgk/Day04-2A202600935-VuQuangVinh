from __future__ import annotations
import argparse
import os
from pathlib import Path
from typing import Dict, Iterator, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Sửa lại dòng này: lùi ra 2 cấp (từ file config -> src -> thư mục gốc)
ROOT_DIR = Path(__file__).resolve().parent.parent 
DEFAULT_ENV_PATH = ROOT_DIR / ".env"

def load_env_config(env_path: Path = DEFAULT_ENV_PATH) -> Dict[str, str]:
    load_dotenv(dotenv_path=env_path)

    config = {
        "LLM_ENDPOINT": os.getenv("LLM_ENDPOINT", "").strip(),
        "API_KEY": os.getenv("API_KEY", "").strip(),
        "MODEL": os.getenv("MODEL", "").strip(),
    }

    missing = [key for key, value in config.items() if not value]
    if missing:
        raise ValueError(
            f"Missing required env values: {', '.join(missing)}. "
            f"Expected them in {env_path} or exported environment variables."
        )
    
    return config # Nhớ return config nhé!