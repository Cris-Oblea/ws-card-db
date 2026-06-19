#requires -Version 7.0
# session-summary.ps1
# SessionEnd hook: imprime un resumen git (rama, cambios, ahead/behind, PRs abiertos).
# Solo informativo (Write-Host). FAIL-OPEN (exit 0) ante cualquier error. El 'gh pr list'
# (red) queda acotado por el timeout del hook en settings.json. PS7 asegurado por #requires.
$ErrorActionPreference = 'SilentlyContinue'
try {
    # stdin trae el JSON del evento; drenarlo SIEMPRE (si no, ReadToEnd cuelga el hook).
    $null = [Console]::In.ReadToEnd()

    $inRepo = git rev-parse --is-inside-work-tree 2>$null
    if ($inRepo -ne 'true') { exit 0 }

    Write-Host ""
    Write-Host "=== Estado al cerrar sesion ==="

    $branch = git symbolic-ref --short HEAD 2>$null
    if ($branch) { Write-Host "Rama actual: $branch" }

    $status = git status --short 2>$null
    if ($status) {
        Write-Host ""
        Write-Host "Cambios sin commitear:"
        Write-Host $status
    } else {
        Write-Host "Working tree limpio."
    }

    $ahead = git rev-list --count '@{u}..HEAD' 2>$null
    $behind = git rev-list --count 'HEAD..@{u}' 2>$null
    if ($ahead -and [int]$ahead -gt 0) { Write-Host "Commits sin push: $ahead" }
    if ($behind -and [int]$behind -gt 0) { Write-Host "Commits sin pull: $behind" }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        # Repo personal: usa el origin del repo actual (sin --repo fijo).
        $prsRaw = gh pr list --author '@me' --state open --json number,title,headRefName 2>$null
        if ($prsRaw -and $prsRaw -ne '[]') {
            Write-Host ""
            Write-Host "PRs abiertos tuyos:"
            ($prsRaw | ConvertFrom-Json) | ForEach-Object {
                Write-Host "  #$($_.number) [$($_.headRefName)] $($_.title)"
            }
        }
    }
    exit 0
} catch {
    exit 0
}
