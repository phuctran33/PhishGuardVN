#!/usr/bin/env bash
# Chép các file nguồn (single source of truth) vào mobile/app/assets/ để Flutter đóng gói.
# Gồm: PSL, brand reference, file parity E2, và Teacher v2 (hai JSON runtime + manifest).
# KHÔNG chép svm_vocabulary.json và teacher_numeric.npz vì runtime Dart không đọc chúng.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DST="$ROOT/mobile/app/assets"
mkdir -p "$DST"

PSL="$ROOT/mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"
BRAND="$ROOT/src/phishguard_vn/resources/brand_reference_v1.csv"
PARITY="$ROOT/docs/mobile_parity_cases.json"
EXTRA="$ROOT/docs/mobile_parity_cases_extra.json"

TEACHER_DIR="$ROOT/artifacts/teacher_v2_android"
TEACHER_MANIFEST="$TEACHER_DIR/manifest.json"
TEACHER_SVM="$TEACHER_DIR/dart_svm_model.json"
TEACHER_MODEL="$TEACHER_DIR/dart_teacher_v2_model.json"

for f in "$PSL" "$BRAND" "$PARITY" "$TEACHER_MANIFEST" "$TEACHER_SVM" "$TEACHER_MODEL"; do
  [ -f "$f" ] || { echo "THIẾU: $f" >&2; exit 1; }
done

for f in "$PSL" "$BRAND" "$PARITY" "$TEACHER_SVM" "$TEACHER_MODEL"; do
  cp "$f" "$DST/"
done
cp "$TEACHER_MANIFEST" "$DST/teacher_v2_manifest.json"
if [ -f "$EXTRA" ]; then cp "$EXTRA" "$DST/"; else echo "(không có mobile_parity_cases_extra.json, bỏ qua)"; fi

echo "Đã chép vào $DST:"
ls -1 "$DST"
echo "brand_reference sha256: $(shasum -a 256 "$DST/brand_reference_v1.csv" | cut -d' ' -f1)"

# Kiểm kích thước và SHA-256 của hai JSON Teacher với manifest (trên bytes thô), lệch thì dừng.
python3 - "$DST/teacher_v2_manifest.json" "$DST" <<'PY'
import hashlib, json, pathlib, sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
dst = pathlib.Path(sys.argv[2])
bad = 0
for name in ("dart_svm_model.json", "dart_teacher_v2_model.json"):
    data = (dst / name).read_bytes()
    want = manifest["files"][name]
    ok = len(data) == want["size_bytes"] and hashlib.sha256(data).hexdigest() == want["sha256"]
    print(("Teacher OK    " if ok else "Teacher LỆCH  ") + name)
    bad += 0 if ok else 1
sys.exit(1 if bad else 0)
PY
