// Run the same scalar checker and finite verifier as the CLI in an isolated worker.
self.onmessage = async ({ data }) => {
  try {
    const { source, budget } = data;
    if (typeof source !== "string" || !Number.isInteger(budget) || budget < 0 || budget > 10000) {
      throw new Error("Enter source code and an assignment budget between 0 and 10000.");
    }
    const encoder = new TextEncoder();
    const bytes = encoder.encode(source);
    if (bytes.length > 32768) throw new Error("The browser verifier accepts up to 32 KiB of source.");

    const [response, hash] = await Promise.all([
      fetch(new URL("playground/verify.wasm", self.location.href)),
      crypto.subtle.digest("SHA-256", bytes),
    ]);
    if (!response.ok) throw new Error("The browser verifier could not be loaded.");
    // ArrayBuffer instantiation also works on static hosts serving generic binary MIME.
    const { instance } = await WebAssembly.instantiate(await response.arrayBuffer());
    const api = instance.exports;
    const digest = Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join("");
    const address = api.input_buffer(bytes.length + digest.length);
    if (!address) throw new Error("The verifier could not allocate an input buffer.");
    const frame = new Uint8Array(api.memory.buffer, address, bytes.length + digest.length);
    frame.set(encoder.encode(digest));
    frame.set(bytes, digest.length);

    const length = api.verify_input(budget);
    const offset = api.output_buffer();
    const json = new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(api.memory.buffer, offset, length));
    // Keep large I64 witnesses exact on browsers whose JSON parser rounds to a double.
    const displayJson = json.replace(/"(?:\\.|[^"\\])*"|-?\d+/g, (token) =>
      token.startsWith('"') || Number.isSafeInteger(Number(token)) ? token : JSON.stringify(token));
    self.postMessage({ report: JSON.parse(displayJson), raw: json.trim() });
  } catch (error) {
    self.postMessage({ error: typeof WebAssembly !== "undefined" && error instanceof WebAssembly.RuntimeError
      ? "The browser verifier reached its execution limit." : String(error.message || error) });
  }
};
