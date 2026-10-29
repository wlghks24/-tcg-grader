# User-initiated removal only.
Unregister-ScheduledTask -TaskName 'TCG_PC_AUDIT_V03' -Confirm:$false
Write-Host 'Scheduled audit task removed.'
