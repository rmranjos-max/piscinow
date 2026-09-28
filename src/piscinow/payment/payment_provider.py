from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProviderError(Exception):
    """Raised by any PaymentProvider implementation when a charge or release fails."""


class PaymentProvider(ABC):
    """Provider-agnostic interface: charge the buyer once, release retained
    amounts to recipients per payment stage as work progresses."""

    @abstractmethod
    async def charge(self, *, amount: Decimal, external_reference: str) -> str:
        """Charge the buyer the full amount. Returns an external charge id."""
        raise NotImplementedError

    @abstractmethod
    async def release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str:
        """Release part of a previously-charged amount to a recipient. Returns an external transfer id."""
        raise NotImplementedError
