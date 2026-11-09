"""Chạy notebook tuần 6 bằng Python hiện tại; code train nằm trong notebook."""
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    path = root / "notebooks/06_teacher_v1.ipynb"
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    client = NotebookClient(notebook, km=manager, timeout=1200,
                            resources={"metadata": {"path": str(root)}},
                            on_cell_start=lambda cell, cell_index: print(f"Cell {cell_index + 1}", flush=True))
    try:
        client.execute()
    finally:
        # Lưu cả output nếu lỗi để biết cell nào dừng.
        nbformat.write(notebook, path)
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    print("Xong. Xem reports/tables/week6 và models/week6_teacher_v1.joblib")


if __name__ == "__main__":
    main()
