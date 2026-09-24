import re
import socket
import time
from typing import Tuple, Optional
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

def send_wol_packet(
    mac: str,
    broadcast_ip: str = "255.255.255.255",
    port: int = 9,
    target_ip: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Sends Wake-on-LAN magic packet to specified MAC address.
    Transmits across configured broadcast IP, global broadcast (255.255.255.255),
    and direct unicast target IP (if known) across ports 9 and 7 in repeated bursts.
    """
    try:
        formatted_mac = clean_mac(mac)
        packet = create_magic_packet(formatted_mac)
        
        # Collect destinations
        destinations = set()
        if broadcast_ip and broadcast_ip.strip():
            destinations.add(broadcast_ip.strip())
        destinations.add("255.255.255.255")
        
        if target_ip and target_ip.strip():
            destinations.add(target_ip.strip())

        # Collect ports (standard WOL ports 9 and 7)
        primary_port = int(port or 9)
        ports = [primary_port]
        if primary_port != 7:
            ports.append(7)
        if primary_port != 9 and 9 not in ports:
            ports.append(9)

        # Send packets using broadcast UDP socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Send 3 bursts spaced 40ms apart to prevent packet loss
            for _ in range(3):
                for dest in destinations:
                    for p in ports:
                        try:
                            sock.sendto(packet, (dest, p))
                        except Exception:
                            pass
                time.sleep(0.04)

        dest_str = ", ".join(destinations)
        msg = f"אות Wake-on-LAN שודר בהצלחה ל-MAC: {formatted_mac} אל ({dest_str}) בפורטים {ports}"
        add_log("INFO", msg)
        return True, msg
    except Exception as e:
        err_msg = f"שגיאה בשליחת פקט WOL: {str(e)}"
        add_log("ERROR", err_msg)
        return False, err_msg
