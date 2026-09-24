// WOL & Telegram Controller Frontend Logic

let autoRefreshInterval = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  refreshStatus();
  fetchLogs();

  // Auto-refresh status and logs every 5 seconds
  autoRefreshInterval = setInterval(() => {
    refreshStatus();
    fetchLogs();
  }, 5000);
});

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `p-3.5 rounded-xl border text-sm shadow-xl flex items-center justify-between gap-3 transition-all duration-300 transform translate-y-2 pointer-events-auto ${
    type === "success" ? "bg-emerald-950/95 border-emerald-500/50 text-emerald-200" :
    type === "error" ? "bg-rose-950/95 border-rose-500/50 text-rose-200" :
    type === "warning" ? "bg-amber-950/95 border-amber-500/50 text-amber-200" :
    "bg-slate-900/95 border-slate-700 text-slate-200"
  }`;

  const icon = type === "success" ? "✅" : type === "error" ? "❌" : type === "warning" ? "⚠️" : "ℹ️";

  toast.innerHTML = `
    <div class="flex items-center gap-2.5">
      <span>${icon}</span>
      <span>${message}</span>
    </div>
    <button onclick="this.parentElement.remove()" class="text-xs opacity-60 hover:opacity-100">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.remove("translate-y-2");
    toast.classList.add("translate-y-0");
  }, 10);

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// Load current configuration from server
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("שגיאה בטעינת נתוני הגדרות");
    const data = await res.json();

    const fields = [
      "telegram_token", "allowed_chat_ids", "mac_address", "target_ip",
      "broadcast_ip", "wol_port", "ping_interval", "ping_timeout", "tcp_fallback_port"
    ];

    fields.forEach(field => {
      const input = document.getElementById(field);
      if (input && data[field] !== undefined && data[field] !== null) {
        input.value = data[field];
      }
    });

  } catch (err) {
    showToast(err.message, "error");
  }
}

// Save configuration
async function saveConfiguration(event) {
  event.preventDefault();
  const form = document.getElementById("configForm");
  const formData = new FormData(form);
  const payload = {};

  formData.forEach((val, key) => {
    if (["wol_port", "ping_interval", "ping_timeout", "tcp_fallback_port"].includes(key)) {
      payload[key] = parseInt(val, 10) || 0;
    } else {
      payload[key] = val;
    }
  });

  const btnSave = document.getElementById("btnSave");
  const originalHtml = btnSave.innerHTML;
  btnSave.disabled = true;
  btnSave.innerHTML = `<span>שומר...</span>`;

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || "שגיאה בשמירת ההגדרות");

    showToast(data.message || "ההגדרות נשמרו בהצלחה!", "success");
    setTimeout(() => {
      refreshStatus();
      fetchLogs();
    }, 1200);

  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btnSave.disabled = false;
    btnSave.innerHTML = originalHtml;
  }
}

// Refresh overall system and PC status
async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    // 1. PC Status
    const pcDot = document.getElementById("pcStatusDot");
    const pcLabel = document.getElementById("pcStatusLabel");
    const pcDetails = document.getElementById("pcStatusDetails");

    if (data.pc.target_ip) {
      pcDetails.textContent = `IP: ${data.pc.target_ip} | MAC: ${data.pc.mac_address || 'לא מוגדר'}`;
      if (data.pc.is_online === true) {
        pcDot.className = "inline-block w-3 h-3 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50";
        pcLabel.textContent = "דולק (Online)";
        pcLabel.className = "text-emerald-400 font-bold";
      } else if (data.pc.is_online === false) {
        pcDot.className = "inline-block w-3 h-3 rounded-full bg-rose-500 shadow-sm shadow-rose-500/50";
        pcLabel.textContent = "כבוי / שינה (Offline)";
        pcLabel.className = "text-rose-400 font-bold";
      } else {
        pcDot.className = "inline-block w-3 h-3 rounded-full bg-slate-500";
        pcLabel.textContent = "בודק...";
        pcLabel.className = "text-slate-400 font-bold";
      }
    } else {
      pcDot.className = "inline-block w-3 h-3 rounded-full bg-slate-600";
      pcLabel.textContent = "לא מוגדר";
      pcLabel.className = "text-slate-400 font-bold";
      pcDetails.textContent = "אנא הגדר כתובת IP ו-MAC";
    }

    // 2. Telegram Bot Status
    const botDot = document.getElementById("botStatusDot");
    const botLabel = document.getElementById("botStatusLabel");
    const botUserText = document.getElementById("botUsernameText");

    if (data.bot.is_running) {
      botDot.className = "inline-block w-3 h-3 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50";
      botLabel.textContent = "פעיל ומאזין";
      botLabel.className = "text-emerald-400 font-bold";
      botUserText.textContent = data.bot.username ? `@${data.bot.username}` : "מחובר";
    } else {
      botDot.className = "inline-block w-3 h-3 rounded-full bg-amber-500";
      botLabel.textContent = data.bot.status || "לא פעיל";
      botLabel.className = "text-amber-400 font-bold";
      botUserText.textContent = "הגדר Token להפעלה";
    }

    // 3. Monitor / Last wake info
    const lastWakeText = document.getElementById("lastWakeText");
    const lastWakeTime = document.getElementById("lastWakeTime");
    const lastWakeDuration = document.getElementById("lastWakeDuration");

    if (data.monitor.is_monitoring) {
      lastWakeText.innerHTML = `<span class="text-amber-400 flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>ממתין להתעוררות...</span>`;
      lastWakeTime.textContent = data.monitor.last_wake_attempt || "";
      lastWakeDuration.textContent = "";
    } else if (data.monitor.last_wake_status) {
      lastWakeText.textContent = data.monitor.last_wake_status;
      lastWakeTime.textContent = data.monitor.last_wake_attempt || "-";
      if (data.monitor.last_wake_duration) {
        lastWakeDuration.textContent = `(לקח ${data.monitor.last_wake_duration} שנ')`;
      } else {
        lastWakeDuration.textContent = "";
      }
    }

  } catch (err) {
    console.error("Status error:", err);
  }
}

// Trigger Wake-on-LAN directly from the Web UI
async function triggerWake() {
  const btn = document.getElementById("btnQuickWake");
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span>שולח...</span>`;

  try {
    const res = await fetch("/api/wake", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || "שליחת WOL נכשלה");

    showToast("אות Wake-on-LAN נשלח בהצלחה!", "success");
    refreshStatus();
    fetchLogs();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

// Test Ping host
async function testPingHost() {
  showToast("מבצע בדיקת פינג למחשב...", "info");
  try {
    const res = await fetch("/api/test-ping", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || "בדיקת פינג נכשלה");

    if (data.is_online) {
      showToast(`המחשב מגיב ברשת! (${data.ip})`, "success");
    } else {
      showToast(`אין תגובה מהמחשב (${data.ip}) - כבוי או במצב שינה`, "warning");
    }
    refreshStatus();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Test Telegram Bot Connection
async function testTelegramConnection() {
  const token = document.getElementById("telegram_token").value.trim();
  const chatId = document.getElementById("allowed_chat_ids").value.split(",")[0].trim();

  if (!token) {
    showToast("נא להזין Telegram Bot Token לפני הבדיקה", "warning");
    return;
  }

  showToast("בודק חיבור לשרתי טלגרם...", "info");
  try {
    const res = await fetch("/api/test-telegram", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token, chat_id: chatId })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.detail || "שגיאה בבדיקת טלגרם", data.status === "warning" ? "warning" : "error");
      return;
    }

    showToast(data.message, "success");
    refreshStatus();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Send test message directly
async function testTelegramMessage() {
  await testTelegramConnection();
}

// Fetch logs
async function fetchLogs() {
  const container = document.getElementById("logsContainer");
  if (!container) return;

  try {
    const res = await fetch("/api/logs");
    if (!res.ok) return;
    const data = await res.json();

    if (!data.logs || data.logs.length === 0) {
      container.innerHTML = `<div class="text-slate-600 text-center py-8">אין רשומות ביומן עדיין.</div>`;
      return;
    }

    container.innerHTML = data.logs.map(log => {
      let colorClass = "text-slate-400";
      if (log.level === "ERROR") colorClass = "text-rose-400";
      else if (log.level === "WARNING") colorClass = "text-amber-400";
      else if (log.level === "INFO") colorClass = "text-emerald-400";

      return `
        <div class="flex items-start gap-2 border-b border-slate-900/50 pb-1">
          <span class="text-slate-600 select-none text-[10px] whitespace-nowrap">${log.time}</span>
          <span class="${colorClass} font-semibold uppercase text-[10px] w-12 text-center select-none">[${log.level}]</span>
          <span class="text-slate-200 flex-1 break-words">${escapeHtml(log.message)}</span>
        </div>
      `;
    }).join("");

  } catch (err) {
    console.error("Error fetching logs:", err);
  }
}

// Helper: Escape HTML to prevent XSS
function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Toggle password visibility
function togglePasswordVisibility(fieldId) {
  const input = document.getElementById(fieldId);
  const btn = event.target;
  if (input.type === "password") {
    input.type = "text";
    btn.textContent = "הסתר";
  } else {
    input.type = "password";
    btn.textContent = "הצג";
  }
}
