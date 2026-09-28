import uuid
from decimal import Decimal

from piscinow.payment.payment_provider import PaymentProvider, PaymentProviderError


class FakePaymentProvider(PaymentProvider):
    """Deterministic in-memory provider for tests: records every charge/release
    call for inspection, and can be configured to simulate a failure."""

    def __init__(self, *, should_fail_charge: bool = False, should_fail_release: bool = False):
        self.should_fail_charge = should_fail_charge
        self.should_fail_release = should_fail_release
        self.charges: list[dict] = []
        self.releases: list[dict] = []

    async def charge(self, *, amount: Decimal, external_reference: str) -> str:
        if self.should_fail_charge:
            raise PaymentProviderError("simulated charge failure")
        charge_id = f"fake-charge-{uuid.uuid4()}"
        self.charges.append({"charge_id": charge_id, "amount": amount, "external_reference": external_reference})
        return charge_id

    async def release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str:
        if self.should_fail_release:
            raise PaymentProviderError("simulated release failure")
        transfer_id = f"fake-transfer-{uuid.uuid4()}"
        self.releases.append(
            {
                "transfer_id": transfer_id,
                "charge_id": charge_id,
                "amount": amount,
                "external_reference": external_reference,
            }
        )
        return transfer_id
