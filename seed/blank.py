"""Start with your own team and nothing else.

`seed.build` populates ten scripted conversations so every screen has something
in it. That is right for a demo and wrong the moment you want to judge the
product on your own work: Meridian's numbers look like results, and it is very
easy to spend twenty minutes reading an analysis of a call that never happened.

This wipes all of it and writes one org and the people you name. No calls, no
plays, no deals, no coaching plans, no cycle report -- those should appear
because you created them, not because they shipped in a fixture.

    python -m seed.blank
    python -m seed.blank --org "Acme" --rep "Ali Raza" --rep "Sara Khan"
    python -m seed.blank --product "our CRM" --icp "mid-market logistics"

The reps matter more than they look. There is no endpoint that creates one --
they exist only through this file -- and the Dojo needs a rep to build a buyer
around, so an empty roster leaves the one genuinely live feature unusable.
A rep with no call history still gets a workout: the persona falls back to a
default sparring buyer holding a status-quo and a price objection.

This deletes data and does not ask twice. That is deliberate: it exists to be
run on a demo database, and anything it would destroy is reproducible with
`python -m seed.build --reset`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "api") not in sys.path:
    sys.path.insert(0, str(REPO / "api"))

from salix.schemas.org import Org, Rep  # noqa: E402
from salix.store import db, repo  # noqa: E402
from salix.store.db import session_scope  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("blank")

DEFAULT_REPS = ["Rep One", "Rep Two"]


def _slug(name: str) -> str:
    """A stable id from a person's name."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"rep_{cleaned or 'unnamed'}"


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--org", default="Your Company", help="the organisation name")
    parser.add_argument(
        "--rep", action="append", dest="reps", metavar="NAME",
        help="a salesperson. Repeat for each; defaults to two placeholders.",
    )
    parser.add_argument("--product", default="your product")
    parser.add_argument("--icp", default="your ideal customer")
    parser.add_argument("--cycle", default="Current quarter")
    parser.add_argument(
        "--keep-schema", action="store_true",
        help="do not drop the tables, only clear them of the demo corpus",
    )
    args = parser.parse_args()

    names = args.reps or DEFAULT_REPS

    if not args.keep_schema:
        log.info("dropping every table")
        await db.drop_all()
    await db.init_db()

    org_id = "org_" + (re.sub(r"[^a-z0-9]+", "_", args.org.lower()).strip("_") or "you")

    async with session_scope() as session:
        await repo.put_org(
            session,
            Org(
                id=org_id,
                name=args.org,
                product=args.product,
                icp=args.icp,
                cycle_label=args.cycle,
            ),
        )

        for index, name in enumerate(names):
            await repo.put_rep(
                session,
                Rep(
                    id=_slug(name),
                    org_id=org_id,
                    name=name,
                    role="ae",
                    initials=_initials(name),
                    # Zero rather than invented. A quota nobody set is a number
                    # on a dashboard that means nothing, and this whole file
                    # exists to remove numbers that mean nothing.
                    quota=0.0,
                    attained=0.0,
                    joined_at="",
                    is_top_performer=index == 0,
                ),
            )

    log.info("")
    log.info("  organisation : %s (%s)", args.org, org_id)
    log.info("  people       : %s", ", ".join(names))
    log.info("  calls        : none")
    log.info("")
    log.info("  The Dojo works now -- it builds a buyer even for a rep with no")
    log.info("  history. Every other screen is empty until you put something in it.")
    log.info("")
    log.info("  To put the demo corpus back:  python -m seed.build --reset --report")
    log.info("")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
