"""Parser URL cho PhishGuardVN.

Quy ước chính
- Khóa nhóm (registrable_domain) được tạo từ host đã chuẩn hóa: chữ thường, bỏ dấu chấm cuối,
  IDN -> Punycode (IDNA/UTS46), IP -> dạng rút gọn chuẩn. Các cách viết khác nhau của cùng
  một host cho cùng một khóa.
- PSL: dùng snapshot đóng gói sẵn trong gói tldextract (không tải mạng, không cache đĩa).
  Muốn tái lập giữa các máy phải ghim đúng phiên bản tldextract trong requirements.txt.
- Dùng urlsplit (không phải urlparse) để không mất phần ';params' của path.
- Đầu vào lỗi không bị biến thành URL "hợp lệ": is_valid=False kèm error_reason để truy vết.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from importlib.metadata import version
from urllib.parse import urlsplit

import idna
import tldextract

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
# scheme (nếu có) hoặc "//" đầu chuỗi: dùng để tính các feature trên URL đã bỏ scheme
SCHEME_STRIP_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//")

# False: khớp vn_compphish.csv, ví dụ *.vercel.app -> vercel.app (một nhóm trong Group CV).
INCLUDE_PSL_PRIVATE_DOMAINS = False
TLDEXTRACT_VERSION = version("tldextract")  # phiên bản này quyết định snapshot PSL

_EXTRACT = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),  # không tải PSL từ mạng; dùng snapshot trong gói
    include_psl_private_domains=INCLUDE_PSL_PRIVATE_DOMAINS,
)


@dataclass(frozen=True)
class ParsedURL:
    raw_url: str
    hostname: str = ""  # host đã chuẩn hóa (Punycode / IP rút gọn) khi parse được
    registrable_domain: str | None = None
    subdomain: str = ""
    path: str = ""
    query: str = ""
    port: int | None = None
    scheme_was_added: bool = False
    is_ip: bool = False
    is_valid: bool = False
    error_reason: str | None = None


def normalize_host(host: str) -> tuple[str, bool]:
    """Trả về (host_chuẩn_hóa, is_ip). Ném UnicodeError nếu IDN không hợp lệ."""
    host = host.strip("[]").rstrip(".")
    try:
        return ipaddress.ip_address(host).compressed, True
    except ValueError:
        pass
    if host.isascii():
        # Không chạy IDNA cho host ASCII: IDNA2008 từ chối '_' mà URL phishing hay dùng.
        return host.lower(), False
    return idna.encode(host, uts46=True).decode("ascii").lower(), False


def parse_url(raw_url: str | None) -> ParsedURL:
    if not isinstance(raw_url, str):
        return ParsedURL("", error_reason="missing_url")
    stripped = raw_url.strip()
    if not stripped:
        return ParsedURL("", error_reason="empty_url")

    if SCHEME_RE.match(stripped):
        working, added = stripped, False
    elif stripped.startswith("//"):  # scheme-relative: //example.com/x
        working, added = "http:" + stripped, True
    else:
        working, added = "http://" + stripped, True

    try:
        parts = urlsplit(working)
        raw_host = parts.hostname
        base = {
            "raw_url": stripped,
            "path": parts.path,
            "query": parts.query,
            "scheme_was_added": added,
        }

        try:
            port = parts.port
        except ValueError:
            return ParsedURL(**base, hostname=raw_host or "", error_reason="invalid_port")

        if not raw_host or any(ch.isspace() for ch in raw_host):
            return ParsedURL(**base, hostname=raw_host or "", port=port,
                             error_reason="invalid_hostname")

        try:
            host, is_ip = normalize_host(raw_host)
        except UnicodeError:
            return ParsedURL(**base, hostname=raw_host, port=port,
                             error_reason="invalid_hostname")

        if is_ip:
            return ParsedURL(**base, hostname=host, port=port, is_ip=True, is_valid=True,
                             error_reason="is_ip_no_domain")

        ext = _EXTRACT(host)
        subdomain = ext.subdomain.lower() if ext.subdomain else ""
        reg_domain = ext.registered_domain.lower() if ext.registered_domain else None
        if not reg_domain:
            return ParsedURL(**base, hostname=host, subdomain=subdomain, port=port,
                             error_reason="unresolved_domain")

        return ParsedURL(**base, hostname=host, registrable_domain=reg_domain,
                         subdomain=subdomain, port=port, is_valid=True)

    except Exception as exc:  # urlsplit có thể ném ValueError (vd. IPv6 thiếu ']')
        return ParsedURL(stripped, scheme_was_added=added,
                         error_reason=f"parsing_error:{type(exc).__name__}")