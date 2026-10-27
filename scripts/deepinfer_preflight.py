"""Read-only source audit and native-token summary. No builds, downloads or GPU operations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from packages.common.deepinfer_measurement import NativeRun, summarize


def audit(root, lock):
    root = root.resolve(strict=True)
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(root), *args], text=True).strip()
    if git("rev-parse", "HEAD") != lock["commit"]:
        raise ValueError("DeepInfer checkout does not match pinned commit")
    if git("-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked source has local changes")
    crlf = []
    for name, expected in lock["files"].items():
        path = (root/name).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Source path escapes checkout")
        text = path.read_text(encoding="utf-8")  # Deliberately normalize Windows CRLF to LF.
        if hashlib.sha256(text.encode()).hexdigest() != expected:
            raise ValueError("Pinned source contract hash mismatch")
        if name.endswith(".sh") and b"\r\n" in path.read_bytes():
            crlf.append(name)
    initialized = {}
    for name, expected in lock["nvidia_submodules"].items():
        entry = git("ls-tree", "HEAD", "--", name).split()
        if len(entry) != 4 or entry[0] != "160000" or entry[2] != expected:
            raise ValueError("Vendor gitlink pin mismatch")
        folder = (root/name).resolve(strict=True)
        if not folder.is_relative_to(root):
            raise ValueError("Vendor path escapes checkout")
        initialized[name] = (folder/".git").exists()
    return {"source_commit": lock["commit"], "source_contract_passed": True,
            "contract_files_verified": len(lock["files"]), "vendor_pins_verified": len(initialized),
            "vendor_checkouts_initialized": initialized, "shell_contract_files_with_crlf": crlf,
            "requires_linux_lf_checkout": True, "python_syntax_checked": False,
            "native_cuda_build_verified": False, "model_downloaded": False, "gpu_execution_verified": False,
            "deployable": False,
            "limitations": "Source/gitlink audit only; not dependency resolution, CUDA compilation, native import or model execution."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    source = sub.add_parser("source")
    source.add_argument("--source", type=Path, required=True)
    source.add_argument("--lock", type=Path, default=Path("infra/throughput/deepinfer-source-lock.json"))
    source.add_argument("--output", type=Path, required=True)
    native = sub.add_parser("summarize-native")
    native.add_argument("--input", type=Path, required=True)
    native.add_argument("--output", type=Path, required=True)
    schema = sub.add_parser("native-schema")
    schema.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite retained evidence")
    if args.action == "source":
        report = audit(args.source, json.loads(args.lock.read_text(encoding="utf-8")))
    elif args.action == "native-schema":
        report = NativeRun.model_json_schema()
    else:
        if args.input.stat().st_size > 32*1024*1024:
            raise ValueError("Native event input exceeds 32 MiB")
        report = summarize(NativeRun.model_validate_json(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"written": str(args.output), "gpu_operation_performed": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit("DeepInfer preflight failed: "+type(error).__name__) from None
