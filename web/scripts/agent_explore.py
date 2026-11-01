"""An AI tester that uses the app the way a person would, and says what it finds.

Scripts only check what somebody thought of. This hands browser-use a goal rather
than steps, so it reads the screen, decides what to do and hits things nobody wrote
a test for. It costs model credit and is not deterministic, so it is a tool to run
by hand and not part of any suite.

    python -m venv agent-venv && agent-venv/Scripts/pip install browser-use
    GEMINI_API_KEY=... BASE=http://127.0.0.1:3000 agent-venv/Scripts/python web/scripts/agent_explore.py

Point it at a test database: it adds and removes real records.

The agent's account of itself is not evidence: in one run it reported finishing steps
its own checklist left open. So each goal is checked afterwards against the pages it
actually visited and what actually changed in the API, and the summary comes from
that. A goal that cannot be shown is reported as unconfirmed, whatever the agent said.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from browser_use import Agent, ChatGoogle

BASE = os.environ.get("BASE", "http://127.0.0.1:3000")
MODEL = os.environ.get("AGENT_MODEL", "gemini-3.1-flash-lite")

TASK = f"""
You are a skeptical QA tester for a B2B sales coaching web app at {BASE}/console.
Nobody is telling you how it works; find out by using it.

Goals, in order:
1. Go through every item in the left-hand navigation.
2. On the Team page, add a salesperson, rename them, remove them and restore them.
3. Open a call, open a salesperson's profile, and read their coaching plan.
4. Open the Dojo, start a session, say two things to the buyer, and end it.
5. Press Ctrl+K, search for "price", and scroll the results.

Do not buy anything and do not upload a file.

When finished, report every problem you saw: anything broken, confusing, stuck, slow,
misleading or inconsistent. For each one give the page, what you did, what happened
and what you expected. If something worked well, you do not need to mention it.
"""


def read(path: str):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as response:
        return json.load(response)


def snapshot() -> dict:
    reps = read("/api/reps")
    return {
        "reps": {r["rep"]["id"]: r["rep"]["name"] for r in reps},
        "archived": {r["id"] for r in read("/api/reps/archived")},
        "sessions": {s["id"]: s for s in read("/api/dojo/sessions")},
    }


NAV = ("/console", "/calls", "/team", "/playbook", "/deals", "/dojo", "/report")


def confirm(before: dict, after: dict, urls: list[str]) -> list[tuple[str, bool, str]]:
    """What can be shown to have happened. A rename and a removal followed by a
    restore leave no trace in the final state beyond the new id, so those three are
    only confirmed from there being a new, active rep at all."""
    seen = " ".join(urls)
    missing = [p for p in NAV if p not in seen]
    added = set(after["reps"]) - set(before["reps"])
    sessions = [s for i, s in after["sessions"].items() if i not in before["sessions"]]
    spoken = [s for s in sessions if sum(t["speaker"] == "rep" for t in s["turns"]) >= 2]
    return [
        ("visited every nav page", not missing, f"missing {missing}" if missing else ""),
        ("added a salesperson who is still active", bool(added), ", ".join(after["reps"][i] for i in added)),
        ("opened a call", "/calls/" in seen, ""),
        ("opened a rep profile", "/reps/" in seen, ""),
        ("finished a Dojo session with two turns", bool(spoken), f"{len(sessions)} new session(s)"),
    ]


async def main() -> None:
    before = snapshot()
    agent = Agent(task=TASK, llm=ChatGoogle(model=MODEL), use_vision=False)
    history = await agent.run(max_steps=int(os.environ.get("AGENT_STEPS", "40")))

    print("\n=== WHAT THE AGENT SAYS (unverified) ===")
    print(history.final_result() or "(the agent stopped before reporting)")
    print(f"\nsteps: {history.number_of_steps()} | errors: {sum(1 for e in history.errors() if e)}")

    print("\n=== WHAT CAN BE CONFIRMED ===")
    results = confirm(before, snapshot(), [u or "" for u in history.urls()])
    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'NOT CONFIRMED'} {name}{f': {detail}' if detail else ''}")
    print(f"\n{sum(ok for _, ok, _ in results)} of {len(results)} goals confirmed")
    print("Ctrl+K search and the rename, removal and restore steps leave no checkable trace.")


if __name__ == "__main__":
    asyncio.run(main())
