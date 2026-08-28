# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import numpy as np

def test_w1():
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

    @iron.jit
    def diag_w1_prog(
        tok_in: In,
        res_out: Out,
        *,
        tok_slots: CompileTime[int],
        res_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        tok_ty = np.ndarray[(tok_slots,), np.dtype[element_type]]
        res_ty = np.ndarray[(res_slots,), np.dtype[element_type]]

        of_tok = ObjectFifo(tok_ty, name="diag_tok")
        of_res = ObjectFifo(res_ty, name="diag_res")

        kernel_path = Path("phoenix_sdr_dsp/pqc/kernels").resolve()
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w1_fn = ExternalFunction("dr11_mldsa44_keygen_w1", source_file=str(kernel_path / "dr11_mldsa44_keygen_w1.cc"), arg_types=[tok_ty, res_ty], include_dirs=inc_dirs)

        def worker1_body(of_t, of_r, fn):
            t = of_t.acquire(1)
            r = of_r.acquire(1)
            fn(t, r)
            of_r.release(1)
            of_t.release(1)

        w1 = Worker(worker1_body, fn_args=[of_tok.cons(), of_res.prod(), w1_fn], stack_size=0x2000)

        def sequence(t, r, t_prod, r_cons):
            t_prod.fill(t)
            r_cons.drain(r, wait=True)

        runtime = Runtime(
            sequence,
            [tok_ty, res_ty, of_tok.prod(), of_res.cons()],
        )
        return Program(iron.get_current_device(), runtime, workers=[w1]).resolve_program()

    # Create dummy token of 8452 B
    tok_buf = bytearray(8452)
    tok_buf[0:4] = (1).to_bytes(4, "little")
    tok_buf[4:36] = bytes.fromhex("0b89806f0eec39f2891116152ed4319d4260dfb8ac0710765bd497e6e1de1778")

    tok_t = XRTTensor(np.frombuffer(tok_buf, dtype=np.uint8).copy(), dtype=np.uint8)
    res_t = XRTTensor(np.zeros(3892, dtype=np.uint8), dtype=np.uint8)

    print("Running isolated W1 on silicon...")
    diag_w1_prog(
        tok_t, res_t,
        tok_slots=8452,
        res_slots=3892,
        element_type=np.uint8,
    )
    res_t.to("cpu")
    out = bytes(res_t._data[:3892])
    print(f"W1 executed successfully! status: {int.from_bytes(out[8:12], 'little')}")

if __name__ == "__main__":
    test_w1()
