
// Extra symbolic obligations appended to the production booking module.
// An active booking owns one seat, so available + 1 must fit the ledger's I64.
fn cancel_twice(available: I64) -> Bool !{} {
    let first = transition(available, Booking::Active, false);
    let again = transition(first.available, first.booking, false);
    return first == Change(available + 1, Booking::Cancelled, Outcome::Ok) && again == first;
}
contract active_cancel_twice(available: I64 in 0..=9223372036854775806) {
    cancel_twice(available)
}
contract repeat_cancel(available: I64 in 0..=9223372036854775807) {
    transition(available, Booking::Cancelled, false) == Change(available, Booking::Cancelled, Outcome::Ok)
}
contract unknown_cancel(available: I64 in 0..=9223372036854775807) {
    transition(available, Booking::Unseen, false) == Change(available, Booking::Unseen, Outcome::UnknownBooking)
}
