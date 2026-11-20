def shipping_fee(subtotal_cents: int, member: bool, pickup: bool) -> int:
    if pickup or subtotal_cents >= 7500:
        return 0
    if member:
        return 299
    return 599
