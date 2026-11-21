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
const sketch = readFileSync(join(root, "examples/calibration/sketch.gpp"), "utf8");
const calibrationReport = JSON.parse(readFileSync(join(root, "examples/calibration/completion.json"), "utf8"));
assert.equal(calibrationReport.revision, "sha256:" + createHash("sha256").update(sketch).digest("hex"));
const calibrationSources = calibrationReport.question.alternatives.map(({expression}) => sketch.replace("?rule: I64", expression));
const eighth = "\ncontract next_reading() { correct(4) == 73 }\n";
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
  [calibrationSources[0], 7, "passed"],
  [calibrationSources[1], 7, "passed"],
  [calibrationSources[0] + eighth, 8, "passed"],
  [calibrationSources[1] + eighth, 8, "counterexample"],
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
  const webRoot = join(work, "site");
  const build = spawnSync("sh", [join(root, "website/build.sh"), webRoot], { encoding: "utf8" });
  assert.equal(build.status, 0, build.stderr);
  const html = readFileSync(join(webRoot, "index.html"), "utf8");
  const template = html.match(/<template id="makes10-demo">([^<]+)<\/template>/);
  assert(template, "expected the makes10 fixture in the published HTML");
  const makes10 = JSON.parse(template[1].replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&"));
  const capture = JSON.parse(readFileSync(join(root, "examples/makes10/development.json"), "utf8"));
  const publicSource = readFileSync(join(root, "examples/makes10/public.gpp"), "utf8");
  assert.deepEqual(makes10.observed, capture.negative_control.feedback.observed);
  for (const [variant, record] of [["source", capture.negative_control], ["alternative", capture.reference], ["weak", capture.weak_contract]]) {
    const obligation = record.obligations[0];
    assert.equal(makes10[variant], publicSource.replace("?change: Bool", record.expression) + "\n" + obligation.declaration + "\n");
    const budget = record.public_examples.checked + obligation.checked;
    checks.push([makes10[variant], budget, obligation.status]);
    const report = JSON.parse(webVerify(makes10[variant], budget));
    assert.equal(report.checked, budget);
    assert.deepEqual(report.contracts.slice(0, -1), record.public_examples.contracts);
    assert.deepEqual(report.contracts.at(-1).counterexample, obligation.counterexample);
  }
  writeFileSync(join(work, "sketch.gpp"), sketch);
  const search = spawnSync(binary, ["complete", "sketch.gpp", "--hole", "rule", "--search", "hybrid", "--limit", "32"], {
    cwd: work, encoding: "utf8", timeout: 10_000,
  });
  assert.equal(search.status, 3, search.stderr);
  assert.deepEqual(JSON.parse(search.stdout), calibrationReport, "refresh the native calibration report");
  const minimum = spawnSync(binary, ["complete", "sketch.gpp", "--hole", "rule", "--search", "minimum", "--limit", "32"], {
    cwd: work, encoding: "utf8", timeout: 10_000,
  });
  assert.equal(minimum.status, 0, minimum.stderr);
  const savedMinimum = JSON.parse(readFileSync(join(root, "examples/calibration/minimum.json"), "utf8"));
  assert.deepEqual(JSON.parse(minimum.stdout), savedMinimum, "refresh the minimum-cost calibration report");
  assert.equal(savedMinimum.selected, calibrationReport.question.alternatives[0].expression);
  for (const [i, choice] of calibrationReport.question.alternatives.entries()) {
    writeFileSync(join(work, "choice.expr"), choice.expression);
    const fill = spawnSync(binary, ["complete", "sketch.gpp", "--hole", "rule", "--fill", "choice.expr", "--stdout"], {
      cwd: work, encoding: "utf8", timeout: 10_000,
    });
    assert.equal(fill.status, 0, fill.stderr);
    assert.equal(fill.stdout, calibrationSources[i], "browser candidate differs from the checked native fill");
  }
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
