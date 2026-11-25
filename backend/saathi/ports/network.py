"""Booking a ride on an open network, and what the network may tell us back.

Saathi does not run a taxi company, and it does not pick a fare. A network
does both: on ONDC's mobility domain (`ONDC:TRV10`) a buyer app asks every
seller app in a city who can take a family from a lodge to a hospital gate, the
sellers answer with what they offer, and one of them quotes a price. This port
is the whole of the seam with that network, and it is deliberately the shape of
the conversation rather than the shape of any one protocol: look for rides,
ask one seller for a firm price, agree to it, ask how it is going, call it off.

**Quoting and agreeing are two calls, and never one.** `quote()` asks for a
price and commits nobody to anything. `confirm()` is what books a car. A caller
that wanted "the cheapest one, booked" would have to make both calls itself,
which is the point: the step that spends a family's money is always a step
somebody chose to take.

**The fare is the seller's, never ours.** `Quote.amount_paise` is what the
seller quoted, in integer paise, with the breakup the seller gave. An adapter
that could not read a price raises `NetworkUnavailable`; it does not fall back
to a distance-times-rate estimate, because an estimate shown as a fare is a
promise the driver never made.

One adapter speaks a real network: `adapters/beckn/client.py`, a Beckn buyer
app. `adapters/beckn/null.py` is what runs without one. The caller never
learns which it has.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class NetworkUnavailable(RuntimeError):
    """The network could not be reached, did not answer, or answered nonsense.

    Raised by an adapter, never swallowed inside one. Silence is the common
    case on an asynchronous network — a seller acknowledges a request and then
    never calls back — and it means exactly this: we do not know. It never
    means "no rides", "no charge" or "cancelled".
    """


class QuoteChanged(NetworkUnavailable):
    """The seller's final price is not the price the family was shown.

    A subclass of `NetworkUnavailable` so a caller that only handles the one
    exception still stops; the extra fields are for a caller that wants to show
    the family the new number and ask again. Nothing is booked when this is
    raised.
    """

    def __init__(self, message: str, *, quoted_paise: int, offered_paise: int) -> None:
        super().__init__(message)
        self.quoted_paise = quoted_paise
        self.offered_paise = offered_paise


class OrderState(StrEnum):
    """Where a booked ride has got to, normalised from the network's words.

    `UNKNOWN` is deliberate and is not an error: a state this code has never
    seen must not silently read as `CONFIRMED`, because that is the one value
    that would send a family to the kerb for a car that is not coming.
    """

    SEARCHING = "searching"
    QUOTED = "quoted"
    #: Booked, and a driver is assigned or on the way. The family is not moving yet.
    CONFIRMED = "confirmed"
    #: The family is in the car.
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_live(self) -> bool:
        """Whether a car is still expected to turn up or is already driving."""
        return self in (OrderState.CONFIRMED, OrderState.IN_PROGRESS)


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float

    def gps(self) -> str:
        """The `"lat,lng"` form Beckn location objects carry."""
        return f"{self.lat:.6f},{self.lng:.6f}"


@dataclass(frozen=True)
class SearchIntent:
    """Who wants to go where. No name or phone: a search identifies nobody."""

    pickup: GeoPoint
    drop: GeoPoint
    #: The network's vehicle category word (`AUTO_RICKSHAW`, `CAB`), or empty
    #: for "anything". Passed through, never interpreted here.
    vehicle_category: str = ""


@dataclass(frozen=True)
class Offer:
    """One seller's answer to a search: a kind of ride they can provide.

    `id` is an opaque handle the adapter issued and alone can resolve; it is
    what `quote()` takes. `estimated_paise` is the seller's catalogue price when
    it states one, and is **only an estimate** — the fare is whatever `quote()`
    returns.
    """

    id: str
    network: str
    provider_name: str
    item_name: str
    vehicle_category: str = ""
    estimated_paise: int | None = None
    currency: str = "INR"


@dataclass(frozen=True)
class QuoteLine:
    """One line of the seller's breakup, in the seller's own words."""

    title: str
    amount_paise: int


@dataclass(frozen=True)
class Quote:
    """A firm price from one seller, for one offer. Booking nothing.

    `amount_paise` is the seller's total. `breakup` is the seller's own
    itemisation and is carried as given; it is not required to sum to the
    total, because reconciling a seller's arithmetic is not a thing we are
    entitled to do quietly.
    """

    id: str
    offer_id: str
    provider_name: str
    amount_paise: int
    currency: str
    breakup: tuple[QuoteLine, ...] = ()
    #: The seller's stated validity, as an ISO-8601 duration, when it gives one.
    valid_for: str = ""


@dataclass(frozen=True)
class Fulfilment:
    """Who the car is for. Sent only on `confirm()`, never on a search."""

    customer_name: str
    customer_phone: str


@dataclass(frozen=True)
class Order:
    """A booked ride, as the seller last described it."""

    id: str
    quote_id: str
    state: OrderState
    provider_name: str = ""
    amount_paise: int | None = None
    currency: str = "INR"
    #: The seller's own state word, kept so an `UNKNOWN` can be explained.
    vendor_state: str = ""
    driver_name: str = ""
    vehicle_registration: str = ""
    #: The ride-start code the driver will ask for, when the seller issues one.
    start_otp: str = ""
    tracking_url: str = ""


class NetworkProvider(Protocol):
    """The seam. Five requests and a way to hang up."""

    #: Shown in `GET /api/live` so the console can say which network answered.
    name: str

    @property
    def live(self) -> bool:
        """Whether this adapter is actually talking to a network over the wire."""
        ...

    async def search(self, intent: SearchIntent) -> tuple[Offer, ...]:
        """Every offer that came back. Raises `NetworkUnavailable` on silence.

        An empty answer and no answer are different facts; only a seller that
        actually replied with nothing produces an empty tuple.
        """
        ...

    async def quote(self, offer_id: str) -> Quote:
        """Ask one seller for a firm price. Commits nobody to anything."""
        ...

    async def confirm(self, quote_id: str, fulfilment: Fulfilment) -> Order:
        """Book the ride at the quoted price, or raise.

        Raises `QuoteChanged` if the seller's final price differs from the
        quote, and books nothing in that case. Confirming the same quote twice
        returns the same order; it never books a second car.
        """
        ...

    async def status(self, order_id: str) -> Order:
        """Ask the seller where the ride has got to."""
        ...

    async def cancel(self, order_id: str, reason: str) -> Order:
        """Call the ride off, and return it in the state the seller reports."""
        ...

    async def close(self) -> None:
        """Release connections and abandon anything still waiting."""
        ...
