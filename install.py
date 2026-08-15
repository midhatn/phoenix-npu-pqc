# Purpose: One-command native Windows installer for Phoenix SDR-DSP.
# Target operating system: Windows 11 Pro 22H2+ (verified 25H2 / 26200).
# Target architecture: AMD Phoenix / Hawk Point NPU1 / XDNA1 / AIE2.
# Verification: Prerequisite probe + idempotent XRT SDK download/extract +
#               pinned mlir-aie checkout + official iron_setup.py.
#
# A new user should only need:
#   git clone https://github.com/midhatn/phoenix-sdr-dsp.git
#   cd phoenix-sdr-dsp
#   python install.py
#
# This file is stdlib-only so it runs on a stock CPython 3.13 before ironenv
# or numpy exist. Do not name it setup.py — that name is reserved for
# setuptools (https://packaging.python.org/en/latest/guides/modernize-setup-py-project/).
#
# Official IRON native-Windows path this wraps:
#   https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
# XRT Windows SDK (tag 2.21.75, sha256 pinned in toolchain.yaml):
#   https://github.com/Xilinx/XRT/releases/download/2.21.75/xrt_windows_sdk.zip
#
# scripts/bootstrap_env.ps1 remains the repair script for an already-populated
# third_party/ tree. This file (install.py) is the first-clone installer.

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent

# Fallback pins used when toolchain.yaml is missing or older than this script.
# Keep identical to toolchain.yaml -> bootstrap.xrt_windows_sdk and
# toolchain.mlir_aie.verified_commit.
DEFAULT_XRT_URL = (
    "https://github.com/Xilinx/XRT/releases/download/2.21.75/xrt_windows_sdk.zip"
)
DEFAULT_XRT_TAG = "2.21.75"
DEFAULT_XRT_BYTES = 70_834_080
DEFAULT_XRT_SHA256 = "ccc244c2c423588972ade76142cdc01049477aaa39a35be97e782b97eb7c5295"
DEFAULT_MLIR_AIE_URL = "https://github.com/Xilinx/mlir-aie.git"
DEFAULT_MLIR_AIE_COMMIT = "3ca0193cea9e2c39ec670a65f93e1dd43c969f22"
DEFAULT_PYTHON_MIN = (3, 10)
DEFAULT_PYTHON_MAX_EXCL = (3, 14)
DEFAULT_PYTHON_REQUIRED = (3, 13)
DEFAULT_NPU_DRIVER_MIN = "32.0.20102.3930"
DEFAULT_OS_MIN_BUILD = 22621  # Windows 11 22H2

IRON_WINDOWS_GUIDE = "https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/"
# Pinned mlir_aie wheel. iron_setup.py on an untagged checkout (our 3ca0193
# pin is v1.4.1+13) selects the rolling latest-wheels-4 channel, which can
# resolve to an older series such as 1.3.4. The 16-suite needs the v1.4.1
# iron.Runtime API:
#   https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1
DEFAULT_MLIR_AIE_WHEEL_URL = (
    "https://github.com/Xilinx/mlir-aie/releases/download/v1.4.1/"
    "mlir_aie-1.4.1-cp313-cp313-win_amd64.whl"
)
DEFAULT_MLIR_AIE_WHEEL_NAME = "mlir_aie-1.4.1-cp313-cp313-win_amd64.whl"
DEFAULT_MLIR_AIE_WHEEL_BYTES = 180_031_689
DEFAULT_MLIR_AIE_WHEEL_SHA256 = (
    "a3a0266051cbeb7bd28c0304d02fa361b3c05036c81f0880a0046992a77e7663"
)
GIT_FETCH_ATTEMPTS = 4
XRT_RELEASE_URL = "https://github.com/Xilinx/XRT/releases/tag/2.21.75"
AMD_DRIVER_URL = "https://www.amd.com/en/support/download/drivers.html"
USER_AGENT = "phoenix-sdr-dsp-bootstrap/0.4.0"
CHUNK_SIZE = 256 * 1024
VSWHERE = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
XRT_SMI = Path(r"C:\Windows\System32\AMD\xrt-smi.exe")

WINGET_GIT = "winget install -e --id Git.Git"
WINGET_PYTHON = "winget install -e --id Python.Python.3.13"
WINGET_CMAKE = "winget install -e --id Kitware.CMake"
WINGET_LLVM = "winget install -e --id LLVM.LLVM"
WINGET_VS = (
    "winget install -e --id Microsoft.VisualStudio.2022.BuildTools "
    "--override "
    '"--wait --passive --add Microsoft.VisualStudio.Workload.VCTools '
    "--add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 "
    "--add Microsoft.VisualStudio.Component.VC.Llvm.Clang "
    '--add Microsoft.VisualStudio.Component.Windows11SDK.22621"'
)


class BootstrapError(RuntimeError):
    """Fatal bootstrap failure with a user-facing message."""


@dataclass
class Pins:
    xrt_url: str = DEFAULT_XRT_URL
    xrt_tag: str = DEFAULT_XRT_TAG
    xrt_bytes: int = DEFAULT_XRT_BYTES
    xrt_sha256: str = DEFAULT_XRT_SHA256
    mlir_url: str = DEFAULT_MLIR_AIE_URL
    mlir_commit: str = DEFAULT_MLIR_AIE_COMMIT
    python_min: tuple[int, int] = DEFAULT_PYTHON_MIN
    python_max_excl: tuple[int, int] = DEFAULT_PYTHON_MAX_EXCL
    python_required: tuple[int, int] = DEFAULT_PYTHON_REQUIRED
    npu_driver_min: str = DEFAULT_NPU_DRIVER_MIN
    os_min_build: int = DEFAULT_OS_MIN_BUILD
    mlir_wheel_url: str = DEFAULT_MLIR_AIE_WHEEL_URL
    mlir_wheel_name: str = DEFAULT_MLIR_AIE_WHEEL_NAME
    mlir_wheel_bytes: int = DEFAULT_MLIR_AIE_WHEEL_BYTES
    mlir_wheel_sha256: str = DEFAULT_MLIR_AIE_WHEEL_SHA256


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str = ""
    hint: str = ""


@dataclass
class CheckReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def required_failed(self) -> list[Check]:
        return [c for c in self.checks if c.required and not c.ok]

    @property
    def all_required_ok(self) -> bool:
        return not self.required_failed


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _yaml_block(text: str, header: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(header):
            start = i + 1
            break
    if start is None:
        return ""
    chunk: list[str] = []
    for line in lines[start:]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        chunk.append(line)
    return "\n".join(chunk)


def _yaml_scalar(text: str, key: str) -> str | None:
    pat = re.compile(
        rf"^[ \t]*{re.escape(key)}:[ \t]*(?:\"([^\"]*)\"|'([^']*)'|(\S+))\s*$"
    )
    for line in text.splitlines():
        match = pat.match(line)
        if match:
            return next(g for g in match.groups() if g is not None)
    return None


def _parse_dotted_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in re.findall(r"\d+", value):
        parts.append(int(token))
        if len(parts) == 4:
            break
    if not parts:
        raise ValueError(f"not a dotted version: {value!r}")
    return tuple(parts)


def load_pins(repo_root: Path) -> Pins:
    pins = Pins()
    yaml_path = repo_root / "toolchain.yaml"
    if not yaml_path.is_file():
        print(f" [ WARN ] {yaml_path.name} not found; using built-in pins")
        return pins

    text = yaml_path.read_text(encoding="utf-8")
    bootstrap = _yaml_block(text, "bootstrap:")
    xrt_block = bootstrap
    url = _yaml_scalar(xrt_block, "url")
    tag = _yaml_scalar(xrt_block, "tag")
    raw_bytes = _yaml_scalar(xrt_block, "bytes")
    sha256 = _yaml_scalar(xrt_block, "sha256")
    if url:
        pins.xrt_url = url
    if tag:
        pins.xrt_tag = tag
    if raw_bytes and raw_bytes.isdigit():
        pins.xrt_bytes = int(raw_bytes)
    if sha256:
        pins.xrt_sha256 = sha256.lower()

    wheel_url = _yaml_scalar(text, "wheel_url")
    wheel_name = _yaml_scalar(text, "wheel_name")
    wheel_bytes = _yaml_scalar(text, "wheel_bytes")
    wheel_sha = _yaml_scalar(text, "wheel_sha256")
    if wheel_url:
        pins.mlir_wheel_url = wheel_url
    if wheel_name:
        pins.mlir_wheel_name = wheel_name
    if wheel_bytes and wheel_bytes.isdigit():
        pins.mlir_wheel_bytes = int(wheel_bytes)
    if wheel_sha:
        pins.mlir_wheel_sha256 = wheel_sha.lower()

    commit = _yaml_scalar(text, "verified_commit")
    if commit:
        pins.mlir_commit = commit

    driver = _yaml_scalar(_yaml_block(text, "drivers:"), "minimum")
    if driver:
        pins.npu_driver_min = driver

    host = _yaml_block(text, "host:")
    python_block = _yaml_block(host, "  python:") if host else ""
    # host.python is nested; fall back to scanning the host block.
    raw_min = _yaml_scalar(python_block or host, "min")
    raw_max = _yaml_scalar(python_block or host, "max_exclusive")
    if raw_min:
        pins.python_min = _parse_dotted_version(raw_min)[:2]
    if raw_max:
        pins.python_max_excl = _parse_dotted_version(raw_max)[:2]
    return pins


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_matches(path: Path, expected_bytes: int, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != expected_bytes:
        return False
    return sha256_file(path) == expected_sha256.lower()


def download_file(
    url: str,
    dest: Path,
    expected_bytes: int,
    expected_sha256: str,
    *,
    force: bool = False,
) -> str:
    """Fetch url into dest. Skip when size+sha256 already match.

    Returns one of: 'skipped', 'downloaded', 'repaired'.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected_sha256 = expected_sha256.lower()
    action = "downloaded"

    if dest.is_file() and not force:
        if file_matches(dest, expected_bytes, expected_sha256):
            print(
                f" [ SKIP ] {dest.name} already present "
                f"({expected_bytes} bytes, sha256 {expected_sha256[:12]}...)"
            )
            return "skipped"
        print(f" [ REPAIR ] {dest.name} size/hash mismatch; re-downloading")
        dest.unlink()
        action = "repaired"
    elif dest.is_file() and force:
        dest.unlink()
        action = "repaired"

    partial = dest.with_name(dest.name + ".partial")
    if partial.exists():
        partial.unlink()

    request = Request(url, headers={"User-Agent": USER_AGENT})
    print(f" [ GET  ] {url}")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=60) as response, partial.open("wb") as handle:
            total_header = response.headers.get("Content-Length")
            total = (
                int(total_header)
                if total_header and total_header.isdigit()
                else expected_bytes
            )
            seen = 0
            last_report = 0
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                seen += len(chunk)
                if seen - last_report >= 5 * 1024 * 1024 or seen == total:
                    pct = (100.0 * seen / total) if total else 0.0
                    print(
                        f"         {seen / (1024 * 1024):6.1f} / {total / (1024 * 1024):6.1f} MiB ({pct:5.1f}%)"
                    )
                    last_report = seen
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        if partial.exists():
            partial.unlink()
        raise BootstrapError(f"download failed: {url}\n       {exc}") from exc

    elapsed = time.perf_counter() - started
    actual_bytes = partial.stat().st_size
    if actual_bytes != expected_bytes:
        partial.unlink()
        raise BootstrapError(
            f"{dest.name} size {actual_bytes} != pinned {expected_bytes} bytes "
            f"(see {XRT_RELEASE_URL})"
        )

    actual_sha = sha256_file(partial)
    if actual_sha != expected_sha256:
        partial.unlink()
        raise BootstrapError(
            f"{dest.name} sha256 {actual_sha} != pinned {expected_sha256}\n"
            f"       Refusing to extract a tampered or unexpected archive."
        )

    partial.replace(dest)
    print(
        f" [ OK   ] {dest.name} ({actual_bytes} bytes, sha256 verified, {elapsed:.1f}s)"
    )
    return action


def safe_extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise BootstrapError(f"refusing unsafe zip path: {info.filename}")
        zf.extractall(dest)


def ensure_extracted_zip(
    archive: Path,
    dest: Path,
    marker_name: str,
    expected_sha256: str,
    required_file: Path,
    *,
    force: bool = False,
) -> str:
    """Extract archive into dest unless a matching marker + payload already exist."""
    marker = dest / marker_name
    expected_sha256 = expected_sha256.lower()
    if (
        not force
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip().lower() == expected_sha256
        and required_file.is_file()
    ):
        print(f" [ SKIP ] {dest.name} already extracted (sha256 marker matches)")
        return "skipped"

    if dest.exists() and force:
        shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

    print(f" [ UNZIP] {archive.name} -> {dest}")
    safe_extract_zip(archive, dest)
    if not required_file.is_file():
        raise BootstrapError(f"extract succeeded but missing {required_file}")
    marker.write_text(expected_sha256 + "\n", encoding="utf-8")
    print(f" [ OK   ] extracted {required_file.relative_to(dest)}")
    return "extracted"


def which_ok(name: str) -> str | None:
    return shutil.which(name)


def run_capture(cmd: list[str], *, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def run_checked(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"         $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False, cwd=str(cwd) if cwd else None)
    if proc.returncode != 0:
        raise BootstrapError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def run_checked_retry(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    attempts: int = GIT_FETCH_ATTEMPTS,
) -> None:
    """Retry flaky GitHub fetches (HTTP/2 CANCEL / early EOF)."""
    last_error: BootstrapError | None = None
    for attempt in range(1, attempts + 1):
        try:
            run_checked(cmd, cwd=cwd)
            return
        except BootstrapError as exc:
            last_error = exc
            if attempt == attempts:
                break
            wait = 2 * attempt
            print(f" [ RETRY ] attempt {attempt}/{attempts} failed; waiting {wait}s")
            time.sleep(wait)
    assert last_error is not None
    raise last_error


def windows_build_number() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        return int(sys.getwindowsversion().build)
    except (AttributeError, ValueError):
        return None


def probe_vs_tools() -> str | None:
    if VSWHERE.is_file():
        code, out = run_capture(
            [
                str(VSWHERE),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ]
        )
        path = out.strip().splitlines()[0].strip() if out.strip() else ""
        if code == 0 and path:
            return path
    # Fall back to a configured native-tools prompt.
    for env_name in ("VCINSTALLDIR", "VSINSTALLDIR"):
        value = os.environ.get(env_name)
        if value and Path(value).is_dir():
            return value
    return None


def _vs_install_paths() -> list[Path]:
    found: list[Path] = []
    vs = probe_vs_tools()
    if vs:
        found.append(Path(vs))
    for candidate in (
        Path(r"C:\Program Files\Microsoft Visual Studio\18\Community"),
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"),
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools"),
        Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"),
    ):
        if candidate.is_dir() and candidate not in found:
            found.append(candidate)
    return found


def find_llvm_objcopy() -> Path | None:
    """Locate llvm-objcopy for iron_setup's Windows llvm-aie wheel fixup.

    iron_setup.fixup_llvm_aie_windows looks for llvm-objcopy.exe inside the
    llvm-aie wheel, then on PATH. Published wheels do not ship it, so a stock
    PowerShell after `conda deactivate` fails with:
      ERROR: llvm-objcopy.exe is required to prepare the llvm-aie wheel
    Official native-Windows IRON guide requires the VS Clang/LLVM component:
      https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
    """
    for name in ("llvm-objcopy.exe", "llvm-objcopy"):
        hit = which_ok(name)
        if hit:
            return Path(hit)
    candidates = [
        Path(r"C:\Program Files\LLVM\bin\llvm-objcopy.exe"),
        Path(r"C:\Program Files (x86)\LLVM\bin\llvm-objcopy.exe"),
    ]
    for vs in _vs_install_paths():
        candidates.append(
            vs / "VC" / "Tools" / "Llvm" / "x64" / "bin" / "llvm-objcopy.exe"
        )
        candidates.append(vs / "VC" / "Tools" / "Llvm" / "bin" / "llvm-objcopy.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for vs in _vs_install_paths():
        llvm_root = vs / "VC" / "Tools" / "Llvm"
        if llvm_root.is_dir():
            matches = sorted(llvm_root.rglob("llvm-objcopy.exe"))
            if matches:
                return matches[0]
    return None


def ensure_llvm_objcopy_on_path() -> Path:
    found = find_llvm_objcopy()
    if found is None:
        raise BootstrapError(
            "llvm-objcopy.exe not found. iron_setup needs it to prepare the "
            "Windows llvm-aie wheel.\n"
            f"       Install LLVM and re-run: {WINGET_LLVM}\n"
            f"       Or add the VS Clang component. Guide: {IRON_WINDOWS_GUIDE}"
        )
    bindir = str(found.parent)
    path = os.environ.get("PATH", "")
    if bindir.lower() not in path.lower().split(os.pathsep):
        os.environ["PATH"] = bindir + os.pathsep + path
    print(f" [ OK   ] llvm-objcopy on PATH -> {found}")
    return found


def probe_npu(min_driver: str) -> Check:
    if not XRT_SMI.is_file():
        return Check(
            name="AMD NPU driver / xrt-smi",
            ok=False,
            required=True,
            detail=f"missing {XRT_SMI}",
            hint=f"Install Adrenalin / OEM NPU driver >= {min_driver} from {AMD_DRIVER_URL}",
        )

    code, out = run_capture([str(XRT_SMI), "examine"], timeout=45)
    if code != 0:
        return Check(
            name="AMD NPU driver / xrt-smi",
            ok=False,
            required=True,
            detail=f"xrt-smi examine exited {code}",
            hint=f"Install or repair the AMD NPU driver >= {min_driver}: {AMD_DRIVER_URL}",
        )

    if "NPU Phoenix" not in out and "NPU" not in out:
        return Check(
            name="AMD NPU driver / xrt-smi",
            ok=False,
            required=True,
            detail="xrt-smi examine did not list an NPU",
            hint="This project needs Phoenix / Hawk Point XDNA1 silicon.",
        )

    match = re.search(r"NPU Driver Version\s*[:=]\s*([0-9.]+)", out, re.IGNORECASE)
    version = match.group(1) if match else None
    if version:
        try:
            if _parse_dotted_version(version) < _parse_dotted_version(min_driver):
                return Check(
                    name="AMD NPU driver / xrt-smi",
                    ok=False,
                    required=True,
                    detail=f"driver {version} < minimum {min_driver}",
                    hint=f"Update the AMD NPU driver: {AMD_DRIVER_URL}",
                )
        except ValueError:
            pass
        detail = f"{XRT_SMI} ; driver {version}"
    else:
        detail = f"{XRT_SMI} ; NPU visible, driver version not parsed"

    if "NPU Phoenix" in out:
        detail += " ; NPU Phoenix"
    return Check(
        name="AMD NPU driver / xrt-smi",
        ok=True,
        required=True,
        detail=detail,
    )


def run_prerequisite_checks(pins: Pins, *, require_silicon: bool) -> CheckReport:
    report = CheckReport()

    if sys.platform == "win32":
        build = windows_build_number()
        win_ok = build is not None and build >= pins.os_min_build
        report.add(
            Check(
                name="Windows 11 (22H2+)",
                ok=bool(win_ok),
                required=True,
                detail=f"build {build}" if build is not None else platform.platform(),
                hint="Upgrade to Windows 11 22H2 or newer.",
            )
        )
    else:
        report.add(
            Check(
                name="Windows 11 (22H2+)",
                ok=False,
                required=True,
                detail=f"this interpreter is {sys.platform}",
                hint="Run install.py on the Phoenix laptop, not WSL/Linux/macOS.",
            )
        )

    ver = sys.version_info
    py_ok = ver[:2] == pins.python_required
    if pins.python_min <= ver[:2] < pins.python_max_excl and not py_ok:
        hint = (
            f"CPython {ver.major}.{ver.minor} is in the project's documented range "
            f"but the Windows XRT SDK ships pyxrt for CPython "
            f"{pins.python_required[0]}.{pins.python_required[1]} only. "
            f"Install that interpreter: {WINGET_PYTHON}"
        )
    else:
        hint = WINGET_PYTHON
    report.add(
        Check(
            name=f"Python {pins.python_required[0]}.{pins.python_required[1]}",
            ok=py_ok,
            required=True,
            detail=platform.python_version(),
            hint=hint,
        )
    )

    git_path = which_ok("git")
    report.add(
        Check(
            name="Git",
            ok=git_path is not None,
            required=True,
            detail=git_path or "not on PATH",
            hint=WINGET_GIT,
        )
    )

    cmake_path = which_ok("cmake")
    report.add(
        Check(
            name="CMake",
            ok=cmake_path is not None,
            required=require_silicon,
            detail=cmake_path or "not on PATH",
            hint=WINGET_CMAKE,
        )
    )

    vs_path = probe_vs_tools() if sys.platform == "win32" else None
    report.add(
        Check(
            name="Visual Studio C++ tools",
            ok=vs_path is not None,
            required=require_silicon,
            detail=vs_path or "vswhere did not find VC.Tools.x86.x64",
            hint=WINGET_VS + f"\n          Guide: {IRON_WINDOWS_GUIDE}",
        )
    )

    if sys.platform == "win32":
        objcopy = find_llvm_objcopy()
        report.add(
            Check(
                name="llvm-objcopy (Peano wheel fixup)",
                ok=objcopy is not None,
                required=require_silicon,
                detail=str(objcopy)
                if objcopy
                else "not on PATH and not under VS LLVM / Program Files\\LLVM",
                hint=(
                    f"{WINGET_LLVM}\n"
                    "          Then re-open PowerShell so PATH picks up "
                    r"C:\Program Files\LLVM\bin"
                    f"\n          Guide: {IRON_WINDOWS_GUIDE}"
                ),
            )
        )

    if sys.platform == "win32":
        report.add(probe_npu(pins.npu_driver_min))
    else:
        report.add(
            Check(
                name="AMD NPU driver / xrt-smi",
                ok=False,
                required=require_silicon,
                detail="skipped (not Windows)",
                hint=f"Install Adrenalin / OEM NPU driver >= {pins.npu_driver_min}: {AMD_DRIVER_URL}",
            )
        )

    return report


def print_check_report(report: CheckReport) -> None:
    section("Prerequisite checks")
    for check in report.checks:
        if check.ok:
            tag = " PASS "
        elif check.required:
            tag = " FAIL "
        else:
            tag = " WARN "
        print(f" [{tag}] {check.name}")
        if check.detail:
            print(f"          {check.detail}")
        if not check.ok and check.hint:
            print(f"          {check.hint}")


def ensure_safe_directory(path: Path) -> None:
    resolved = str(path.resolve())
    variants = [resolved, resolved.replace("\\", "/")]
    code, out = run_capture(
        ["git", "config", "--global", "--get-all", "safe.directory"]
    )
    have = (
        {line.strip() for line in out.splitlines() if line.strip()}
        if code == 0
        else set()
    )
    for variant in variants:
        if variant not in have:
            run_checked(
                ["git", "config", "--global", "--add", "safe.directory", variant]
            )
            print(f" [ OK   ] git safe.directory += {variant}")
            have.add(variant)


def git_head(repo: Path) -> str | None:
    code, out = run_capture(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if code != 0:
        return None
    return out.strip() or None


def _rmtree(path: Path) -> None:
    """Remove a tree, including Windows git files marked read-only."""

    def _onexc(func, item, _exc):
        os.chmod(item, stat.S_IWRITE)
        func(item)

    shutil.rmtree(path, onexc=_onexc)


def _shallow_fetch_pin(dest: Path, url: str, commit: str) -> None:
    """Fetch one commit. No history, no submodules.

    A full `git clone --recurse-submodules` of mlir-aie is ~2 GB / 1.3M
    objects (https://github.com/Xilinx/mlir-aie). iron_setup.py only needs
    this checkout so it can install published wheels; it does not build
    the tree or its submodules.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        run_checked(["git", "init", str(dest)])
        run_checked(["git", "-C", str(dest), "remote", "add", "origin", url])
    else:
        code, _out = run_capture(
            ["git", "-C", str(dest), "remote", "get-url", "origin"]
        )
        if code != 0:
            run_checked(["git", "-C", str(dest), "remote", "add", "origin", url])
    print(
        f" [ GIT  ] fetch --depth 1 {commit[:12]} (pin only, no history, no submodules)"
    )
    # HTTP/1.1 avoids the HTTP/2 CANCEL / early-EOF failures seen on long
    # shallow fetches of Xilinx/mlir-aie from some Windows Git clients.
    run_checked_retry(
        [
            "git",
            "-C",
            str(dest),
            "-c",
            "http.version=HTTP/1.1",
            "fetch",
            "--depth",
            "1",
            "--no-tags",
            "origin",
            commit,
        ]
    )
    run_checked(
        ["git", "-C", str(dest), "checkout", "--force", "--detach", "FETCH_HEAD"]
    )
    ensure_safe_directory(dest)
    setup = dest / "utils" / "iron_setup.py"
    if not setup.is_file():
        raise BootstrapError(f"shallow fetch succeeded but missing {setup}")


def ensure_mlir_aie(dest: Path, url: str, commit: str, *, force: bool = False) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    setup = dest / "utils" / "iron_setup.py"
    if dest.is_dir() and (dest / ".git").exists():
        ensure_safe_directory(dest)
        head = git_head(dest)
        if head and head.lower() == commit.lower() and setup.is_file() and not force:
            print(f" [ SKIP ] mlir-aie already at {commit[:12]}")
            return "skipped"
        if not setup.is_file() or force:
            print(f" [ WIPE ] incomplete or forced mlir-aie tree at {dest}")
            try:
                _rmtree(dest)
            except OSError as exc:
                raise BootstrapError(
                    f"Could not remove {dest}: {exc}. "
                    "Stop any running git clone (Ctrl+C), then re-run."
                ) from exc
            _shallow_fetch_pin(dest, url, commit)
            print(f" [ OK   ] mlir-aie @ {commit[:12]} (shallow)")
            return "cloned"
        print(f" [ GIT  ] updating existing checkout to {commit[:12]}")
        _shallow_fetch_pin(dest, url, commit)
        print(f" [ OK   ] mlir-aie @ {commit[:12]} (shallow)")
        return "updated"

    if dest.exists():
        if force or not setup.is_file():
            print(f" [ WIPE ] {dest}")
            try:
                _rmtree(dest)
            except OSError as exc:
                raise BootstrapError(
                    f"Could not remove {dest}: {exc}. "
                    "Stop any running git clone (Ctrl+C), then re-run."
                ) from exc
        else:
            raise BootstrapError(
                f"{dest} exists but is not a git checkout. Move it aside and re-run."
            )

    _shallow_fetch_pin(dest, url, commit)
    print(f" [ OK   ] mlir-aie @ {commit[:12]} (shallow)")
    return "cloned"


def run_iron_setup(mlir_root: Path, xrt_root: Path, wheelhouse: Path) -> None:
    setup = mlir_root / "utils" / "iron_setup.py"
    if not setup.is_file():
        raise BootstrapError(f"missing official installer: {setup}")
    if not wheelhouse.is_dir():
        raise BootstrapError(f"missing mlir_aie wheelhouse: {wheelhouse}")
    section("IRON environment (official iron_setup.py)")
    # --wheelhouse keeps iron_setup offline for mlir_aie and forces the
    # pinned v1.4.1 wheel. Untagged HEAD would otherwise install whatever
    # latest-wheels-4 currently serves (observed: mlir_aie 1.3.4).
    # iron_setup.py (3ca0193): resolve_mlir_aie_wheel / install_mlir_aie
    #   https://github.com/Xilinx/mlir-aie/blob/3ca0193/utils/iron_setup.py
    run_checked(
        [
            sys.executable,
            str(setup),
            "--xrt-root",
            str(xrt_root),
            "--wheelhouse",
            str(wheelhouse),
        ],
        cwd=mlir_root,
    )


def install_vendored_pyxrt(ironenv: Path, xrt_root: Path) -> None:
    src = xrt_root / "python" / "pyxrt.pyd"
    if not src.is_file():
        raise BootstrapError(f"missing vendored binding {src}")
    site_pkgs = ironenv / "Lib" / "site-packages"
    if not site_pkgs.is_dir():
        raise BootstrapError(f"ironenv site-packages not found: {site_pkgs}")
    shutil.copy2(src, site_pkgs / "pyxrt.pyd")
    sitecustomize = site_pkgs / "sitecustomize.py"
    sitecustomize.write_text(
        "import os\n"
        "_paths = [\n"
        r'    r"C:\Windows\System32",' + "\n"
        r'    r"C:\Windows\System32\AMD",' + "\n"
        f'    r"{xrt_root}",\n'
        "]\n"
        "for _p in _paths:\n"
        "    if os.path.isdir(_p):\n"
        "        try:\n"
        "            os.add_dll_directory(_p)\n"
        "        except Exception:\n"
        "            pass\n"
        "        if _p not in os.environ.get('PATH', ''):\n"
        "            os.environ['PATH'] = _p + os.pathsep + os.environ.get('PATH', '')\n",
        encoding="utf-8",
    )
    peano = site_pkgs / "llvm-aie"
    clang = peano / "bin" / "clang++.exe"
    if clang.is_file():
        os.environ["PEANO_INSTALL_DIR"] = str(peano)
        try:
            subprocess.run(["setx", "PEANO_INSTALL_DIR", str(peano)], check=False)
        except OSError:
            pass
        print(f" [ OK   ] PEANO_INSTALL_DIR={peano}")
    print(f" [ OK   ] copied pyxrt.pyd -> {site_pkgs / 'pyxrt.pyd'}")


def smoke_check(iron_python: Path, peano_clang: Path) -> None:
    section("Smoke check")
    run_checked(
        [str(iron_python), "-c", "import pyxrt; print('pyxrt OK:', pyxrt.__file__)"]
    )
    run_checked(
        [
            str(iron_python),
            "-c",
            "import aie; from aie.iron import ObjectFifo; print('mlir-aie / IRON OK')",
        ]
    )
    if peano_clang.is_file():
        run_checked([str(peano_clang), "--version"])


def self_test() -> int:
    """Exercise skip / repair / hash-fail paths without touching the real SDK."""
    section("Self-test (idempotent download)")
    payload = b"phoenix-sdr-dsp-bootstrap-self-test\n"
    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="phoenix-bootstrap-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "payload.bin"
        dest = tmp_path / "cache" / "payload.bin"
        source.write_bytes(payload)
        url = source.resolve().as_uri()

        first = download_file(url, dest, len(payload), digest)
        second = download_file(url, dest, len(payload), digest)
        dest.write_bytes(b"corrupt")
        third = download_file(url, dest, len(payload), digest)

        try:
            download_file(url, dest, len(payload), "0" * 64, force=True)
        except BootstrapError:
            hash_fail_ok = True
        else:
            hash_fail_ok = False

        extract_dir = tmp_path / "extracted"
        archive = tmp_path / "payload.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("xrt_sdk/xrt/python/pyxrt.pyd", payload)
        required = extract_dir / "xrt_sdk" / "xrt" / "python" / "pyxrt.pyd"
        unzip_first = ensure_extracted_zip(
            archive, extract_dir, ".phoenix-xrt-sha256", digest, required
        )
        unzip_second = ensure_extracted_zip(
            archive, extract_dir, ".phoenix-xrt-sha256", digest, required
        )

    print(f"         first={first} second={second} third={third}")
    print(f"         unzip first={unzip_first} second={unzip_second}")
    ok = (
        first == "downloaded"
        and second == "skipped"
        and third == "repaired"
        and hash_fail_ok
        and unzip_first == "extracted"
        and unzip_second == "skipped"
    )
    if not ok:
        print(" [ FAIL ] self-test assertions did not hold")
        return 1
    print(" [ PASS ] skip / repair / hash-fail / unzip-skip")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phoenix SDR-DSP one-command Windows installer.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run prerequisite checks and exit (no downloads).",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Prereqs + idempotent XRT download/extract + mlir-aie pin. Skip iron_setup.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-extract even when the sha256 marker matches.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="After a full install, run python run_all_silicon_tests.py.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run local skip/repair/hash tests (no network, any OS).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Checkout root. Defaults to the directory containing this file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()

    repo_root = args.repo_root.resolve()
    pins = load_pins(repo_root)

    print("======================================================================")
    print("              PHOENIX SDR-DSP WINDOWS INSTALLER                       ")
    print("======================================================================")
    print(f" Repo:        {repo_root}")
    print(f" XRT SDK:     {pins.xrt_tag}  ({pins.xrt_bytes} bytes)")
    print(f" mlir-aie:    {pins.mlir_commit[:12]}")
    print(f" Guide:       {IRON_WINDOWS_GUIDE}")

    require_silicon = not args.download_only
    report = run_prerequisite_checks(pins, require_silicon=require_silicon)
    print_check_report(report)

    if args.check_only:
        return 0 if report.all_required_ok else 2

    if report.required_failed:
        print("\nPrerequisite checks failed. Fix the FAIL rows above and re-run.")
        print("This script will not install Visual Studio or the AMD NPU driver")
        print("silently — those need an administrator / OEM installer.")
        return 2

    third_party = repo_root / "third_party"
    xrt_dir = third_party / "xrt_windows_sdk"
    xrt_zip = third_party / "cache" / "xrt_windows_sdk.zip"
    xrt_root = xrt_dir / "xrt_sdk" / "xrt"
    pyxrt = xrt_root / "python" / "pyxrt.pyd"
    mlir_root = third_party / "mlir-aie"
    ironenv = mlir_root / "ironenv"

    section("Idempotent downloads")
    if (repo_root / ".git").exists() and which_ok("git"):
        ensure_safe_directory(repo_root)

    download_file(
        pins.xrt_url,
        xrt_zip,
        pins.xrt_bytes,
        pins.xrt_sha256,
        force=args.force,
    )
    ensure_extracted_zip(
        xrt_zip,
        xrt_dir,
        ".phoenix-xrt-sha256",
        pins.xrt_sha256,
        pyxrt,
        force=args.force,
    )

    wheelhouse = third_party / "cache" / "wheels"
    wheel_path = wheelhouse / pins.mlir_wheel_name
    download_file(
        pins.mlir_wheel_url,
        wheel_path,
        pins.mlir_wheel_bytes,
        pins.mlir_wheel_sha256,
        force=args.force,
    )

    section("Pinned mlir-aie checkout")
    ensure_mlir_aie(mlir_root, pins.mlir_url, pins.mlir_commit, force=args.force)

    if args.download_only:
        print("\nDownload-only complete.")
        print(f" XRT root:    {xrt_root}")
        print(f" mlir-aie:    {mlir_root}")
        print(" Re-run without --download-only to create ironenv.")
        return 0

    if sys.platform == "win32":
        ensure_llvm_objcopy_on_path()
    run_iron_setup(mlir_root, xrt_root, wheelhouse)
    section("Vendored pyxrt + Peano")
    install_vendored_pyxrt(ironenv, xrt_root)

    iron_python = ironenv / "Scripts" / "python.exe"
    peano_clang = ironenv / "Lib" / "site-packages" / "llvm-aie" / "bin" / "clang++.exe"
    if iron_python.is_file():
        smoke_check(iron_python, peano_clang)

    print("\n======================================================================")
    print(" Install complete.")
    print("======================================================================")
    print(" Next step:")
    print("   python run_all_silicon_tests.py")
    print(" The test runner uses ironenv automatically. No activate step.")
    print(" Expected at v0.4.0: 16/16 PASS.")

    if args.run_tests:
        section("Silicon regression")
        runner = repo_root / "run_all_silicon_tests.py"
        run_checked([str(iron_python), str(runner)], cwd=repo_root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BootstrapError as exc:
        print(f"\n [ FAIL ] {exc}")
        sys.exit(1)
