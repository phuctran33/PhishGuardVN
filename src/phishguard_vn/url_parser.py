"""TODO(Hy): URL-only parsing; do not fetch destination websites."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedURL:
    raw_url: str
    hostname: str
    registrable_domain: str
    subdomain: str
    path: str
    query: str
    port: int | None
    scheme_was_added: bool


def parse_url(raw_url: str) -> ParsedURL:
    """TODO: handle missing scheme, PSL domains, IP, @, ports and IDN.

    Preserve raw input and path/query case. Define invalid-input behavior and
    the Public Suffix List snapshot/private-suffix settings used by the team.
    """
    raise NotImplementedError("TODO(Hy): implement parse_url.")
