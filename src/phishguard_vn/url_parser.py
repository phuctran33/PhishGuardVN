from dataclasses import dataclass
import re
from urllib.parse import urlparse
import tldextract
import ipaddress

@dataclass(frozen=True)
class ParsedURL:
    raw_url: str
    hostname: str
    registrable_domain: str
    subdomain: str
    path: str
    query: str
    port: int | None
    scheme_was_added: bool
    is_ip: bool

def parse_url(raw_url: str) -> ParsedURL:
    """Xử lý URL thiếu scheme, bóc tách bằng PSL, bắt IPv4/IPv6 chuẩn và chống rỗng key."""
    if not isinstance(raw_url, str):
        raw_url = ""
    raw_url_stripped = raw_url.strip()
    
    has_scheme = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", raw_url_stripped))
    working_url = raw_url_stripped if has_scheme else "http://" + raw_url_stripped
    
    try:
        parsed = urlparse(working_url)
        # urlparse tự động xử lý ngoặc vuông của IPv6 và chuyển hostname thành chữ thường
        hostname = parsed.hostname or ""
        
        # 1. Nhận diện IP hợp lệ (IPv4 & IPv6)
        is_ip = False
        try:
            ip_str = hostname.strip("[]")
            ipaddress.ip_address(ip_str)
            is_ip = True
        except ValueError:
            pass

        # 2. Bóc tách bằng tldextract
        ext = tldextract.extract(working_url)
        reg_domain = ext.registered_domain.lower()
        subdomain = ext.subdomain.lower()
        
        # 3. Chống rỗng grouping key (Phòng ngừa Data Leakage khi Group CV)
        if is_ip:
            reg_domain = hostname  # Dùng luôn IP làm key chia nhóm
        elif not reg_domain:
            # Fallback cho các domain nội bộ (vd: .example) hoặc lỗi
            reg_domain = hostname if hostname else "UNKNOWN_DOMAIN"
            
        return ParsedURL(
            raw_url=raw_url_stripped,
            hostname=hostname,
            registrable_domain=reg_domain,
            subdomain=subdomain,
            path=parsed.path,
            query=parsed.query,
            port=parsed.port,
            scheme_was_added=not has_scheme,
            is_ip=is_ip
        )
    except Exception:
        return ParsedURL(
            raw_url=raw_url_stripped, hostname="", registrable_domain="ERROR_DOMAIN", 
            subdomain="", path="", query="", port=None, scheme_was_added=not has_scheme, is_ip=False
        )