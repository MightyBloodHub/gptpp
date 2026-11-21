const specimen = document.querySelector("[data-specimen]");
const tabList = specimen.querySelector("[data-tabs]");
const tabs = [...tabList.querySelectorAll("button")];
const panels = tabs.map((tab) => document.getElementById(tab.dataset.panel));
const copyButton = specimen.querySelector("[data-copy]");
const status = specimen.querySelector("[data-status]");
let active = 0;
let selectionVersion = 0;
let pendingFeedback;

function selectTab(index, focus = false) {
  active = index;
  selectionVersion += 1;
  clearTimeout(pendingFeedback);
  copyButton.textContent = "Copy";
  status.textContent = "";
  tabs.forEach((tab, position) => {
    const selected = index === position;
    tab.setAttribute("aria-selected", selected);
    tab.tabIndex = selected ? 0 : -1;
    panels[position].hidden = !selected;
  });
  if (focus) tabs[index].focus();
}

tabList.setAttribute("role", "tablist");
tabs.forEach((tab, index) => {
  tab.setAttribute("role", "tab");
  tab.setAttribute("aria-controls", panels[index].id);
  panels[index].setAttribute("role", "tabpanel");
  panels[index].setAttribute("aria-labelledby", tab.id);
  panels[index].tabIndex = 0;
  panels[index].querySelector(".example-label").hidden = true;

  tab.addEventListener("click", () => selectTab(index));
  tab.addEventListener("keydown", (event) => {
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowRight": {
        const direction = event.key === "ArrowRight" ? 1 : -1;
        selectTab((index + direction + tabs.length) % tabs.length, true);
        break;
      }
      case "Home":
        selectTab(0, true);
        break;
      case "End":
        selectTab(tabs.length - 1, true);
        break;
      default:
        return;
    }
    event.preventDefault();
  });
});

copyButton.addEventListener("click", async () => {
  const version = selectionVersion;
  const code = panels[active].querySelector("pre code");
  try {
    await navigator.clipboard.writeText(code.textContent);
    if (version !== selectionVersion) return;
    copyButton.textContent = "Copied";
    status.textContent = "Copied to clipboard.";
  } catch {
    if (version !== selectionVersion) return;
    const range = document.createRange();
    range.selectNodeContents(code);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    copyButton.textContent = "Selected";
    status.textContent = "Text selected. Use your device's copy command.";
  }
  clearTimeout(pendingFeedback);
  pendingFeedback = setTimeout(() => {
    copyButton.textContent = "Copy";
  }, 2200);
});

selectTab(0);
tabList.hidden = false;
copyButton.hidden = false;

function enableContractVerifier() {
  const form = document.getElementById("contract-playground");
  if (!window.Worker || !window.WebAssembly || !window.TextEncoder) return;

  const source = form.querySelector("#contract-source");
  const budget = form.querySelector("#contract-budget");
  const submit = form.querySelector("[type=submit]");
  const result = form.querySelector(".contract-result");
  const title = result.querySelector("[data-result-title]");
  const detail = result.querySelector("[data-result-detail]");
  const reportBox = form.querySelector(".contract-json");
  const preset = form.querySelector("#contract-example");
  const bugButton = form.querySelector("[data-load-bug]");
  const weakButton = form.querySelector("[data-makes10-weak]");
  const makes10 = JSON.parse(form.querySelector("#makes10-demo").content.textContent);
  const repeat = "if booking == Booking::Cancelled { return Change(available, booking, Outcome::Ok); }";
  const booking = form.querySelector("#booking-example").content.textContent;
  const queue = form.querySelector("#queue-example").content.textContent;
  const sketch = form.querySelector("#calibration-sketch").content.textContent;
  const searchReport = JSON.parse(form.querySelector("#calibration-report").content.textContent);
  const [linear, competing] = searchReport.question.alternatives.map(({expression}) =>
    sketch.replace("?rule: I64", expression));
  const extraObservation = form.querySelector("#extra-observation");
  const calibrationControl = form.querySelector("[data-calibration-control]");
  const eighth = "\ncontract next_reading() { correct(4) == 73 }\n";
  const scenario = document.getElementById("contract-scenario");
  const heading = document.getElementById("contracts-title");
  const terminals = document.querySelectorAll("[data-terminal]");
  const examples = {
    booking: {
      source: booking,
      alternative: booking.replace(repeat, repeat.replace("Change(available,", "Change(available + 1,")),
      button: "Introduce double release",
      title: "Does cancelling twice free two seats?",
      description: "A and B each hold a seat. Cancel A twice and B should still hold its booking, with one seat available. Run the reservation module, then introduce a double release to see which history fails.",
    },
    queue: {
      source: queue,
      alternative: queue.replace("return queued < 8;", "return queued <= 8;"),
      button: "Introduce off-by-one",
      title: "Can this queue admit one more item?",
      description: "The queue has eight slots. Check sizes zero through eight, then change the comparison to admit one item too many.",
    },
    calibration: {
      source: linear,
      alternative: competing,
      button: "Try competing formula",
      title: heading.textContent,
      description: scenario.textContent,
    },
    makes10: {
      ...makes10,
      button: "Try correct reference",
      title: "Does swapping the arguments change the answer?",
      description: "makes10 should return true when either argument is 10 or the pair sums to 10. The archived edit passes all 24 public examples. Check symmetry, try the correct reference, or test the archived edit with a weaker rule that checks only pairs with 10 on the right.",
    },
  };
  let worker = null;
  let deadline;
  let hasInteracted = false;

  function stopWorker() {
    clearTimeout(deadline);
    if (worker) worker.terminate();
    worker = null;
    submit.disabled = false;
    submit.textContent = "Verify source";
    result.removeAttribute("aria-busy");
  }

  function show(state, heading, description, rawReport) {
    result.dataset.state = state;
    title.textContent = heading;
    detail.textContent = description;
    reportBox.hidden = !rawReport;
    reportBox.querySelector("pre").textContent = rawReport || "";
  }

  function showReport(report, rawReport) {
    if (report.schema === "gpp.bootstrap-diagnostic/1") {
      show("error", "Compiler diagnostic", report.code + " · " + report.message, rawReport);
      return;
    }
    if (report.schema !== "gpp.verify/1" || !Array.isArray(report.contracts)) {
      show("error", "Verification failed", "The compiler returned an unexpected report.", rawReport);
      return;
    }

    const coverage = report.checked + (report.checked === 1 ? " assignment checked." : " assignments checked.");
    if (report.status === "passed") {
      const contracts = report.contracts.length === 1 ? report.contracts[0].name : report.contracts.length + " contracts";
      let description = contracts + " · " + coverage;
      if (source.value === makes10.weak || source.value === makes10.alternative) {
        const rule = report.contracts.at(-1);
        const examplesPassed = report.contracts.length - 1;
        description = examplesPassed + " public examples passed. " + (source.value === makes10.weak
          ? "The weaker rule checked " + rule.checked + " pairs with b = 10. It leaves other pairs with a = 10 uncovered."
          : "Swapping the arguments preserved the answer for all " + rule.checked + " ordered pairs with each input from −5 to 18.");
      }
      show("passed", "Passed", description, rawReport);
    } else if (report.status === "counterexample") {
      const row = report.contracts.find((entry) => entry.counterexample);
      const witness = row.counterexample;
      const inputs = Object.entries(witness.inputs).map(([name, value]) => name + " = " + value);
      const outcome = witness.fault ? " raised " + witness.fault : " returned false";
      let description = row.name + "(" + inputs.join(", ") + ")" + outcome + ". " + coverage;
      if (source.value === examples.booking.alternative && row.name === "three_actions") {
        const actions = ["reserve A", "cancel A", "reserve B", "cancel B"];
        description = "First failing history · " + witness.args.map((index) => actions[index]).join(" → ") + ". The second cancellation releases an extra seat. " + coverage;
      }
      if (source.value === competing + eighth && row.name === "next_reading") {
        description = "At reading 4, the competing formula returns 158. The added observation requires 73. " + coverage;
      }
      if (source.value === makes10.source && row.name === "interchangeable") {
        const [first, swapped] = makes10.observed;
        if (witness.inputs.a === first.locals.a && witness.inputs.b === first.locals.b) {
          const call = (entry) => "(" + entry.locals.a + ", " + entry.locals.b + ") returns " + entry.value;
          description = (report.contracts.length - 1) + " public examples passed. " + call(first) + ", and " + call(swapped) + ". The arguments must be interchangeable.";
        }
      }
      show("counterexample", "Counterexample", description, rawReport);
    } else if (report.status === "incomplete") {
      const reasons = {
        budget: "Assignment budget exhausted.",
        resource_limit: "Interpreter resource limit reached.",
        no_contracts: "The module declares no contracts.",
      };
      show("incomplete", "Incomplete", (reasons[report.reason] || "Verification stopped.") + " " + coverage, rawReport);
    } else {
      show("error", "Verification failed", "The compiler returned an unknown status.", rawReport);
    }
  }

  function verify() {
    hasInteracted = true;
    stopWorker();
    if (!form.reportValidity()) return;
    if (new TextEncoder().encode(source.value).length > 32768) {
      show("error", "Source too large", "The browser verifier accepts up to 32 KiB of UTF-8 source.");
      return;
    }

    try {
      const current = new Worker("/contract-worker.js", { type: "module" });
      worker = current;
      submit.disabled = true;
      submit.textContent = "Verifying…";
      result.setAttribute("aria-busy", "true");
      show("running", "Verifying…", "Checking the current source in your browser.");
      current.onmessage = ({ data }) => {
        if (worker !== current) return;
        stopWorker();
        if (data.report) showReport(data.report, data.raw);
        else show("error", "Verification failed", data.error || "No compiler report was returned.");
      };
      current.onerror = () => {
        if (worker !== current) return;
        stopWorker();
        show("error", "Verifier unavailable", "The compiler worker could not run. Try the terminal command below.");
      };
      deadline = setTimeout(() => {
        stopWorker();
        show("incomplete", "Browser time limit", "The worker stopped after 8 seconds. Try fewer assignments or run the terminal verifier.");
      }, 8000);
      current.postMessage({ source: source.value, budget: budget.valueAsNumber });
    } catch (error) {
      stopWorker();
      show("error", "Verifier unavailable", error.message);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    verify();
  });
  form.addEventListener("input", () => {
    hasInteracted = true;
    stopWorker();
    show("ready", "Ready to verify", "Run the verifier to check these changes.");
  });
  function loadExample(variant = "source", run = true) {
    const example = examples[preset.value];
    heading.textContent = example.title;
    scenario.textContent = example.description;
    for (const terminal of terminals) terminal.hidden = terminal.dataset.terminal !== preset.value;
    const calibration = preset.value === "calibration";
    calibrationControl.hidden = !calibration;
    weakButton.hidden = preset.value !== "makes10";
    source.value = example[variant] + (calibration && extraObservation.checked ? eighth : "");
    bugButton.textContent = example.button;
    budget.value = budget.defaultValue;
    source.scrollTop = 0;
    if (variant === "alternative" && preset.value === "booking") {
      const line = source.value.split("Change(available + 1, booking")[0].split("\n").length;
      source.scrollTop = Math.max(0, (line - 5) * parseFloat(getComputedStyle(source).lineHeight));
    }
    if (run) verify();
  }
  source.addEventListener("input", () => {
    if (preset.value === "calibration") extraObservation.checked = source.value.includes(eighth.trim());
  });
  extraObservation.addEventListener("change", () => {
    source.value = extraObservation.checked
      ? source.value + eighth
      : source.value.replace(source.value.includes(eighth) ? eighth : eighth.trim(), "");
    verify();
  });
  preset.addEventListener("change", () => {
    extraObservation.checked = true;
    loadExample();
  });
  bugButton.addEventListener("click", () => loadExample("alternative"));
  weakButton.addEventListener("click", () => loadExample("weak"));
  form.querySelector("[data-reset-source]").addEventListener("click", () => loadExample());

  form.hidden = false;
  for (const terminal of terminals) terminal.open = false;
  const requested = new URL(window.location.href).searchParams.get("example");
  if (requested && Object.hasOwn(examples, requested)) preset.value = requested;
  loadExample("source", !window.IntersectionObserver);
  if (window.IntersectionObserver) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        if (!hasInteracted) verify();
      }
    });
    observer.observe(form);
  }
}

enableContractVerifier();
