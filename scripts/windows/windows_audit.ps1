# Purpose: Read-only Phoenix SDR-DSP Milestone 0 Windows environment audit.
# Target operating system: Windows 11 Pro (primary execution environment).
# Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2 / npu1.
# Input types: local WMI, PnP, filesystem, registry read, and command output.
# Output types: UTF-8 text report at C:\phoenix-sdr-dsp\audit\windows_audit.txt.
# Scaling: not applicable.
# Alignment assumptions: not applicable.
# State requirements: none. The script creates only the audit directory and report file.
# Error handling: every probe is isolated. Missing tools are recorded, never installed.
# No unexplained constants: all search paths and hardware keywords are listed below.
#
# This script must not:
#   install software, update drivers, change permissions, change environment
#   variables, modify the registry, change power settings, or flash LimeSDR
#   firmware or gateware.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$AuditRoot = "C:\phoenix-sdr-dsp\audit"
$AuditFile = Join-Path $AuditRoot "windows_audit.txt"
$ScriptStart = Get-Date
$ScriptVersion = "phoenix-sdr-dsp-milestone-0-windows-audit-2026-08-14"

$XrtSearchRoots = @(
    "C:\Xilinx\XRT",
    "C:\Xilinx\xrt",
    "C:\Technical\XRT",
    "C:\Technical\xrtNPUfromDLL",
    "C:\Program Files\Xilinx\XRT",
    "C:\Program Files (x86)\Xilinx\XRT",
    "C:\Windows\System32\AMD",
    "C:\Windows\System32"
)

$MlirSearchRoots = @(
    "C:\dev\mlir-aie",
    "C:\Technical\mlir-aie",
    "C:\phoenix-sdr-dsp\third_party\mlir-aie",
    "C:\src\mlir-aie",
    (Join-Path $env:USERPROFILE "mlir-aie"),
    (Join-Path $env:USERPROFILE "source\mlir-aie"),
    (Join-Path $env:USERPROFILE "dev\mlir-aie")
)

$PeanoSearchRoots = @(
    "C:\Xilinx\llvm-aie",
    "C:\dev\llvm-aie",
    "C:\Technical\llvm-aie",
    (Join-Path $env:USERPROFILE "llvm-aie")
)

$LimeSearchRoots = @(
    "C:\Program Files\PothosSDR",
    "C:\Program Files\Lime Suite",
    "C:\Program Files\LimeSuite",
    "C:\Program Files\myriadrf",
    "C:\Program Files (x86)\PothosSDR",
    "C:\Program Files (x86)\Lime Suite",
    "C:\Program Files (x86)\LimeSuite"
)

$RelevantEnvNames = @(
    "PATH",
    "PATHEXT",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "XILINX_XRT",
    "XRT_PATH",
    "XRT_INSTALL_DIR",
    "MLIR_AIE_INSTALL_DIR",
    "PEANO_INSTALL_DIR",
    "AIETOOLS_ROOT",
    "IRON_ROOT",
    "AIE_ROOT",
    "SOAPY_SDR_ROOT",
    "SOAPY_SDR_PLUGIN_PATH",
    "LIME_SUITE_ROOT",
    "LIMESUITE_ROOT",
    "GNU_RADIO_PATH",
    "VSINSTALLDIR",
    "VCINSTALLDIR",
    "WindowsSdkDir",
    "WindowsSDKVersion",
    "INCLUDE",
    "LIB",
    "LIBPATH"
)

$NpuKeywords = @(
    "NPU",
    "XDNA",
    "IPU",
    "Ryzen AI",
    "Neural",
    "AMD IPU",
    "Compute Accelerator"
)

$AmdDeviceKeywords = @(
    "AMD",
    "Advanced Micro Devices",
    "Radeon",
    "Ryzen",
    "XDNA",
    "NPU",
    "IPU",
    "Graphics",
    "Audio"
)

$LimeVidPids = @(
    "VID_1D50&PID_6108",
    "VID_1D50&PID_610A",
    "VID_04B4&PID_00F1",
    "VID_04B4&PID_00F3",
    "VID_0403&PID_601F",
    "VID_1D50",
    "LimeSDR",
    "Lime",
    "Myriad",
    "LMS7002"
)

function New-AuditDirectory {
    if (-not (Test-Path -LiteralPath $AuditRoot)) {
        New-Item -ItemType Directory -Path $AuditRoot -Force | Out-Null
    }
}

function Write-Audit {
    param(
        [Parameter(ValueFromPipeline = $true)]
        [AllowNull()]
        [object]$Line
    )
    process {
        if ($null -eq $Line) {
            $text = ""
        }
        else {
            $text = [string]$Line
        }
        Add-Content -LiteralPath $AuditFile -Value $text -Encoding utf8
    }
}

function Write-Section {
    param([string]$Title)
    Write-Audit ""
    Write-Audit ("=" * 78)
    Write-Audit $Title
    Write-Audit ("=" * 78)
}

function Write-Subsection {
    param([string]$Title)
    Write-Audit ""
    Write-Audit ("--- " + $Title + " ---")
}

function Invoke-SafeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [int]$MaxChars = 20000
    )
    Write-Subsection $Label
    try {
        $raw = & $Command 2>&1
        if ($null -eq $raw) {
            Write-Audit "(no output)"
            return
        }
        $text = ($raw | Out-String)
        if ([string]::IsNullOrWhiteSpace($text)) {
            Write-Audit "(empty output)"
            return
        }
        if ($text.Length -gt $MaxChars) {
            Write-Audit ($text.Substring(0, $MaxChars))
            Write-Audit ("(truncated after " + $MaxChars + " characters)")
        }
        else {
            Write-Audit $text.TrimEnd()
        }
    }
    catch {
        Write-Audit ("ERROR: " + $_.Exception.Message)
    }
}

function Get-CommandPath {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

function Test-PythonModule {
    param(
        [string]$PythonExe,
        [string]$ModuleName
    )
    try {
        $code = "import importlib.util,sys; spec=importlib.util.find_spec('$ModuleName'); print('FOUND' if spec else 'MISSING'); print(getattr(spec,'origin',''))"
        $out = & $PythonExe -c $code 2>&1 | Out-String
        return $out.Trim()
    }
    catch {
        return ("ERROR: " + $_.Exception.Message)
    }
}

function Get-FileVersionSafe {
    param([string]$Path)
    try {
        if (Test-Path -LiteralPath $Path) {
            $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
            return ("FileVersion=" + $info.FileVersion + "; ProductVersion=" + $info.ProductVersion + "; ProductName=" + $info.ProductName)
        }
    }
    catch {
        return ("ERROR: " + $_.Exception.Message)
    }
    return "not found"
}

function Get-PnpDetails {
    param([object]$Device)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("Name: $($Device.FriendlyName)")
    $lines.Add("Status: $($Device.Status)")
    $lines.Add("Class: $($Device.Class)")
    $lines.Add("InstanceId: $($Device.InstanceId)")
    $lines.Add("Manufacturer: $($Device.Manufacturer)")
    $propertyIds = @(
        "DEVPKEY_Device_DriverVersion",
        "DEVPKEY_Device_DriverDate",
        "DEVPKEY_Device_DriverProvider",
        "DEVPKEY_Device_DriverDesc",
        "DEVPKEY_Device_HardwareIds",
        "DEVPKEY_Device_LocationInfo",
        "DEVPKEY_Device_Service",
        "DEVPKEY_Device_EnumeratorName"
    )
    foreach ($propertyId in $propertyIds) {
        try {
            $prop = Get-PnpDeviceProperty -InstanceId $Device.InstanceId -KeyName $propertyId -ErrorAction SilentlyContinue
            if ($prop -and $null -ne $prop.Data) {
                $data = $prop.Data
                if ($data -is [array]) {
                    $data = ($data -join "; ")
                }
                $lines.Add(($propertyId + ": " + $data))
            }
        }
        catch {
            $lines.Add(($propertyId + ": ERROR " + $_.Exception.Message))
        }
    }
    return $lines
}

New-AuditDirectory
Set-Content -LiteralPath $AuditFile -Value "" -Encoding utf8

Write-Audit "Phoenix SDR-DSP Milestone 0 Windows Audit"
Write-Audit ("Script version: " + $ScriptVersion)
Write-Audit ("Generated: " + $ScriptStart.ToString("yyyy-MM-dd HH:mm:ss zzz"))
Write-Audit "Mode: read-only inventory. No software, drivers, firmware, or settings were changed."
Write-Audit "Output file: C:\phoenix-sdr-dsp\audit\windows_audit.txt"

Write-Section "1. Windows edition, version, and build"
Invoke-SafeCommand "systeminfo filtered" {
    systeminfo | Select-String -Pattern "OS Name|OS Version|OS Manufacturer|OS Configuration|OS Build Type|System Type|Processor|Total Physical Memory|Available Physical Memory|Virtual Memory|Hotfix|System Locale|Input Locale|Time Zone"
}
Invoke-SafeCommand "Get-ComputerInfo selected fields" {
    Get-ComputerInfo | Select-Object WindowsProductName, WindowsEditionId, WindowsInstallationType, WindowsVersion, OsName, OsVersion, OsBuildNumber, OsHardwareAbstractionLayer, OsArchitecture, CsName, CsProcessors, CsNumberOfLogicalProcessors, CsPhyicallyInstalledMemory, CsTotalPhysicalMemory
}
Invoke-SafeCommand "Current Windows version registry" {
    Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" | Select-Object ProductName, DisplayVersion, CurrentBuild, CurrentBuildNumber, UBR, BuildLabEx, ReleaseId, CompositionEditionID, EditionID, InstallationType
}
Invoke-SafeCommand "PowerShell version" {
    $PSVersionTable
}

Write-Section "2. CPU and memory"
Invoke-SafeCommand "Win32_Processor" {
    Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, DeviceID, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, AddressWidth, Architecture, SocketDesignation, ProcessorId, Caption
}
Invoke-SafeCommand "Win32_ComputerSystem memory" {
    Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, TotalPhysicalMemory, NumberOfProcessors, NumberOfLogicalProcessors, HypervisorPresent, SystemType
}
Invoke-SafeCommand "Win32_PhysicalMemory modules" {
    Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel, DeviceLocator, Manufacturer, PartNumber, SerialNumber, Speed, ConfiguredClockSpeed, Capacity, DeviceLocator, FormFactor, MemoryType, SMBIOSMemoryType
}
Invoke-SafeCommand "OperatingSystem memory counters" {
    Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory, TotalVirtualMemorySize, FreeVirtualMemory
}

Write-Section "3. AMD NPU and related system devices"
Invoke-SafeCommand "PnP devices matching NPU/XDNA/IPU/Neural keywords" {
    $devices = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
    $hits = foreach ($device in $devices) {
        $blob = (($device.FriendlyName, $device.InstanceId, $device.Class, $device.Manufacturer) -join " ")
        foreach ($keyword in $NpuKeywords) {
            if ($blob -like ("*" + $keyword + "*")) {
                $device
                break
            }
        }
    }
    if (-not $hits) {
        "No present PnP device matched NPU/XDNA/IPU/Neural keywords."
    }
    else {
        foreach ($hit in $hits | Sort-Object InstanceId -Unique) {
            Get-PnpDetails -Device $hit
            ""
        }
    }
}
Invoke-SafeCommand "All present AMD-related PnP devices" {
    $devices = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
    $hits = foreach ($device in $devices) {
        $blob = (($device.FriendlyName, $device.InstanceId, $device.Class, $device.Manufacturer) -join " ")
        foreach ($keyword in $AmdDeviceKeywords) {
            if ($blob -like ("*" + $keyword + "*")) {
                "{0} | {1} | {2} | {3}" -f $device.Status, $device.Class, $device.FriendlyName, $device.InstanceId
                break
            }
        }
    }
    if (-not $hits) { "No AMD-related present devices were found." } else { $hits }
}
Invoke-SafeCommand "ComputeAccelerator class devices" {
    Get-PnpDevice -Class ComputeAccelerator -ErrorAction SilentlyContinue | Format-List *
}
Invoke-SafeCommand "SoftwareComponent and System devices mentioning AMD NPU" {
    Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
        $_.FriendlyName -match "NPU|XDNA|IPU|Ryzen AI" -or $_.InstanceId -match "NPU|XDNA|IPU"
    } | Select-Object Status, Class, FriendlyName, InstanceId, Manufacturer
}

Write-Section "4. Windows XRT SDK, xrt-smi, and pyxrt"
Invoke-SafeCommand "xrt-smi on PATH" {
    $path = Get-CommandPath "xrt-smi"
    if ($path) { "xrt-smi PATH location: $path" } else { "xrt-smi is not on PATH." }
}
Invoke-SafeCommand "Known xrt-smi and XRT file locations" {
    $candidates = @(
        "C:\Windows\System32\AMD\xrt-smi.exe",
        "C:\Windows\System32\xrt-smi.exe",
        "C:\Xilinx\XRT\bin\xrt-smi.exe",
        "C:\Xilinx\XRT\xrt-smi.exe",
        "C:\Windows\System32\AMD\xrt_coreutil.dll",
        "C:\Windows\System32\xrt_coreutil.dll",
        "C:\Xilinx\XRT\include\xrt.h",
        "C:\Xilinx\XRT\include\xrt\xrt_kernel.h",
        "C:\Xilinx\XRT\lib\xrt_coreutil.lib",
        "C:\Technical\xrtNPUfromDLL\xrt_coreutil.dll",
        "C:\Technical\xrtNPUfromDLL\xrt_coreutil.lib",
        "C:\Technical\xrtNPUfromDLL\xrt_coreutil.def"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $item = Get-Item -LiteralPath $candidate
            $ver = Get-FileVersionSafe $candidate
            "FOUND  $candidate  Size=$($item.Length)  LastWriteTime=$($item.LastWriteTime)  $ver"
        }
        else {
            "MISSING $candidate"
        }
    }
}
Invoke-SafeCommand "Recursive XRT-looking directories" {
    foreach ($root in $XrtSearchRoots) {
        if (Test-Path -LiteralPath $root) {
            "EXISTS $root"
            Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | Select-Object Mode, Length, LastWriteTime, Name | Format-Table -AutoSize | Out-String
        }
        else {
            "MISSING $root"
        }
    }
}
Invoke-SafeCommand "xrt-smi examine if present" {
    $exe = @(
        "C:\Windows\System32\AMD\xrt-smi.exe",
        "C:\Windows\System32\xrt-smi.exe",
        "C:\Xilinx\XRT\bin\xrt-smi.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $pathExe = Get-CommandPath "xrt-smi"
    if (-not $exe -and $pathExe) { $exe = $pathExe }
    if (-not $exe) {
        "xrt-smi.exe was not found. Not executed."
    }
    else {
        "Executing: `"$exe`" examine"
        & $exe examine 2>&1
    }
}
Invoke-SafeCommand "xrt-smi version if present" {
    $exe = @(
        "C:\Windows\System32\AMD\xrt-smi.exe",
        "C:\Windows\System32\xrt-smi.exe",
        "C:\Xilinx\XRT\bin\xrt-smi.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $pathExe = Get-CommandPath "xrt-smi"
    if (-not $exe -and $pathExe) { $exe = $pathExe }
    if (-not $exe) {
        "xrt-smi.exe was not found. Not executed."
    }
    else {
        & $exe version 2>&1
        & $exe --version 2>&1
    }
}

Write-Section "5. Python, conda, and pyxrt"
Invoke-SafeCommand "python launchers on PATH" {
    foreach ($name in @("python", "python3", "py", "pip", "pip3")) {
        $path = Get-CommandPath $name
        if ($path) { "$name -> $path" } else { "$name -> not on PATH" }
    }
}
Invoke-SafeCommand "py launcher list" {
    $py = Get-CommandPath "py"
    if ($py) { & $py -0p 2>&1 } else { "py launcher not found." }
}
Invoke-SafeCommand "Common Python executables" {
    $pythons = @(
        "C:\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Program Files\Python313\python.exe",
        "C:\Program Files\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:USERPROFILE\miniforge3\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe",
        "C:\ProgramData\miniforge3\python.exe",
        "C:\ProgramData\miniconda3\python.exe"
    )
    $found = @()
    foreach ($python in $pythons) {
        if (Test-Path -LiteralPath $python) {
            $found += $python
            $ver = & $python --version 2>&1 | Out-String
            "FOUND $python  $($ver.Trim())"
        }
    }
    $pathPython = Get-CommandPath "python"
    if ($pathPython -and ($found -notcontains $pathPython)) {
        $ver = & $pathPython --version 2>&1 | Out-String
        "PATH  $pathPython  $($ver.Trim())"
        $found += $pathPython
    }
    if (-not $found) { "No common Python interpreters were found." }
}
Invoke-SafeCommand "pyxrt import checks" {
    $interpreters = @()
    foreach ($name in @("python", "python3")) {
        $path = Get-CommandPath $name
        if ($path) { $interpreters += $path }
    }
    $py = Get-CommandPath "py"
    if ($py) {
        $pyList = & $py -0p 2>&1
        foreach ($line in $pyList) {
            if ($line -match "([A-Za-z]:\\[^\s]+python.exe)") {
                $interpreters += $Matches[1]
            }
        }
    }
    $interpreters = $interpreters | Select-Object -Unique
    if (-not $interpreters) {
        "No Python interpreters available for pyxrt import checks."
    }
    else {
        foreach ($interpreter in $interpreters) {
            "Interpreter: $interpreter"
            "  version: " + ((& $interpreter --version 2>&1) | Out-String).Trim()
            "  pyxrt: " + (Test-PythonModule -PythonExe $interpreter -ModuleName "pyxrt")
            "  numpy: " + (Test-PythonModule -PythonExe $interpreter -ModuleName "numpy")
            "  aie: " + (Test-PythonModule -PythonExe $interpreter -ModuleName "aie")
            "  mlir_aie: " + (Test-PythonModule -PythonExe $interpreter -ModuleName "mlir_aie")
            "  iron: " + (Test-PythonModule -PythonExe $interpreter -ModuleName "iron")
        }
    }
}
Invoke-SafeCommand "Conda and Miniforge" {
    foreach ($name in @("conda", "mamba", "micromamba")) {
        $path = Get-CommandPath $name
        if ($path) {
            "$name -> $path"
            & $path --version 2>&1
            & $path info 2>&1
            & $path env list 2>&1
        }
        else {
            "$name -> not on PATH"
        }
    }
    foreach ($root in @(
            "$env:USERPROFILE\miniforge3",
            "$env:USERPROFILE\miniconda3",
            "$env:USERPROFILE\anaconda3",
            "C:\ProgramData\miniforge3",
            "C:\ProgramData\miniconda3",
            "C:\ProgramData\anaconda3"
        )) {
        if (Test-Path -LiteralPath $root) { "EXISTS $root" } else { "MISSING $root" }
    }
}

Write-Section "6. Visual Studio, MSVC, Windows SDK, CMake, Ninja, Git"
Invoke-SafeCommand "vswhere" {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        & $vswhere -all -prerelease -format json 2>&1
    }
    else {
        "vswhere.exe not found at $vswhere"
    }
}
Invoke-SafeCommand "Visual Studio install roots" {
    $roots = @(
        "C:\Program Files\Microsoft Visual Studio\2026",
        "C:\Program Files\Microsoft Visual Studio\2022",
        "C:\Program Files (x86)\Microsoft Visual Studio\2022",
        "C:\Program Files (x86)\Microsoft Visual Studio\2019"
    )
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            "EXISTS $root"
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object { "  " + $_.FullName }
        }
        else {
            "MISSING $root"
        }
    }
}
Invoke-SafeCommand "cl.exe discovery via vswhere" {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($installPath) {
            "VS installationPath: $installPath"
            $aux = Join-Path $installPath "VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt"
            if (Test-Path -LiteralPath $aux) {
                $toolsVersion = (Get-Content -LiteralPath $aux -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
                "MSVC tools version file: $toolsVersion"
                $cl = Join-Path $installPath ("VC\Tools\MSVC\" + $toolsVersion + "\bin\Hostx64\x64\cl.exe")
                if (Test-Path -LiteralPath $cl) {
                    "FOUND $cl"
                    & $cl 2>&1 | Select-Object -First 3
                }
                else {
                    "MISSING $cl"
                }
            }
        }
        else {
            "vswhere did not return a Visual C++ installation path."
        }
    }
    else {
        "vswhere.exe not found."
    }
}
Invoke-SafeCommand "Windows SDK versions" {
    $sdkRoot = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Microsoft SDKs\Windows\v10.0"
    if (Test-Path $sdkRoot) {
        Get-ItemProperty $sdkRoot | Select-Object ProductName, InstallationFolder, ProductVersion
    }
    else {
        "Windows 10/11 SDK registry key not found."
    }
    $includeRoot = "C:\Program Files (x86)\Windows Kits\10\Include"
    if (Test-Path -LiteralPath $includeRoot) {
        Get-ChildItem -LiteralPath $includeRoot -Directory | Select-Object Name, FullName
    }
    else {
        "MISSING $includeRoot"
    }
}
Invoke-SafeCommand "CMake, Ninja, Git, clang, winget" {
    foreach ($name in @("cmake", "ninja", "git", "clang", "clang-cl", "lld", "winget")) {
        $path = Get-CommandPath $name
        if ($path) {
            "$name -> $path"
            & $path --version 2>&1 | Select-Object -First 5
        }
        else {
            "$name -> not on PATH"
        }
    }
}

Write-Section "7. MLIR-AIE, IRON, Peano / LLVM-AIE"
Invoke-SafeCommand "Compiler and IRON tools on PATH" {
    foreach ($name in @("aie-opt", "aie-translate", "aiecc.py", "clang++", "llc", "llvm-aie", "peano")) {
        $path = Get-CommandPath $name
        if ($path) { "$name -> $path" } else { "$name -> not on PATH" }
    }
}
Invoke-SafeCommand "Known mlir-aie checkout locations" {
    foreach ($root in $MlirSearchRoots) {
        if (Test-Path -LiteralPath $root) {
            "EXISTS $root"
            $gitHead = Join-Path $root ".git"
            if (Test-Path -LiteralPath $gitHead) {
                Push-Location $root
                try {
                    "  git remote: " + (git remote -v 2>&1 | Out-String).Trim()
                    "  git describe: " + (git describe --always --dirty --tags 2>&1 | Out-String).Trim()
                    "  git log -1: " + (git log -1 --oneline 2>&1 | Out-String).Trim()
                    "  git branch: " + (git branch --show-current 2>&1 | Out-String).Trim()
                }
                finally {
                    Pop-Location
                }
            }
            foreach ($marker in @("utils\iron_setup.py", "utils\iron_env.cmd", "iron_env.cmd", "iron_env.ps1", "python\requirements.txt", "programming_examples\getting_started\01_SAXPY\saxpy.py")) {
                $path = Join-Path $root $marker
                if (Test-Path -LiteralPath $path) { "  FOUND $path" } else { "  MISSING $path" }
            }
        }
        else {
            "MISSING $root"
        }
    }
}
Invoke-SafeCommand "Known Peano / llvm-aie locations" {
    foreach ($root in $PeanoSearchRoots) {
        if (Test-Path -LiteralPath $root) { "EXISTS $root" } else { "MISSING $root" }
    }
}
Invoke-SafeCommand "pip show for IRON-related packages using default python" {
    $python = Get-CommandPath "python"
    if ($python) {
        foreach ($pkg in @("mlir_aie", "llvm-aie", "aie", "iron", "pyxrt")) {
            & $python -m pip show $pkg 2>&1
            ""
        }
    }
    else {
        "python not on PATH; pip show skipped."
    }
}

Write-Section "8. Lime Suite, SoapySDR, GNU Radio, and LimeSDR hardware"
Invoke-SafeCommand "SDR tools on PATH" {
    foreach ($name in @("LimeUtil", "LimeUtil.exe", "LimeSuiteNG", "SoapySDRUtil", "SoapySDRUtil.exe", "gnuradio-config-info", "limeSDR")) {
        $path = Get-CommandPath $name
        if ($path) { "$name -> $path" } else { "$name -> not on PATH" }
    }
}
Invoke-SafeCommand "Known SDR install trees" {
    foreach ($root in $LimeSearchRoots) {
        if (Test-Path -LiteralPath $root) {
            "EXISTS $root"
            Get-ChildItem -LiteralPath $root -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match "Lime|Soapy|LMS|GNU" } |
                Select-Object FullName, Length, LastWriteTime
        }
        else {
            "MISSING $root"
        }
    }
}
Invoke-SafeCommand "LimeUtil --find / --info if present" {
    $exe = Get-CommandPath "LimeUtil"
    if (-not $exe) { $exe = Get-CommandPath "LimeUtil.exe" }
    if (-not $exe) {
        $guesses = @(
            "C:\Program Files\PothosSDR\bin\LimeUtil.exe",
            "C:\Program Files\Lime Suite\bin\LimeUtil.exe",
            "C:\Program Files (x86)\PothosSDR\bin\LimeUtil.exe"
        )
        $exe = $guesses | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $exe) {
        "LimeUtil was not found. Device enumeration via LimeUtil was skipped."
    }
    else {
        "Executing `"$exe`" --help"
        & $exe --help 2>&1 | Select-Object -First 40
        "Executing `"$exe`" --find"
        & $exe --find 2>&1
        "Executing `"$exe`" --info"
        & $exe --info 2>&1
    }
}
Invoke-SafeCommand "SoapySDRUtil if present" {
    $exe = Get-CommandPath "SoapySDRUtil"
    if (-not $exe) { $exe = Get-CommandPath "SoapySDRUtil.exe" }
    if (-not $exe) {
        $guesses = @(
            "C:\Program Files\PothosSDR\bin\SoapySDRUtil.exe",
            "C:\Program Files (x86)\PothosSDR\bin\SoapySDRUtil.exe"
        )
        $exe = $guesses | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $exe) {
        "SoapySDRUtil was not found."
    }
    else {
        "Executing `"$exe`" --info"
        & $exe --info 2>&1
        "Executing `"$exe`" --find"
        & $exe --find 2>&1
        "Executing `"$exe`" --probe"
        & $exe --probe 2>&1
    }
}
Invoke-SafeCommand "PnP and USB devices matching LimeSDR identifiers" {
    $devices = Get-PnpDevice -ErrorAction SilentlyContinue
    $hits = foreach ($device in $devices) {
        $blob = (($device.FriendlyName, $device.InstanceId, $device.Manufacturer, $device.Class) -join " ")
        foreach ($keyword in $LimeVidPids) {
            if ($blob -like ("*" + $keyword + "*")) {
                Get-PnpDetails -Device $device
                ""
                break
            }
        }
    }
    if (-not $hits) {
        "No PnP device matched LimeSDR VID/PID or name keywords. This is not proof that no device is attached; some FX3/WinUSB devices enumerate under generic names."
    }
    else {
        $hits
    }
}
Invoke-SafeCommand "USB controllers and USB devices" {
    Get-CimInstance Win32_USBController | Select-Object Name, DeviceID, Manufacturer, Status, PNPDeviceID
    ""
    Get-PnpDevice -Class USB -ErrorAction SilentlyContinue | Select-Object Status, Class, FriendlyName, InstanceId
}
Invoke-SafeCommand "USB hub negotiated-speed hints from PnP" {
    $usb = Get-PnpDevice -Class USB -ErrorAction SilentlyContinue
    foreach ($device in $usb) {
        try {
            $speed = Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_BusReportedDeviceDesc" -ErrorAction SilentlyContinue
            $loc = Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_LocationInfo" -ErrorAction SilentlyContinue
            $addr = Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_Address" -ErrorAction SilentlyContinue
            "{0} | {1} | Location={2} | Address={3} | BusReported={4}" -f $device.Status, $device.FriendlyName, $loc.Data, $addr.Data, $speed.Data
        }
        catch {
            "{0} | {1} | property read error: {2}" -f $device.Status, $device.FriendlyName, $_.Exception.Message
        }
    }
}
Invoke-SafeCommand "GNU Radio presence" {
    foreach ($name in @("gnuradio-config-info", "gnuradio-companion", "gr_modtool")) {
        $path = Get-CommandPath $name
        if ($path) {
            "$name -> $path"
            & $path --version 2>&1
        }
        else {
            "$name -> not on PATH"
        }
    }
    foreach ($root in @(
            "C:\Program Files\GNURadio-3.10",
            "C:\Program Files\GNURadio",
            "C:\Program Files\PothosSDR"
        )) {
        if (Test-Path -LiteralPath $root) { "EXISTS $root" } else { "MISSING $root" }
    }
}

Write-Section "9. Disk space and relevant environment variables"
Invoke-SafeCommand "Logical disks" {
    Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID, VolumeName, FileSystem, DriveType, @{n = "SizeGB"; e = { [math]::Round($_.Size / 1GB, 2) } }, @{n = "FreeGB"; e = { [math]::Round($_.FreeSpace / 1GB, 2) } }
}
Invoke-SafeCommand "Project root and audit directory" {
    foreach ($path in @("C:\phoenix-sdr-dsp", "C:\phoenix-sdr-dsp\audit")) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            "EXISTS $path  Attributes=$($item.Attributes)  Created=$($item.CreationTime)"
        }
        else {
            "MISSING $path"
        }
    }
}
Invoke-SafeCommand "Selected environment variables" {
    foreach ($name in $RelevantEnvNames) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrEmpty($value)) {
            "$name=<unset in this process>"
        }
        else {
            "$name=$value"
        }
    }
}
Invoke-SafeCommand "User and machine environment variable names containing XRT, AIE, IRON, SOAPY, LIME, PYTHON" {
    $targets = @("XRT", "AIE", "IRON", "SOAPY", "LIME", "PYTHON", "XILINX", "PEANO", "MLIR")
    foreach ($scope in @("User", "Machine")) {
        $vars = [Environment]::GetEnvironmentVariables($scope)
        foreach ($key in $vars.Keys) {
            foreach ($target in $targets) {
                if ($key -like ("*" + $target + "*")) {
                    "{0}: {1}={2}" -f $scope, $key, $vars[$key]
                    break
                }
            }
        }
    }
}

Write-Section "10. WSL presence from Windows"
Invoke-SafeCommand "wsl --status / --list" {
    $wsl = Get-CommandPath "wsl"
    if (-not $wsl) {
        "wsl.exe not on PATH."
    }
    else {
        "wsl -> $wsl"
        & $wsl --status 2>&1
        & $wsl -l -v 2>&1
        & $wsl --version 2>&1
    }
}

Write-Section "11. Audit integrity"
$ScriptEnd = Get-Date
Write-Audit ("Start: " + $ScriptStart.ToString("yyyy-MM-dd HH:mm:ss zzz"))
Write-Audit ("End:   " + $ScriptEnd.ToString("yyyy-MM-dd HH:mm:ss zzz"))
Write-Audit ("Elapsed seconds: " + [math]::Round(($ScriptEnd - $ScriptStart).TotalSeconds, 2))
Write-Audit ("Host: " + $env:COMPUTERNAME)
Write-Audit ("User: " + $env:USERNAME)
Write-Audit ("Process architecture: " + [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture)
Write-Audit ("OS architecture: " + [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)
Write-Audit "The script created only C:\phoenix-sdr-dsp\audit and windows_audit.txt."
Write-Audit "No drivers, packages, firmware, registry values, or environment variables were modified."
Write-Audit "END OF WINDOWS AUDIT"

Write-Output "Wrote $AuditFile"
