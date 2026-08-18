"""Diagnostic-only direct egress for the unchanged DR2d W0 secret token.

This module is additive test infrastructure.  It is not part of the production
six-worker graph, is not a fallback, and must not be imported by the canonical
runner.  It exposes the complete 2,096-byte W0 token before any downstream
worker or serializer can observe it.
"""

import hashlib
import os
import struct
from pathlib import Path
from typing import Any

import numpy as np

from . import dr2d_mlkem512_kpke_keygen_abi as abi

BACKEND_LABEL = "dr2d-mlkem512-kpke-keygen:w0-token-tap:diagnostic-only"
RETAINED_W0_OBJECT_SHA256 = (
    "7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70"
)
RETAINED_CACHE_KEY = "04f147d54cb01d160974a6e6"
_PROGRAM: Any | None = None

_PQC_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PINNED_PRODUCTION_FILES = {
    "w0_source": (
        _PQC_DIR / "kernels" / "dr2d_mlkem512_kpke_keygen_seed.cc",
        "2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf",
    ),
    "internal_header": (
        _PQC_DIR / "kernels" / "dr2d_mlkem512_kpke_keygen_internal.hpp",
        "16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519",
    ),
    "production_graph": (
        _PQC_DIR / "dr2d_mlkem512_kpke_keygen_graph.py",
        "e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694",
    ),
    "production_abi": (
        _PQC_DIR / "dr2d_mlkem512_kpke_keygen_abi.py",
        "a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4",
    ),
    "canonical_runner": (
        _REPO_ROOT / "run_all_silicon_tests.py",
        "742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad",
    ),
}

_SECRET_HEADER_BYTES = 16
_RHO_OFFSET = 16
_S0_OFFSET = 48
_S1_OFFSET = 560
_E0_OFFSET = 1072
_E1_OFFSET = 1584
_POLY_BYTES = 2 * abi.N


class NativeBackendUnavailable(RuntimeError):
    """The native diagnostic path is unavailable or failed closed."""


class DiagnosticIntegrityError(RuntimeError):
    """A pinned production input or retained W0 object changed."""


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def retained_w0_object_path() -> Path:
    """Return the pinned comparison object path, allowing an explicit override."""
    override = os.environ.get("PQC_DR2D_W0_RETAINED_OBJECT")
    if override:
        return Path(override).expanduser().resolve()
    return (
        Path.home()
        / ".npu"
        / "cache"
        / RETAINED_CACHE_KEY
        / "dr2d_kpke_keygen_seed_noise.o"
    )


def verify_production_hashes(*, require_retained_object: bool = True) -> dict[str, str]:
    """Fail before IRON loading if a pinned production input changed."""
    observed: dict[str, str] = {}
    for name, (path, expected) in _PINNED_PRODUCTION_FILES.items():
        if not path.is_file():
            raise DiagnosticIntegrityError(f"missing pinned production file: {path}")
        actual = _sha256(path)
        if actual != expected:
            if (
                name == "canonical_runner"
                and "host-safe"
                in path.read_text(encoding="utf-8", errors="replace").lower()
            ):
                raise DiagnosticIntegrityError(
                    "historical canonical_runner pin refuses the current host-safe "
                    "compatibility runner; use the archived historical baseline "
                    f"with sha256 {expected}, not current main ({actual})"
                )
            raise DiagnosticIntegrityError(
                f"{name} hash mismatch: expected {expected}, observed {actual}"
            )
        observed[name] = actual
    object_path = retained_w0_object_path()
    if require_retained_object:
        if not object_path.is_file():
            raise DiagnosticIntegrityError(
                f"missing retained W0 comparison object: {object_path}"
            )
        actual = _sha256(object_path)
        if actual != RETAINED_W0_OBJECT_SHA256:
            raise DiagnosticIntegrityError(
                "retained W0 object hash mismatch: "
                f"expected {RETAINED_W0_OBJECT_SHA256}, observed {actual}"
            )
        observed["retained_w0_object"] = actual
    return observed


def _clear_host_staging(array: np.ndarray, tensor: Any | None) -> None:
    array.fill(0)
    backing = getattr(tensor, "_data", None)
    if backing is array:
        return
    if isinstance(backing, np.ndarray):
        backing.fill(0)
    elif isinstance(backing, memoryview) and not backing.readonly:
        backing[:] = b"\0" * backing.nbytes
    elif isinstance(backing, bytearray):
        backing[:] = b"\0" * len(backing)


def _load_iron() -> tuple[Any, ...]:
    try:
        from aie import iron
        from aie.iron import (
            CompileTime,
            ExternalFunction,
            In,
            ObjectFifo,
            Out,
            Program,
            Runtime,
            Worker,
        )
        from aie.utils.config import cxx_header_path
        from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
    except Exception as exc:
        raise NativeBackendUnavailable(
            "The W0 token tap requires MLIR-AIE/IRON 1.4.1, XRT, and an "
            "XRT-visible Phoenix NPU; no host or reference fallback exists."
        ) from exc
    return (
        iron,
        CompileTime,
        ExternalFunction,
        In,
        ObjectFifo,
        Out,
        Program,
        Runtime,
        Worker,
        cxx_header_path,
        XRTTensor,
    )


def require_hardware_runtime() -> None:
    """Check integrity and dependencies without creating a result."""
    verify_production_hashes()
    _load_iron()


def _program() -> Any:
    global _PROGRAM
    if _PROGRAM is not None:
        return _PROGRAM
    (
        iron,
        CompileTime,
        ExternalFunction,
        In,
        ObjectFifo,
        Out,
        Program,
        Runtime,
        Worker,
        cxx_header_path,
        _,
    ) = _load_iron()

    @iron.jit
    def dr2d_mlkem512_kpke_keygen_w0_token_tap_program(
        d_in: In,
        descriptor_in: In,
        secret_token_out: Out,
        *,
        d_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        secret_token_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        d_ty = np.ndarray[(d_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        secret_token_ty = np.ndarray[(secret_token_slots,), np.dtype[element_type]]
        of_d = ObjectFifo(d_ty, name="dr2d_w0_tap_d")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr2d_w0_tap_descriptor")
        of_secret = ObjectFifo(secret_token_ty, name="dr2d_w0_tap_secret_token")
        kernel_path = Path(__file__).resolve().parent / "kernels"
        seed_noise = ExternalFunction(
            "dr2d_kpke_keygen_seed_noise",
            source_file=str(kernel_path / "dr2d_mlkem512_kpke_keygen_seed.cc"),
            arg_types=[d_ty, descriptor_ty, secret_token_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )

        def worker_body(of_d, of_descriptor, of_secret, seed_noise):
            d, descriptor, secret_token = (
                of_d.acquire(1),
                of_descriptor.acquire(1),
                of_secret.acquire(1),
            )
            seed_noise(d, descriptor, secret_token)
            of_secret.release(1)
            of_d.release(1)
            of_descriptor.release(1)

        worker = Worker(
            worker_body,
            fn_args=[
                of_d.cons(),
                of_descriptor.cons(),
                of_secret.prod(),
                seed_noise,
            ],
            stack_size=0x1000,
        )

        def sequence(
            d,
            descriptor,
            secret_token,
            d_prod,
            descriptor_prod,
            secret_cons,
        ):
            d_prod.fill(d)
            descriptor_prod.fill(descriptor)
            secret_cons.drain(secret_token, wait=True)

        runtime = Runtime(
            sequence,
            [
                d_ty,
                descriptor_ty,
                secret_token_ty,
                of_d.prod(),
                of_descriptor.prod(),
                of_secret.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[worker]
        ).resolve_program()

    _PROGRAM = dr2d_mlkem512_kpke_keygen_w0_token_tap_program
    return _PROGRAM


def _token_bytes(token: bytes | bytearray | memoryview) -> bytes:
    if not isinstance(token, (bytes, bytearray, memoryview)):
        raise TypeError("W0 token must be bytes-like")
    raw = bytes(token)
    if len(raw) != abi.SECRET_TOKEN_BYTES:
        raise abi.Dr2dAbiError(
            f"W0 token must contain exactly {abi.SECRET_TOKEN_BYTES} bytes; "
            f"got {len(raw)}"
        )
    return raw


def _validate_poly16(raw: bytes, offset: int, name: str) -> None:
    for index in range(abi.N):
        coefficient = struct.unpack_from("<H", raw, offset + 2 * index)[0]
        if coefficient >= abi.Q:
            raise abi.Dr2dAbiError(
                f"successful W0 token has non-canonical {name}[{index}]"
            )


def validate_w0_secret_token(
    token: bytes | bytearray | memoryview, request_id: int
) -> bytes:
    """Validate one complete W0 token without computing a reference result."""
    raw = _token_bytes(token)
    expected_request_id = abi.validate_request_id(request_id)
    echoed_request_id, status = struct.unpack_from("<II", raw, 0)
    if echoed_request_id != expected_request_id:
        raise abi.Dr2dAbiError("W0 token request_id does not echo the request")
    if status not in abi.VALID_STATUSES:
        raise abi.Dr2dAbiError(f"W0 token has unknown status {status}")
    if any(raw[8:_SECRET_HEADER_BYTES]):
        raise abi.Dr2dAbiError("W0 token reserved header bytes are nonzero")
    if status != abi.STATUS_OK:
        if any(raw[8:]):
            raise abi.Dr2dAbiError(
                "W0 error token must have a fixed zero reserved area and payload"
            )
        names = {
            abi.STATUS_LIMIT_EXCEEDED: "LIMIT_EXCEEDED",
            abi.STATUS_BAD_DESCRIPTOR: "BAD_DESCRIPTOR",
            abi.STATUS_BAD_TOKEN: "BAD_TOKEN",
        }
        raise abi.Dr2dOperationError(
            f"W0 token tap returned {names[status]}; no fallback is available"
        )
    _validate_poly16(raw, _S0_OFFSET, "s_hat[0]")
    _validate_poly16(raw, _S1_OFFSET, "s_hat[1]")
    _validate_poly16(raw, _E0_OFFSET, "e_hat[0]")
    _validate_poly16(raw, _E1_OFFSET, "e_hat[1]")
    return raw


def token_region_hashes(token: bytes | bytearray | memoryview) -> dict[str, str]:
    """Hash the complete record and each semantic region without a reference."""
    raw = _token_bytes(token)
    regions = {
        "token": raw,
        "header": raw[:_SECRET_HEADER_BYTES],
        "rho": raw[_RHO_OFFSET:_S0_OFFSET],
        "s_hat_0": raw[_S0_OFFSET:_S1_OFFSET],
        "s_hat_1": raw[_S1_OFFSET:_E0_OFFSET],
        "e_hat_0": raw[_E0_OFFSET:_E1_OFFSET],
        "e_hat_1": raw[_E1_OFFSET:],
    }
    return {name: hashlib.sha256(value).hexdigest() for name, value in regions.items()}


def run_w0_token_tap(d: bytes | bytearray | memoryview, request_id: int) -> bytes:
    """Return one validated raw W0 token or fail closed; never use a fallback."""
    d_bytes, descriptor_bytes = abi.validate_request(d, request_id)
    before = verify_production_hashes()
    d_np = np.frombuffer(d_bytes, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(descriptor_bytes, dtype=np.uint8).copy()
    token_np = np.full(abi.SECRET_TOKEN_BYTES, 0xA5, dtype=np.uint8)
    d_t = descriptor_t = token_t = None
    try:
        dispatch_error: Exception | None = None
        try:
            *_, XRTTensor = _load_iron()
            d_t = XRTTensor(d_np, dtype=np.uint8)
            descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
            token_t = XRTTensor(token_np, dtype=np.uint8)
            _program()(
                d_t,
                descriptor_t,
                token_t,
                d_slots=abi.D_BYTES,
                descriptor_slots=abi.DESCRIPTOR_BYTES,
                secret_token_slots=abi.SECRET_TOKEN_BYTES,
                element_type=np.uint8,
            )
            token_t.to("cpu")
        except Exception as exc:  # noqa: BLE001 - native diagnostic fails closed
            dispatch_error = exc
        finally:
            _clear_host_staging(d_np, d_t)
            _clear_host_staging(descriptor_np, descriptor_t)
            after = verify_production_hashes()
        if after != before:
            raise DiagnosticIntegrityError(
                "pinned production hashes changed during W0 token-tap dispatch"
            )
        if dispatch_error is not None:
            raise NativeBackendUnavailable(
                "W0 token-tap native dispatch failed; no replacement ran."
            ) from dispatch_error
        return validate_w0_secret_token(
            bytes(token_t._data[: abi.SECRET_TOKEN_BYTES]), request_id
        )
    finally:
        _clear_host_staging(d_np, d_t)
        _clear_host_staging(descriptor_np, descriptor_t)
        _clear_host_staging(token_np, token_t)


__all__ = [
    "BACKEND_LABEL",
    "RETAINED_W0_OBJECT_SHA256",
    "DiagnosticIntegrityError",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "retained_w0_object_path",
    "run_w0_token_tap",
    "token_region_hashes",
    "validate_w0_secret_token",
    "verify_production_hashes",
]
