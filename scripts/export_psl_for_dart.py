# scripts/export_psl_for_dart.py
import hashlib, tldextract
ex = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=False)
tlds = sorted(ex._get_tld_extractor().tlds())  # chỉ ICANN vì include_psl_private_domains=False
text = "\n".join(tlds) + "\n"
open("psl_icann_tldextract_5.4.0.txt", "w", encoding="utf-8").write(text)
print("tldextract", tldextract.__version__ if hasattr(tldextract, "__version__") else "?")
print("n =", len(tlds), "| wildcard:", sum(t.startswith("*") for t in tlds),
      "| exception:", sum(t.startswith("!") for t in tlds))
print("sha256 =", hashlib.sha256(text.encode()).hexdigest())
print([t for t in tlds if t in ("com", "vn", "com.vn", "co.uk", "gov.vn", "weebly.com")])