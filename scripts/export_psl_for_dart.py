
# scripts/export_psl_for_dart.py
import hashlib
from pathlib import Path

import tldextract

ex = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),
    include_psl_private_domains=False,
)
tlds = sorted(ex._get_tld_extractor().tlds())  # chỉ ICANN vì include_psl_private_domains=False
text = "\n".join(tlds) + "\n"

# Xuất trực tiếp vào assets chính thức của package Dart.
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(text, encoding="utf-8")

print("output =", OUT)
print("tldextract", tldextract.__version__ if hasattr(tldextract, "__version__") else "?")
print("n =", len(tlds), "| wildcard:", sum(t.startswith("*") for t in tlds),
      "| exception:", sum(t.startswith("!") for t in tlds))
print("sha256 =", hashlib.sha256(text.encode()).hexdigest())
print([t for t in tlds if t in ("com", "vn", "com.vn", "co.uk", "gov.vn", "weebly.com")])
