import json
import os
import sys
import logging
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field

DATA_DIR = os.environ.get("DATA_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data")))
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# In-memory log buffer for Web UI
MAX_LOG_ENTRIES = 120
recent_logs: List[Dict[str, Any]] = []

def add_log(level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {"time": timestamp, "level": level.upper(), "message": message}
    recent_logs.append(entry)
    if len(recent_logs) > MAX_LOG_ENTRIES:
        recent_logs.pop(0)
    
    # Also log to standard logger
    py_logger = logging.getLogger("WOLApp")
    if level.upper() == "ERROR":
        py_logger.error(message)
    elif level.upper() == "WARNING":
        py_logger.warning(message)
    else:
        py_logger.info(message)


class AppConfig(BaseModel):
    telegram_token: str = Field(default="", description="Telegram Bot Token from @BotFather")
    allowed_chat_ids: str = Field(default="", description="Comma-separated Telegram Chat/User IDs")
    mac_address: str = Field(default="", description="Target MAC Address e.g. AA:BB:CC:DD:EE:FF")
    target_ip: str = Field(default="", description="Target IP Address for ping check e.g. 192.168.1.100")
    broadcast_ip: str = Field(default="255.255.255.255", description="Broadcast IP address")
    wol_port: int = Field(default=9, description="WOL UDP port (typically 7 or 9)")
    ping_interval: int = Field(default=3, description="Seconds between ping checks")
    ping_timeout: int = Field(default=90, description="Max seconds to wait for PC to wake up")
    tcp_fallback_port: int = Field(default=0, description="Optional TCP port to check (e.g. 445 or 3389) if ICMP ping blocked, 0 to disable")
    web_port: int = Field(default=7892, description="Web interface port")

    def get_allowed_ids(self) -> List[int]:
        ids = []
        if not self.allowed_chat_ids:
            return ids
        for item in self.allowed_chat_ids.replace(";", ",").split(","):
            cleaned = item.strip()
            if cleaned and (cleaned.lstrip("-").isdigit()):
                ids.append(int(cleaned))
        return ids


def load_config() -> AppConfig:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        cfg = AppConfig()
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return AppConfig(**data)
    except Exception as e:
        add_log("ERROR", f"שגיאה בטעינת קובץ הגדרות: {e}")
        return AppConfig()


def save_config(cfg: AppConfig):
    os.makedirs(DATA_DIR, exist_ok=True)
    dumped = cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.dict()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=2, ensure_ascii=False)
    add_log("INFO", "ההגדרות נשמרו בהצלחה")
