import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [input, outputDirectory] = process.argv.slice(2);
if (!input || !outputDirectory) throw new Error("Usage: build_velocity_workbook.mjs <data.json> <output-directory>");
const data = JSON.parse(await fs.readFile(input, "utf8"));
const workbook = Workbook.create();
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const quarterColumns = ["E", "I", "M", "Q"];
const quarterRanges = [["B", "D"], ["F", "H"], ["J", "L"], ["N", "P"]];
const boardLabels = { SC: "SC — Social Commerce", IMP: "IMP — TrueID HERO", LS: "LS — Watch", EXP: "EXP — Today", VAL: "VAL — DevEx" };
const renderedRows = new Map();
await fs.mkdir(outputDirectory, { recursive: true });

for (const source of data.sheets) {
  const sheet = workbook.worksheets.add(source.name);
  const rows = [];
  const people = [];
  const sectionRows = [];
  let previousBoard;
  for (const sourceRow of source.rows) {
    const [board, person, ...points] = sourceRow;
    if (board !== previousBoard) {
      sectionRows.push(rows.length + 4);
      rows.push([boardLabels[board] || board, ...Array(16).fill(null)]);
      previousBoard = board;
    }
    const rowNumber = rows.length + 4;
    const values = [person];
    for (let quarter = 0; quarter < 4; quarter++) values.push(...points.slice(quarter * 3, quarter * 3 + 3), null);
    rows.push(values);
    people.push({ rowNumber, sourceRow });
  }
  renderedRows.set(source.name, people);
  const last = rows.length + 3;
  const area = sheet.getRange(`A1:Q${last}`);
  area.format.font = { name: "Arial", size: 11, color: "#202124" };
  area.format.rowHeight = 23;
  sheet.getRange("A1").values = [[`Velocity report ${data.year} ${source.name}`]];
  sheet.getRange("A1").format.font = { name: "Arial", size: 15, bold: true };
  sheet.getRange("A2").values = [[`Jira points. As of ${data.as_of}. Current month is partial. Blank = no data. Quarter average uses populated months.`]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 10, color: "#5F6368" };
  const headers = ["Person"];
  for (let quarter = 0; quarter < 4; quarter++) headers.push(...months.slice(quarter * 3, quarter * 3 + 3), `Q${quarter + 1} Average`);
  sheet.getRange("A3:Q3").values = [headers];
  sheet.getRange("A3:Q3").format = { fill: "#F1F3F4", font: { name: "Arial", size: 11, bold: true }, horizontalAlignment: "center" };
  if (rows.length) {
    sheet.getRange(`A4:Q${last}`).values = rows;
    sheet.getRange(`B4:Q${last}`).setNumberFormat("0.0");
    sheet.getRange(`B4:Q${last}`).format.horizontalAlignment = "right";
    for (let quarter = 0; quarter < 4; quarter++) {
      const [start, end] = quarterRanges[quarter];
      const column = quarterColumns[quarter];
      sheet.getRange(`${column}4:${column}${last}`).setNumberFormat("0.00");
      for (const { rowNumber } of people) sheet.getRange(`${column}${rowNumber}`).formulas = [[
        `=IF(COUNT(${start}${rowNumber}:${end}${rowNumber})=0,"",AVERAGE(${start}${rowNumber}:${end}${rowNumber}))`,
      ]];
    }
  }
  sheet.getRange(`A1:A${last}`).format.columnWidth = 43;
  sheet.getRange(`B1:Q${last}`).format.columnWidth = 9;
  for (const column of quarterColumns) sheet.getRange(`${column}1:${column}${last}`).format.columnWidth = 14;
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(1);
  for (const row of sectionRows) {
    sheet.getRange(`A${row}:Q${row}`).format = {
      fill: "#E8EAED", font: { name: "Arial", size: 11, bold: true }, horizontalAlignment: "left",
    };
  }
}

workbook.recalculate();
for (const source of data.sheets) {
  const sheet = workbook.worksheets.getItem(source.name);
  for (const { rowNumber, sourceRow } of renderedRows.get(source.name)) {
    for (let quarter = 0; quarter < 4; quarter++) {
      const actual = sheet.getRange(`${quarterColumns[quarter]}${rowNumber}`).values[0][0];
      const values = sourceRow.slice(2 + quarter * 3, 5 + quarter * 3).filter(value => value !== null);
      if (values.length) assert.ok(Math.abs(actual - values.reduce((a, b) => a + b, 0) / values.length) < 1e-9);
      else assert.ok(actual === "" || actual === null);
    }
  }
  const image = await workbook.render({ sheetName: source.name, range: "A1:Q12", scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDirectory, `${source.name}.png`), new Uint8Array(await image.arrayBuffer()));
  console.log(`${source.name}: ${source.rows.length} rows, all quarterly averages verified`);
}
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 10 }, maxChars: 1500 });
console.log(errors.ndjson);
const output = await SpreadsheetFile.exportXlsx(workbook);
const target = path.join(outputDirectory, `velocity-${data.year}.xlsx`);
await output.save(target);
console.log(target);
