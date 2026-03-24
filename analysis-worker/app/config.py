import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    provider: str
    api_key_file: str
    api_base_url: str
    model: str
    max_tokens: int

    def get_api_key(self) -> str:
        """Read API key from file."""
        key_path = Path(self.api_key_file)
        if not key_path.exists():
            raise FileNotFoundError(f"API key file not found: {self.api_key_file}")
        return key_path.read_text().strip()


@dataclass
class Config:
    daily_reel_target: int
    report_output_dir: str
    watch_seconds_per_reel: int
    screenshots_per_reel: int
    browser_profile_dir: str
    database_path: str
    headless: bool
    max_run_minutes: int
    skip_if_already_completed_today: bool
    llm: LLMConfig
    screenshot_dir: str
    log_dir: str
    project_root: str


def get_project_root() -> Path:
    """Get the project root directory."""
    # Navigate up from analysis-worker/app to project root
    return Path(__file__).parent.parent.parent


def resolve_path(project_root: Path, file_path: str) -> str:
    """Resolve a relative path to absolute."""
    path = Path(file_path)
    if path.is_absolute():
        return str(path)
    return str(project_root / path)


def load_config(project_root: Optional[Path] = None) -> Config:
    """Load configuration from config.json."""
    if project_root is None:
        project_root = get_project_root()

    config_path = project_root / "shared" / "config" / "config.json"

    # Default values
    defaults = {
        "daily_reel_target": 50,
        "report_output_dir": "./data/reports",
        "watch_seconds_per_reel": 18,
        "screenshots_per_reel": 2,
        "browser_profile_dir": "./data/browser-profile",
        "database_path": "./data/app.db",
        "headless": False,
        "max_run_minutes": 180,
        "skip_if_already_completed_today": True,
        "llm": {
            "provider": "anthropic",
            "api_key_file": "./api key.txt",
            "api_base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096
        },
        "screenshot_dir": "./data/screenshots",
        "log_dir": "./data/logs"
    }

    # Load config file
    if config_path.exists():
        with open(config_path, "r") as f:
            user_config = json.load(f)
        # Merge with defaults
        for key, value in user_config.items():
            if key == "llm" and isinstance(value, dict):
                defaults["llm"].update(value)
            else:
                defaults[key] = value

    # Resolve paths
    llm_config = LLMConfig(
        provider=defaults["llm"]["provider"],
        api_key_file=resolve_path(project_root, defaults["llm"]["api_key_file"]),
        api_base_url=defaults["llm"]["api_base_url"],
        model=defaults["llm"]["model"],
        max_tokens=defaults["llm"]["max_tokens"]
    )

    config = Config(
        daily_reel_target=defaults["daily_reel_target"],
        report_output_dir=resolve_path(project_root, defaults["report_output_dir"]),
        watch_seconds_per_reel=defaults["watch_seconds_per_reel"],
        screenshots_per_reel=defaults["screenshots_per_reel"],
        browser_profile_dir=resolve_path(project_root, defaults["browser_profile_dir"]),
        database_path=resolve_path(project_root, defaults["database_path"]),
        headless=defaults["headless"],
        max_run_minutes=defaults["max_run_minutes"],
        skip_if_already_completed_today=defaults["skip_if_already_completed_today"],
        llm=llm_config,
        screenshot_dir=resolve_path(project_root, defaults["screenshot_dir"]),
        log_dir=resolve_path(project_root, defaults["log_dir"]),
        project_root=str(project_root)
    )

    # Ensure directories exist
    for dir_path in [config.report_output_dir, config.screenshot_dir, config.log_dir]:
        os.makedirs(dir_path, exist_ok=True)

    return config
