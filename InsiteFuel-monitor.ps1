$ErrorActionPreference = "SilentlyContinue"

$interval = 2

while ($true) {
    $cpu = (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples[0].CookedValue

    $os = Get-CimInstance Win32_OperatingSystem
    $ramTotal = [double]$os.TotalVisibleMemorySize / 1MB
    $ramFree = [double]$os.FreePhysicalMemory / 1MB
    $ramUsed = $ramTotal - $ramFree
    $ramPct = ($ramUsed / $ramTotal) * 100

    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"

    $gpuSamples = Get-Counter '\GPU Engine(*)\Utilization Percentage' |
        Select-Object -ExpandProperty CounterSamples
    $gpu = ($gpuSamples | Measure-Object CookedValue -Sum).Sum
    if ($gpu -gt 100) { $gpu = 100 }
    if (-not $gpu) { $gpu = 0 }

    $gpuName = (Get-CimInstance Win32_VideoController |
        Select-Object -First 1 -ExpandProperty Name)
    if (-not $gpuName) { $gpuName = "Not detected" }

    $net = Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface |
        Where-Object { $_.Name -notmatch "Loopback|Teredo" }

    $rxMbps = 0
    $txMbps = 0
    foreach ($n in $net) {
        $rxMbps += [double]$n.BytesReceivedPerSec * 8 / 1MB
        $txMbps += [double]$n.BytesSentPerSec * 8 / 1MB
    }

    $portListening = $false
    try {
        $portListening = [bool](Get-NetTCPConnection -LocalPort 8010 -State Listen)
    } catch {}

    Clear-Host
    Write-Host "============================================================"
    Write-Host "              INSITEFUEL SERVER MONITOR"
    Write-Host "============================================================"
    Write-Host (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Write-Host ""

    Write-Host "CPU"
    Write-Host (" Usage:       {0,6:N1} %" -f $cpu)
    Write-Host ""

    Write-Host "MEMORY"
    Write-Host (" Used:        {0,6:N1} GB / {1:N1} GB   ({2:N1} %)" -f $ramUsed, $ramTotal, $ramPct)
    Write-Host ""

    Write-Host "GPU"
    Write-Host (" Usage:       {0,6:N1} %" -f $gpu)
    Write-Host (" Device:      {0}" -f $gpuName)
    Write-Host ""

    Write-Host "NETWORK"
    Write-Host (" Download:    {0,8:N2} Mbps" -f $rxMbps)
    Write-Host (" Upload:      {0,8:N2} Mbps" -f $txMbps)
    Write-Host ""

    Write-Host "DISK"
    foreach ($d in $disk) {
        $used = if ($d.Size) { (1 - ($d.FreeSpace / $d.Size)) * 100 } else { 0 }
        Write-Host (" {0}            {1,6:N1} %" -f $d.DeviceID, $used)
    }
    Write-Host ""

    Write-Host "INSITEFUEL"
    Write-Host (" Port 8010:   {0}" -f ($(if ($portListening) { "LISTENING" } else { "NOT LISTENING" })))
    Write-Host ""

    Write-Host "============================================================"
    Write-Host "Refreshing every $interval seconds. Press Ctrl+C to exit."

    Start-Sleep -Seconds $interval
}
