param(
    [Parameter(Mandatory = $true)]
    [string]$Note,

    [string]$File = "NOTES.md",

    [switch]$NoPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $File)) {
    throw "Notes file not found: $File"
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$entry = "- [$timestamp] $Note"
Add-Content -Path $File -Value $entry

# Stage only the notes file so unrelated workspace changes are not committed.
git add -- $File

if (-not (git diff --cached --quiet -- $File)) {
    git commit -m "notes: update trading journal"
    if (-not $NoPush) {
        git push
    }
    Write-Output "Saved note to $File and synced to git." 
} else {
    Write-Output "No note changes detected; nothing committed."
}
