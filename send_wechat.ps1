Add-Type -AssemblyName System.Windows.Forms

# Step 1: Ensure WeChat is visible - Ctrl+Alt+W
Write-Host "Step 1: Show WeChat..."
[System.Windows.Forms.SendKeys]::SendWait("^%w")
Start-Sleep -Milliseconds 800

# Step 2: Open search - Ctrl+F
Write-Host "Step 2: Open search..."
[System.Windows.Forms.SendKeys]::SendWait("^f")
Start-Sleep -Milliseconds 500

# Step 3: Type "文件传输助手"
Write-Host "Step 3: Search for file transfer assistant..."
[System.Windows.Forms.SendKeys]::SendWait("文件传输助手")
Start-Sleep -Milliseconds 800

# Step 4: Press Enter to open the chat
Write-Host "Step 4: Open chat..."
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 800

# Step 5: Type "1"
Write-Host "Step 5: Type message..."
[System.Windows.Forms.SendKeys]::SendWait("1")
Start-Sleep -Milliseconds 300

# Step 6: Press Enter to send
Write-Host "Step 6: Send message..."
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

Write-Host "All done!"