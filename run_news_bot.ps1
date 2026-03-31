$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

& "C:\Users\berka\anaconda3\python.exe" ".\src\news_bot.py"
