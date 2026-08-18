"""Additive, one-core, no-dispatch DR2d sigma-plus-PRF trace graph."""

import hashlib
import os
from pathlib import Path

import numpy as np
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

D_BYTES = 32
SIGMA_BYTES = 32
PRF_BYTES = 192
PRF_COUNT = 4
TRACE_BYTES = SIGMA_BYTES + PRF_COUNT * PRF_BYTES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels" / (
    "dr2d_mlkem512_kpke_sigma_prf_tap.cc"
)
_RETAINED_W0_OBJECT = (
    Path.home()
    / ".npu"
    / "cache"
    / "04f147d54cb01d160974a6e6"
    / "dr2d_kpke_keygen_seed_noise.o"
)

_PRODUCTION_HASHES = {
    "canonical_runner": (
        _REPO_ROOT / "run_all_silicon_tests.py",
        "742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad",
    ),
    "production_abi": (
        _REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "dr2d_mlkem512_kpke_keygen_abi.py",
        "a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4",
    ),
    "production_graph": (
        _REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "dr2d_mlkem512_kpke_keygen_graph.py",
        "e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694",
    ),
    "internal_header": (
        _REPO_ROOT
        / "phoenix_sdr_dsp"
        / "pqc"
        / "kernels"
        / "dr2d_mlkem512_kpke_keygen_internal.hpp",
        "16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519",
    ),
    "keccak_header": (
        _REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels" / "dr1_keccak_f1600.hpp",
        "0470fb39277478a368004a49e551a3411d8f9185b492ac01f85d2297bcea3c1f",
    ),
    "w0_source": (
        _REPO_ROOT
        / "phoenix_sdr_dsp"
        / "pqc"
        / "kernels"
        / "dr2d_mlkem512_kpke_keygen_seed.cc",
        "2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf",
    ),
}
_RETAINED_W0_SHA256 = "7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70"


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"REFUSED: required pinned input is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_production_hashes() -> dict[str, str]:
    """Require unchanged production inputs and the retained W0 witness object."""
    observed: dict[str, str] = {}
    for name, (path, expected) in _PRODUCTION_HASHES.items():
        digest = _sha256(path)
        if digest != expected:
            raise RuntimeError(
                f"REFUSED: protected hash mismatch for {name}: "
                f"expected={expected} observed={digest}"
            )
        observed[name] = digest
    retained = Path(os.environ.get("PQC_DR2D_W0_RETAINED_OBJECT", _RETAINED_W0_OBJECT))
    digest = _sha256(retained)
    if digest != _RETAINED_W0_SHA256:
        raise RuntimeError(
            "REFUSED: retained W0 comparison object hash mismatch: "
            f"expected={_RETAINED_W0_SHA256} observed={digest}"
        )
    observed["retained_w0_object"] = digest
    return observed


def _program():
    """Return an unspecialized CallableDesign; never compile from this factory."""

    @iron.jit
    def _specialized_program(
        d: In,
        trace: Out,
        *,
        d_slots: CompileTime[int],
        trace_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        if d_slots != D_BYTES:
            raise ValueError(f"d_slots must be {D_BYTES}, got {d_slots}")
        if trace_slots != TRACE_BYTES:
            raise ValueError(f"trace_slots must be {TRACE_BYTES}, got {trace_slots}")
        if element_type is not np.uint8:
            raise TypeError("sigma-plus-PRF trace requires numpy.uint8")

        d_type = np.ndarray[(d_slots,), np.dtype[element_type]]
        trace_type = np.ndarray[(trace_slots,), np.dtype[element_type]]
        d_fifo = ObjectFifo(d_type, name="dr2d_sigma_prf_tap_d")
        trace_fifo = ObjectFifo(trace_type, name="dr2d_sigma_prf_tap_trace")
        tap = ExternalFunction(
            "dr2d_kpke_sigma_prf_tap",
            source_file=str(_KERNEL),
            arg_types=[d_type, trace_type],
            include_dirs=[cxx_header_path(), str(_KERNEL.parent)],
        )

        def core_body(d_cons, trace_prod, tap_fn):
            d_item = d_cons.acquire(1)
            trace_item = trace_prod.acquire(1)
            tap_fn(d_item, trace_item)
            d_cons.release(1)
            trace_prod.release(1)

        worker = Worker(
            core_body,
            fn_args=[d_fifo.cons(), trace_fifo.prod(), tap],
        )

        def sequence(d_input, trace_output, d_prod, trace_cons):
            d_prod.fill(d_input)
            trace_cons.drain(trace_output, wait=True)

        runtime = Runtime(
            sequence,
            [d_type, trace_type, d_fifo.prod(), trace_fifo.cons()],
        )
        return Program(iron.get_current_device(), runtime, workers=[worker]).resolve_program()

    return _specialized_program
