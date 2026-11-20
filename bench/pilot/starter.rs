pub fn shipping_fee(subtotal_cents: i64, member: bool, pickup: bool) -> i64 {
    if pickup || subtotal_cents >= 7500 {
        return 0;
    }
    if member {
        return 299;
    }
    599
}
