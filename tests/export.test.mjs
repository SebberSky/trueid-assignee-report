import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
import test from "node:test";

const html = fs.readFileSync(new URL("../app/static/index.html", import.meta.url), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\s*boot\(\);\s*$/, "");

function harness({ clipboardDenied = false, json = null, contentType = "application/json" } = {}) {
  const elements = new Map();
  const opened = [];
  let copied;
  const element = id => {
    if (!elements.has(id)) elements.set(id, { value: "", style: {}, textContent: "", appendChild() {}, focus() {}, select() {} });
    return elements.get(id);
  };
  const context = vm.createContext({
    document: { getElementById: element, querySelectorAll: () => [], createElement: () => ({}) },
    window: { open(url) { opened.push(url); return {}; } },
    navigator: { clipboard: { async writeText(value) { if (clipboardDenied) throw new Error("Clipboard denied"); copied = value; } } },
    fetch: async () => ({ ok: true, headers: { get: () => contentType }, json: async () => {
      if (contentType === "text/html") throw new SyntaxError("Unexpected token '<'");
      return json;
    } }),
    setTimeout: () => {}, URL, Date, Intl, console,
  });
  vm.runInContext(script, context);
  return { context, element, opened, copied: () => copied };
}

test("original export and velocity have separate buttons and handlers", () => {
  assert.match(html, /id="export-sheet"[^>]*>Copy to Google Sheets/);
  assert.match(html, /id="export-velocity"[^>]*>Export velocity report/);
});

test("monthly export keeps the selected report and search filter", async () => {
  const h = harness();
  vm.runInContext('report = {rows:[{name:"Alice",boards:["SC"],tickets_ios:2,tickets_ios_points:8},{name:"Bob",boards:["IMP"]}]}', h.context);
  h.element("q").value = "Alice";
  await vm.runInContext("exportToGoogleSheets()", h.context);
  assert.match(h.copied(), /Tickets iOS Points/);
  assert.match(h.copied(), /Alice\tSC\t2\t8/);
  assert.doesNotMatch(h.copied(), /Bob/);
  assert.deepEqual(h.opened, ["https://sheets.new"]);
});

test("denied clipboard presents selectable data instead of losing the export", async () => {
  const h = harness({ clipboardDenied: true });
  vm.runInContext('report = {rows:[{name:"Alice",boards:["SC"]}]}', h.context);
  await vm.runInContext("exportToGoogleSheets()", h.context);
  assert.equal(h.element("export-copy-fallback").style.display, "block");
  assert.match(h.element("export-copy-fallback").value, /Alice/);
  assert.match(h.element("export-status").textContent, /Ctrl\+C/);
});

test("missing JSON served as HTML produces a specific message", async () => {
  const h = harness({ contentType: "text/html" });
  await vm.runInContext("loadVelocityExport()", h.context);
  h.element("export-velocity").onclick();
  assert.match(h.element("export-status").textContent, /ยังไม่มี Google Sheet/);
  assert.deepEqual(h.opened, []);
});

test("velocity opens its prepared native Google Sheet without clipboard", async () => {
  const url = "https://docs.google.com/spreadsheets/d/test-sheet/edit";
  const year = Number(new Intl.DateTimeFormat("en", {year:"numeric",timeZone:"Asia/Bangkok"}).format(new Date()));
  const h = harness({ clipboardDenied: true, json: {year,url,generated_at:new Date().toISOString()} });
  await vm.runInContext("loadVelocityExport()", h.context);
  h.element("export-velocity").onclick();
  assert.deepEqual(h.opened, [url]);
  assert.match(h.element("export-status").textContent, /iOS \/ Android/);
});
