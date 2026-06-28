Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinLister {
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}

$result = @()
[WinLister]::EnumWindows({
    param($hwnd, $lParam)
    if ([WinLister]::IsWindowVisible($hwnd)) {
        $sb = New-Object System.Text.StringBuilder(256)
        [WinLister]::GetWindowText($hwnd, $sb, 256)
        $title = $sb.ToString()
        if ($title.Length -gt 0) {
            $pid = 0
            [WinLister]::GetWindowThreadProcessId($hwnd, [ref]$pid)
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            $pname = if($proc) { $proc.ProcessName } else { "N/A" }
            $result += "$title | PID: $pid | Process: $pname"
        }
    }
    return $true
}, [IntPtr]::Zero)

$result | Where-Object { $_ -like "*微信*" -or $_ -like "*wechat*" -or $_ -like "*WeChat*" }
Write-Host "---ALL WINDOWS---"
$result