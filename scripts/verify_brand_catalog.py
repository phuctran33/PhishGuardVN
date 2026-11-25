"""Validate the checked-in source snapshot and rebuild its checksum manifest on request."""

import argparse
import json

from phishguard_vn.brand_features import load_reference
from phishguard_vn.inspection_catalog import (
    CATALOG_PATH, CATALOG_VERSION, MANIFEST_PATH, load_catalog, read_catalog,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true",
                        help="Publish a manifest after adding independently sourced rows")
    args = parser.parse_args()
    if args.write_manifest:
        catalog = read_catalog(CATALOG_PATH.read_bytes())
        manifest = {
            "version": CATALOG_VERSION,
            "catalog_sha256": catalog.sha256,
            "reference_v1_sha256": load_reference().sha256,
            "counts": catalog.stats,
        }
        with MANIFEST_PATH.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(load_catalog().stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
