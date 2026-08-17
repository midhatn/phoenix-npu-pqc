"""Fail-closed, device-resident PQC graph entry points for Phoenix AIE2."""

from .abi import N, Q, reference_negacyclic_product
from .m33_product_graph import BACKEND_LABEL, NativeBackendUnavailable, run_m33_product

__all__ = [
    "BACKEND_LABEL",
    "N",
    "NativeBackendUnavailable",
    "Q",
    "reference_negacyclic_product",
    "run_m33_product",
]
