Add-Type -AssemblyName System.Windows.Forms
# Common WeChat shortcut: Ctrl+Alt+W to show/hide
[System.Windows.Forms.SendKeys]::SendWait("^%w")
Start-Sleep -Milliseconds 1000
Write-Host "Ctrl+Alt+W sent"