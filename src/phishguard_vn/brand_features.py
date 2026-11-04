"""Brand-aware features (schema E2 = 12 lexical E1 + 8 brand features).

Nguyên tắc
- Chỉ dùng chuỗi URL + brand reference đóng gói sẵn: tính được offline, không tra web/API.
- Dùng parser chính thức (url_parser.parse_url); không tự trích domain theo cách khác.
- Brand reference KHÔNG chứa nhãn và không được xây từ cột nhãn/source/impersonated_org của dataset.
- 12 cột E1 giữ nguyên tên, thứ tự, công thức (xem features.py); brand features chỉ được thêm vào sau.
- URL parse lỗi (is_valid=False) trả toàn None giống E1: dòng đó bị loại khỏi X và ghi vào excluded.
- Một nguồn logic duy nhất (_scan): cả features lẫn explain_brand_matches (dùng để audit) đều đi qua nó.
"""
from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

import idna
import pandas as pd

from phishguard_vn.features import CANDIDATE_FEATURES, extract_features_from_parsed
from phishguard_vn.url_parser import ParsedURL, parse_url

FEATURE_SCHEMA_VERSION = "e2-brand-v0"
REFERENCE_PATH = Path(__file__).resolve().parent / "resources" / "brand_reference_v1.csv"

BRAND_FEATURES = (
    "brand_in_domain",        # 0/1: brand trong nhãn domain đăng ký (SLD)
    "brand_in_subdomain",     # 0/1: brand trong subdomain
    "brand_in_path",          # 0/1: brand trong path/query
    "brand_domain_mismatch",  # 0/1: có brand nhưng domain đăng ký không thuộc brand đó
    "brand_typo_score",       # 0..1: độ gần của token domain/subdomain với tên brand (lỗi gõ)
    "susp_token_cnt",         # số từ khóa nhạy cảm khác nhau (login, xacminh, ...)
    "idna_flag",              # 0/1: có nhãn Punycode xn--
    "homoglyph_brand_hit",    # 0/1: brand chỉ khớp sau khi gộp ký tự dễ nhầm (0/o, 1/l/i, rn/m ...)
)
E2_FEATURES = CANDIDATE_FEATURES + BRAND_FEATURES

# --- Tham số công thức (đổi bất kỳ giá trị nào = đổi FEATURE_SCHEMA_VERSION) ---------------
MIN_ALIAS_LEN = 3        # alias < 3 ký tự bị từ chối khi nạp reference
SUBSTRING_MIN_LEN = 5    # key >= 5 ký tự: khớp chuỗi con; ngắn hơn: phải trùng nguyên token
TYPO_MIN_LEN = 5         # chỉ so lỗi gõ với token/key >= 5 ký tự
TYPO_MAX_DIST = 2        # khoảng cách chỉnh sửa tối đa
TYPO_MAX_RATIO = 0.25    # và d / len(key) <= 0.25 (heuristic ban đầu, chưa xác nhận tối ưu)

# Từ chung không được làm alias (xử lý va chạm tên). Bắt buộc phát hiện lúc nạp reference.
STOPLIST = frozenset({
    "bank", "ngan", "hang", "viet", "vietnam", "online", "mobile", "pay", "shop", "store",
    "app", "web", "www", "com", "net", "org", "gov", "vnn", "the", "and", "bao", "tin",
})

# Từ khóa nhạy cảm tổng quát (không lấy từ nhãn dataset). Không dấu, chữ thường.
SUSPICIOUS_TOKENS = (
    "login", "signin", "verify", "secure", "security", "account", "update", "confirm",
    "wallet", "otp", "bonus", "gift", "promo", "refund", "support", "helpdesk",
    "ebanking", "internetbanking", "payment", "billing",
    "dangnhap", "xacminh", "xacthuc", "taikhoan", "baomat", "capnhat", "khuyenmai",
    "uudai", "trungthuong", "nhanqua", "hoantien", "thanhtoan", "hotro",
)

CONFUSABLE_TABLE = {"0": "o", "1": "l", "i": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"}
CONFUSABLE_MULTI = (("rn", "m"), ("vv", "w"))  # áp dụng TRƯỚC bảng ký tự đơn
_CONFUSABLE_MAP = str.maketrans(CONFUSABLE_TABLE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


# --- Chuẩn hóa chuỗi -----------------------------------------------------------------------
def fold_text(text: str) -> str:
    """casefold + NFKD + bỏ dấu tổ hợp + đ -> d. 'Đăng Nhập' -> 'dang nhap'."""
    text = unicodedata.normalize("NFKD", text.casefold()).replace("đ", "d")
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def confusable_fold(text: str) -> str:
    """Gộp ký tự dễ nhầm; áp dụng đối xứng cho cả key brand lẫn chuỗi cần so."""
    for src, dst in CONFUSABLE_MULTI:
        text = text.replace(src, dst)
    return text.translate(_CONFUSABLE_MAP)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(fold_text(text))


def _decode_host(host: str) -> str:
    """Giải Punycode từng nhãn để so với tên brand Unicode; lỗi thì giữ nguyên nhãn."""
    labels = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = idna.decode(label)
            except (idna.IDNAError, UnicodeError):
                pass
        labels.append(label)
    return ".".join(labels)


@dataclass(frozen=True)
class _Zone:
    tokens: tuple[str, ...]
    joined: str
    cf_tokens: tuple[str, ...]
    cf_joined: str


def _make_zone(text: str) -> _Zone:
    toks = tuple(_tokens(text))
    cf = tuple(confusable_fold(t) for t in toks)
    return _Zone(toks, "".join(toks), cf, "".join(cf))


def _key_hit(key: str, tokens: tuple[str, ...], joined: str) -> bool:
    if len(key) >= SUBSTRING_MIN_LEN:
        return key in joined
    return key in tokens


@lru_cache(maxsize=262_144)
def _osa_distance(a: str, b: str) -> int:
    """Optimal string alignment (Levenshtein + hoán vị hai ký tự liền kề)."""
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)  # type: ignore[index]
        prev2, prev = prev, cur
    return prev[len(b)]


# --- Brand reference -------------------------------------------------------------------------
@dataclass(frozen=True)
class Brand:
    brand_id: str
    canonical_name: str
    official_domains: frozenset[str]
    keys: tuple[str, ...]      # đã fold, bỏ khoảng trắng
    cf_keys: tuple[str, ...]   # keys sau confusable_fold (song song với keys)
    # Tùy chọn, mặc định rỗng (không đổi hành vi). Chỉ điền sau khi rà soát từng ca và có nguồn xác minh:
    official_suffixes: tuple[str, ...] = ()   # vd. ('.gov.vn',): hit CỦA BRAND NÀY trên domain kết thúc như vậy không là mismatch
    typo_ignore: frozenset[str] = frozenset() # token đã xác nhận KHÔNG phải lỗi gõ của brand này (vd. địa danh)


@dataclass(frozen=True)
class BrandReference:
    brands: tuple[Brand, ...]
    all_keys: frozenset[str]
    all_official_domains: frozenset[str]
    sha256: str
    file_name: str
    statuses: tuple[tuple[str, int], ...]  # (status, số brand)
    n_missing_source_accessed: int
    n_missing_source_url: int

    @property
    def is_fully_verified(self) -> bool:
        """Điều kiện để freeze E2 v1: mọi brand verified và đủ provenance."""
        counts = dict(self.statuses)
        return (set(counts) == {"verified"} and self.n_missing_source_accessed == 0
                and self.n_missing_source_url == 0)

    def summary(self) -> dict:
        return {
            "file": self.file_name,
            "sha256": self.sha256,
            "n_brands": len(self.brands),
            "status_counts": dict(self.statuses),
            "n_missing_source_accessed": self.n_missing_source_accessed,
            "n_missing_source_url": self.n_missing_source_url,
            "fully_verified": self.is_fully_verified,
            "n_brands_with_official_suffixes": sum(1 for b in self.brands if b.official_suffixes),
            "n_brands_with_typo_ignore": sum(1 for b in self.brands if b.typo_ignore),
        }


def _split(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split("|") if v.strip()]


@lru_cache(maxsize=4)
def load_reference(path: Path = REFERENCE_PATH) -> BrandReference:
    path = Path(path)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    brands: list[Brand] = []
    seen_ids: set[str] = set()
    key_owner: dict[str, str] = {}
    for row in rows:
        bid = row["brand_id"].strip()
        if not bid or bid in seen_ids:
            raise ValueError(f"brand_id trống hoặc trùng: {bid!r}")
        seen_ids.add(bid)
        domains = frozenset(d.lower() for d in _split(row["official_domains"]))
        if not domains:
            raise ValueError(f"{bid}: thiếu official_domains")
        keys: list[str] = []
        for alias in [row["canonical_name"], *_split(row["aliases"])]:
            key = "".join(_tokens(alias))
            if len(key) < MIN_ALIAS_LEN:
                raise ValueError(f"{bid}: alias {alias!r} ngắn hơn {MIN_ALIAS_LEN} ký tự")
            if key in STOPLIST:
                raise ValueError(f"{bid}: alias {alias!r} nằm trong STOPLIST")
            if key in key_owner and key_owner[key] != bid:
                raise ValueError(f"alias {key!r} va chạm giữa {key_owner[key]} và {bid}")
            key_owner[key] = bid
            if key not in keys:
                keys.append(key)
        suffixes = tuple(x.lower() for x in _split(row.get("official_suffixes", "")))
        if any(not x.startswith(".") for x in suffixes):
            raise ValueError(f"{bid}: official_suffixes phải bắt đầu bằng '.'")
        ignore = frozenset("".join(_tokens(x)) for x in _split(row.get("typo_ignore_tokens", "")))
        brands.append(Brand(bid, row["canonical_name"].strip(), domains, tuple(keys),
                            tuple(confusable_fold(k) for k in keys), suffixes, ignore))
    counts: dict[str, int] = {}
    for row in rows:
        status = row["status"].strip()
        counts[status] = counts.get(status, 0) + 1
    return BrandReference(
        brands=tuple(brands),
        all_keys=frozenset(key_owner),
        all_official_domains=frozenset(d for b in brands for d in b.official_domains),
        sha256=sha,
        file_name=path.name,
        statuses=tuple(sorted(counts.items())),
        n_missing_source_accessed=sum(1 for r in rows if not r["source_accessed"].strip()),
        n_missing_source_url=sum(1 for r in rows if not r["source_url"].strip()),
    )


# --- Lõi logic (một nguồn duy nhất cho features và audit) -------------------------------------
def _first_hit(keys: tuple[str, ...], tokens: tuple[str, ...], joined: str) -> str | None:
    for key in keys:
        if _key_hit(key, tokens, joined):
            return key
    return None


def _scan(parsed: ParsedURL, ref: BrandReference, events: list[dict] | None = None) -> dict[str, float]:
    reg = parsed.registrable_domain  # None với URL là IP
    sld = _decode_host(reg).split(".")[0] if reg else ""
    sub = _decode_host(parsed.subdomain) if parsed.subdomain else ""
    zone_dom, zone_sub = _make_zone(sld), _make_zone(sub)
    zone_path = _make_zone(unquote(parsed.path) + " " + unquote(parsed.query))
    zones = (("domain", zone_dom), ("subdomain", zone_sub), ("path", zone_path))

    in_dom = in_sub = in_path = mismatch = homoglyph = 0
    typo = 0.0
    on_known_official = reg in ref.all_official_domains
    near_tokens = [t for t in (*zone_dom.tokens, *zone_sub.tokens)
                   if len(t) >= TYPO_MIN_LEN and t not in ref.all_keys]

    for brand in ref.brands:
        hits = {name: _first_hit(brand.keys, z.tokens, z.joined) for name, z in zones}
        hit_d, hit_s, hit_p = (hits[n] is not None for n in ("domain", "subdomain", "path"))
        in_dom |= hit_d
        in_sub |= hit_s
        in_path |= hit_p
        if events is not None:
            for name, key in hits.items():
                if key is not None:
                    events.append({"rule": f"brand_in_{name}", "brand_id": brand.brand_id, "key": key,
                                   "text": dict(zones)[name].joined, "value": 1.0})
        # Domain chính thức của BẤT KỲ brand nào không bị coi là mismatch (vd. viettelpost.vn
        # chứa key 'viettel' nhưng là domain chính thức của Viettel Post).
        brand_suffix_ok = bool(reg and brand.official_suffixes and reg.endswith(brand.official_suffixes))
        if (hit_d or hit_s or hit_p) and not on_known_official and reg not in brand.official_domains \
                and not brand_suffix_ok:
            mismatch = 1
            if events is not None:
                first = next(n for n in ("domain", "subdomain", "path") if hits[n] is not None)
                events.append({"rule": "brand_domain_mismatch", "brand_id": brand.brand_id,
                               "key": hits[first], "text": dict(zones)[first].joined, "value": 1.0})
        if on_known_official:
            continue  # domain chính thức của một brand: không xét lỗi gõ / homoglyph
        if not (hit_d or hit_s):
            cf = _first_hit(brand.cf_keys, zone_dom.cf_tokens, zone_dom.cf_joined) or \
                _first_hit(brand.cf_keys, zone_sub.cf_tokens, zone_sub.cf_joined)
            if cf is not None:
                homoglyph = 1
                if events is not None:
                    events.append({"rule": "homoglyph_brand_hit", "brand_id": brand.brand_id,
                                   "key": cf, "text": zone_dom.cf_joined + "|" + zone_sub.cf_joined, "value": 1.0})
        for token in near_tokens:
            if token in brand.typo_ignore:
                continue
            for key in brand.keys:
                if len(key) < TYPO_MIN_LEN or abs(len(token) - len(key)) > TYPO_MAX_DIST:
                    continue
                dist = _osa_distance(token, key)
                if 1 <= dist <= TYPO_MAX_DIST and dist / len(key) <= TYPO_MAX_RATIO:
                    score = 1.0 - dist / len(key)
                    typo = max(typo, score)
                    if events is not None:
                        events.append({"rule": "brand_typo_score", "brand_id": brand.brand_id, "key": key,
                                       "text": token, "value": score, "distance": dist})

    susp = 0
    for kw in SUSPICIOUS_TOKENS:
        if any(_key_hit(kw, z.tokens, z.joined) for _, z in zones):
            susp += 1
            if events is not None:
                events.append({"rule": "susp_token", "brand_id": "", "key": kw, "text": kw, "value": 1.0})
    idna_flag = any(label.startswith("xn--") for label in parsed.hostname.split("."))

    return {
        "brand_in_domain": float(in_dom),
        "brand_in_subdomain": float(in_sub),
        "brand_in_path": float(in_path),
        "brand_domain_mismatch": float(mismatch),
        "brand_typo_score": float(typo),
        "susp_token_cnt": float(susp),
        "idna_flag": 1.0 if idna_flag else 0.0,
        "homoglyph_brand_hit": float(homoglyph),
    }


# --- API công khai -------------------------------------------------------------------------------
def extract_brand_features_from_parsed(
    parsed: ParsedURL, reference: BrandReference | None = None
) -> dict[str, float | None]:
    if not parsed.is_valid:
        return {name: None for name in BRAND_FEATURES}
    return _scan(parsed, reference or load_reference())  # type: ignore[return-value]


def extract_brand_features(raw_url: str | None) -> dict[str, float | None]:
    return extract_brand_features_from_parsed(parse_url(raw_url))


def explain_brand_matches(raw_url: str | None, reference: BrandReference | None = None) -> tuple[dict, list[dict]]:
    """(features, events): mỗi event = một lý do khiến feature được bật (rule, brand_id, key, text).

    Dùng để rà soát false match / thiếu official domain; đi qua đúng _scan nên không lệch với features.
    """
    parsed = parse_url(raw_url)
    if not parsed.is_valid:
        return {name: None for name in BRAND_FEATURES}, []
    events: list[dict] = []
    feats = _scan(parsed, reference or load_reference(), events)
    return feats, events


def extract_e2_features(raw_url: str | None) -> dict[str, float | None]:
    """12 lexical E1 + 8 brand, đúng thứ tự E2_FEATURES; train và predict dùng chung hàm này."""
    parsed = parse_url(raw_url)
    merged = {**extract_features_from_parsed(parsed), **extract_brand_features_from_parsed(parsed)}
    return {name: merged[name] for name in E2_FEATURES}


def build_e2_feature_table(frame: pd.DataFrame, reference: BrandReference | None = None) -> pd.DataFrame:
    """Một dòng/URL: id + 20 features + metadata (registrable_domain, error_reason, is_valid).

    Chỉ đọc hai cột `id`, `url`: không có đường nào để nhãn/source/split lọt vào X.
    Tập dòng hợp lệ trùng đúng với E1 vì cùng một parse_url.
    """
    ref = reference or load_reference()
    records = []
    for row_id, url in zip(frame["id"], frame["url"]):
        parsed = parse_url(url if isinstance(url, str) else None)
        record = {**extract_features_from_parsed(parsed), **extract_brand_features_from_parsed(parsed, ref)}
        record["id"] = row_id
        record["registrable_domain"] = parsed.registrable_domain or pd.NA
        record["error_reason"] = parsed.error_reason
        record["is_valid"] = parsed.is_valid
        records.append(record)
    return pd.DataFrame(records)