#!/usr/bin/env python
"""Y5.2: điền verdict theo NHÓM, kiểm tra lại sau khi sửa reference, và sinh regression test.

    python scripts/05_audit_decisions.py apply     # điền verdict/note vào audit CSV từ file quyết định
    python scripts/05_audit_decisions.py check     # sau khi sửa reference: cờ false_match đã mất, cờ correct_flag còn không?
    python scripts/05_audit_decisions.py tests     # sinh tests/test_brand_regressions.py từ các verdict

File quyết định (reports/tables/05_gov_edu_audit_decisions.csv), mỗi dòng một NHÓM ca cùng nguyên nhân:
    rule,brand_id,key,domain_pattern,verdict,note
    - rule: brand_domain_mismatch | brand_typo_score
    - brand_id, key: để trống = mọi giá trị
    - domain_pattern: biểu thức chính quy áp lên registrable_domain, để trống = mọi domain
    - verdict: correct_flag | false_match | missing_official_domain | unresolved
    - note: BẮT BUỘC, ghi bằng chứng và nguồn (không ghi 'ok')
Dòng đầu tiên khớp thì thắng, nên đặt dòng cụ thể lên trước dòng chung.
Không miễn trừ cả .gov.vn/.edu.vn: mỗi quyết định gắn với một rule, một brand và (nếu có) một nguồn xác minh.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn.brand_features import REFERENCE_PATH, explain_brand_matches, load_reference  # noqa: E402

FLAG_RULES = {"brand_domain_mismatch", "brand_typo_score"}
ALLOWED = {"correct_flag", "false_match", "missing_official_domain", "unresolved"}
FIXED = {"false_match", "missing_official_domain"}  # sau khi sửa reference/logic, cờ này phải biến mất


def read_audit(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_decisions(path: Path) -> list[dict]:
    rows = pd.read_csv(path, dtype=str, keep_default_na=False).to_dict("records")
    errors = []
    for n, d in enumerate(rows, start=2):
        if d["rule"] not in FLAG_RULES:
            errors.append(f"dòng {n}: rule phải là một trong {sorted(FLAG_RULES)}")
        if d["verdict"] not in ALLOWED:
            errors.append(f"dòng {n}: verdict phải là một trong {sorted(ALLOWED)}")
        if len(d["note"].strip()) < 10:
            errors.append(f"dòng {n}: note quá ngắn, ghi bằng chứng/nguồn")
        try:
            re.compile(d["domain_pattern"])
        except re.error as exc:
            errors.append(f"dòng {n}: domain_pattern không hợp lệ ({exc})")
    if errors:
        sys.exit("LỖI file quyết định:\n  " + "\n  ".join(errors))
    return rows


def matches(d: dict, row: pd.Series) -> bool:
    return (d["rule"] == row["rule"] and d["brand_id"] in ("", row["brand_id"]) and d["key"] in ("", row["key"])
            and re.search(d["domain_pattern"], row["registrable_domain"]) is not None)


def cmd_apply(args) -> int:
    audit, decisions = read_audit(args.audit), load_decisions(args.decisions)
    unmatched = []
    for i, row in audit.iterrows():
        if row["rule"] not in FLAG_RULES or (row["verdict"] and not args.overwrite):
            continue
        hit = next((d for d in decisions if matches(d, row)), None)
        if hit is None:
            unmatched.append(i)
        else:
            audit.at[i, "verdict"], audit.at[i, "note"] = hit["verdict"], hit["note"]
    flag_rows = audit[audit["rule"].isin(FLAG_RULES)]
    per_url = flag_rows.groupby("id")["verdict"].agg(lambda s: {v for v in s if v})
    for i, row in audit.iterrows():  # dòng hỗ trợ (brand_in_*, ...) thừa hưởng verdict của URL nếu thống nhất
        if row["rule"] in FLAG_RULES or (row["verdict"] and not args.overwrite):
            continue
        verdicts = per_url.get(row["id"], set())
        if len(verdicts) == 1:
            audit.at[i, "verdict"], audit.at[i, "note"] = next(iter(verdicts)), "(thừa hưởng từ dòng cờ của cùng URL)"
        elif len(verdicts) > 1:
            audit.at[i, "verdict"], audit.at[i, "note"] = "mixed", "(các dòng cờ của URL có verdict khác nhau)"
    audit.to_csv(args.audit, index=False, lineterminator="\n")
    flags = audit[audit["rule"].isin(FLAG_RULES)]
    print(f"[apply] {len(flags)} dòng cờ; verdict:\n{flags['verdict'].replace('', '(trống)').value_counts().to_string()}")
    if unmatched:
        print(f"\n[CHƯA CÓ QUYẾT ĐỊNH] {len(unmatched)} dòng cờ không khớp nhóm nào, cần thêm dòng vào file quyết định:")
        print(audit.loc[unmatched, ["registrable_domain", "rule", "brand_id", "key", "text"]].drop_duplicates().to_string(index=False))
        return 1
    return 0


def cmd_check(args) -> int:
    ref = load_reference(args.reference)
    audit = read_audit(args.audit)
    flags = audit[audit["rule"].isin(FLAG_RULES) & (audit["verdict"] != "")]
    present_by_url: dict[str, set] = {}
    problems = []
    for url in flags["url"].unique():
        _, events = explain_brand_matches(url, ref)
        present_by_url[url] = {(e["rule"], e["brand_id"], e["key"]) for e in events}
    for _, row in flags.iterrows():
        still = (row["rule"], row["brand_id"], row["key"]) in present_by_url[row["url"]]
        if row["verdict"] in FIXED and still:
            problems.append(f"CÒN CỜ dù verdict={row['verdict']}: {row['registrable_domain']} [{row['rule']}/{row['brand_id']}/{row['key']}]")
        if row["verdict"] == "correct_flag" and not still:
            problems.append(f"CỜ ĐÚNG THIẾT KẾ NHƯNG ĐÃ MẤT (miễn trừ quá rộng?): {row['registrable_domain']} [{row['rule']}/{row['brand_id']}/{row['key']}]")
    pending = flags[flags["verdict"] == "unresolved"]
    print(f"[check] {len(flags)} dòng có verdict; unresolved: {len(pending)}")
    for p in sorted(set(problems)):
        print("  " + p)
    if not problems:
        print("[check] OK: mọi false_match/missing_official_domain đã hết cờ, mọi correct_flag vẫn còn cờ.")
    return 1 if problems else 0


def cmd_tests(args) -> int:
    audit = read_audit(args.audit)
    kinds = FIXED | ({"correct_flag"} if args.include_correct else set())
    rows = audit[audit["rule"].isin(FLAG_RULES) & audit["verdict"].isin(kinds)]
    cases = sorted({(r.verdict in FIXED, r.url, r.rule, r.brand_id, r.key) for r in rows.itertuples()})
    fixed = [c[1:] for c in cases if c[0]]
    kept = [c[1:] for c in cases if not c[0]]

    def fmt(items):
        return "[\n" + "".join(f"    {item!r},\n" for item in items) + "]"

    text = f'''"""Regression tests cho các false match đã xác nhận ở Y5.2.

SINH TỰ ĐỘNG bởi scripts/05_audit_decisions.py từ {args.audit.name}; đừng sửa tay, hãy đổi verdict rồi sinh lại.
Mỗi ca khẳng định ĐÚNG MỘT lý do (rule, brand_id, key) không còn xuất hiện, nên không phụ thuộc các cờ khác của cùng URL.
Chuỗi URL là chuỗi tĩnh (không truy cập mạng).
"""
import pytest

from phishguard_vn.brand_features import explain_brand_matches

CONFIRMED_FIXED = {fmt(fixed)}  # (url, rule, brand_id, key)
CONFIRMED_STILL_FLAGGED = {fmt(kept)}  # đối chứng: miễn trừ KHÔNG được lan sang các ca này


@pytest.mark.parametrize("url,rule,brand_id,key", CONFIRMED_FIXED)
def test_confirmed_false_match_is_not_flagged(url, rule, brand_id, key):
    _, events = explain_brand_matches(url)
    assert (rule, brand_id, key) not in {{(e["rule"], e["brand_id"], e["key"]) for e in events}}


@pytest.mark.parametrize("url,rule,brand_id,key", CONFIRMED_STILL_FLAGGED)
def test_correct_flags_are_still_flagged(url, rule, brand_id, key):
    _, events = explain_brand_matches(url)
    assert (rule, brand_id, key) in {{(e["rule"], e["brand_id"], e["key"]) for e in events}}
'''
    args.tests_out.parent.mkdir(parents=True, exist_ok=True)
    args.tests_out.write_text(text, encoding="utf-8")
    print(f"-> đã ghi {args.tests_out}: {len(fixed)} ca xác nhận false match, {len(kept)} ca đối chứng")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["apply", "check", "tests"])
    ap.add_argument("--audit", type=Path, default=ROOT / "reports/tables/05_gov_edu_brand_audit.csv")
    ap.add_argument("--decisions", type=Path, default=ROOT / "reports/tables/05_gov_edu_audit_decisions.csv")
    ap.add_argument("--reference", type=Path, default=REFERENCE_PATH)
    ap.add_argument("--tests-out", type=Path, default=ROOT / "tests/test_brand_regressions.py")
    ap.add_argument("--overwrite", action="store_true", help="apply: ghi đè cả verdict đã có")
    ap.add_argument("--include-correct", action="store_true", help="tests: thêm ca đối chứng correct_flag")
    args = ap.parse_args()
    return {"apply": cmd_apply, "check": cmd_check, "tests": cmd_tests}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
