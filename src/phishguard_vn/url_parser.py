from dataclasses import dataclass
import re
from urllib.parse import urlparse
import tldextract
import ipaddress

@dataclass(frozen=True)
class ParsedURL:
    raw_url: str
    hostname: str
    registrable_domain: str | None
    subdomain: str
    path: str
    query: str
    port: int | None
    scheme_was_added: bool
    is_ip: bool
    is_valid: bool
    error_reason: str | None

def parse_url(raw_url: str | None) -> ParsedURL:
    if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
        return ParsedURL(str(raw_url), "", None, "", "", "", None, False, False, False, "empty_url")
    
    raw_url_stripped = raw_url.strip()
    has_scheme = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", raw_url_stripped))
    working_url = raw_url_stripped if has_scheme else "http://" + raw_url_stripped
    
    try:
        parsed = urlparse(working_url)
        hostname = parsed.hostname or ""
        
        port = None
        try:
            port = parsed.port
        except ValueError:
            return ParsedURL(raw_url_stripped, hostname, None, "", parsed.path, parsed.query, None, not has_scheme, False, False, "invalid_port")

        if not hostname or " " in hostname:
            return ParsedURL(raw_url_stripped, hostname, None, "", parsed.path, parsed.query, port, not has_scheme, False, False, "invalid_hostname")

        is_ip = False
        try:
            ip_str = hostname.strip("[]")
            if ip_str:
                ipaddress.ip_address(ip_str)
                is_ip = True
        except ValueError:
            pass

        ext = tldextract.extract(working_url)
        reg_domain = ext.registered_domain.lower() if ext.registered_domain else None
        subdomain = ext.subdomain.lower() if ext.subdomain else ""
        
        if is_ip:
            return ParsedURL(raw_url_stripped, hostname, None, subdomain, parsed.path, parsed.query, port, not has_scheme, True, True, "is_ip_no_domain")
        elif not reg_domain:
            return ParsedURL(raw_url_stripped, hostname, None, subdomain, parsed.path, parsed.query, port, not has_scheme, False, False, "unresolved_domain")
            
        return ParsedURL(raw_url_stripped, hostname, reg_domain, subdomain, parsed.path, parsed.query, port, not has_scheme, is_ip, True, None)

    except Exception as e:
        return ParsedURL(raw_url_stripped, "", None, "", "", "", None, not has_scheme, False, False, f"parsing_error")