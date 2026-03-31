# AI News

Standalone global developments and signal dashboard.

## Run

From anywhere in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File C:\AI\AI_news\run_news_bot.ps1
```

## Outputs

Generated files:

- `output/world_developments_dashboard.html`
- `output/world_developments_payload.json`
- `output/world_developments_report.md`

## GitHub Automation

Workflow file:

- `.github/workflows/daily-news-bot.yml`

After pushing to GitHub, enable GitHub Pages from the `docs` folder to serve the latest dashboard on the web.
