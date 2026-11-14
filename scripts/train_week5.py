r"""Chạy notebook ML tuần 5 bằng đúng Python đang gọi script.

Code train ở notebook 05_advanced_models (lexical) hoặc 05_e2_ablation; script chỉ thực thi notebook đã chọn.
Chạy E1: .\.venv\Scripts\python.exe scripts/train_week5.py
Chạy ablation: .\.venv\Scripts\python.exe scripts/train_week5.py --ablation
"""
from pathlib import Path
import argparse
import json
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation", action="store_true", help="Chạy 05_e2_ablation; mặc định chạy 05_advanced_models")
    args = parser.parse_args()
    filename = "05_e2_ablation.ipynb" if args.ablation else "05_advanced_models.ipynb"
    path = root / "notebooks" / filename
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name="python3")
    # Dùng .venv hiện tại, không phụ thuộc kernel đã đăng ký trên máy khác.
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    client = NotebookClient(notebook, km=manager, timeout=600,
                            resources={"metadata": {"path": str(root)}},
                            on_cell_start=lambda cell, cell_index: print(f"Cell {cell_index+1}", flush=True))
    try:
        client.execute()
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    nbformat.write(notebook, path)
    if args.ablation:
        metadata = json.loads((root / "reports/tables/06_ablation_metadata.json").read_text(encoding="utf-8"))
        print("Đã chạy ablation. Shortlist:", metadata["teacher_candidates"])
        print("Bàn giao: ba file 06_*predictions.csv.gz và 06_training_partitions.csv.gz trong reports/tables/")
    else:
        metadata = json.loads((root / "reports/tables/05_readable_metadata.json").read_text(encoding="utf-8"))
        print("Đã chạy notebook v2. Ứng viên lexical-only:", metadata["selected_model"])
        print("Xem reports/tables/05_readable_comparison.csv và reports/week5_readable.md")


if __name__ == "__main__":
    main()
