r"""Chạy notebook ML tuần 5 bằng đúng Python đang gọi script.

Code train chỉ nằm ở notebooks/05_advanced_models.ipynb để không có hai phiên bản.
Chạy: .\.venv\Scripts\python.exe scripts/train_week5.py
"""
from pathlib import Path
import json
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    path = root / "notebooks/05_advanced_models.ipynb"
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
    metadata = json.loads((root / "reports/tables/05_readable_metadata.json").read_text(encoding="utf-8"))
    print("Đã chạy notebook v2. Ứng viên lexical-only:", metadata["selected_model"])
    print("Xem reports/tables/05_readable_comparison.csv và reports/week5_readable.md")


if __name__ == "__main__":
    main()
