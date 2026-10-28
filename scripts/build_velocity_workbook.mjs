// Run with the Codex bundled Node.js and @oai/artifact-tool dependency runtime.
import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [input, outputDirectory] = process.argv.slice(2);
if (!input || !outputDirectory) throw new Error("Usage: build_velocity_workbook.mjs <data.json> <output-directory>");
const data = JSON.parse(await fs.readFile(input, "utf8"));
const workbook = Workbook.create();
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
await fs.mkdir(outputDirectory, { recursive: true });

for (const source of data.sheets) {
  const sheet = workbook.worksheets.add(source.name);
  const last = source.rows.length + 3;
  const area = sheet.getRange(`A1:R${last}`);
  area.format.font = { name: "Arial", size: 11, color: "#202124" };
  area.format.rowHeight = 23;
  sheet.getRange("A1").values = [[`Velocity report ${data.year} ${source.name}`]];
  sheet.getRange("A1").format.font = { name: "Arial", size: 15, bold: true };
  sheet.getRange("A2").values = [[`Jira points. As of ${data.as_of}. Current month is partial. Blank = no data. Quarter average uses populated months.`]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 10, color: "#5F6368" };
  sheet.getRange("A3:R3").values = [["Board", "Person", ...months, "Q1 Average", "Q2 Average", "Q3 Average", "Q4 Average"]];
  sheet.getRange("A3:R3").format = { fill: "#F1F3F4", font: { name: "Arial", size: 11, bold: true }, horizontalAlignment: "center" };
  if (source.rows.length) {
    sheet.getRange(`A4:N${last}`).values = source.rows;
    const formulas = source.rows.map((_, index) => {
      const row = index + 4;
      return [["C", "E"], ["F", "H"], ["I", "K"], ["L", "N"]].map(([start, end]) =>
        `=IF(COUNT(${start}${row}:${end}${row})=0,"",AVERAGE(${start}${row}:${end}${row}))`);
    });
    sheet.getRange(`O4:R${last}`).formulas = formulas;
    sheet.getRange(`C4:N${last}`).setNumberFormat("0.0");
    sheet.getRange(`O4:R${last}`).setNumberFormat("0.00");
    sheet.getRange(`C4:R${last}`).format.horizontalAlignment = "right";
  }
  sheet.getRange(`A1:A${last}`).format.columnWidth = 10;
  sheet.getRange(`B1:B${last}`).format.columnWidth = 43;
  sheet.getRange(`C1:N${last}`).format.columnWidth = 9;
  sheet.getRange(`O1:R${last}`).format.columnWidth = 14;
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(2);
  for (let index = 0; index < source.rows.length; index++) {
    if (index === 0 || source.rows[index][0] !== source.rows[index - 1][0]) {
      sheet.getRange(`A${index + 4}:R${index + 4}`).format.borders = { top: { style: "thin", color: "#DADCE0" } };
    }
  }
}

workbook.recalculate();
for (const source of data.sheets) {
  const sheet = workbook.worksheets.getItem(source.name);
  const actual = sheet.getRange(`O4:R${source.rows.length + 3}`).values;
  for (let row = 0; row < source.rows.length; row++) {
    for (let quarter = 0; quarter < 4; quarter++) {
      const values = source.rows[row].slice(2 + quarter * 3, 5 + quarter * 3).filter(value => value !== null);
      if (values.length) assert.ok(Math.abs(actual[row][quarter] - values.reduce((a, b) => a + b, 0) / values.length) < 1e-9);
      else assert.ok(actual[row][quarter] === "" || actual[row][quarter] === null);
    }
  }
  const image = await workbook.render({ sheetName: source.name, range: "A1:R12", scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDirectory, `${source.name}.png`), new Uint8Array(await image.arrayBuffer()));
  console.log(`${source.name}: ${source.rows.length} rows, all quarterly averages verified`);
}
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 10 }, maxChars: 1500 });
console.log(errors.ndjson);
const output = await SpreadsheetFile.exportXlsx(workbook);
const target = path.join(outputDirectory, `velocity-${data.year}.xlsx`);
await output.save(target);
console.log(target);
