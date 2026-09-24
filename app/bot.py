import asyncio
import logging
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from app.config import AppConfig, load_config, add_log
from app.wol import send_wol_packet
from app.monitor import monitor

logger = logging.getLogger("WOLBot")

class TelegramBotManager:
    def __init__(self):
        self.application: Optional[Application] = None
        self.is_running: bool = False
        self.bot_status: str = "כבוי"
        self.bot_username: Optional[str] = None
        self._lock = asyncio.Lock()

    def _is_authorized(self, user_id: int, allowed_ids: List[int]) -> bool:
        if not allowed_ids:
            return False
        return user_id in allowed_ids

    def _get_main_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("⚡ הער את המחשב", callback_data="btn_wake"),
                InlineKeyboardButton("🔍 בדוק סטטוס", callback_data="btn_status")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return

        cfg = load_config()
        allowed_ids = cfg.get_allowed_ids()
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not allowed_ids:
            await update.effective_message.reply_text(
                f"👋 שלום {update.effective_user.first_name}!\n\n"
                f"⚠️ **הבוט מופעל אך עדיין לא הוגדרה רשימת מורשים.**\n\n"
                f"🆔 ה-Chat ID שלך הוא:\n`{chat_id}`\n\n"
                f"העתק מזהה זה והדבק אותו בממשק הניהול של השרת בשדה **Allowed Chat ID**.",
                parse_mode="Markdown"
            )
            return

        if not self._is_authorized(user_id, allowed_ids) and not self._is_authorized(chat_id, allowed_ids):
            await update.effective_message.reply_text(
                f"⛔ **גישה נדחתה**\nאינך מורשה להפעיל שרת זה.\n"
                f"🆔 ה-Chat ID שלך הוא: `{chat_id}`",
                parse_mode="Markdown"
            )
            return

        welcome_text = (
            f"👋 שלום {update.effective_user.first_name}!\n\n"
            "ברוך הבא למערכת ההדלקה מרחוק (Wake-on-LAN).\n\n"
            "📋 **פקודות זמינות:**\n"
            "⚡ `/wake` - שולח פקט התעוררות ומעדכן כשהמחשב עולה\n"
            "🔍 `/status` - בודק האם המחשב דולק כעת (Ping)\n"
            "ℹ️ `/help` - מציג הודעה זו\n\n"
            "באפשרותך גם ללחוץ על הכפתורים המהירים למטה:"
        )
        await update.effective_message.reply_text(
            welcome_text,
            reply_markup=self._get_main_keyboard(),
            parse_mode="Markdown"
        )

    async def _cmd_wake(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return

        cfg = load_config()
        allowed_ids = cfg.get_allowed_ids()
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if allowed_ids and not (self._is_authorized(user_id, allowed_ids) or self._is_authorized(chat_id, allowed_ids)):
            await update.effective_message.reply_text("⛔ אינך מורשה לבצע פעולה זו.")
            return

        if not cfg.mac_address:
            await update.effective_message.reply_text(
                "⚠️ **טרם הוגדרה כתובת MAC למחשב היעד.**\n"
                "אנא היכנס לממשק הניהול והזן את כתובת ה-MAC של כרטיס הרשת.",
                parse_mode="Markdown"
            )
            return

        # Send WOL packet
        success, msg = send_wol_packet(cfg.mac_address, cfg.broadcast_ip, cfg.wol_port)
        if not success:
            await update.effective_message.reply_text(f"❌ שגיאה בשליחת פקט ההתעוררות: {msg}")
            return

        resp_msg = (
            f"⚡ **אות Wake-on-LAN נשלח בהצלחה!**\n"
            f"🎯 כתובת MAC: `{cfg.mac_address}`\n"
        )

        if cfg.target_ip:
            resp_msg += (
                f"⏳ מאזין לרשת בכתובת `{cfg.target_ip}`...\n"
                f"אשלח לך הודעה ברגע שהמחשב יתעורר ויהיה זמין (עד {cfg.ping_timeout} שנ')."
            )
            await update.effective_message.reply_text(resp_msg, parse_mode="Markdown")

            # Define wake completion callback to notify the Telegram user
            async def on_wake_completed(is_online: bool, duration: float):
                try:
                    if is_online:
                        notification = (
                            f"🎉 **המחשב נדלק והתחבר לרשת בהצלחה!** 🟢\n\n"
                            f"⏱️ **זמן התעוררות:** {duration} שניות\n"
                            f"🌐 **IP:** `{cfg.target_ip}`"
                        )
                    else:
                        notification = (
                            f"⚠️ **זמן ההמתנה הסתיים ללא מענה**\n\n"
                            f"חלפו {cfg.ping_timeout} שניות והמחשב (`{cfg.target_ip}`) עדיין אינו מגיב ל-Ping.\n"
                            f"💡 ייתכן שהמחשב עדיין עולה, או שחומת האש (Windows Firewall) חוסמת פינגים."
                        )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=notification,
                        reply_markup=self._get_main_keyboard(),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    add_log("ERROR", f"שגיאה בשליחת התראה לטלגרם: {e}")

            monitor.start_wake_monitor_task(
                ip=cfg.target_ip,
                mac=cfg.mac_address,
                timeout=cfg.ping_timeout,
                interval=cfg.ping_interval,
                tcp_fallback_port=cfg.tcp_fallback_port,
                callback=on_wake_completed
            )
        else:
            resp_msg += "\n💡 *טיפ:* הגדר כתובת IP בממשק הניהול כדי לקבל הודעה כשהמחשב נדלק."
            await update.effective_message.reply_text(resp_msg, reply_markup=self._get_main_keyboard(), parse_mode="Markdown")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return

        cfg = load_config()
        allowed_ids = cfg.get_allowed_ids()
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if allowed_ids and not (self._is_authorized(user_id, allowed_ids) or self._is_authorized(chat_id, allowed_ids)):
            await update.effective_message.reply_text("⛔ אינך מורשה לבצע פעולה זו.")
            return

        if not cfg.target_ip:
            await update.effective_message.reply_text(
                "⚠️ **טרם הוגדרה כתובת IP לבדיקה.**\nאנא הגדר כתובת IP בממשק הניהול.",
                parse_mode="Markdown"
            )
            return

        status_msg = await update.effective_message.reply_text(
            f"🔍 בודק האם המחשב (`{cfg.target_ip}`) מגיב ברשת...",
            parse_mode="Markdown"
        )

        is_online = await monitor.ping_host(cfg.target_ip, cfg.tcp_fallback_port)
        if is_online:
            text = (
                f"🟢 **המחשב דולק ומגיב ברשת!**\n"
                f"🖥️ כתובת IP: `{cfg.target_ip}`\n"
                f"📟 כתובת MAC: `{cfg.mac_address or 'לא הוגדר'}`"
            )
        else:
            text = (
                f"🔴 **המחשב כבוי או במצב שינה.**\n"
                f"לא התקבלה תגובה מ-`{cfg.target_ip}`.\n\n"
                f"באפשרותך ללחוץ על 'הער את המחשב' כדי להדליקו."
            )

        await status_msg.edit_text(text, reply_markup=self._get_main_keyboard(), parse_mode="Markdown")

    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        if query.data == "btn_wake":
            await self._cmd_wake(update, context)
        elif query.data == "btn_status":
            await self._cmd_status(update, context)

    async def start(self):
        async with self._lock:
            cfg = load_config()
            token = (cfg.telegram_token or "").strip()

            if not token:
                self.bot_status = "לא הוגדר Token"
                self.is_running = False
                add_log("WARNING", "טלגרם בוט לא הופעל: טוקן חסר")
                return

            try:
                self.application = Application.builder().token(token).build()

                # Add handlers
                self.application.add_handler(CommandHandler("start", self._cmd_start))
                self.application.add_handler(CommandHandler("help", self._cmd_start))
                self.application.add_handler(CommandHandler("wake", self._cmd_wake))
                self.application.add_handler(CommandHandler("status", self._cmd_status))
                self.application.add_handler(CallbackQueryHandler(self._handle_callback_query))

                # Initialize and start polling
                await self.application.initialize()
                me = await self.application.bot.get_me()
                self.bot_username = me.username
                await self.application.start()
                await self.application.updater.start_polling(drop_pending_updates=True)

                self.is_running = True
                self.bot_status = f"מחובר כ-@{self.bot_username}"
                add_log("INFO", f"הבוט של טלגרם הופעל בהצלחה (@{self.bot_username})")

            except Exception as e:
                self.is_running = False
                self.bot_status = f"שגיאה: {str(e)}"
                add_log("ERROR", f"שגיאה בהפעלת בוט טלגרם: {e}")

    async def stop(self):
        async with self._lock:
            if self.application and self.is_running:
                try:
                    add_log("INFO", "עוצר את בוט הטלגרם...")
                    if self.application.updater and self.application.updater.running:
                        await self.application.updater.stop()
                    await self.application.stop()
                    await self.application.shutdown()
                except Exception as e:
                    add_log("ERROR", f"שגיאה בעצירת בוט טלגרם: {e}")
                finally:
                    self.application = None
                    self.is_running = False
                    self.bot_status = "כבוי"
                    self.bot_username = None

    async def restart(self):
        await self.stop()
        await self.start()

    async def send_notification_to_allowed(self, text: str) -> bool:
        """Sends a notification to all allowed chat IDs."""
        cfg = load_config()
        if not self.application or not self.is_running:
            return False
        allowed_ids = cfg.get_allowed_ids()
        if not allowed_ids:
            return False
        
        sent_any = False
        for chat_id in allowed_ids:
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )
                sent_any = True
            except Exception as e:
                add_log("ERROR", f"נכשלה שליחת הודעה ל-chat_id {chat_id}: {e}")
        return sent_any

bot_manager = TelegramBotManager()
