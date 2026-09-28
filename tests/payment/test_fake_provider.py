import pytest
from decimal import Decimal

from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.payment.payment_provider import PaymentProviderError


@pytest.mark.asyncio
async def test_charge_returns_unique_id_and_records_call():
    provider = FakePaymentProvider()

    charge_id = await provider.charge(amount=Decimal("1000.00"), external_reference="payment-1")

    assert charge_id
    assert provider.charges == [
        {"charge_id": charge_id, "amount": Decimal("1000.00"), "external_reference": "payment-1"}
    ]


@pytest.mark.asyncio
async def test_charge_raises_when_configured_to_fail():
    provider = FakePaymentProvider(should_fail_charge=True)

    with pytest.raises(PaymentProviderError):
        await provider.charge(amount=Decimal("1000.00"), external_reference="payment-1")

    assert provider.charges == []


@pytest.mark.asyncio
async def test_release_returns_unique_id_and_records_call():
    provider = FakePaymentProvider()

    transfer_id = await provider.release(
        charge_id="fake-charge-abc", amount=Decimal("300.00"), external_reference="allocation-1"
    )

    assert transfer_id
    assert provider.releases == [
        {
            "transfer_id": transfer_id,
            "charge_id": "fake-charge-abc",
            "amount": Decimal("300.00"),
            "external_reference": "allocation-1",
        }
    ]


@pytest.mark.asyncio
async def test_release_raises_when_configured_to_fail():
    provider = FakePaymentProvider(should_fail_release=True)

    with pytest.raises(PaymentProviderError):
        await provider.release(charge_id="fake-charge-abc", amount=Decimal("300.00"), external_reference="allocation-1")

    assert provider.releases == []
