import re
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # Private RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # Private RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Private
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]

def validate_safe_url(url_str: str) -> Tuple[bool, str]:
    """
    Validates that a URL is safe from SSRF attacks (no private or internal networks).
    """
    url_str = url_str.strip()
    if not url_str:
        return False, "URL cannot be empty"

    try:
        parsed = urlparse(url_str)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ["http", "https"]:
        return False, "Only HTTP and HTTPS URLs are allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must contain a valid hostname"

    # Block localhost explicitly
    if hostname.lower() in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
        return False, "Access to local network addresses is forbidden"

    try:
        # Resolve hostname to IP address
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)

            # Check against blocked networks
            for blocked_net in BLOCKED_IP_NETWORKS:
                if ip_obj in blocked_net:
                    return False, f"Access to private IP range ({ip_str}) is prohibited"
    except socket.gaierror:
        # If hostname can't be resolved, let yt-dlp handle or return error
        pass
    except Exception as e:
        return False, f"URL validation error: {str(e)}"

    return True, "URL is safe"

def sanitize_filename(name: str) -> str:
    """
    Removes dangerous characters from filenames to prevent directory traversal.
    """
    cleaned = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    return cleaned.strip('._') or "unnamed_file"
