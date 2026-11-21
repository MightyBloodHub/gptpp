// Public rebooking specification. Track issued tickets and ownership separately.
// Inventory is always derived from ticket ownership. Action 4 pads a short word.
record Tickets { issued_a: Bool, owns_a: Bool, issued_b: Bool, owns_b: Bool, receipt: Outcome }

fn issue(capacity: I64, tickets: Tickets, action: I64) -> Tickets !{} {
    if action == 4 { return tickets; }
    let a = action < 2;
    let reserve = action == 0 || action == 2;
    let issued = if a { tickets.issued_a } else { tickets.issued_b };
    let owns = if a { tickets.owns_a } else { tickets.owns_b };
    let occupied = tickets.owns_a as I64 + tickets.owns_b as I64;
    let granted = reserve && (owns || occupied < capacity);
    let receipt = if reserve && !granted { Outcome::SoldOut }
        else if !reserve && !issued { Outcome::UnknownBooking } else { Outcome::Ok };
    return if a { Tickets(issued || granted, granted, tickets.issued_b, tickets.owns_b, receipt) }
        else { Tickets(tickets.issued_a, tickets.owns_a, issued || granted, granted, receipt) };
}

fn ticket_state(issued: Bool, owns: Bool) -> Booking !{} {
    return if owns { Booking::Active } else if issued { Booking::Cancelled } else { Booking::Unseen };
}

fn expected(capacity: I64, w: I64, x: I64, y: I64, z: I64) -> Ledger !{} {
    let empty = Tickets(false, false, false, false, Outcome::Ok);
    let first = issue(capacity, issue(capacity, empty, w), x);
    let all = issue(capacity, issue(capacity, first, y), z);
    return Ledger(capacity - all.owns_a as I64 - all.owns_b as I64,
        ticket_state(all.issued_a, all.owns_a), ticket_state(all.issued_b, all.owns_b), all.receipt);
}

fn observed(capacity: I64, w: I64, x: I64, y: I64, z: I64) -> Ledger !{} {
    let empty = Ledger(capacity, Booking::Unseen, Booking::Unseen, Outcome::Ok);
    return apply_action(apply_action(apply_action(apply_action(empty, w), x), y), z);
}

contract local_reopen() {
    observed(1, 0, 1, 0, 4) == Ledger(0, Booking::Active, Booking::Unseen, Outcome::Ok)
}
contract one_step(capacity: I64 in 0..=2, z: I64 in 0..=3) {
    observed(capacity, 4, 4, 4, z) == expected(capacity, 4, 4, 4, z)
}
contract two_steps(capacity: I64 in 0..=2, y: I64 in 0..=3, z: I64 in 0..=3) {
    observed(capacity, 4, 4, y, z) == expected(capacity, 4, 4, y, z)
}
contract three_steps(capacity: I64 in 0..=2, x: I64 in 0..=3, y: I64 in 0..=3, z: I64 in 0..=3) {
    observed(capacity, 4, x, y, z) == expected(capacity, 4, x, y, z)
}
contract four_steps(capacity: I64 in 0..=2, w: I64 in 0..=3, x: I64 in 0..=3,
        y: I64 in 0..=3, z: I64 in 0..=3) {
    observed(capacity, w, x, y, z) == expected(capacity, w, x, y, z)
}
