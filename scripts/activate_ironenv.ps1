$projectRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $projectRoot "third_party\mlir-aie\ironenv\Scripts\Activate.ps1")

$env:PYTHONPATH = "C:\Xilinx\XRT\python" + `
    $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })

$env:PATH = "C:\Xilinx\XRT\bin;C:\Xilinx\XRT\lib;$env:PATH"

Write-Host "Phoenix SDR-DSP ironenv activated with XRT Python bindings."
