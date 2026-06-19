#requires -Version 7.0
# gitleaks-precommit.ps1
# PreToolUse hook (Bash): intercepta 'git commit' y corre 'gitleaks protect --staged'.
# Si hay secretos en archivos staged -> exit 2 (BLOQUEA el commit). FAIL-OPEN (exit 0)
# si gitleaks no esta instalado o el hook falla. PS7 asegurado por #requires + 'pwsh'.
$ErrorActionPreference = 'Stop'
try {
    # stdin trae el JSON del tool; drenarlo SIEMPRE (si no, ReadToEnd cuelga el hook).
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $obj = $raw | ConvertFrom-Json
    $cmd = $obj.tool_input.command
    if (-not $cmd) { exit 0 }

    # Tolera opciones globales entre 'git' y 'commit' (-c k=v, -C dir, --no-pager, ...),
    # que de otro modo evadirian el escaneo (auditoria adversarial 2026-06-11).
    if ($cmd -notmatch '(?:^|[\s;|&(])git(?:\s+-{1,2}\S+(?:[=\s]\S+)?)*\s+commit\b') { exit 0 }

    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root -or $LASTEXITCODE -ne 0) { exit 0 }

    Push-Location $root
    try {
        $out = & gitleaks protect --staged --no-banner --redact 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($code -ne 0) {
        $msg = "gitleaks detecto posibles secretos en archivos staged. Commit bloqueado.`n`n$out`n`nSi es falso positivo, agrega regla a .gitleaksignore o quita el archivo del stage antes de reintentar."
        [Console]::Error.WriteLine($msg)
        exit 2
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("gitleaks hook error (fail-open): $_")
    exit 0
}
