Set-Location "c:\Users\Hp\pstu-final-onsite\frontend"
"===page.tsx===" | Out-File fe.txt
Get-Content "src\app\page.tsx" | Out-File -Append fe.txt
"===layout.tsx===" | Out-File -Append fe.txt
Get-Content "src\app\layout.tsx" | Out-File -Append fe.txt
"===globals.css===" | Out-File -Append fe.txt
Get-Content "src\app\globals.css" | Out-File -Append fe.txt
"===api.ts===" | Out-File -Append fe.txt
Get-Content "src\lib\api.ts" | Out-File -Append fe.txt
"===UserContext.tsx===" | Out-File -Append fe.txt
Get-Content "src\lib\UserContext.tsx" | Out-File -Append fe.txt
"===SideNav.tsx===" | Out-File -Append fe.txt
Get-Content "src\components\SideNav.tsx" | Out-File -Append fe.txt
"===TopNav.tsx===" | Out-File -Append fe.txt
Get-Content "src\components\TopNav.tsx" | Out-File -Append fe.txt
"===send page===" | Out-File -Append fe.txt
Get-Content "src\app\send\page.tsx" | Out-File -Append fe.txt
"===request page===" | Out-File -Append fe.txt
Get-Content "src\app\request\page.tsx" | Out-File -Append fe.txt
Get-Content "fe.txt" | Out-String
