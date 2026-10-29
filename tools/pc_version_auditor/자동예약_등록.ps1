# Optional opt-in: v0.6 replaces the SAME V03 task name to avoid duplicate scheduled jobs.
# This legacy task ID is intentionally stable for an in-place upgrade.
# Does NOT install software, grant elevated rights, train AI, edit repository or run code from it.
[CmdletBinding()]
param(
    [string] $RepoDir,
    [string] $OutputDir,
    [ValidateRange(1,9999)] [int] $Latest = 879,
    [ValidateRange(0,23)] [int] $Hour = 9,
    [ValidateRange(0,59)] [int] $Minute = 15
)
$ErrorActionPreference = 'Stop'
if (-not $RepoDir) { $RepoDir = Read-Host 'Enter cloned TCG repository root path' }
if (-not $OutputDir) { $OutputDir = Read-Host 'Enter reports folder OUTSIDE repository' }
if ([string]::IsNullOrWhiteSpace($RepoDir) -or [string]::IsNullOrWhiteSpace($OutputDir)) { throw 'Required folders missing' }
$repo = [System.IO.Path]::GetFullPath($RepoDir)
$out = [System.IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw 'Not a local Git repository root' }
if ($out.TrimEnd('\') -eq $repo.TrimEnd('\') -or $out.StartsWith(($repo.TrimEnd('\') + '\'),[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Reports folder must be outside repository' }
$python = Get-Command 'py.exe' -ErrorAction Stop
$script = Join-Path $PSScriptRoot 'pc_auditor\audit.py'
if (-not (Test-Path -LiteralPath $script)) { throw 'PC audit script missing' }
# Arguments are for the local machine's scheduled action, with quotes preserved.
if ($repo.Contains('"') -or $out.Contains('"')) { throw 'Invalid quote in path' }
$arguments = '-3 "' + $script + '" --repo "' + $repo + '" --output "' + $out + '" --latest ' + $Latest + ' --auto'
$action = New-ScheduledTaskAction -Execute $python.Source -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($Hour).AddMinutes($Minute))
Register-ScheduledTask -TaskName 'TCG_PC_AUDIT_V03' -Action $action -Trigger $trigger -Description 'Read-only TCG V-number audit and staging-only patch proposals' -Force | Out-Null
Write-Host 'TCG PC v0.6 mandatory two-pass review installed into existing TCG_PC_AUDIT_V03 task ID (no duplicate).'
Write-Host 'Remove via: Unregister-ScheduledTask -TaskName TCG_PC_AUDIT_V03 -Confirm:$false'
