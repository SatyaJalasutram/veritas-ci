#!/usr/bin/env python3
# Copyright 2026 Veritas
# SPDX-License-Identifier: Apache-2.0
"""
veritas: run an agent's Veritas tests from CI and gate on the result.

    VERITAS_API_KEY=vk_... veritas run --api-url https://veritas.example.com \
        --agent <agent id> [--invoke-url https://pr-42.preview.example.com/run]

Starts a run of the agent's current Blueprint, waits for it, prints what
happened, and exits:

    0  pass   every test case passed
    1  fail   at least one test case failed
    2  error  the run couldn't judge every case, the agent never reached
              its tool server (not tested), Veritas couldn't be reached, or
              the key was refused. Never treated as a pass.

Python 3.9+, standard library only, so it runs on any CI runner as is.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

__version__ = "0.1.2"

EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 2
# Every request has a timeout; a hung connection never hangs the pipeline.
REQUEST_TIMEOUT_SECONDS = 30
POLL_ATTEMPTS_PER_REQUEST = 5
# Marks the pull request comment for one agent, so a re-run updates it.
MARKER = "<!-- veritas-ci:{agent_id} -->"


class VeritasError(Exception):
    """A failure to talk to Veritas, with a message for the CI log."""


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class Client:
    def __init__(self, api_url: str, key: str):
        self.base = api_url.rstrip("/")
        self.key = key

    def _once(self, method: str, path: str, body: Optional[dict[str, Any]]) -> tuple[int, dict[str, Any], dict]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": f"veritas-ci/{__version__}"})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.status, json.loads(response.read() or b"{}"), dict(response.headers)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read() or b"{}")
            except ValueError:
                payload = {}
            return exc.code, payload, dict(exc.headers or {})

    def request(self, method: str, path: str, body: Optional[dict[str, Any]] = None,
                retry_unavailable: bool = False) -> dict[str, Any]:
        """Retries a rate limit (429: nothing happened, so it's always safe)
        after the Retry-After Veritas gives. Retries connection failures and
        5xx only when asked: reading a run is safe to repeat, but starting
        one twice would start two runs."""
        delay = 2.0
        for attempt in range(1, POLL_ATTEMPTS_PER_REQUEST + 1):
            last = attempt == POLL_ATTEMPTS_PER_REQUEST
            try:
                status, payload, headers = self._once(method, path, body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                if retry_unavailable and not last:
                    _log(f"Couldn't reach Veritas ({reason}); retrying in {delay:.0f}s.")
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise VeritasError(f"Couldn't reach Veritas at {self.base} ({reason}).") from None
            if status == 429 and not last:
                wait = float(headers.get("Retry-After") or headers.get("retry-after") or delay)
                _log(f"Veritas rate limit reached; retrying in {wait:.0f}s.")
                time.sleep(wait)
                continue
            if status >= 500 and retry_unavailable and not last:
                _log(f"Veritas answered HTTP {status}; retrying in {delay:.0f}s.")
                time.sleep(delay)
                delay *= 2
                continue
            if status >= 400:
                error = payload.get("error") if isinstance(payload, dict) else None
                message = (error or {}).get("message") or f"HTTP {status}"
                code = (error or {}).get("code")
                raise VeritasError(f"Veritas refused the request: {message}" + (f" ({code})" if code else ""))
            return payload
        raise VeritasError("Veritas kept refusing the request.")  # unreachable; keeps the type checker honest


# --- the summary: a PR comment and a job summary -----------------------------------------

def _cell(text: Optional[str], limit: int = 200) -> str:
    """Titles and notes can carry text from the agent under test: shown as
    plain text in a table cell, never as markup, links or images."""
    text = " ".join((text or "").split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    out = []
    for ch in text:
        if ch in "&<>":
            out.append({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[ch])
        elif ch in "\\`*_{}[]()#+-.!|~/:":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


HEADLINE = {"pass": "Passed", "fail": "Failed", "error": "No verdict", "running": "Still running"}


def summary_markdown(run: dict[str, Any], note: Optional[str] = None) -> str:
    verdict = run.get("verdict", "error")
    counts = run.get("counts") or {}
    agent_id = "".join(ch for ch in str(run.get("agent_id")) if ch in "0123456789abcdef-")
    if run.get("error_reason") == "not_tested":
        # Nothing was tested: no counts, no table, no pass state. Just why,
        # and where to read how to fix it.
        lines = [MARKER.format(agent_id=agent_id),
                 f"### Veritas: Not tested for {_cell(run.get('agent_name'), 100)}", "",
                 _cell(note or run.get("summary"), 700), ""]
        help_url = str(run.get("help_url") or "")
        if help_url.startswith("https://") and not any(ch in help_url for ch in " ()<>[]"):
            lines += [f"[Make your agent testable]({help_url})", ""]
        if run.get("url"):
            lines.append(f"[Open the run in Veritas]({run['url']}).")
        return "\n".join(lines) + "\n"
    lines = [MARKER.format(agent_id=agent_id),
             f"### Veritas: {HEADLINE.get(verdict, verdict)} for {_cell(run.get('agent_name'), 100)}", "",
             _cell(note or run.get("summary"), 500), ""]
    because = run.get("failed_because") or []
    if verdict == "fail" and because:
        # Say plainly what failed the check, before any detail.
        why = {"patterns": "one or more of the 8 Assurance Pattern test cases failed",
               "adversarial": "the agent followed a planted prompt-injection attack"}
        lines += ["**Why this check failed:** " + "; and ".join(why[b] for b in because if b in why) + "\\.", ""]
    lines.append(f"Assurance Patterns: {counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed, "
                 f"{counts.get('incomplete', 0)} without a verdict, of {counts.get('total', 0)} test cases. "
                 f"Tested at {_cell(run.get('invoke_url'), 300)}\\.")
    cases = run.get("cases") or []
    # Adversarial checks (e.g. indirect prompt injection) are not one of the
    # 8 Assurance Patterns: they get their own section. A followed attack
    # fails the check, and the section carries the evidence to fix it.
    core = [c for c in cases if c.get("category") != "adversarial"]
    shown = [c for c in core if c.get("status") != "passed"]
    if shown:
        lines += ["", "| Pattern | Test case | Result | Why |", "|---|---|---|---|"]
        for c in shown[:50]:
            result = {"failed": "Failed", "incomplete": "No verdict"}.get(c.get("status"), c.get("status"))
            lines.append(f"| {_cell(c.get('pattern_id'))} {_cell(c.get('pattern_name'))} | {_cell(c.get('title'))} "
                         f"| {result} | {_cell(c.get('note'))} |")
        if len(shown) > 50:
            lines.append(f"\n{len(shown) - 50} more are in the full run.")
    adv = run.get("adversarial") or {}
    total_adv = adv.get("resisted", 0) + adv.get("followed", 0) + adv.get("not_run", 0)
    if total_adv:
        followed = adv.get("followed", 0)
        lines += ["", "#### Adversarial checks", "",
                  f"{followed} planted {'attack' if followed == 1 else 'attacks'} followed, {adv.get('resisted', 0)} "
                  f"resisted" + (f", {adv['not_run']} not run" if adv.get("not_run") else "") + f", of {total_adv}\\."
                  + (" A followed attack fails this check\\." if followed else "")]
        for f in (adv.get("findings") or [])[:20]:
            lines += ["", f"**{_cell(f.get('title'))}** \\({_cell(f.get('check_id'))} {_cell(f.get('check_name'))}\\)", "",
                      f"- Planted in: {_cell(f.get('carrier_tool'))} response, field {_cell(f.get('field'))}",
                      f"- Planted text \\({_cell(f.get('payload'))}\\): {_cell(f.get('planted_instruction'), 400)}",
                      f"- The agent then called {_cell(f.get('target_tool'))} with "
                      f"{_cell(json.dumps(f.get('agent_call_arguments') or {}), 300)}",
                      f"- Why it counts: {_cell(f.get('target_param'))} carried {_cell(f.get('canary'))}, a value that "
                      "appears only in the planted text"]
        if len(adv.get("findings") or []) > 20:
            lines.append(f"\n{len(adv['findings']) - 20} more are in the full run.")
    if run.get("url"):
        lines += ["", f"[Open the run in Veritas]({run['url']}) for every trace and its evidence."]
    return "\n".join(lines) + "\n"


def _write(path: Optional[str], text: str, append: bool = False) -> None:
    if not path:
        return
    with open(path, "a" if append else "w", encoding="utf-8") as f:
        f.write(text)


# --- the command ------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    key = os.environ.get("VERITAS_API_KEY", "").strip()
    if not key:
        _log("Set VERITAS_API_KEY to a Veritas API key (Settings > API keys), from your CI's secrets.")
        return EXIT_ERROR
    if not args.api_url:
        _log("Set --api-url or VERITAS_API_URL to your Veritas address, e.g. https://veritas.example.com.")
        return EXIT_ERROR
    if not args.agent:
        _log("Set --agent or VERITAS_AGENT_ID to the id of the agent to test (it's in the agent's page URL).")
        return EXIT_ERROR
    client = Client(args.api_url, key)
    body: dict[str, Any] = {"agent_id": args.agent}
    if args.invoke_url:
        body["invoke_url"] = args.invoke_url
    try:
        started = client.request("POST", "/api/ci/runs", body)
    except VeritasError as exc:
        _log(str(exc))
        return EXIT_ERROR
    _log(f"Veritas run started for {started.get('agent_name')}: {started.get('counts', {}).get('total')} "
         f"test cases against {started.get('invoke_url')}.")
    _log(f"Follow it at {started.get('url')}")

    deadline = time.monotonic() + args.timeout
    run_state = started
    last_done = -1
    while run_state.get("verdict") == "running":
        if time.monotonic() >= deadline:
            note = (f"The run was still going after {args.timeout} seconds, so this job stopped waiting. "
                    "It carries on in Veritas.")
            _log(note)
            text = summary_markdown(run_state, note)
            _write(args.summary_file, text)
            _write(os.environ.get("GITHUB_STEP_SUMMARY") if args.github else None, text, append=True)
            return EXIT_ERROR
        time.sleep(args.poll_interval)
        try:
            run_state = client.request("GET", f"/api/ci/runs/{started['id']}", retry_unavailable=True)
        except VeritasError as exc:
            _log(str(exc))
            return EXIT_ERROR
        counts = run_state.get("counts") or {}
        done = counts.get("passed", 0) + counts.get("failed", 0) + counts.get("incomplete", 0)
        if done != last_done:
            _log(f"{done} of {counts.get('total', 0)} test cases done "
                 f"({counts.get('failed', 0)} failed so far).")
            last_done = done

    verdict = run_state.get("verdict")
    headline = "Not tested" if run_state.get("error_reason") == "not_tested" else HEADLINE.get(verdict, verdict)
    _log(f"Veritas: {headline}. {run_state.get('summary', '')}")
    text = summary_markdown(run_state)
    if args.json:
        print(json.dumps(run_state, indent=2))
    else:
        print(text)
    _write(args.summary_file, text)
    _write(os.environ.get("GITHUB_STEP_SUMMARY") if args.github else None, text, append=True)
    return {"pass": EXIT_PASS, "fail": EXIT_FAIL}.get(verdict, EXIT_ERROR)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="veritas", description="Run Veritas tests from CI.")
    parser.add_argument("--version", action="version", version=f"veritas-ci {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run", help="Run an agent's tests and exit 0 (pass), 1 (fail) or 2 (error).")
    # Decision: the key comes from the environment only, never a flag, so
    # it can't end up in a process list or a logged command line.
    r.add_argument("--api-url", default=os.environ.get("VERITAS_API_URL"),
                   help="Your Veritas address (or VERITAS_API_URL).")
    r.add_argument("--agent", default=os.environ.get("VERITAS_AGENT_ID"),
                   help="The agent's id (or VERITAS_AGENT_ID).")
    r.add_argument("--invoke-url", default=os.environ.get("VERITAS_INVOKE_URL") or None,
                   help="Test this deployment of the agent (a pull request's preview) instead of its saved "
                        "address. Must be reachable from the internet.")
    r.add_argument("--timeout", type=int, default=1800, help="Seconds to wait for the run (default 1800).")
    r.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between checks (default 5).")
    r.add_argument("--summary-file", help="Also write the Markdown summary to this file.")
    r.add_argument("--json", action="store_true", help="Print the run as JSON instead of Markdown.")
    r.add_argument("--github", action="store_true", default=bool(os.environ.get("GITHUB_ACTIONS")),
                   help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
