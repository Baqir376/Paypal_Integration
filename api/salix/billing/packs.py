"""What is for sale.

Defined here and nowhere else. The browser names a pack and the price comes from
this table, so nobody can buy credits at a price they sent us.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Pack:
    id: str
    label: str
    credits: int
    #: A decimal string, because that is what PayPal takes and what a float
    #: cannot be trusted to hold.
    price: str
    currency: str = "USD"

    def public(self) -> dict:
        return asdict(self)


PACKS: dict[str, Pack] = {
    pack.id: pack
    for pack in (
        Pack(id="starter", label="Starter", credits=5, price="10.00"),
        Pack(id="team", label="Team", credits=25, price="40.00"),
        Pack(id="floor", label="Sales floor", credits=100, price="120.00"),
    )
}
