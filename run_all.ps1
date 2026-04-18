# Runs the pipeline on all 9 required input combinations.
# Usage:  .\run_all.ps1
# Optional:  .\run_all.ps1 -UseBinary   (uses the PyInstaller exe instead of main.py)

param(
    [switch]$UseBinary
)

$pairs = @(
    @("inputs/cis-r1.pdf", "inputs/cis-r1.pdf"),
    @("inputs/cis-r1.pdf", "inputs/cis-r2.pdf"),
    @("inputs/cis-r1.pdf", "inputs/cis-r3.pdf"),
    @("inputs/cis-r1.pdf", "inputs/cis-r4.pdf"),
    @("inputs/cis-r2.pdf", "inputs/cis-r2.pdf"),
    @("inputs/cis-r2.pdf", "inputs/cis-r3.pdf"),
    @("inputs/cis-r2.pdf", "inputs/cis-r4.pdf"),
    @("inputs/cis-r3.pdf", "inputs/cis-r3.pdf"),
    @("inputs/cis-r3.pdf", "inputs/cis-r4.pdf")
)

foreach ($p in $pairs) {
    Write-Host "=== $($p[0])  vs  $($p[1]) ==="
    if ($UseBinary) {
        & .\dist\comp5700-pipeline.exe $p[0] $p[1]
    } else {
        python main.py $p[0] $p[1]
    }
}