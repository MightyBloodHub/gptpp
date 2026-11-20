// Cancellation projection of the reservation transition on valid booking states.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Booking {
    Unseen,
    Active,
    Cancelled,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Outcome {
    Ok,
    UnknownBooking,
}

type Change = (i64, Booking, Outcome);
fn cancel(n: i64, state: Booking) -> Change {
    match state {
        Booking::Active => (n.checked_add(1).unwrap(), Booking::Cancelled, Outcome::Ok),
        Booking::Cancelled => (n, Booking::Cancelled, Outcome::Ok),
        Booking::Unseen => (n, Booking::Unseen, Outcome::UnknownBooking),
    }
}

#[kani::proof]
fn active_cancel_twice() {
    let n: i64 = kani::any();
    kani::assume((0..i64::MAX).contains(&n));
    let first = cancel(n, Booking::Active);
    let second = cancel(first.0, first.1);
    assert!(first == (n + 1, Booking::Cancelled, Outcome::Ok) && second == first);
}

#[kani::proof]
fn repeat_cancel() {
    let n: i64 = kani::any();
    kani::assume(n >= 0);
    assert!(cancel(n, Booking::Cancelled) == (n, Booking::Cancelled, Outcome::Ok));
}

#[kani::proof]
fn unknown_cancel() {
    let n: i64 = kani::any();
    kani::assume(n >= 0);
    assert!(cancel(n, Booking::Unseen) == (n, Booking::Unseen, Outcome::UnknownBooking));
}
