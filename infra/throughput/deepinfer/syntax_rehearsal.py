"""CPU-only syntax rehearsal. Does not import, install or execute DeepInfer code."""
import argparse
import ast
import json
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or platform.system() != "Linux":
        raise SystemExit("Use an isolated Linux Python 3.12 environment")
    root = args.source.resolve(strict=True)
    python_files = sorted(root.rglob("*.py"))
    shell_files = sorted(root.rglob("*.sh"))
    for path in python_files+shell_files:
        if not path.resolve().is_relative_to(root):
            raise ValueError("Source symlink escapes checkout")
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in shell_files:
        subprocess.run(["bash", "-n"], input=path.read_text(encoding="utf-8"), text=True,
                       check=True, capture_output=True, timeout=10)
    print(json.dumps({"python": platform.python_version(), "python_files_parsed": len(python_files),
        "shell_files_parsed_after_lf_normalization": len(shell_files),
        "shell_files_with_windows_checkout_crlf": sum(b"\r\n" in path.read_bytes() for path in shell_files),
        "deepinfer_code_imported": False, "native_cuda_build_performed": False,
        "gpu_execution_performed": False}))


if __name__ == "__main__":
    main()
