import os
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import AppConfig, load_config, save_config, add_log, recent_logs
from app.wol import send_wol_packet, clean_mac
from app.monitor import monitor
from app.bot import bot_manager

# Setup lifespan for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    add_log("INFO", "שרת WOL הופעל")
    # Start Telegram Bot if token configured
    asyncio.create_task(bot_manager.start())
    yield
    # Shutdown
    await bot_manager.stop()
    add_log("INFO", "שרת WOL נעצר")

app = FastAPI(
    title="WOL Telegram Server",
    description="Wake-on-LAN server with Telegram Bot and Web Management UI",
    lifespan=lifespan
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Request Models
class ConfigUpdateRequest(BaseModel):
    telegram_token: Optional[str] = ""
    allowed_chat_ids: Optional[str] = ""
    mac_address: Optional[str] = ""
    target_ip: Optional[str] = ""
    broadcast_ip: Optional[str] = "255.255.255.255"
    wol_port: Optional[int] = 9
    ping_interval: Optional[int] = 3
    ping_timeout: Optional[int] = 90
    tcp_fallback_port: Optional[int] = 0
    web_port: Optional[int] = 7892

class TestTelegramRequest(BaseModel):
    token: Optional[str] = None
    chat_id: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/config")
async def get_config():
    cfg = load_config()
    return cfg.model_dump()


@app.post("/api/config")
async def update_config(payload: ConfigUpdateRequest):
    current = load_config()
    
    # Validate MAC if provided
    mac = (payload.mac_address or "").strip()
    if mac:
        try:
            mac = clean_mac(mac)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    updated = AppConfig(
        telegram_token=payload.telegram_token.strip() if payload.telegram_token else "",
        allowed_chat_ids=(payload.allowed_chat_ids or "").strip(),
        mac_address=mac,
        target_ip=(payload.target_ip or "").strip(),
        broadcast_ip=(payload.broadcast_ip or "255.255.255.255").strip(),
        wol_port=payload.wol_port or 9,
        ping_interval=payload.ping_interval or 3,
        ping_timeout=payload.ping_timeout or 90,
        tcp_fallback_port=payload.tcp_fallback_port or 0,
        web_port=payload.web_port or 7892
    )

    save_config(updated)

    # If telegram token changed, restart bot
    add_log("INFO", "הגדרות עודכנו ממשק הניהול. מרענן את בוט הטלגרם...")
    asyncio.create_task(bot_manager.restart())

    return {"status": "success", "message": "ההגדרות נשמרו בהצלחה והבוט עודכן!"}


@app.get("/api/status")
async def get_system_status():
    cfg = load_config()
    monitor_summary = monitor.get_status_summary()

    # Fast check of target host if configured
    is_pc_online = None
    if cfg.target_ip:
        is_pc_online = await monitor.ping_host(cfg.target_ip, cfg.tcp_fallback_port, timeout_sec=0.8)

    return {
        "bot": {
            "is_running": bot_manager.is_running,
            "status": bot_manager.bot_status,
            "username": bot_manager.bot_username
        },
        "pc": {
            "target_ip": cfg.target_ip,
            "mac_address": cfg.mac_address,
            "is_online": is_pc_online
        },
        "monitor": monitor_summary
    }


@app.post("/api/wake")
async def trigger_wake():
    cfg = load_config()
    if not cfg.mac_address:
        raise HTTPException(status_code=400, detail="טרם הוגדרה כתובת MAC בהגדרות")

    success, msg = send_wol_packet(cfg.mac_address, cfg.broadcast_ip, cfg.wol_port)
    if not success:
        raise HTTPException(status_code=500, detail=msg)

    # Start monitor task and notify via Telegram if online
    if cfg.target_ip:
        async def on_wake_completed(is_online: bool, duration: float):
            if is_online:
                await bot_manager.send_notification_to_allowed(
                    f"🎉 **המחשב נדלק והתחבר לרשת!** 🟢\n"
                    f"⏱️ זמן התעוררות: {duration} שניות\n"
                    f"🌐 כתובת IP: `{cfg.target_ip}`"
                )
            else:
                await bot_manager.send_notification_to_allowed(
                    f"⚠️ חלפו {cfg.ping_timeout} שניות והמחשב (`{cfg.target_ip}`) עדיין לא מגיב ל-Ping."
                )

        monitor.start_wake_monitor_task(
            ip=cfg.target_ip,
            mac=cfg.mac_address,
            timeout=cfg.ping_timeout,
            interval=cfg.ping_interval,
            tcp_fallback_port=cfg.tcp_fallback_port,
            callback=on_wake_completed
        )

    return {"status": "success", "message": msg}


@app.post("/api/test-ping")
async def test_ping():
    cfg = load_config()
    if not cfg.target_ip:
        raise HTTPException(status_code=400, detail="טרם הוגדרה כתובת IP בהגדרות")

    is_online = await monitor.ping_host(cfg.target_ip, cfg.tcp_fallback_port, timeout_sec=2.0)
    return {
        "status": "success",
        "ip": cfg.target_ip,
        "is_online": is_online,
        "message": "המחשב מגיב ברשת (ONLINE)" if is_online else "אין תגובה מהמחשב (OFFLINE / Sleep)"
    }


@app.post("/api/test-telegram")
async def test_telegram(payload: TestTelegramRequest):
    cfg = load_config()
    token = payload.token or cfg.telegram_token
    chat_id = payload.chat_id or (cfg.get_allowed_ids()[0] if cfg.get_allowed_ids() else None)

    if not token:
        raise HTTPException(status_code=400, detail="לא סופק Telegram Bot Token לבדיקה")

    # Call Telegram getMe API
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            me_resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            me_data = me_resp.json()
            if not me_data.get("ok"):
                error_desc = me_data.get("description", "Token לא תקין")
                return JSONResponse(status_code=400, content={"status": "error", "message": f"שגיאת טלגרם: {error_desc}"})

            bot_user = me_data["result"]["username"]

            # If chat_id is provided, try sending a test message
            if chat_id:
                send_resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"🔔 **הודעת בדיקה משרת WOL!**\nהחיבור בין שרת ה-WOL לטלגרם תקין לחלוטין. הבוט: @{bot_user}",
                        "parse_mode": "Markdown"
                    }
                )
                send_data = send_resp.json()
                if not send_data.get("ok"):
                    send_err = send_data.get("description", "לא ניתן לשלוח הודעה ל-Chat ID זה")
                    return JSONResponse(status_code=400, content={
                        "status": "warning",
                        "message": f"הטוקן תקין (@{bot_user}), אך שליחת ההודעה נכשלה: {send_err}. ודא שפתחת שיחה עם הבוט ושלחת לו /start."
                    })

            return {
                "status": "success",
                "message": f"החיבור תקין! הבוט: @{bot_user}" + (f" ונשלחה הודעת בדיקה ל-Chat ID {chat_id}" if chat_id else " (לא צוין Chat ID לשליחת הודעת בדיקה).")
            }
        except httpx.RequestError as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"שגיאת רשת בחיבור לטלגרם: {str(e)}"})


@app.get("/api/logs")
async def get_logs():
    return {"logs": list(reversed(recent_logs))}
