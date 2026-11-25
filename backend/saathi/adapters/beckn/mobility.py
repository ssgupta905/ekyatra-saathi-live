"""Reading ONDC:TRV10 (ride-hailing) callbacks into the port's types.

Everything here is a pure function of a callback's `message`. The rules it
keeps:

- **A fare is the seller's `quote.price`, or nothing.** Missing, unreadable or
  fractional-paise prices raise `NetworkUnavailable`. Nothing is computed from
  distance or the catalogue estimate.
- **A state word this code has not seen is `OrderState.UNKNOWN`.** The raw word
  is kept on the order so a person can read it.
- **A cancelled order is cancelled**, whatever a stale fulfilment state on the
  same payload still says.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ...ports.network import NetworkUnavailable, Order, OrderState, QuoteLine

#: TRV10 fulfilment state codes -> ours.
FULFILMENT_STATES: dict[str, OrderState] = {
    "RIDE_CONFIRMED": OrderState.CONFIRMED,
    "RIDE_ASSIGNED": OrderState.CONFIRMED,
    "RIDE_ENROUTE_PICKUP": OrderState.CONFIRMED,
    "RIDE_ARRIVED_PICKUP": OrderState.CONFIRMED,
    "RIDE_STARTED": OrderState.IN_PROGRESS,
    "RIDE_ENDED": OrderState.COMPLETED,
    "RIDE_CANCELLED": OrderState.CANCELLED,
}

#: Order-level status words -> ours, used when no fulfilment state is given.
ORDER_STATES: dict[str, OrderState] = {
    "ACTIVE": OrderState.CONFIRMED,
    "COMPLETE": OrderState.COMPLETED,
    "COMPLETED": OrderState.COMPLETED,
    "CANCELLED": OrderState.CANCELLED,
}


@dataclass(frozen=True)
class CatalogItem:
    """One rideable item from an `on_search` catalogue, with what selects it."""

    provider_id: str
    provider_name: str
    item_id: str
    item_name: str
    fulfillment_id: str
    vehicle_category: str
    estimated_paise: int | None
    currency: str


@dataclass(frozen=True)
class SellerQuote:
    amount_paise: int
    currency: str
    breakup: tuple[QuoteLine, ...]
    valid_for: str


def to_paise(value: object) -> int:
    """`"145.50"` -> `14550`. Anything that is not a whole number of paise raises."""
    try:
        amount = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError) as exc:
        raise NetworkUnavailable(f"unreadable price {value!r}") from exc
    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
        raise NetworkUnavailable(f"price {value!r} is not a whole number of paise")
    return int(amount)


def _price(price: object) -> tuple[int, str]:
    if not isinstance(price, dict) or "value" not in price:
        raise NetworkUnavailable("seller gave no price")
    currency = price.get("currency")
    if not isinstance(currency, str) or not currency:
        raise NetworkUnavailable("seller gave a price with no currency")
    return to_paise(price["value"]), currency


def _name(obj: object) -> str:
    if isinstance(obj, dict):
        descriptor = obj.get("descriptor")
        if isinstance(descriptor, dict):
            return str(descriptor.get("name") or descriptor.get("code") or "")
    return ""


def _list(obj: object, key: str) -> list[dict]:
    value = obj.get(key) if isinstance(obj, dict) else None
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def catalog_items(message: dict) -> list[CatalogItem]:
    """Every item in an `on_search` catalogue. Unpriced items are kept, unpriced."""
    catalog = message.get("catalog") if isinstance(message, dict) else None
    items: list[CatalogItem] = []
    for provider in _list(catalog, "providers"):
        provider_id = str(provider.get("id") or "")
        if not provider_id:
            continue
        fulfilments = {str(f.get("id")): f for f in _list(provider, "fulfillments")}
        for item in _list(provider, "items"):
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            fulfillment_ids = item.get("fulfillment_ids") or []
            fulfillment_id = str(fulfillment_ids[0]) if fulfillment_ids else ""
            vehicle = fulfilments.get(fulfillment_id, {}).get("vehicle") or {}
            estimated: int | None = None
            currency = "INR"
            if isinstance(item.get("price"), dict):
                try:
                    estimated, currency = _price(item["price"])
                except NetworkUnavailable:
                    estimated = None
            items.append(
                CatalogItem(
                    provider_id=provider_id,
                    provider_name=_name(provider) or provider_id,
                    item_id=item_id,
                    item_name=_name(item) or item_id,
                    fulfillment_id=fulfillment_id,
                    vehicle_category=str(vehicle.get("category") or ""),
                    estimated_paise=estimated,
                    currency=currency,
                )
            )
    return items


def seller_quote(message: dict) -> SellerQuote:
    """The firm price in an `on_select` / `on_init` / `on_confirm` order."""
    order = message.get("order") if isinstance(message, dict) else None
    quote = order.get("quote") if isinstance(order, dict) else None
    if not isinstance(quote, dict):
        raise NetworkUnavailable("seller's answer carried no quote")
    amount, currency = _price(quote.get("price"))
    breakup = []
    for line in _list(quote, "breakup"):
        try:
            line_amount, _ = _price(line.get("price"))
        except NetworkUnavailable:
            continue
        breakup.append(QuoteLine(title=str(line.get("title") or ""), amount_paise=line_amount))
    return SellerQuote(
        amount_paise=amount,
        currency=currency,
        breakup=tuple(breakup),
        valid_for=str(quote.get("ttl") or ""),
    )


def order_state(order: dict) -> tuple[OrderState, str]:
    """Our state, and the seller's word for it."""
    status = str(order.get("status") or "").upper()
    if ORDER_STATES.get(status) is OrderState.CANCELLED or status == "SOFT_CANCEL":
        return OrderState.CANCELLED, status
    for fulfilment in _list(order, "fulfillments"):
        state = fulfilment.get("state")
        descriptor = state.get("descriptor") if isinstance(state, dict) else None
        code = descriptor.get("code") if isinstance(descriptor, dict) else None
        if code:
            code = str(code).upper()
            return FULFILMENT_STATES.get(code, OrderState.UNKNOWN), code
    if status:
        return ORDER_STATES.get(status, OrderState.UNKNOWN), status
    return OrderState.UNKNOWN, ""


def read_order(message: dict, *, quote_id: str, provider_name: str = "") -> Order:
    """An `on_confirm` / `on_status` / `on_cancel` message as an `Order`."""
    order = message.get("order") if isinstance(message, dict) else None
    if not isinstance(order, dict) or not order.get("id"):
        raise NetworkUnavailable("seller's answer carried no order id")
    state, vendor_state = order_state(order)

    amount: int | None = None
    currency = "INR"
    if isinstance(order.get("quote"), dict):
        try:
            priced = seller_quote(message)
            amount, currency = priced.amount_paise, priced.currency
        except NetworkUnavailable:
            amount = None

    driver = registration = otp = tracking = ""
    for fulfilment in _list(order, "fulfillments"):
        agent = fulfilment.get("agent") or {}
        person = agent.get("person") if isinstance(agent, dict) else None
        if isinstance(person, dict) and person.get("name"):
            driver = str(person["name"])
        vehicle = fulfilment.get("vehicle")
        if isinstance(vehicle, dict) and vehicle.get("registration"):
            registration = str(vehicle["registration"])
        for stop in _list(fulfilment, "stops"):
            auth = stop.get("authorization")
            if (
                str(stop.get("type") or "").upper() == "START"
                and isinstance(auth, dict)
                and str(auth.get("type") or "").upper() == "OTP"
            ):
                otp = str(auth.get("token") or "")
        tracking_tag = fulfilment.get("tracking_url") or ""
        if tracking_tag:
            tracking = str(tracking_tag)

    provider = order.get("provider")
    return Order(
        id=str(order["id"]),
        quote_id=quote_id,
        state=state,
        provider_name=_name(provider) or provider_name,
        amount_paise=amount,
        currency=currency,
        vendor_state=vendor_state,
        driver_name=driver,
        vehicle_registration=registration,
        start_otp=otp,
        tracking_url=tracking,
    )
