#!/usr/bin/env python3
"""Check that this machine can run the carbon-placement-advisor pipeline.

Prints one PASS / FAIL / WARN line per check and exits 0 only if nothing FAILED.
It makes no network calls and starts no service. For HuggingFace it only learns
whether a login exists (yes / no). It never prints, logs or stores the token.

Exit codes: 0 ready, 1 at least one check failed.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import sys
from pathlib import Path

WEIGHTS_REPO = "facebook/sam3"
WEIGHTS_FILE = "config.json"
MIN_FREE_GB = 6.0  # weights are about 5 GB; leave a margin
REQUIRED_MODULES = ["torch", "torchvision", "PIL", "numpy", "sam3", "sam3_mac", "huggingface_hub"]
SKILL_ROOT = Path(__file__).resolve().parent.parent

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str) -> None:
    results.append((status, name, detail))
    print(f"{status:<5} {name}: {detail}")


def check_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) == (3, 12):
        record("PASS", "python", f"{v.major}.{v.minor}.{v.micro}")
    elif (v.major, v.minor) >= (3, 10):
        record("WARN", "python", f"{v.major}.{v.minor} works but SAM 3 officially targets 3.12")
    else:
        record("FAIL", "python", f"{v.major}.{v.minor} is too old. Use Python 3.12")


def check_modules() -> None:
    for mod in REQUIRED_MODULES:
        try:
            if mod == "sam3":
                # `import sam3` needs triton, which does not exist on macOS; sam3_mac.install()
                # supplies a stand-in at run time. So only check that the package is installed.
                importlib.metadata.version("sam3")
            else:
                importlib.import_module(mod)
            record("PASS", f"import {mod}", "ok")
        except Exception as exc:  # noqa: BLE001 - report the type only, not the message
            record("FAIL", f"import {mod}", f"{type(exc).__name__}. Re-run the install steps in README.md")


def check_sam3_loads() -> None:
    """Run the same setup path the pipeline uses, without loading the 3.5 GB weights."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from common import ensure_pkg_resources

        ensure_pkg_resources()
        import sam3_mac

        sam3_mac.install(None)
        import sam3  # noqa: F401  (works only after install())

        record("PASS", "sam3 setup", "sam3_mac.install() succeeded and sam3 imports")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "sam3 setup", f"{type(exc).__name__}. Re-run the install steps in README.md")


def check_device() -> None:
    try:
        import torch

        if torch.backends.mps.is_available():
            record("PASS", "device", "Apple MPS available")
        else:
            record("WARN", "device", "MPS not available. CPU will be used and will be slow")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "device", f"could not query torch ({type(exc).__name__})")


def check_weights() -> None:
    try:
        from huggingface_hub import get_token, try_to_load_from_cache

        cached = try_to_load_from_cache(WEIGHTS_REPO, WEIGHTS_FILE)
        if isinstance(cached, str):
            record("PASS", "sam3 weights", "found in the local HuggingFace cache")
            return
        logged_in = get_token() is not None  # boolean only; the value is never used
        if logged_in:
            record("WARN", "sam3 weights", "not cached yet. The first run downloads about 5 GB over HTTPS")
        else:
            record(
                "FAIL",
                "sam3 weights",
                "not cached and no HuggingFace login found. Request access to facebook/sam3, "
                "then run `hf auth login` yourself",
            )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "sam3 weights", f"could not check ({type(exc).__name__})")


def check_disk() -> None:
    free_gb = shutil.disk_usage(Path.home()).free / 1e9
    if free_gb >= MIN_FREE_GB:
        record("PASS", "disk", f"{free_gb:.0f} GB free")
    else:
        record("WARN", "disk", f"{free_gb:.1f} GB free; the weights need about 5 GB")


def check_versions() -> None:
    """Compare installed versions with scripts/requirements.txt."""
    req = Path(__file__).with_name("requirements.txt")
    if not req.is_file():
        record("WARN", "requirements", "requirements.txt not found")
        return
    drift = []
    for line in req.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, want = line.split("==", 1)
        try:
            have = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            drift.append(f"{name} missing")
            continue
        if have != want:
            drift.append(f"{name} {have} (pinned {want})")
    if drift:
        record("WARN", "requirements", "differs from pinned versions: " + "; ".join(drift))
    else:
        record("PASS", "requirements", "installed versions match requirements.txt")


def main() -> int:
    print(f"Checking environment for {SKILL_ROOT.name}\n")
    check_python()
    check_modules()
    check_sam3_loads()
    check_device()
    check_weights()
    check_disk()
    check_versions()
    failed = [r for r in results if r[0] == "FAIL"]
    print()
    if failed:
        print(f"NOT READY: {len(failed)} check(s) failed.")
        return 1
    print("READY: all required checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
