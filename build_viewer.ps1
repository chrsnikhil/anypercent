# Assembles viewer.html from viewer_template.html by inlining the turntable
# sequence and the still renders as base64 JPEG data URIs.
#
# Published artifacts run under a strict CSP that blocks external image hosts,
# so every asset has to live inside the HTML itself. Frames are downscaled
# hard because they display small on a phone and total payload is what matters.

param(
    [int]$FrameSize    = 640,   # square px for turntable frames
    [int]$FrameQuality = 75,
    [int]$StillWidth   = 1000,  # px for the still gallery
    [int]$StillQuality = 80,
    [int]$FrameStride  = 1      # 2 = use every other frame, halves payload
)

Add-Type -AssemblyName System.Drawing

$root      = "C:\Users\chrsn\Desktop\retro-handheld-ethglobal"
$turnDir   = Join-Path $root "render\turntable"
$renderDir = Join-Path $root "render"
$template  = Join-Path $root "viewer_template.html"
$outFile   = Join-Path $root "viewer.html"

if (-not (Test-Path $template)) { throw "Template not found: $template" }
if (-not (Test-Path $turnDir))  { throw "Turntable folder not found: $turnDir" }

$jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
             Where-Object { $_.MimeType -eq 'image/jpeg' }

function ConvertTo-DataUri {
    param([string]$Path, [int]$MaxW, [int]$MaxH, [int]$Quality)

    $img = [System.Drawing.Image]::FromFile($Path)
    try {
        $scale = [Math]::Min($MaxW / $img.Width, $MaxH / $img.Height)
        if ($scale -gt 1) { $scale = 1 }
        $w = [int][Math]::Round($img.Width * $scale)
        $h = [int][Math]::Round($img.Height * $scale)

        $bmp = New-Object System.Drawing.Bitmap($w, $h)
        try {
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            try {
                $g.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $g.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $g.DrawImage($img, 0, 0, $w, $h)
            } finally { $g.Dispose() }

            $ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
            $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
                [System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)

            $ms = New-Object System.IO.MemoryStream
            try {
                $bmp.Save($ms, $jpegCodec, $ep)
                $bytes = $ms.ToArray()
            } finally { $ms.Dispose() }
        } finally { $bmp.Dispose() }
    } finally { $img.Dispose() }

    return @{
        Uri   = "data:image/jpeg;base64," + [Convert]::ToBase64String($bytes)
        Bytes = $bytes.Length
    }
}

# ---- turntable frames ----

# One turntable sequence per swappable rear panel. Each lives in its own
# subfolder; if the subfolders are absent we fall back to the flat legacy
# folder and publish a single-panel viewer, so a partial render still builds.
$plates = @(
    @{ Key = "WORLD"; Dir = "world"; Alt = "Handheld console with World panel, rotating view" },
    @{ Key = "0G";    Dir = "0g";    Alt = "Handheld console with 0G panel, rotating view" },
    @{ Key = "ARKIV"; Dir = "arkiv"; Alt = "Handheld console with Arkiv panel, rotating view" }
)

# NOTE: accumulators must not share a name with the param block variables.
# PowerShell variable names are case-insensitive, so $frameSize would silently
# clobber $FrameSize and pass 0 as the target dimension.
$frameBlocks = @{}
$frameBytes  = 0
$frameTotal  = 0

foreach ($plate in $plates) {
    $dir = Join-Path $turnDir $plate.Dir
    if (-not (Test-Path $dir)) {
        if ($plate.Dir -eq "world") { $dir = $turnDir } else { $dir = $null }
    }

    if (-not $dir) {
        Write-Output "  $($plate.Dir): no frames, panel will be disabled in the viewer"
        $frameBlocks[$plate.Key] = ""
        continue
    }

    $files = Get-ChildItem $dir -File | Where-Object { $_.Extension -match '^\.(png|jpe?g)$' } | Sort-Object Name
    if ($FrameStride -gt 1) {
        $files = @($files | Where-Object { ($files.IndexOf($_) % $FrameStride) -eq 0 })
    }
    if (-not $files) {
        Write-Output "  $($plate.Dir): folder present but empty, panel disabled"
        $frameBlocks[$plate.Key] = ""
        continue
    }

    $sb = New-Object System.Text.StringBuilder
    $bytes = 0
    $i = 0
    foreach ($f in $files) {
        $r = ConvertTo-DataUri -Path $f.FullName -MaxW $FrameSize -MaxH $FrameSize -Quality $FrameQuality
        $bytes += $r.Bytes
        $alt = if ($i -eq 0) { " alt=`"$($plate.Alt)`"" } else { ' alt=""' }
        [void]$sb.AppendLine("        <img src=`"$($r.Uri)`"$alt>")
        $i++
    }
    $frameBlocks[$plate.Key] = $sb.ToString().TrimEnd()
    $frameBytes += $bytes
    $frameTotal += $files.Count
    Write-Output ("  {0,-6} {1,3} frames, {2,5} KB" -f $plate.Dir, $files.Count, [math]::Round($bytes/1KB))
}

if ($frameTotal -eq 0) { throw "No turntable frames found under $turnDir" }
Write-Output ("Frames encoded: {0} total at {1}px q{2}, {3} KB" -f `
    $frameTotal, $FrameSize, $FrameQuality, [math]::Round($frameBytes/1KB))

# ---- stills ----

$stills = @(
    @{ File = "01_hero_front_three_quarter.png";  Caption = "Front three-quarter" },
    @{ File = "02_rear_world_plate_attached.png"; Caption = "Rear, World plate attached" },
    @{ File = "03_sponsor_plates_lineup.png";     Caption = "All three sponsor plates" },
    @{ File = "04_plate_rear_magnets.png";        Caption = "Plate rear, pocketed magnets" }
)

$sbStills   = New-Object System.Text.StringBuilder
$stillBytes = 0
foreach ($s in $stills) {
    $p = Join-Path $renderDir $s.File
    if (-not (Test-Path $p)) { Write-Output "  skipped (missing): $($s.File)"; continue }
    $r = ConvertTo-DataUri -Path $p -MaxW $StillWidth -MaxH 4000 -Quality $StillQuality
    $stillBytes += $r.Bytes
    [void]$sbStills.AppendLine("      <figure class=`"shot`">")
    [void]$sbStills.AppendLine("        <img src=`"$($r.Uri)`" alt=`"$($s.Caption)`">")
    [void]$sbStills.AppendLine("        <span>$($s.Caption)</span>")
    [void]$sbStills.AppendLine("      </figure>")
}
Write-Output ("Stills encoded: {0} KB total" -f [math]::Round($stillBytes/1KB))

# ---- assemble ----

$html = Get-Content $template -Raw -Encoding UTF8
foreach ($plate in $plates) {
    $html = $html.Replace("<!--FRAMES_$($plate.Key)-->", $frameBlocks[$plate.Key])
}
$html = $html.Replace("<!--STILL_SHOTS-->", $sbStills.ToString().TrimEnd())

[System.IO.File]::WriteAllText($outFile, $html, (New-Object System.Text.UTF8Encoding($false)))

$mb = [math]::Round((Get-Item $outFile).Length / 1MB, 2)
Write-Output ""
Write-Output "Wrote: $outFile"
Write-Output "Total page size: $mb MB"
