"""Offline hostname retrieval over a local catalogue of historical phishing cases."""

from dataclasses import dataclass
from difflib import SequenceMatcher
import ipaddress
import json
from pathlib import Path
import re

from sklearn.feature_extraction.text import TfidfVectorizer

from phishguard_vn.url_parser import parse_url


CORPUS_PATH = Path(__file__).with_name("resources") / "similar_cases_v1.json"
SCHEMA_VERSION = "similar-cases-host-v1"
MIN_SIMILARITY = 0.40
MAX_CASES = 5
DNS_HOST = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)+")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+")
IPV6_HOST = re.compile(r"[a-f0-9:]+")
VISIBLE_CHAR = re.compile(r"[a-z0-9]")


def supported_hostname(hostname: str) -> bool:
    if DNS_HOST.fullmatch(hostname):
        return True
    if ":" in hostname and IPV6_HOST.fullmatch(hostname):
        try:
            ipaddress.IPv6Address(hostname)
            return True
        except ValueError:
            pass
    return False


@dataclass(frozen=True)
class HistoricalCase:
    case_id: str
    hostname: str
    scheme: str
    source: str

    @property
    def display_url(self) -> str:
        prefix = f"hxxp{'s' if self.scheme == 'https' else ''}://"
        authority = f"[{self.hostname}]" if ":" in self.hostname else self.hostname.replace(".", "[.]")
        return prefix + authority

    def highlights(self, query_host: str) -> list[dict[str, int]]:
        # Leave the final DNS label out of the visual comparison. Common suffixes
        # should not be mistaken for a matching organization or host name.
        left = self.hostname.rsplit(".", 1)[0]
        right = query_host.rsplit(".", 1)[0]
        start = len(self.display_url.partition("://")[0]) + 3
        positions = [start + int(":" in self.hostname)]
        for char in left:
            positions.append(positions[-1] + (3 if char == "." else 1))
        ranges = []
        for match in SequenceMatcher(None, left, right, autojunk=False).get_matching_blocks():
            part = left[match.a:match.a + match.size]
            visible = part.strip(".-_:")
            if len(VISIBLE_CHAR.findall(visible)) < 4:
                continue
            first = match.a + len(part) - len(part.lstrip(".-_:"))
            ranges.append({"start": positions[first], "end": positions[first + len(visible)]})
        return ranges


class SimilarCasesIndex:
    """Fit the catalogue vectorizer once per process, then score by sparse dot product."""

    def __init__(self, cases: list[HistoricalCase]):
        self.cases = sorted(cases, key=lambda case: case.case_id)
        self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5),
                                          lowercase=False, norm="l2")
        self.matrix = self.vectorizer.fit_transform([case.hostname for case in self.cases])

    @classmethod
    def load(cls, path: Path):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema") != SCHEMA_VERSION:
            raise ValueError("Invalid similar cases schema")
        records = document.get("cases")
        if not isinstance(records, list) or not records:
            raise ValueError("Empty or invalid similar cases catalogue")
        cases = []
        ids, hosts = set(), set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Invalid similar case record")
            case = HistoricalCase(**record)
            if (not all(isinstance(field, str) for field in
                        (case.case_id, case.hostname, case.scheme, case.source))
                    or not IDENTIFIER.fullmatch(case.case_id)
                    or not IDENTIFIER.fullmatch(case.source)
                    or not supported_hostname(case.hostname)
                    or case.scheme not in {"http", "https"}
                    or case.case_id in ids or case.hostname in hosts):
                raise ValueError("Invalid or duplicated similar case")
            ids.add(case.case_id)
            hosts.add(case.hostname)
            cases.append(case)
        return cls(cases)

    def search(self, url: str) -> list[dict]:
        parsed = parse_url(url)
        if not parsed.is_valid or not supported_hostname(parsed.hostname):
            return []
        query = self.vectorizer.transform([parsed.hostname])
        scores = (self.matrix @ query.T).toarray().ravel()
        ranked = sorted(
            (i for i, score in enumerate(scores)
             if score >= MIN_SIMILARITY and self.cases[i].hostname != parsed.hostname),
            key=lambda i: (-scores[i], self.cases[i].case_id),
        )
        results = []
        for i in ranked:
            case = self.cases[i]
            highlights = case.highlights(parsed.hostname)
            if not highlights:
                continue
            results.append({
                "case_id": case.case_id,
                "display_url": case.display_url,
                "source": case.source,
                "cosine_similarity": min(1.0, float(scores[i])),
                "highlights": highlights,
            })
            if len(results) == MAX_CASES:
                break
        return results
