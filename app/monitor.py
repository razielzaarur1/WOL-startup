import asyncio
import platform
import time
from typing import Callable, Optional, Dict, Any
from app.config import add_log

class HostMonitor:
    def __init__(self):
        self.is_monitoring: bool = False
        self.last_wake_attempt: Optional[str] = None
        self.last_wake_status: Optional[str] = None # "success", "timeout", "failed"
        self.last_wake_duration: Optional[float] = None
        self._current_task: Optional[asyncio.Task] = None

    async def ping_host(self, ip: str, tcp_fallback_port: int = 0, timeout_sec: float = 1.2) -> bool:
        """
        Tests if target host is reachable via ICMP ping or TCP port check.
        """
        if not ip or not ip.strip():
            return False

        target_ip = ip.strip()
        system = platform.system().lower()

        # 1. Try ICMP Ping
        try:
            if "windows" in system:
                cmd = ["ping", "-n", "1", "-w", str(int(timeout_sec * 1000)), target_ip]
            else: # Linux / Docker container / macOS
                cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_sec))), target_ip]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            returncode = await asyncio.wait_for(proc.wait(), timeout=timeout_sec + 1.0)
            if returncode == 0:
                return True
        except Exception:
            pass

        # 2. Try TCP probing (configured port and common Windows ports: 135, 445, 139, 3389)
        ports_to_try = []
        if tcp_fallback_port and tcp_fallback_port > 0:
            ports_to_try.append(tcp_fallback_port)
        for p in [135, 445, 139, 3389, 5357, 80]:
            if p not in ports_to_try:
                ports_to_try.append(p)

        for port in ports_to_try:
            try:
                fut = asyncio.open_connection(target_ip, port)
                _, writer = await asyncio.wait_for(fut, timeout=0.6)
                writer.close()
                await writer.wait_closed()
                return True
            except Exception:
                continue

        return False

    async def monitor_wake(
        self,
        ip: str,
        mac: str,
        timeout: int,
        interval: int,
        tcp_fallback_port: int,
        callback: Optional[Callable[[bool, float], Any]] = None
    ):
        """
        Monitors host until it comes online or timeout is reached.
        """
        self.is_monitoring = True
        self.last_wake_attempt = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_wake_status = "ממתין להתעוררות..."
        self.last_wake_duration = None

        start_time = time.time()
        add_log("INFO", f"החל מעקב התעוררות עבור {ip} (זמן מקסימלי: {timeout} שניות)")

        # Short initial delay before first ping (PC needs a few seconds to react to packet)
        await asyncio.sleep(2)

        try:
            while (time.time() - start_time) < timeout:
                is_online = await self.ping_host(ip, tcp_fallback_port)
                elapsed = round(time.time() - start_time, 1)

                if is_online:
                    self.last_wake_status = "המחשב נדלק בהצלחה"
                    self.last_wake_duration = elapsed
                    self.is_monitoring = False
                    add_log("INFO", f"✅ המחשב ({ip}) נדלק ומגיב ברשת! זמן התעוררות: {elapsed} שניות.")
                    if callback:
                        asyncio.create_task(self._safe_callback(callback, True, elapsed))
                    return

                await asyncio.sleep(interval)

            # Reached timeout
            elapsed = round(time.time() - start_time, 1)
            self.last_wake_status = f"פסק זמן ({timeout} שניות ללא מענה)"
            self.last_wake_duration = elapsed
            self.is_monitoring = False
            add_log("WARNING", f"⚠️ חלפו {timeout} שניות והמחשב ({ip}) עדיין לא מגיב ל-Ping.")
            if callback:
                asyncio.create_task(self._safe_callback(callback, False, elapsed))

        except asyncio.CancelledError:
            self.is_monitoring = False
            self.last_wake_status = "בוטל"
            add_log("INFO", "מעקב התעוררות בוטל")
        except Exception as e:
            self.is_monitoring = False
            self.last_wake_status = f"שגיאה: {str(e)}"
            add_log("ERROR", f"שגיאה במהלך מעקב התעוררות: {e}")

    async def _safe_callback(self, cb: Callable, success: bool, duration: float):
        try:
            res = cb(success, duration)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            add_log("ERROR", f"שגיאה בקריאת הפונקציה החוזרת (callback): {e}")

    def start_wake_monitor_task(
        self,
        ip: str,
        mac: str,
        timeout: int,
        interval: int,
        tcp_fallback_port: int,
        callback: Optional[Callable[[bool, float], Any]] = None
    ):
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        self._current_task = asyncio.create_task(
            self.monitor_wake(ip, mac, timeout, interval, tcp_fallback_port, callback)
        )

    def get_status_summary(self) -> Dict[str, Any]:
        return {
            "is_monitoring": self.is_monitoring,
            "last_wake_attempt": self.last_wake_attempt,
            "last_wake_status": self.last_wake_status,
            "last_wake_duration": self.last_wake_duration,
        }

monitor = HostMonitor()
