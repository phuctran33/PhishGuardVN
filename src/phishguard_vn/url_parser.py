from dataclasses import dataclass
import re
from urllib.parse import urlparse
import tldextract

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

def parse_url(raw_url: str) -> ParsedURL:
    """Xử lý URL thiếu scheme, bóc tách bằng Public Suffix List, lấy port và IP."""
    if not isinstance(raw_url, str):
        raw_url = ""
    raw_url_stripped = raw_url.strip()
    
    # Kiểm tra scheme
    has_scheme = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", raw_url_stripped))
    working_url = raw_url_stripped if has_scheme else "http://" + raw_url_stripped
    
    try:
        parsed = urlparse(working_url)
        ext = tldextract.extract(working_url)
        
        hostname = (f"{ext.subdomain}.{ext.registered_domain}" if ext.subdomain else ext.registered_domain).lower()
        if not hostname: 
            hostname = parsed.netloc.split(":")[0].lower()
            
        return ParsedURL(
            raw_url=raw_url_stripped,
            hostname=hostname,
            registrable_domain=ext.registered_domain.lower(),
            subdomain=ext.subdomain.lower(),
            path=parsed.path,
            query=parsed.query,
            port=parsed.port,
            scheme_was_added=not has_scheme
        )
    except Exception:
        # Trường hợp input không hợp lệ
        return ParsedURL(
            raw_url=raw_url_stripped, hostname="", registrable_domain="", 
            subdomain="", path="", query="", port=None, scheme_was_added=not has_scheme
        )