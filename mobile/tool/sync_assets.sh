#!/usr/bin/env bash
# Chép các file nguồn (single source of truth) vào mobile/app/assets/ để Flutter đóng gói.
# Gồm: PSL, brand reference, file parity E2, Teacher v2 (hai JSON runtime + manifest), và Student MLP (gzip + manifest).
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

# Student MLP artifacts:
# Ưu tiên artifacts đã có trong repo (sau khi PR #35 merge).
# Nếu chưa có, fallback sang PR #35 remote ref, không checkout/merge.
STUDENT_DIR="$ROOT/artifacts/student_mlp_android"
STUDENT_MANIFEST="$STUDENT_DIR/manifest.json"
STUDENT_MODEL="$STUDENT_DIR/student_mlp.json.gz"
STUDENT_REF="refs/remotes/pr/35"

if [ -f "$STUDENT_MANIFEST" ] && [ -f "$STUDENT_MODEL" ]; then
  echo "Student source: repo artifacts"

  cp "$STUDENT_MANIFEST" "$DST/student_mlp_manifest.json"
  cp "$STUDENT_MODEL" "$DST/student_mlp.json.gz"

else
  echo "Student artifacts chưa đầy đủ trong repo; thử fallback PR #35..."

  if ! git -C "$ROOT" show-ref --verify --quiet "$STUDENT_REF"; then
    echo "LỖI: Không có Student artifacts trong repo và không tìm thấy ref $STUDENT_REF." >&2
    echo "Sau khi PR #35 merge, hãy pull main để lấy artifacts." >&2
    echo "Nếu cần fallback PR #35, fetch ref bằng lệnh:" >&2
    echo "  git -C \"$ROOT\" fetch origin pull/35/head:refs/remotes/pr/35" >&2
    exit 1
  fi

  if ! git -C "$ROOT" cat-file -e \
    "$STUDENT_REF:artifacts/student_mlp_android/manifest.json" 2>/dev/null ||
     ! git -C "$ROOT" cat-file -e \
    "$STUDENT_REF:artifacts/student_mlp_android/student_mlp.json.gz" 2>/dev/null; then
    echo "LỖI: Ref $STUDENT_REF không chứa đủ Student artifacts." >&2
    exit 1
  fi

  git -C "$ROOT" show \
    "$STUDENT_REF:artifacts/student_mlp_android/manifest.json" \
    > "$DST/student_mlp_manifest.json"

  git -C "$ROOT" show \
    "$STUDENT_REF:artifacts/student_mlp_android/student_mlp.json.gz" \
    > "$DST/student_mlp.json.gz"
fi

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

# Kiểm kích thước và SHA-256 Student model gzip + PSL theo manifest.
python3 - "$DST/student_mlp_manifest.json" "$DST" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
dst = pathlib.Path(sys.argv[2])

files = {
    "student_mlp.json.gz": manifest["model"],
    "psl_icann_tldextract_5.4.0.txt": manifest["psl"],
}

bad = 0
for name, expected in files.items():
    data = (dst / name).read_bytes()
    size_ok = len(data) == expected["bytes"]
    sha_ok = hashlib.sha256(data).hexdigest() == expected["sha256"]
    ok = size_ok and sha_ok

    print(("Student OK    " if ok else "Student LỆCH  ") + name)
    if not size_ok:
        print(f"  size: {len(data)} != {expected['bytes']}")
    if not sha_ok:
        print(f"  sha256: {hashlib.sha256(data).hexdigest()}")
    bad += 0 if ok else 1

sys.exit(1 if bad else 0)
PY