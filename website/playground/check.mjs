// Compare the checked-in browser verifier against the command-line compiler.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const binary = resolve(process.argv[2] ?? join(root, "target/debug/gpp"));
const sample = readFileSync(join(root, "examples/capacity.gpp"), "utf8");
const booking = readFileSync(join(root, "examples/reservations/booking.gpp"), "utf8");
const repeat = "if booking == Booking::Cancelled { return Change(available, booking, Outcome::Ok); }";
assert(booking.includes(repeat));
const brokenLedger = booking.replace(repeat, repeat.replace("Change(available,", "Change(available + 1,"));
const wasm = readFileSync(new URL("verify.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiate(wasm);
const api = instance.exports;

function webVerify(source, budget) {
  const data = Buffer.from(source);
  const hash = createHash("sha256").update(data).digest("hex");
  const length = 64 + data.length;
  const ptr = api.input_buffer(length);
  assert.notEqual(ptr, 0);
  const view = new Uint8Array(api.memory.buffer, ptr, length);
  view.set(Buffer.from(hash));
  view.set(data, 64);
  const size = api.verify_input(budget);
  return new TextDecoder().decode(new Uint8Array(api.memory.buffer, api.output_buffer(), size)).trim();
}

const bare = "module demo; pub fn main() -> I64 !{} { return 0; }\n";
const checks = [
  [booking, 341, "passed"],
  [booking, 340, "incomplete"],
  [brokenLedger, 341, "counterexample"],
  [sample, 9, "passed"],
  [sample, 8, "incomplete"],
  [sample.replace("queued < 8", "queued <= 8"), 9, "counterexample"],
  [bare + "contract extreme(x: I64 in 9223372036854775806..=9223372036854775807) { x < 9223372036854775807 }", 2, "counterexample"],
  [bare + "contract fault(x: I64 in -1..=1) { 1 / x != 2 }", 3, "counterexample"],
  [bare + "contract singleton() { true }", 1, "passed"],
  [bare, 1, "incomplete"],
  [bare + "contract invalid(b: Bool) { b + 1 }", 3, "gpp.bootstrap-diagnostic/1"],
];
const work = mkdtempSync(join(tmpdir(), "gpp-playground-"));
try {
  for (const [source, budget, status] of checks) {
    writeFileSync(join(work, "playground.gpp"), source);
    const run = spawnSync(binary, ["verify", "playground.gpp", "--budget", String(budget)], {
      cwd: work, encoding: "utf8", timeout: 10_000,
    });
    if (run.error) throw run.error;
    const cli = (run.stdout || run.stderr).trim();
    const output = webVerify(source, budget);
    assert.equal(output, cli);
    const data = JSON.parse(cli);
    assert.equal(data.status ?? data.schema, status);
  }
  console.log(`Browser and CLI outputs match on ${checks.length} checks.`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
