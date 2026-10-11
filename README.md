# Veritas CI

Run an agent's [Veritas](https://veritas.example.com) tests on every pull
request and fail the check when a test case fails.

Each run tests the agent's Blueprint as it stands in Veritas when the job
starts. It is judged exactly like a run started in the app:

- **Pass:** every test case passed. Exit code `0`.
- **Fail:** at least one test case failed. Exit code `1`.
- **Error:** the run couldn't judge every case, Veritas couldn't be reached,
  the key was refused, or the run was still going when the job stopped
  waiting. Exit code `2`. An error is never treated as a pass.

The results, with every trace and its evidence, are in Veritas. The job
links to them.

If the agent's plan includes adversarial checks (for example indirect
prompt injection), a planted attack the agent followed **fails the check**
(exit code `1`).
- The summary says why the check failed: the patterns, the attacks, or
  both.
- Each attack gets its own section with the evidence: where it was
  planted, the exact text, and the call the agent made.

## Before you start

1. **The CI/CD add-on.** It's included on Enterprise and during a trial. On
   Team, an admin adds it in **Settings → Billing**.
2. **An API key.** An admin creates one in **Settings → API keys**. It is
   shown once. Save it as a secret in your CI, for example
   `VERITAS_API_KEY`. You can limit a key to one agent, and give it an
   expiry.
3. **The agent's id.** It's in the agent's page address in Veritas:
   `/agents/<agent id>/...`.
4. **A reachable deployment.** Veritas calls the agent from the internet.
   To test a pull request's own changes, deploy a preview of the agent and
   pass its address as `invoke-url`. Veritas refuses private and internal
   addresses.

   If the agent has a saved credential in Veritas, Veritas only sends that
   credential to the address it was saved for. A preview on another host
   must not need it.

## GitHub Actions

```yaml
name: Agent tests
on: pull_request

permissions:
  contents: read
  pull-requests: write   # to comment the result on the pull request

jobs:
  veritas:
    runs-on: ubuntu-latest
    steps:
      # ... deploy the pull request's preview of the agent here ...
      - uses: SatyaJalasutram/veritas-ci@v0
        with:
          api-key: ${{ secrets.VERITAS_API_KEY }}
          api-url: https://veritas.example.com
          agent-id: 3f0c2a4e-...
          invoke-url: https://pr-${{ github.event.pull_request.number }}.preview.example.com/run
```

The action posts the result as a comment on the pull request. On the next
push it updates that comment instead of adding another. It uses the
workflow's own `GITHUB_TOKEN` for this; Veritas never sees a GitHub
credential. If the token can't comment, the action leaves a warning, and
the check's pass or fail is unaffected.

**Pull requests from forks.** GitHub doesn't give a fork's `pull_request`
workflow your secrets. The job then errors instead of running, and never
passes by default. Don't switch to `pull_request_target` to get around
this: that runs the fork's code with your Veritas key in reach. Run the
check on a branch in your own repository instead.

| Input | Required | Default | |
|---|---|---|---|
| `api-key` | yes | | A Veritas API key, from a secret. |
| `api-url` | yes | | Your Veritas address. |
| `agent-id` | yes | | The agent to test. |
| `invoke-url` | no | the agent's saved address | The deployment to test. |
| `timeout-seconds` | no | `1800` | How long to wait for the run. |
| `comment` | no | `true` | Comment the result on the pull request. |
| `github-token` | no | `github.token` | Token for the comment. |

Output: `verdict` is `pass`, `fail` or `error`.

To make the check block merging, mark it as required in the repository's
branch protection settings.

## Any other CI

The CLI is a single Python file with no dependencies. It needs Python 3.9
or newer.

```sh
# veritas_ci.py from this repository (a PyPI package is planned)
curl -fsSLO https://raw.githubusercontent.com/SatyaJalasutram/veritas-ci/v0/veritas_ci.py
export VERITAS_API_KEY=...        # from your CI's secrets
python3 veritas_ci.py run --api-url https://veritas.example.com --agent <agent id> \
  [--invoke-url https://preview.example.com/run] [--summary-file result.md]
```

- The key is read only from `VERITAS_API_KEY`, never from a flag, so it
  can't show up in a process list or a logged command line.
- `--api-url`, `--agent` and `--invoke-url` can also be given as
  `VERITAS_API_URL`, `VERITAS_AGENT_ID` and `VERITAS_INVOKE_URL`.
- `--json` prints the run as JSON instead of Markdown.

## Runs and your plan

Every CI run counts against your plan's monthly run quota, like any other
run. If the quota is used up, the job errors and says so.

## Licence

Apache License 2.0. See `LICENSE`.
