import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from phishguard_vn.api import create_app
from phishguard_vn.similar_cases import CORPUS_PATH, SCHEMA_VERSION, SimilarCasesIndex, HistoricalCase


BUILDER = Path(__file__).resolve().parents[1] / "scripts/build_similar_cases.py"


def test_build_uses_only_train_core_and_deduplicates_hostnames(tmp_path):
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("build_similar_cases", BUILDER)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    path = tmp_path / "train.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["id", "url", "label", "tier", "split", "source"])
        writer.writerows([
            ("1", "https://alice:password@portal.example.org/login?secret=token#fragment",
             "phishing", "gold", "train", "feed"),
            ("2", "portal.example.org/another-path", "phishing", "silver", "train", "other"),
            ("3", "unsafe.example.org", "phishing", "bronze", "train", "other"),
            ("4", "benign.example.org", "benign", "gold", "train", "other"),
            ("5", "ftp://bad.example.org", "phishing", "gold", "train", "other"),
        ])
    corpus = module.build_catalogue(path)
    assert corpus["manifest"]["eligible_rows"] == 3
    assert corpus["manifest"]["invalid_or_unsupported_rows"] == 1
    assert corpus["manifest"]["duplicate_hostname_rows"] == 1
    assert corpus["manifest"]["queries_removed"] == 1
    assert corpus["manifest"]["cases"] == 1
    assert corpus["cases"] == [
        {"case_id": "1", "hostname": "portal.example.org", "scheme": "https", "source": "feed"}
    ]
    with path.open("a", encoding="utf-8") as file:
        file.write("6,offlimits.example.org,phishing,gold,val,other\n")
    with pytest.raises(ValueError, match="Train rows only"):
        module.build_catalogue(path)


@pytest.fixture
def catalogue(tmp_path):
    cases = [
        {"case_id": f"demo-{i}", "hostname": f"customer-support-{i}.example.org",
         "scheme": "https", "source": "synthetic"}
        for i in range(9)
    ]
    cases.append({"case_id": "unrelated", "hostname": "astronomy.example.net",
                  "scheme": "http", "source": "synthetic"})
    file = tmp_path / "catalogue.json"
    file.write_text(json.dumps({"schema": SCHEMA_VERSION, "cases": cases}), encoding="utf-8")
    return file


def test_api_contract_rank_limit_and_redacted_highlights(catalogue):
    with TestClient(create_app(similar_cases_path=catalogue)) as client:
        assert client.get("/health").json()["model_ready"] is False
        query = "https://name:secret@CUSTOMER-SUPPORT-0.EXAMPLE.ORG/user?token=private#fragment"
        response = client.post("/similar-cases", json={"url": query})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        cases = payload["cases"]
        assert len(cases) == 5
        assert all(row["case_id"] not in {"demo-0", "unrelated"} for row in cases)
        assert len({row["display_url"] for row in cases}) == len(cases)
        keys = [(-row["cosine_similarity"], row["case_id"]) for row in cases]
        assert keys == sorted(keys)
        assert 0 <= cases[-1]["cosine_similarity"] <= cases[0]["cosine_similarity"] <= 1
        for row in cases:
            url = row["display_url"]
            assert url.startswith("hxxps://customer-support-")
            assert url.endswith("[.]example[.]org")
            assert row["source"] == "synthetic"
            ranges = row["highlights"]
            assert ranges
            assert any("customer-support" in url[s["start"]:s["end"]] for s in ranges)
            previous_end = 0
            for s in ranges:
                assert previous_end <= s["start"] < s["end"] <= len(url)
                assert not url[s["start"]:s["end"]].startswith("hxxp")
                previous_end = s["end"]
        assert all(secret not in response.text for secret in ("@", "private", "fragment"))
        # Scheme, path, userinfo, fragment and query do not affect hostname ranking.
        assert client.post("/similar-cases", json={"url": "customer-support-0.example.org"}).json() == payload


def test_api_empty_and_invalid_url(catalogue):
    with TestClient(create_app(similar_cases_path=catalogue)) as client:
        empty = client.post("/similar-cases", json={"url": "qzjxkvw.com"})
        assert empty.status_code == 200
        assert empty.json() == {"status": "empty", "cases": []}
        wrong = client.post("/similar-cases", json={"url": "ftp://example.org/path"})
        assert wrong.status_code == 422
        assert wrong.json()["error"]["reason"] == "unsupported_scheme"
        assert client.post("/similar-cases", json={"url": "example.org", "limit": 50}).status_code == 422


@pytest.mark.parametrize("exists", [False, True])
def test_catalogue_failure_is_independent_from_inspection(tmp_path, exists):
    path = tmp_path / "corrupt.json"
    if exists:
        path.write_text("invalid document", encoding="utf-8")
    with TestClient(create_app(similar_cases_path=path)) as client:
        response = client.post("/similar-cases", json={"url": "example.org"})
        assert response.status_code == 503
        assert response.json()["error"]["reason"] == "catalogue_unavailable"
        assert str(path) not in response.text
        assert client.post("/inspect", json={"url": "example.org"}).status_code == 200


def test_normalized_idna_and_ipv6_display():
    index = SimilarCasesIndex([
        HistoricalCase("idna", "xn--bcher-kva.example.org", "https", "synthetic"),
        HistoricalCase("ipv6", "2001:db8:1234::1", "http", "synthetic"),
    ])
    idna = index.search("https://b\u00fccher.example.net")[0]
    assert idna["display_url"] == "hxxps://xn--bcher-kva[.]example[.]org"
    ip = index.search("http://[2001:db8:1234::2]")[0]
    assert ip["display_url"] == "hxxp://[2001:db8:1234::1]"
    assert all(ip["display_url"][span["start"]] != "[" for span in ip["highlights"])


def test_short_suffix_match_does_not_produce_a_case():
    index = SimilarCasesIndex([
        HistoricalCase("weak", "k88.com", "http", "synthetic"),
        HistoricalCase("other", "astronomy.example.org", "http", "synthetic"),
    ])
    assert float((index.matrix @ index.vectorizer.transform(["p88.com"]).T).toarray().max()) >= 0.40
    assert index.search("p88.com") == []


def test_release_catalogue_contains_only_supported_hostnames():
    catalogue = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    manifest = catalogue["manifest"]
    assert manifest["input_split"] == "train"
    assert sum(manifest["source_counts"].values()) == len(catalogue["cases"])
    assert manifest["eligible_rows"] == (
        manifest["cases"] + manifest["duplicate_hostname_rows"]
        + manifest["invalid_or_unsupported_rows"]
    )
    assert len(SimilarCasesIndex.load(CORPUS_PATH).cases) == manifest["cases"]
