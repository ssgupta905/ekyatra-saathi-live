"""What a journey is likely to cost, from published rates rather than guesses.

`domain/budget.py` says it plainly: *"Nothing here holds money. There is no
amount, no quote and no total, because this project does not report a fare it
was not given."* That rule stands for anything presented as fact. This package
is the narrow, deliberate exception, and the shape of the exception is what
keeps it honest:

**Every number has a published basis, named on screen.** A rail fare comes from
Indian Railways' distance slabs; a bus fare from a state transport
corporation's per-kilometre rate; an auto fare from a city's gazetted meter
rate. The basis and the date it was read are carried with the figure, all the
way to the family's screen, so "where did that come from?" has an answer.

**Nothing is ever a quote.** Every figure is an estimate and says so. A family
who is told "about ₹1,400" and finds it is ₹1,600 has been inconvenienced; a
family told "₹1,400" as though it were a price has been lied to.

**No number is ever attributed to a company.** IRCTC, MakeMyTrip, OYO, Uber and
Ola are where a family books, not where our figures come from — we have no
access to their pricing and inventing it would misrepresent a real business.
Lodging is therefore a band for a *kind* of place in an area, never "an OYO
room costs X".

**What the family says always wins.** A stated figure replaces an estimate for
that family and that route, permanently, and carries the sentence they said it
in. Our arithmetic is the fallback for a family who has not told us yet, not a
correction to one who has.
"""

from .journey import cost_of_journey, mode_for, nights_for
from .rates import (
    Estimate,
    JourneyCost,
    Rate,
    RateTable,
    load_rates,
)

__all__ = [
    "Estimate",
    "JourneyCost",
    "Rate",
    "RateTable",
    "cost_of_journey",
    "load_rates",
    "mode_for",
    "nights_for",
]
