"""Payment gateway adapters: Razorpay, Cashfree, and an in-memory fake.

The vendor's gateway collects; Saathi only asks for links and reads webhooks.
"""

from .cashfree import CashfreePayments
from .fake import FakePayments
from .razorpay import RazorpayPayments

__all__ = ["CashfreePayments", "FakePayments", "RazorpayPayments"]
