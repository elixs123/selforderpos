import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())


def cameras_in_env() -> bool:
    return bool(os.environ.get("CAM_SERVER_URL") or (os.environ.get("CAM_A_HOST") and os.environ.get("CAM_B_HOST")))


@dataclass
class Settings:
    register_id: str = "K1"
    fullscreen: bool = False
    demo_payments: bool = False
    terminal_url: str = "http://127.0.0.1:3421"
    terminal_api_key: str = ""
    terminal_print_slip: bool = True
    terminal_slip_copies: int = 1
    fiscal_enabled: bool = False
    fiscal_url: str = "http://localhost:8085"
    fiscal_unit: str = "ko"
    fiscal_tax_label: str = "E"
    fiscal_card_payment: str = "Kartica"
    fiscal_qr_payment: str = "Virman"
    cameras_enabled: bool = field(default_factory=cameras_in_env)
    vision_server_url: str = field(default_factory=lambda: os.environ.get("CAM_SERVER_URL", ""))
    camera_a_host: str = field(default_factory=lambda: os.environ.get("CAM_A_HOST", ""))
    camera_a2_host: str = field(default_factory=lambda: os.environ.get("CAM_A2_HOST", ""))
    camera_b_host: str = field(default_factory=lambda: os.environ.get("CAM_B_HOST", ""))
    camera_b2_host: str = field(default_factory=lambda: os.environ.get("CAM_B2_HOST", ""))
    camera_channel: str = field(default_factory=lambda: os.environ.get("CAM_CHANNEL", "102"))
    camera_model: str = "clip"
    match_threshold: float = 0.0
    receipt_return_seconds: int = 20


def load_settings(path: Path) -> Settings:
    defaults = Settings()
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    values = {}
    for item in fields(Settings):
        if item.name in data:
            default = getattr(defaults, item.name)
            try:
                values[item.name] = type(default)(data[item.name])
            except (TypeError, ValueError):
                values[item.name] = default
    return Settings(**{**asdict(defaults), **values})


def save_settings(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
