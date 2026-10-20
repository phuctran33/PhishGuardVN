"""Read-only dataset/config check; no EDA or model training is performed."""
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from phishguard_vn.paths import get_config_path, get_data_dir, get_project_root


def main() -> int:
    root, data = get_project_root(), get_data_dir()
    print(f"Project: {root}")
    print(f"Dataset: {data}")
    with get_config_path().open("rb") as handle:
        config = tomllib.load(handle)
    print(f"Config: {config['experiment']['name']}")
    required = ["dataset_url.csv", "vn_compphish.csv", "abuse_type.csv",
                "splits/url_train.csv", "splits/url_val.csv", "splits/url_test.csv"]
    missing = []
    for name in required:
        present = (data / name).is_file()
        print(f"[{'OK' if present else 'MISSING'}] {name}")
        if not present:
            missing.append(name)
    print("Template only: implement TODO modules/notebooks before running experiments.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
