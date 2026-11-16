#!/usr/bin/env bash
# Chép các file nguồn (single source of truth) vào mobile/app/assets/ để Flutter đóng gói.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DST="$ROOT/mobile/app/assets"
mkdir -p "$DST"

PSL="$ROOT/mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"
BRAND="$ROOT/src/phishguard_vn/resources/brand_reference_v1.csv"
PARITY="$ROOT/docs/mobile_parity_cases.json"
EXTRA="$ROOT/docs/mobile_parity_cases_extra.json"

for f in "$PSL" "$BRAND" "$PARITY"; do
  [ -f "$f" ] || { echo "THIẾU: $f" >&2; exit 1; }
  cp "$f" "$DST/"
done
if [ -f "$EXTRA" ]; then cp "$EXTRA" "$DST/"; else echo "(không có mobile_parity_cases_extra.json, bỏ qua)"; fi

echo "Đã chép vào $DST:"
ls -1 "$DST"
echo "brand_reference sha256: $(shasum -a 256 "$DST/brand_reference_v1.csv" | cut -d' ' -f1)"
