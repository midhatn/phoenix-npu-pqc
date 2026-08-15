# Purpose: Milestone 3 SAXPY Silicon Execution on Phoenix NPU (AIE2 / Ryzen AI 7940HS)
# Target operating system: Windows 11 Pro 25H2
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2
# Input types: bfloat16 tensors (4096 elements)
# Output types: bfloat16 output tensor verified against NumPy reference (3*x + y)
# Scaling: direct bfloat16
# Alignment assumptions: handled by IRON XRTTensor/BO runtime
# State requirements: device 0 (NPU Phoenix)
# Error handling: bit-accurate assert_pass against CPU reference

from pathlib import Path
import aie.iron as iron
import numpy as np
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
from aie.utils.verify import assert_pass
from ml_dtypes import bfloat16


@iron.jit
def saxpy(
    input0: In,
    input1: In,
    output: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N,), np.dtype[element_type]]
    out_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_x = ObjectFifo(in_ty, name="x")
    of_y = ObjectFifo(in_ty, name="y")
    of_z = ObjectFifo(out_ty, name="z")

    current_dir = Path(__file__).parent.resolve()
    saxpy_kernel = ExternalFunction(
        "saxpy",
        source_file=str(current_dir / "saxpy.cc"),
        arg_types=[in_ty, in_ty, out_ty],
        include_dirs=[cxx_header_path()],
    )

    def core_body(of_x, of_y, of_z, saxpy_kernel):
        elem_x = of_x.acquire(1)
        elem_y = of_y.acquire(1)
        elem_z = of_z.acquire(1)
        saxpy_kernel(elem_x, elem_y, elem_z)
        of_x.release(1)
        of_y.release(1)
        of_z.release(1)

    worker = Worker(
        core_body, fn_args=[of_x.cons(), of_y.cons(), of_z.prod(), saxpy_kernel]
    )

    def sequence(a_x, a_y, c_z, x_prod, y_prod, z_cons):
        x_prod.fill(a_x)
        y_prod.fill(a_y)
        z_cons.drain(c_z, wait=True)

    rt = Runtime(
        sequence,
        [in_ty, in_ty, out_ty, of_x.prod(), of_y.prod(), of_z.cons()],
    )

    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 3: SAXPY Silicon Execution ===")
    data_size = 4096
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Vector Length: {data_size} elements of {element_type.__name__}")

    input0 = iron.arange(data_size, dtype=element_type, device="npu")
    input1 = iron.arange(data_size, dtype=element_type, device="npu")
    output = iron.zeros_like(input0)

    print("Compiling kernel with Peano and dispatching to Phoenix NPU...")
    res = saxpy(input0, input1, output, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    print("Execution complete. Inspecting output buffer vs reference...")
    ref = 3 * input0.numpy() + input1.numpy()
    out_np = output.numpy()

    print(f"Input0 sample [0..4]: {input0.numpy()[:4]}")
    print(f"Input1 sample [0..4]: {input1.numpy()[:4]}")
    print(f"Ref Out sample [0..4]: {ref[:4]}")
    print(f"Actual Out sample [0..4]: {out_np[:4]}")

    assert_pass(out_np, ref, fail_msg="saxpy output does not match 3*x + y")
    print("SUCCESS: Phoenix NPU executed kernel on physical silicon and verified bit-accurate output!")
    print("PASS!")


if __name__ == "__main__":
    main()
