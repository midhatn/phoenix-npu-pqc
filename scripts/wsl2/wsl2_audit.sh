#!/usr/bin/env bash
# Purpose: Read-only Phoenix SDR-DSP Milestone 0 WSL2 Ubuntu environment audit.
# Target operating system: Ubuntu under WSL2, used only as a secondary compile aid.
# Target architecture: inventory of the WSL2 userspace visible to this distribution.
# Input types: local files, uname, /proc, package queries, and command output.
# Output types: UTF-8 text report at /mnt/c/phoenix-sdr-dsp/audit/wsl2_audit.txt.
# Scaling: not applicable.
# Alignment assumptions: not applicable.
# State requirements: none. The script creates only the audit directory and report file.
# Error handling: every probe is isolated. Missing tools are recorded, never installed.
# No unexplained constants: all search paths are listed below.
#
# This script must not install packages, change files outside the audit path,
# alter environment persistence, load kernel modules, or assume NPU access.

set +e
set -o pipefail
umask 022

AUDIT_DIR="/mnt/c/phoenix-sdr-dsp/audit"
AUDIT_FILE="${AUDIT_DIR}/wsl2_audit.txt"
SCRIPT_VERSION="phoenix-sdr-dsp-milestone-0-wsl2-audit-2026-08-14"
START_TS="$(date '+%Y-%m-%d %H:%M:%S %z')"

MLIR_SEARCH_ROOTS=(
  "${HOME}/mlir-aie"
  "${HOME}/src/mlir-aie"
  "${HOME}/dev/mlir-aie"
  "/home/${USER}/mlir-aie"
  "/opt/mlir-aie"
  "/opt/xilinx/mlir-aie"
  "/mnt/c/dev/mlir-aie"
  "/mnt/c/Technical/mlir-aie"
  "/mnt/c/phoenix-sdr-dsp/third_party/mlir-aie"
)

XRT_SEARCH_ROOTS=(
  "/opt/xilinx/xrt"
  "/usr/local/xrt"
  "${HOME}/XRT"
  "/mnt/c/Xilinx/XRT"
  "/mnt/c/Technical/XRT"
  "/mnt/c/Windows/System32/AMD"
)

PEANO_SEARCH_ROOTS=(
  "${HOME}/llvm-aie"
  "/opt/llvm-aie"
  "/usr/local/llvm-aie"
  "/mnt/c/Xilinx/llvm-aie"
)

ENV_NAMES=(
  PATH
  PYTHONPATH
  PYTHONHOME
  VIRTUAL_ENV
  CONDA_PREFIX
  CONDA_DEFAULT_ENV
  XILINX_XRT
  XRT_PATH
  XRT_INSTALL_DIR
  MLIR_AIE_INSTALL_DIR
  PEANO_INSTALL_DIR
  AIETOOLS_ROOT
  IRON_ROOT
  AIE_ROOT
  SOAPY_SDR_ROOT
  SOAPY_SDR_PLUGIN_PATH
  LIME_SUITE_ROOT
  LIMESUITE_ROOT
  WSL_DISTRO_NAME
  WSL_INTEROP
  WSLENV
  DISPLAY
)

mkdir -p "${AUDIT_DIR}"
: > "${AUDIT_FILE}"

audit() {
  printf '%s\n' "$*" >> "${AUDIT_FILE}"
}

section() {
  audit ""
  audit "=============================================================================="
  audit "$1"
  audit "=============================================================================="
}

subsection() {
  audit ""
  audit "--- $1 ---"
}

run_cmd() {
  local label="$1"
  shift
  subsection "${label}"
  audit "+ $*"
  if ! command -v "$1" >/dev/null 2>&1 && [[ "$1" != /* ]]; then
    audit "command not found: $1"
    return 0
  fi
  "$@" >> "${AUDIT_FILE}" 2>&1
  local rc=$?
  audit "exit_code=${rc}"
  return 0
}

capture() {
  local label="$1"
  shift
  subsection "${label}"
  audit "+ $*"
  {
    eval "$@"
  } >> "${AUDIT_FILE}" 2>&1
  local rc=$?
  audit "exit_code=${rc}"
  return 0
}

file_status() {
  local path="$1"
  if [[ -e "${path}" ]]; then
    ls -ld "${path}" >> "${AUDIT_FILE}" 2>&1
  else
    audit "MISSING ${path}"
  fi
}

python_module_check() {
  local python_exe="$1"
  local module="$2"
  "${python_exe}" - <<PY >> "${AUDIT_FILE}" 2>&1
import importlib.util
spec = importlib.util.find_spec("${module}")
print("${module}: " + ("FOUND " + (spec.origin or "namespace") if spec else "MISSING"))
PY
}

audit "Phoenix SDR-DSP Milestone 0 WSL2 Ubuntu Audit"
audit "Script version: ${SCRIPT_VERSION}"
audit "Generated: ${START_TS}"
audit "Mode: read-only inventory. No packages, drivers, firmware, or settings were changed."
audit "Output file: /mnt/c/phoenix-sdr-dsp/audit/wsl2_audit.txt"
audit "This script does not assume that the Phoenix NPU is visible inside WSL2."

section "1. WSL and Ubuntu identity"
capture "uname -a" "uname -a"
capture "/proc/version" "cat /proc/version"
capture "/etc/os-release" "cat /etc/os-release"
capture "lsb_release" "lsb_release -a"
capture "WSL interop files" "ls -l /proc/sys/fs/binfmt_misc 2>/dev/null; printf '\n'; ls -l /usr/lib/wsl 2>/dev/null; printf '\n'; ls -l /mnt/wsl 2>/dev/null"
capture "WSL environment markers" "printf 'WSL_DISTRO_NAME=%s\nWSL_INTEROP=%s\nWSLENV=%s\n' \"${WSL_DISTRO_NAME-}\" \"${WSL_INTEROP-}\" \"${WSLENV-}\""
capture "/proc/sys/kernel/osrelease" "cat /proc/sys/kernel/osrelease"
capture "wsl.conf if present" "if [ -f /etc/wsl.conf ]; then cat /etc/wsl.conf; else echo 'MISSING /etc/wsl.conf'; fi"

section "2. CPU, memory, and mounts"
capture "/proc/cpuinfo model lines" "grep -E 'model name|vendor_id|cpu cores|siblings|flags' /proc/cpuinfo | head -n 40"
capture "lscpu if present" "lscpu"
capture "/proc/meminfo" "cat /proc/meminfo"
capture "free -h" "free -h"
capture "df -h" "df -h"
capture "mount table" "mount | sort"
capture "Windows drive mounts" "ls -ld /mnt/c /mnt/d /mnt/e /mnt/wsl /mnt/wslg 2>&1"
capture "/mnt/c access test" "if [ -d /mnt/c ]; then echo '/mnt/c is a directory'; ls -ld /mnt/c; ls /mnt/c | head; else echo '/mnt/c is not accessible'; fi"
capture "project path from WSL" "ls -ld /mnt/c/phoenix-sdr-dsp /mnt/c/phoenix-sdr-dsp/audit 2>&1"

section "3. Compilers and core development tools"
for tool in python3 python pip3 pip cmake ninja git clang clang++ gcc g++ ld lld llc llvm-config mlir-opt mlir-translate aie-opt aie-translate aiecc.py xrt-smi xbutil xclbinutil; do
  subsection "which ${tool}"
  if command -v "${tool}" >/dev/null 2>&1; then
    audit "$(command -v "${tool}")"
    "${tool}" --version >> "${AUDIT_FILE}" 2>&1
  else
    audit "not on PATH: ${tool}"
  fi
done

section "4. LLVM, MLIR, MLIR-AIE, IRON, Peano packages"
capture "dpkg LLVM/MLIR/XRT/AIE names" "dpkg -l | grep -Ei 'llvm|clang|mlir|xrt|xdna|aie|peano|iron' || true"
capture "apt-cache policy selected packages" "apt-cache policy llvm clang cmake ninja-build python3 2>/dev/null | sed -n '1,120p'"

subsection "Known mlir-aie locations"
for root in "${MLIR_SEARCH_ROOTS[@]}"; do
  if [[ -e "${root}" ]]; then
    audit "EXISTS ${root}"
    ls -ld "${root}" >> "${AUDIT_FILE}" 2>&1
    if [[ -d "${root}/.git" ]]; then
      git -C "${root}" remote -v >> "${AUDIT_FILE}" 2>&1
      git -C "${root}" describe --always --dirty --tags >> "${AUDIT_FILE}" 2>&1
      git -C "${root}" log -1 --oneline >> "${AUDIT_FILE}" 2>&1
      git -C "${root}" branch --show-current >> "${AUDIT_FILE}" 2>&1
    fi
    for marker in utils/env_setup.sh utils/env_install.sh utils/iron_setup.py ironenv python/requirements.txt programming_examples/getting_started/01_SAXPY/saxpy.py; do
      file_status "${root}/${marker}"
    done
  else
    audit "MISSING ${root}"
  fi
done

subsection "Known Peano / llvm-aie locations"
for root in "${PEANO_SEARCH_ROOTS[@]}"; do
  file_status "${root}"
done

section "5. Python virtual environments and IRON modules"
capture "python3 details" "python3 -c 'import sys,sysconfig,platform; print(sys.version); print(sys.executable); print(platform.platform()); print(sysconfig.get_paths())'"
subsection "import checks with python3"
if command -v python3 >/dev/null 2>&1; then
  for module in pyxrt numpy aie mlir_aie iron torch; do
    python_module_check python3 "${module}"
  done
  python3 -m pip show mlir_aie llvm-aie pyxrt aie 2>> "${AUDIT_FILE}" >> "${AUDIT_FILE}"
else
  audit "python3 not available"
fi

subsection "virtual environments in common locations"
for venv in \
  "${HOME}/mlir-aie/ironenv" \
  "${HOME}/ironenv" \
  "${HOME}/.virtualenvs/iron" \
  "${HOME}/miniforge3" \
  "${HOME}/miniconda3" \
  "${HOME}/anaconda3"
do
  file_status "${venv}"
  if [[ -x "${venv}/bin/python" ]]; then
    audit "venv python: ${venv}/bin/python"
    "${venv}/bin/python" --version >> "${AUDIT_FILE}" 2>&1
    for module in pyxrt aie mlir_aie iron; do
      python_module_check "${venv}/bin/python" "${module}"
    done
  fi
done

section "6. XRT tools and NPU visibility inside WSL2"
subsection "This section records visibility only. Absence of /dev/accel is expected unless a current test proves otherwise."
capture "ls -l /dev/accel" "ls -l /dev/accel 2>&1"
capture "ls -l /dev/dri" "ls -l /dev/dri 2>&1"
capture "ls -l /dev/kfd /dev/mkfd /dev/xdna*" "ls -l /dev/kfd /dev/mkfd /dev/xdna* 2>&1"
capture "lsmod xdna/amdxdna hints" "lsmod 2>/dev/null | grep -Ei 'xdna|amdxdna|accel|drm' || true"
for root in "${XRT_SEARCH_ROOTS[@]}"; do
  file_status "${root}"
done
file_status "/usr/bin/xrt-smi"
file_status "/opt/xilinx/xrt/bin/xrt-smi"
file_status "/mnt/c/Windows/System32/AMD/xrt-smi.exe"
if command -v xrt-smi >/dev/null 2>&1; then
  run_cmd "xrt-smi examine" xrt-smi examine
  run_cmd "xrt-smi version" xrt-smi version
else
  subsection "xrt-smi"
  audit "xrt-smi is not on PATH inside WSL2. This is not treated as proof that Windows lacks an NPU."
fi
capture "python3 pyxrt import only" "python3 -c 'import pyxrt; print(pyxrt)'"

section "7. Relevant environment variables"
subsection "selected variables"
for name in "${ENV_NAMES[@]}"; do
  eval "value=\${${name}-}"
  if [[ -n "${value}" ]]; then
    audit "${name}=${value}"
  else
    audit "${name}=<unset>"
  fi
done
subsection "exported names containing XRT, AIE, IRON, SOAPY, LIME, PYTHON, WSL"
env | grep -Ei 'XRT|AIE|IRON|SOAPY|LIME|PYTHON|WSL|XILINX|PEANO|MLIR' | sort || true

section "8. Disk space and audit path write check"
capture "df of / and /mnt/c" "df -h / /mnt/c /tmp /home 2>&1"
capture "audit directory listing" "ls -la /mnt/c/phoenix-sdr-dsp/audit 2>&1"

section "9. Audit integrity"
END_TS="$(date '+%Y-%m-%d %H:%M:%S %z')"
audit "Start: ${START_TS}"
audit "End:   ${END_TS}"
audit "Host: $(hostname)"
audit "User: $(id)"
audit "PWD: $(pwd)"
audit "The script created only /mnt/c/phoenix-sdr-dsp/audit and wsl2_audit.txt."
audit "No packages, drivers, firmware, or persistent settings were modified."
audit "NPU visibility inside WSL2 was inspected, not assumed."
audit "END OF WSL2 AUDIT"

printf 'Wrote %s\n' "${AUDIT_FILE}"
