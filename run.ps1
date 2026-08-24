[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$SkipDisplaySetup,
    [switch]$SkipHardwareCheck,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ApplicationArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-RunnerLog {
    param([string]$Message)

    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] [runner] $Message"
}

function Assert-ProductionHardware {
    Write-RunnerLog "Validate hardware configuration"

    $gpu = Get-CimInstance -ClassName Win32_VideoController |
        Where-Object { $_.Name -match "RTX\s*3050" } |
        Select-Object -First 1
    if ($null -eq $gpu) {
        $detectedGpu = (Get-CimInstance -ClassName Win32_VideoController | Select-Object -ExpandProperty Name) -join ", "
        throw "Unsupported GPU. Detected: $detectedGpu"
    }

    $computer = Get-CimInstance -ClassName Win32_ComputerSystem
    $memoryGb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
    if ($computer.TotalPhysicalMemory -lt 7.5GB) {
        throw "At least 8 GB of system memory is required. Detected: $memoryGb GB"
    }

    Write-RunnerLog "GPU detected: $($gpu.Name)"
    Write-RunnerLog "RAM: $memoryGb GB"

    $monitor = Get-CimInstance -Namespace "root\wmi" -ClassName WmiMonitorBasicDisplayParams -ErrorAction SilentlyContinue |
        Where-Object { $_.Active -and $_.MaxHorizontalImageSize -gt 0 -and $_.MaxVerticalImageSize -gt 0 } |
        Select-Object -First 1
    if ($null -eq $monitor) {
        Write-RunnerLog "Monitor size could not be read from EDID. Confirm that the installed panel is at least 24in."
        return
    }

    $diagonalInches = [math]::Sqrt(
        [math]::Pow($monitor.MaxHorizontalImageSize, 2) +
        [math]::Pow($monitor.MaxVerticalImageSize, 2)
    ) / 2.54
    $diagonalInches = [math]::Round($diagonalInches, 1)
    if ($diagonalInches -lt 23.0 -or $diagonalInches -gt 25.0) {
        Write-RunnerLog "Monitor size is $diagonalInches inches; the production target is 24 inches."
        return
    }

    Write-RunnerLog "Monitor size detected: $diagonalInches inches"
}

function Set-ProductionDisplay {
    if (-not ("SmushDisplay" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct SmushDevMode
{
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string dmDeviceName;
    public ushort dmSpecVersion;
    public ushort dmDriverVersion;
    public ushort dmSize;
    public ushort dmDriverExtra;
    public uint dmFields;
    public int dmPositionX;
    public int dmPositionY;
    public uint dmDisplayOrientation;
    public uint dmDisplayFixedOutput;
    public short dmColor;
    public short dmDuplex;
    public short dmYResolution;
    public short dmTTOption;
    public short dmCollate;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string dmFormName;
    public ushort dmLogPixels;
    public uint dmBitsPerPel;
    public uint dmPelsWidth;
    public uint dmPelsHeight;
    public uint dmDisplayFlags;
    public uint dmDisplayFrequency;
    public uint dmICMMethod;
    public uint dmICMIntent;
    public uint dmMediaType;
    public uint dmDitherType;
    public uint dmReserved1;
    public uint dmReserved2;
    public uint dmPanningWidth;
    public uint dmPanningHeight;
}

public static class SmushDisplay
{
    private const int EnumCurrentSettings = -1;
    private const uint DmPelsWidth = 0x00080000;
    private const uint DmPelsHeight = 0x00100000;
    private const uint DmDisplayOrientation = 0x00000080;
    private const uint Portrait = 1;
    private const uint UpdateRegistry = 0x00000001;

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplaySettings(
        string deviceName,
        int modeNumber,
        ref SmushDevMode devMode
    );

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int ChangeDisplaySettingsEx(
        string deviceName,
        ref SmushDevMode devMode,
        IntPtr window,
        uint flags,
        IntPtr parameters
    );

    private static SmushDevMode CurrentMode()
    {
        SmushDevMode mode = new SmushDevMode();
        mode.dmSize = (ushort)Marshal.SizeOf(typeof(SmushDevMode));
        if (!EnumDisplaySettings(null, EnumCurrentSettings, ref mode))
        {
            throw new InvalidOperationException("The primary display mode could not be read.");
        }
        return mode;
    }

    public static void SetPortraitFullHd()
    {
        SmushDevMode mode = CurrentMode();
        mode.dmDisplayOrientation = Portrait;
        mode.dmPelsWidth = 1080;
        mode.dmPelsHeight = 1920;
        mode.dmFields |= DmDisplayOrientation | DmPelsWidth | DmPelsHeight;
        int result = ChangeDisplaySettingsEx(null, ref mode, IntPtr.Zero, UpdateRegistry, IntPtr.Zero);
        if (result == 1)
        {
            throw new InvalidOperationException("Windows must be restarted to apply the portrait display mode.");
        }
        if (result != 0)
        {
            throw new InvalidOperationException("Windows rejected the portrait display mode with code " + result + ".");
        }
    }

    public static string GetMode()
    {
        SmushDevMode mode = CurrentMode();
        return mode.dmPelsWidth + "x" + mode.dmPelsHeight + ", orientation " + mode.dmDisplayOrientation;
    }

    public static bool IsPortraitFullHd()
    {
        SmushDevMode mode = CurrentMode();
        return mode.dmPelsWidth == 1080 && mode.dmPelsHeight == 1920 && mode.dmDisplayOrientation == Portrait;
    }
}
"@
    }

    Write-RunnerLog "Configuring the primary display for FHD portrait mode..."
    [SmushDisplay]::SetPortraitFullHd()
    if (-not [SmushDisplay]::IsPortraitFullHd()) {
        throw "The primary display is not using 1080x1920 portrait mode. Current mode: $([SmushDisplay]::GetMode())"
    }
    Write-RunnerLog "Primary display ready: 1080x1920, portrait orientation"
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "run.ps1 requires Windows 10."
}

$projectRoot = $PSScriptRoot
$buildScript = Join-Path $projectRoot "build.bat"
$applicationPath = Join-Path $projectRoot "dist\smush\smush.exe"

if ($Build -or -not (Test-Path -LiteralPath $applicationPath -PathType Leaf)) {
    Write-RunnerLog "Building the production application..."
    & $buildScript
    if ($LASTEXITCODE -ne 0) {
        throw "The production build failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $applicationPath -PathType Leaf)) {
    throw "Production executable not found: $applicationPath"
}

if (-not $SkipHardwareCheck) {
    Assert-ProductionHardware
}

if (-not $SkipDisplaySetup) {
    Set-ProductionDisplay
}

$env:__COMPAT_LAYER = "HIGHDPIAWARE"
$applicationDirectory = Split-Path -Parent $applicationPath
Write-RunnerLog "Starting smush..."
$startParameters = @{
    FilePath = $applicationPath
    WorkingDirectory = $applicationDirectory
    PassThru = $true
    Wait = $true
}
if ($null -ne $ApplicationArguments -and $ApplicationArguments.Count -gt 0) {
    $startParameters.ArgumentList = $ApplicationArguments
}
$process = Start-Process @startParameters
Write-RunnerLog "smush exited with code $($process.ExitCode)."
exit $process.ExitCode
