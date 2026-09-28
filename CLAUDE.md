# Card project

## GitHub account
This project always uses the GitHub account **nikrozi** (never Nikrozii). Do not ask which account to use.
- Git: repo-local config commits as nikrozi and the remote URL pins the `nikrozi@` username, so `git push` uses nikrozi's credentials.
- `gh` CLI: prefix every command with nikrozi's token so it works regardless of the globally active account:
  `GH_TOKEN=$(gh auth token --user nikrozi) gh <command>`

## Cloud run
`.github/workflows/daily-picks.yml` runs referee -> referee_filter -> theodds -> `src.report` daily at 06:00 UTC
and commits `results/latest.md`. `ODDSAPI_KEY` is a repo secret; never hardcode it.
