"""The seed organisation: who sells what, to whom, and how it went.

This is a fictional but internally consistent sales team, built so that every
feature in Salix has something real to bite on. The design is deliberate:

* **Zara** is the top performer. Her calls carry the narrative plays the
  playbook is built from.
* **Bilal** is the coaching subject. He monologues, pitches features instead of
  diagnosing, and loses on price -- and his failures are the exact ones Zara's
  plays solve, so the Coach has somewhere real to retrieve from.
* **Fatima** discovers beautifully and then fails to close, which produces a
  different shaped gap so the radar is not one-dimensional.
* **Daniyal** is competent and unremarkable, the control case.
* **Hina** is new and improving, so the trend sparkline has a rising line.

Deal outcomes are set so that win-rate lift per play is computable rather than
decorative.
"""

from __future__ import annotations

from datetime import datetime, timezone

ORG_ID = "org_meridian"

ORG = {
    "id": ORG_ID,
    "name": "Meridian",
    "product": "Cadence, a revenue operations platform for renewal-heavy teams",
    "icp": "Mid-market logistics, manufacturing and distribution ops teams, 200-2000 staff",
    "cycle_label": "Q1 2026",
}

REPS = [
    {
        "id": "rep_zara", "name": "Zara Iqbal", "initials": "ZI",
        "role": "senior_ae", "quota": 900_000, "attained": 1_040_000,
        "joined_at": "2023-02-13", "is_top_performer": True,
        "voice": "Cherry",
    },
    {
        "id": "rep_daniyal", "name": "Daniyal Ahmed", "initials": "DA",
        "role": "ae", "quota": 700_000, "attained": 688_000,
        "joined_at": "2024-01-08", "is_top_performer": False,
        "voice": "Ethan",
    },
    {
        "id": "rep_fatima", "name": "Fatima Sheikh", "initials": "FS",
        "role": "ae", "quota": 700_000, "attained": 512_000,
        "joined_at": "2024-06-03", "is_top_performer": False,
        "voice": "Jennifer",
    },
    {
        "id": "rep_bilal", "name": "Bilal Khan", "initials": "BK",
        "role": "ae", "quota": 700_000, "attained": 274_000,
        "joined_at": "2025-03-17", "is_top_performer": False,
        "voice": "Ryan",
    },
    {
        "id": "rep_hina", "name": "Hina Raza", "initials": "HR",
        "role": "ae", "quota": 500_000, "attained": 361_000,
        "joined_at": "2025-09-01", "is_top_performer": False,
        "voice": "Katerina",
    },
]

# Buyer voices are assigned per deal so diarization has genuinely different
# speakers to separate, and so a returning contact sounds like themselves.
DEALS = [
    {
        "id": "deal_northwind", "name": "Northwind renewal operations",
        "account": "Northwind Logistics", "owner_id": "rep_zara",
        "value": 128_000, "stage": "closed_won", "outcome": "won",
        "opened_at": "2026-01-12", "closed_at": "2026-03-06",
        "contacts": ["Ayesha Rahman", "Marcus Webb"], "buyer_voice": "Nofish",
    },
    {
        "id": "deal_kestrel", "name": "Kestrel platform rollout",
        "account": "Kestrel Manufacturing", "owner_id": "rep_zara",
        "value": 96_000, "stage": "negotiation", "outcome": "open",
        "opened_at": "2026-02-02", "closed_at": None,
        "contacts": ["Tomas Lindqvist"], "buyer_voice": "Elias",
    },
    {
        "id": "deal_orbit", "name": "Orbit Freight expansion",
        "account": "Orbit Freight", "owner_id": "rep_daniyal",
        "value": 74_000, "stage": "closed_won", "outcome": "won",
        "opened_at": "2026-01-20", "closed_at": "2026-03-11",
        "contacts": ["Priya Nair", "Sam Okafor"], "buyer_voice": "Dylan",
    },
    {
        "id": "deal_vantage", "name": "Vantage Foods renewals",
        "account": "Vantage Foods", "owner_id": "rep_fatima",
        "value": 88_000, "stage": "proposal", "outcome": "open",
        "opened_at": "2026-02-09", "closed_at": None,
        "contacts": ["Grace Mbeki"], "buyer_voice": "Katerina",
    },
    {
        "id": "deal_halcyon", "name": "Halcyon Medical ops",
        "account": "Halcyon Medical", "owner_id": "rep_bilal",
        "value": 112_000, "stage": "closed_lost", "outcome": "lost",
        "opened_at": "2026-01-26", "closed_at": "2026-03-02",
        "contacts": ["Dr Ines Oyelaran"], "buyer_voice": "Jennifer",
    },
    {
        "id": "deal_brightline", "name": "Brightline Retail pilot",
        "account": "Brightline Retail", "owner_id": "rep_bilal",
        "value": 68_000, "stage": "negotiation", "outcome": "open",
        "opened_at": "2026-02-16", "closed_at": None,
        "contacts": ["Owen Castellanos"], "buyer_voice": "Elias",
    },
    {
        "id": "deal_cobalt", "name": "Cobalt Industrial rollout",
        "account": "Cobalt Industrial", "owner_id": "rep_hina",
        "value": 54_000, "stage": "discovery", "outcome": "open",
        "opened_at": "2026-03-02", "closed_at": None,
        "contacts": ["Rachel Adeyemi"], "buyer_voice": "Cherry",
    },
    {
        "id": "deal_tanner", "name": "Tanner and Rowe renewal desk",
        "account": "Tanner & Rowe", "owner_id": "rep_daniyal",
        "value": 61_000, "stage": "closed_lost", "outcome": "lost",
        "opened_at": "2026-01-15", "closed_at": "2026-02-24",
        "contacts": ["Henrik Sole"], "buyer_voice": "Nofish",
    },
]


def _dt(day: str, hour: int = 10, minute: int = 0) -> datetime:
    year, month, date = (int(p) for p in day.split("-"))
    return datetime(year, month, date, hour, minute, tzinfo=timezone.utc)


# `script` names the file in seed/scripts/. `outcome` is the deal outcome at the
# time, used to weight the moment index.
CALLS = [
    # -- Zara / Northwind: the reference deal, won -----------------------
    {
        "id": "call_northwind_1", "deal_id": "deal_northwind", "rep_id": "rep_zara",
        "title": "Northwind - discovery", "account": "Northwind Logistics",
        "occurred_at": _dt("2026-01-14", 10, 0), "outcome": "won",
        "script": "northwind_1_discovery",
    },
    {
        "id": "call_northwind_2", "deal_id": "deal_northwind", "rep_id": "rep_zara",
        "title": "Northwind - working session with ops", "account": "Northwind Logistics",
        "occurred_at": _dt("2026-02-04", 14, 30), "outcome": "won",
        "script": "northwind_2_pricing",
    },
    # -- Zara / Kestrel: open, healthy ----------------------------------
    {
        "id": "call_kestrel_1", "deal_id": "deal_kestrel", "rep_id": "rep_zara",
        "title": "Kestrel - discovery", "account": "Kestrel Manufacturing",
        "occurred_at": _dt("2026-02-05", 9, 0), "outcome": "open",
        "script": "kestrel_1_discovery",
    },
    # -- Bilal / Halcyon: the loss the coaching plan is built from -------
    {
        "id": "call_halcyon_1", "deal_id": "deal_halcyon", "rep_id": "rep_bilal",
        "title": "Halcyon - intro and demo", "account": "Halcyon Medical",
        "occurred_at": _dt("2026-01-28", 11, 0), "outcome": "lost",
        "script": "halcyon_1_demo",
    },
    {
        "id": "call_halcyon_2", "deal_id": "deal_halcyon", "rep_id": "rep_bilal",
        "title": "Halcyon - pricing follow-up", "account": "Halcyon Medical",
        "occurred_at": _dt("2026-02-18", 15, 0), "outcome": "lost",
        "script": "halcyon_2_pricing",
    },
    # -- Bilal / Brightline: open and slipping --------------------------
    {
        "id": "call_brightline_1", "deal_id": "deal_brightline", "rep_id": "rep_bilal",
        "title": "Brightline - pilot scoping", "account": "Brightline Retail",
        "occurred_at": _dt("2026-02-19", 13, 0), "outcome": "open",
        "script": "brightline_1_scoping",
    },
    # -- Daniyal / Orbit: competent, won --------------------------------
    {
        "id": "call_orbit_1", "deal_id": "deal_orbit", "rep_id": "rep_daniyal",
        "title": "Orbit Freight - expansion review", "account": "Orbit Freight",
        "occurred_at": _dt("2026-01-22", 10, 30), "outcome": "won",
        "script": "orbit_1_expansion",
    },
    # -- Daniyal / Tanner: lost to the incumbent ------------------------
    {
        "id": "call_tanner_1", "deal_id": "deal_tanner", "rep_id": "rep_daniyal",
        "title": "Tanner & Rowe - evaluation", "account": "Tanner & Rowe",
        "occurred_at": _dt("2026-01-19", 16, 0), "outcome": "lost",
        "script": "tanner_1_evaluation",
    },
    # -- Fatima / Vantage: great discovery, no close --------------------
    {
        "id": "call_vantage_1", "deal_id": "deal_vantage", "rep_id": "rep_fatima",
        "title": "Vantage Foods - discovery", "account": "Vantage Foods",
        "occurred_at": _dt("2026-02-11", 11, 30), "outcome": "open",
        "script": "vantage_1_discovery",
    },
    # -- Hina / Cobalt: new rep, improving ------------------------------
    {
        "id": "call_cobalt_1", "deal_id": "deal_cobalt", "rep_id": "rep_hina",
        "title": "Cobalt Industrial - first call", "account": "Cobalt Industrial",
        "occurred_at": _dt("2026-03-04", 9, 30), "outcome": "open",
        "script": "cobalt_1_intro",
    },
]


def deal_for(deal_id: str) -> dict:
    return next(d for d in DEALS if d["id"] == deal_id)


def rep_for(rep_id: str) -> dict:
    return next(r for r in REPS if r["id"] == rep_id)
