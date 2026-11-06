# Assembles stl_viewer.html from stl_viewer_template.html by inlining every
# exported STL as gzipped base64. The page decompresses in-browser via
# DecompressionStream, so no external fetch is needed - published artifacts
# run under a CSP that blocks other hosts entirely.
#
# Gzip matters here: STL is highly repetitive and typically compresses 70-80
# percent, which is the difference between a viewable page and a 20 MB one.
#
# Inputs:
#   cad2\stl\           print-oriented parts, one viewer button each
#   cad2\stl_assembly\  assembled-position components (cad2\build_assembly.sh),
#                       combined into the "Assembly" view and coloured by
#                       $AssemblyManifest below
# Outputs:
#   stl_viewer.html
#   cad2\stl_assembly\assembly_colours.json   the manifest as data, so the
#                       OpenSCAD colour renders (cad2\render_coloured.py) use
#                       exactly the same colours as the viewer

param(
    [string]$StlDir,
    [string]$AsmDir,
    [string]$AsmPanel = "world",   # rear panel shown when the assembled view opens
    [int]$MaxPageMB = 12
)

$root     = "C:\Users\chrsn\Desktop\retro-handheld-ethglobal"
$template = Join-Path $root "stl_viewer_template.html"
$outFile  = Join-Path $root "stl_viewer.html"
$inv      = [System.Globalization.CultureInfo]::InvariantCulture

# ---------------------------------------------------------------------------
# COLOUR MANIFEST for the assembled view
# ---------------------------------------------------------------------------
# One row per assembled-position STL (file name without .stl).
#   colour  sRGB hex
#   alpha   1 = opaque. Below 1 the mesh is drawn translucent, AFTER every
#           opaque mesh. The value is the opacity of ONE WALL of the part as
#           seen straight through it (e.g. 0.40 = looking through the 2.4 mm
#           face you see 40 percent smoke, 60 percent of what is behind). The
#           viewer draws both surfaces of the wall, so it splits this into a
#           per-surface alpha of 1 - sqrt(1 - alpha).
#   label   legend text
#   group   one physical sub-assembly. Every mesh in a group explodes as one
#           unit. Groups named panel:<kind> are ALTERNATIVES: only one rear
#           panel is ever fitted, and the viewer shows exactly one at a time,
#           with a switcher. Drawing two at once puts their coplanar faces at
#           identical depth and they z-fight into diagonal stripes.
#
# Brand colours are from cad2\README.md section 7 ("Colour themes").
$AssemblyManifest = [ordered]@{
    # --- body ---------------------------------------------------------------
    'asm_front_shell'      = @{ colour = '#111111'; alpha = 0.40; group = 'shell';   label = 'Front shell, smoke PLA' }
    # --- rear panels: body + raised emblem, one pair per brand --------------
    'asm_panel_world_body' = @{ colour = '#F9F9F8'; alpha = 1; group = 'panel:world'; label = 'World panel, off-white' }
    'asm_panel_world_logo' = @{ colour = '#181818'; alpha = 1; group = 'panel:world'; label = 'World emblem, near-black' }
    'asm_panel_arkiv_body' = @{ colour = '#181EA9'; alpha = 1; group = 'panel:arkiv'; label = 'Arkiv panel, Arkiv Blue' }
    'asm_panel_arkiv_logo' = @{ colour = '#F6F4EF'; alpha = 1; group = 'panel:arkiv'; label = 'Arkiv emblem, Arkiv Sand' }
    'asm_panel_arc_body'   = @{ colour = '#163756'; alpha = 1; group = 'panel:arc';   label = 'Arc panel, deep navy' }
    'asm_panel_arc_logo'   = @{ colour = '#CDDDF2'; alpha = 1; group = 'panel:arc';   label = 'Arc emblem, pale blue' }
    # --- controls: charcoal D-pad and shoulders, slate X/Y, pale START/SELECT,
    #     one warm accent on A/B (a muted World Orange) ------------------------
    'asm_cap_dpad'         = @{ colour = '#26282C'; alpha = 1; group = 'controls';  label = 'D-pad, charcoal' }
    'asm_cap_a'            = @{ colour = '#E4572E'; alpha = 1; group = 'controls';  label = 'A button, signal orange' }
    'asm_cap_b'            = @{ colour = '#E4572E'; alpha = 1; group = 'controls';  label = 'B button, signal orange' }
    'asm_cap_x'            = @{ colour = '#5F646B'; alpha = 1; group = 'controls';  label = 'X button, slate' }
    'asm_cap_y'            = @{ colour = '#5F646B'; alpha = 1; group = 'controls';  label = 'Y button, slate' }
    'asm_cap_pills'        = @{ colour = '#C9CCD1'; alpha = 1; group = 'controls';  label = 'START / SELECT, pale grey' }
    'asm_shoulders'        = @{ colour = '#26282C'; alpha = 1; group = 'shoulders'; label = 'Shoulder paddles, charcoal' }
    'asm_pins'             = @{ colour = '#E8D9A8'; alpha = 1; group = 'shoulders'; label = 'Paddle pins, 1.75 filament' }
    'asm_plate_face'       = @{ colour = '#6E747C'; alpha = 1; group = 'plates';    label = 'Switch plate, ABXY' }
    'asm_plate_dpad'       = @{ colour = '#6E747C'; alpha = 1; group = 'plates';    label = 'Switch plate, D-pad' }
    'asm_plate_pills'      = @{ colour = '#6E747C'; alpha = 1; group = 'plates';    label = 'Switch plate, START/SELECT' }
    # --- printed structure, neutral so the panels and boards carry colour ---
    'asm_bay_tray'         = @{ colour = '#5A6068'; alpha = 1; group = 'tray';      label = 'Bay tray' }
    'asm_rear_frame'       = @{ colour = '#3F444B'; alpha = 1; group = 'frame';     label = 'Rear frame' }
    'asm_spacers'          = @{ colour = '#7C828A'; alpha = 1; group = 'spacers';   label = 'Display spacer pucks' }
    # --- bought parts: real models, their real colours ----------------------
    'asm_display'          = @{ colour = '#1A1E25'; alpha = 1; group = 'display';   label = 'Waveshare 5in DSI (vendor model)' }
    'asm_pi_board'         = @{ colour = '#2F6F3F'; alpha = 1; group = 'pi';        label = 'Pi 3B+ board' }
    'asm_pi_parts'         = @{ colour = '#A3A8AE'; alpha = 1; group = 'pi';        label = 'Pi 3B+ connectors' }
    'asm_heatsinks'        = @{ colour = '#4F86C6'; alpha = 1; group = 'pi';        label = 'Heatsinks' }
    'asm_bank'             = @{ colour = '#D8DADE'; alpha = 1; group = 'bank';      label = 'Noise 10000 mAh bank' }
    'asm_speaker'          = @{ colour = '#1B1B1B'; alpha = 1; group = 'speaker';   label = 'FIT0502 speaker' }
    'asm_pico'             = @{ colour = '#1F5F2F'; alpha = 1; group = 'frame';     label = 'Pico (vendor model)' }
    'asm_pam'              = @{ colour = '#1E4FAA'; alpha = 1; group = 'frame';     label = 'PAM8403 amp' }
    'asm_switches_plates'  = @{ colour = '#2E3035'; alpha = 1; group = 'plates';    label = 'Tactile switches (10)' }
    'asm_switches_shoulder'= @{ colour = '#2E3035'; alpha = 1; group = 'shoulders'; label = 'Tactile switches (2)' }
    'asm_screws_frame'     = @{ colour = '#B8BCC2'; alpha = 1; group = 'frame';     label = 'M3x8 frame screws (8)' }
    'asm_screws_plates'    = @{ colour = '#B8BCC2'; alpha = 1; group = 'plates';    label = 'M3x8 plate screws (6)' }
    'asm_screw_pivot'      = @{ colour = '#B8BCC2'; alpha = 1; group = 'plates';    label = 'M3x8 D-pad pivot' }
    'asm_inserts'          = @{ colour = '#C9A24A'; alpha = 1; group = 'shell';     label = 'M3 heat-set inserts (8)' }
    'asm_magnets_frame'    = @{ colour = '#A9AEB5'; alpha = 1; group = 'frame';     label = 'Magnets, frame (6)' }
    'asm_magnets_panel'    = @{ colour = '#A9AEB5'; alpha = 1; group = 'panelmag';  label = 'Magnets, panel (6)' }
}

# One-mesh-per-group exports that the split files above replace. They stay in
# the folder (the SCAD targets still exist) but are never drawn: each would sit
# exactly on top of its split pieces and z-fight with them.
$AssemblySuperseded = @('asm_pi')   # fit-check mesh; the viewer draws board + connectors

# Prefer the current CAD (cad2, built for the parts actually bought) and fall
# back to the superseded GamePi43 work only if cad2 has not been generated yet.
if (-not $StlDir) {
    foreach ($c in @("cad2\viewer_cache\stl", "cad2\stl", "cad\stl")) {
        $p = Join-Path $root $c
        if (Test-Path $p) { $StlDir = $p; break }
    }
}
if (-not $AsmDir) {
    foreach ($c in @("cad2\viewer_cache\asm", "cad2\stl_assembly", "cad2\stl\assembly", "cad\stl_assembly")) {
        $p = Join-Path $root $c
        if (Test-Path $p) { $AsmDir = $p; break }
    }
}
Write-Output "Parts   : $StlDir"
Write-Output "Assembly: $(if ($AsmDir) { $AsmDir } else { '(none found)' })"
Write-Output ""

if (-not (Test-Path $template)) { throw "Template not found: $template" }
if (-not (Test-Path $StlDir))   { throw "STL folder not found: $StlDir" }

function Get-GzipBase64 {
    param([string]$Path)
    $raw = [System.IO.File]::ReadAllBytes($Path)
    $ms  = New-Object System.IO.MemoryStream
    try {
        $gz = New-Object System.IO.Compression.GZipStream($ms, [System.IO.Compression.CompressionLevel]::Optimal, $true)
        try { $gz.Write($raw, 0, $raw.Length) } finally { $gz.Dispose() }
        $packed = $ms.ToArray()
    } finally { $ms.Dispose() }
    return @{
        B64      = [Convert]::ToBase64String($packed)
        RawBytes = $raw.Length
        GzBytes  = $packed.Length
    }
}

function Get-PrettyName {
    param([string]$FileName)
    $n = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    $n = $n -replace '^\d+[_-]', ''      # strip any ordering prefix
    $n = $n -replace '[_-]+', ' '
    return (Get-Culture).TextInfo.ToTitleCase($n.ToLower())
}

# Numbers go into JavaScript, so they must never pick up a locale's decimal
# comma.
function Format-Num { param([double]$V) return $V.ToString('0.####', $inv) }

function ConvertTo-RgbArray {
    param([string]$Hex)
    $h = $Hex.Trim().TrimStart('#')
    if ($h.Length -eq 3) { $h = -join ($h.ToCharArray() | ForEach-Object { "$_$_" }) }
    if ($h -notmatch '^[0-9A-Fa-f]{6}$') { throw "Bad colour '$Hex' in the assembly manifest" }
    $c = 0..2 | ForEach-Object { Format-Num ([Convert]::ToInt32($h.Substring($_ * 2, 2), 16) / 255.0) }
    return '[' + ($c -join ',') + ']'
}

# FALLBACK ONLY: a colour guessed from the file name, for an assembly STL that
# is missing from $AssemblyManifest. The build warns whenever this is used.
function Get-GuessedStyle {
    param([string]$Name)
    $n = $Name.ToLower()
    if ($n -match 'panel_([a-z0-9]+)')          { return @{ colour = '#D9D9D4'; group = "panel:$($Matches[1])" } }
    if ($n -match 'hardware|internal|board|pcb|pi|mock') { return @{ colour = '#478F61'; group = 'internals' } }
    if ($n -match 'screen|display|lcd')         { return @{ colour = '#1A1E25'; group = $n } }
    if ($n -match 'bay|tray|drawer')            { return @{ colour = '#8C6B4D'; group = $n } }
    if ($n -match 'spacer|puck|shim')           { return @{ colour = '#9E4D52'; group = $n } }
    if ($n -match 'cap|button|dpad|pill')       { return @{ colour = '#DBD6CC'; group = 'controls' } }
    if ($n -match 'frame|rear|mid')             { return @{ colour = '#547599'; group = $n } }
    if ($n -match 'shell|front|body')           { return @{ colour = '#B8B3A8'; group = $n } }
    return @{ colour = '#C7993D'; group = $n }
}

$stls = Get-ChildItem $StlDir -File -Filter *.stl | Sort-Object Name
if (-not $stls) { throw "No STL files in $StlDir" }

Write-Output "STL files found: $($stls.Count)"

$entries  = New-Object System.Collections.Generic.List[string]
$rawTotal = 0
$gzTotal  = 0
$warnings = New-Object System.Collections.Generic.List[string]

# ---- assembled view (one grouped entry, listed first) ----------------------
# These are exported in true in-device coordinates rather than print
# orientation, so the viewer can stack them with no transforms of its own.
if ($AsmDir -and (Test-Path $AsmDir)) {
    $onDisk = @{}
    Get-ChildItem $AsmDir -File -Filter *.stl | ForEach-Object { $onDisk[$_.BaseName] = $_ }

    # Manifest rows first, in manifest order, then anything unmapped.
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($key in $AssemblyManifest.Keys) {
        if ($onDisk.ContainsKey($key)) {
            $rows.Add([pscustomobject]@{ Key = $key; File = $onDisk[$key]; Style = $AssemblyManifest[$key]; Mapped = $true })
        } else {
            $warnings.Add("MISSING  $key.stl is in the manifest but not in $AsmDir - run cad2\build_assembly.sh")
        }
    }
    foreach ($key in ($onDisk.Keys | Sort-Object)) {
        if ($AssemblyManifest.Contains($key) -or $AssemblySuperseded -contains $key) { continue }
        $g = Get-GuessedStyle $key
        $style = @{ colour = $g.colour; alpha = 1; group = $g.group; label = ((Get-PrettyName $key) -replace '^Asm ', '') }
        $rows.Add([pscustomobject]@{ Key = $key; File = $onDisk[$key]; Style = $style; Mapped = $false })
        $warnings.Add("UNMAPPED $key.stl has no manifest row - colour GUESSED from its name ($($g.colour), group '$($g.group)')")
    }
    $skipped = @($AssemblySuperseded | Where-Object { $onDisk.ContainsKey($_) })
    if ($skipped.Count) { Write-Output "  assembly: skipping superseded one-piece exports: $($skipped -join ', ')" }

    $panelKinds = @($rows | ForEach-Object { $_.Style.group } | Where-Object { $_ -like 'panel:*' } |
                    ForEach-Object { $_.Substring(6) } | Select-Object -Unique)
    if ($panelKinds.Count -and -not ($panelKinds -contains $AsmPanel)) {
        $warnings.Add("PANEL    default panel '$AsmPanel' not found; opening on '$($panelKinds[0])'")
        $AsmPanel = $panelKinds[0]
    }

    $members  = New-Object System.Collections.Generic.List[string]
    $jsonRows = New-Object System.Collections.Generic.List[object]
    foreach ($row in $rows) {
        $st = $row.Style
        $r  = Get-GzipBase64 -Path $row.File.FullName
        $rawTotal += $r.RawBytes
        $gzTotal  += $r.GzBytes
        $label = ($st.label -replace '"', '')
        Write-Output ("  assembly/{0,-26} {1,6} KB -> {2,5} KB  {3,-8} a={4,-4} {5,-12} {6}" -f `
            $row.File.Name, [math]::Round($r.RawBytes/1KB), [math]::Round($r.GzBytes/1KB), `
            $st.colour, (Format-Num $st.alpha), $st.group, $(if ($row.Mapped) { $label } else { "$label  [GUESSED]" }))
        $members.Add('{file:"' + $row.File.Name + '",name:"' + $label + '",colour:' + (ConvertTo-RgbArray $st.colour) +
                     ',alpha:' + (Format-Num $st.alpha) + ',group:"' + $st.group + '",gz:"' + $r.B64 + '"}')
        $jsonRows.Add([ordered]@{ file = $row.File.Name; colour = $st.colour; alpha = [double]$st.alpha;
                                  group = $st.group; label = $label; mapped = [bool]$row.Mapped })
    }
    if ($members.Count -gt 0) {
        $entries.Add('{name:"Assembly",panel:"' + $AsmPanel + '",members:[' + ($members -join ",") + ']}')
        Write-Output "  assembly entry: $($members.Count) components, panels: $($panelKinds -join ', ') (opens on $AsmPanel)"
    }

    $jsonPath = Join-Path (Join-Path $root "cad2\stl_assembly") "assembly_colours.json"
    $json = [ordered]@{
        note       = 'Generated by build_stl_viewer.ps1 from its AssemblyManifest. Edit the manifest there, not this file.'
        panels     = $panelKinds
        superseded = $AssemblySuperseded
        parts      = $jsonRows
    } | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($jsonPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "  wrote $jsonPath"
} else {
    Write-Output "  no assembly folder at $AsmDir, skipping assembled view"
}

foreach ($s in $stls) {
    $r = Get-GzipBase64 -Path $s.FullName
    $rawTotal += $r.RawBytes
    $gzTotal  += $r.GzBytes
    $ratio = if ($r.RawBytes -gt 0) { 100 - [math]::Round(($r.GzBytes / $r.RawBytes) * 100) } else { 0 }
    Write-Output ("  {0,-34} {1,7} KB -> {2,6} KB  ({3}% smaller)" -f `
        $s.Name, [math]::Round($r.RawBytes/1KB), [math]::Round($r.GzBytes/1KB), $ratio)

    $name = (Get-PrettyName $s.Name) -replace '"', ''
    $entries.Add('{name:"' + $name + '",file:"' + $s.Name + '",gz:"' + $r.B64 + '"}')
}

Write-Output ("Total: {0} KB raw -> {1} KB gzipped" -f `
    [math]::Round($rawTotal/1KB), [math]::Round($gzTotal/1KB))

$payload = "[" + ($entries -join ",") + "]"

$html = Get-Content $template -Raw -Encoding UTF8
# Use Contains, not -like: the needle ends in "[]", which -like parses as a
# wildcard character class and rejects as an invalid pattern.
$needle = '/*<!--PARTS_DATA-->*/ []'
if (-not $html.Contains($needle)) { throw "Placeholder not found in template" }
$html = $html.Replace($needle, $payload)

# Assembly steps and the latest check_assembly.py report, for the step-by-step
# mode. Both are optional: the page still works without them.
foreach ($pair in @(@('/*<!--STEPS_DATA-->*/ null', 'cad2\assembly_steps.json'),
                    @('/*<!--REPORT_DATA-->*/ null', 'cad2\preview\assembly_report.json'))) {
    $p = Join-Path $root $pair[1]
    if ((Test-Path $p) -and $html.Contains($pair[0])) {
        $j = (Get-Content $p -Raw -Encoding UTF8) -replace '</', '<\/'
        $html = $html.Replace($pair[0], $j)
        Write-Output "  embedded $($pair[1])"
    } else { Write-Output "  (not embedded: $($pair[1]))" }
}

[System.IO.File]::WriteAllText($outFile, $html, (New-Object System.Text.UTF8Encoding($false)))

$bytes = (Get-Item $outFile).Length
$mb = [math]::Round($bytes / 1MB, 2)
Write-Output ""
Write-Output "Wrote: $outFile"
Write-Output "Total page size: $mb MB ($bytes bytes)"
if ($warnings.Count) {
    Write-Output ""
    $warnings | ForEach-Object { Write-Output "WARNING: $_" }
}
if ($mb -gt $MaxPageMB) {
    Write-Output ""
    Write-Output "WARNING: page exceeds ${MaxPageMB} MB and will be slow to load."
    Write-Output "Decimate the STLs before export, or split the viewer across several pages."
}
