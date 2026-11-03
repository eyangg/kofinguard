param([string]$Kind = "stop")
if ($Kind -eq "notify") { $Message = "확인이 필요해요 (권한 요청 또는 입력 대기)." }
else { $Message = "작업이 끝났어요. 결과를 확인해 주세요." }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Media.SystemSounds]::Asterisk.Play()
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip(5000, "Claude Code (KoFinGuard)", $Message, [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 6
$n.Dispose()
