import re
import socket
from typing import Tuple
from app.config import add_log

def clean_mac(mac: str) -> str:
    """Sanitizes and returns standard MAC address format XX:XX:XX:XX:XX:XX."""
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', mac or "")
    if len(cleaned) != 12:
        raise ValueError(f"כתובת MAC לא תקינה: '{mac}'. חייבת להכיל 12 תווים הקסדצימליים.")
    return ":".join(cleaned[i:i+2].upper() for i in range(0, 12, 2))

def create_magic_packet(mac: str) -> bytes:
    """Builds a 102-byte Wake-on-LAN magic packet."""
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', mac)
    if len(cleaned) != 12:
        raise ValueError("Invalid MAC address length")
    mac_bytes = bytes.fromhex(cleaned)
    return b'\xff' * 6 + mac_bytes * 16

def send_wol_packet(mac: str, broadcast_ip: str = "255.255.255.255", port: int = 9) -> Tuple[bool, str]:
    """
    Sends Wake-on-LAN magic packet to specified MAC and broadcast address.
    Returns (success, message).
    """
    try:
        formatted_mac = clean_mac(mac)
        packet = create_magic_packet(formatted_mac)
        
        target_ip = (broadcast_ip or "255.255.255.255").strip()
        port = int(port or 9)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (target_ip, port))
            
        msg = f"אות Wake-on-LAN נשלח בהצלחה ל-MAC: {formatted_mac} דרך {target_ip}:{port}"
        add_log("INFO", msg)
        return True, msg
    except Exception as e:
        err_msg = f"שגיאה בשליחת פקט WOL: {str(e)}"
        add_log("ERROR", err_msg)
        return False, err_msg
