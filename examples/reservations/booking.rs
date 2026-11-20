// An independent client of libbooking. Supply capacity, then action/ID pairs.
use std::{collections::BTreeMap, env, process::ExitCode};

type Call = unsafe extern "C" fn(i64, i64, i64, *mut i64) -> i32;
#[link(name = "booking")]
unsafe extern "C" {
    fn gpp_v1_available_after(available: i64, state: i64, reserve: i64, out: *mut i64) -> i32;
    fn gpp_v1_booking_after(available: i64, state: i64, reserve: i64, out: *mut i64) -> i32;
    fn gpp_v1_booking_outcome(available: i64, state: i64, reserve: i64, out: *mut i64) -> i32;
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut available = args
        .next()
        .ok_or("usage: booking CAPACITY [reserve|cancel ID]...")?
        .parse::<i64>()
        .map_err(|_| "invalid capacity")?;
    if available < 0 {
        return Err("capacity must be nonnegative".into());
    }
    let mut ledger = BTreeMap::new();
    let mut rejected = false;
    while let Some(action) = args.next() {
        let id = args.next().ok_or("missing booking ID")?;
        if id.is_empty() {
            return Err("missing booking ID".into());
        }
        let reserve = match action.as_str() {
            "reserve" => 1,
            "cancel" => 0,
            _ => return Err(format!("unknown action {action}")),
        };
        let state = ledger.get(&id).copied().unwrap_or(0);
        let call = |f: Call| -> Result<i64, String> {
            let mut out = 0;
            let status = unsafe { f(available, state, reserve, &mut out) };
            if status != 0 {
                return Err(format!("checked call failed with status {status}"));
            }
            Ok(out)
        };
        let outcome = call(gpp_v1_booking_outcome)?;
        let next_available = call(gpp_v1_available_after)?;
        let next_state = call(gpp_v1_booking_after)?;
        let message = [
            "ok",
            "unknown_booking",
            "sold_out",
            "closed_booking",
            "invalid_input",
        ]
        .get(outcome as usize)
        .ok_or("invalid outcome from library")?;
        if outcome == 0 {
            available = next_available;
            ledger.insert(id.clone(), next_state);
        } else {
            rejected = true;
        }
        println!("{action} {id} {message} available={available}");
    }
    for (id, state) in ledger {
        let name = ["unseen", "active", "cancelled"]
            .get(state as usize)
            .ok_or("invalid state from library")?;
        println!("booking {id} {name}");
    }
    if rejected {
        std::process::exit(2);
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
