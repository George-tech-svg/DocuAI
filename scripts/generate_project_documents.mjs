import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { jsPDF } from '../frontend/node_modules/jspdf/dist/jspdf.es.min.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputDir = path.join(root, 'docs');
const allowed = new Set(['.py', '.ts', '.tsx', '.css', '.html', '.md', '.json', '.toml', '.yml', '.yaml', '.ini', '.txt', '.mjs', '.svg']);
const skippedDirs = new Set(['.git', 'node_modules', 'dist', '__pycache__', '.pytest_cache', '.venv']);

function clean(value) {
  return value.normalize('NFKD').replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/[\u2013\u2014]/g, '-').replace(/[^\x09\x0a\x0d\x20-\x7e]/g, '?');
}

function makePdf(title, subtitle) {
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  let y = 20;
  pdf.setFont('helvetica', 'bold'); pdf.setFontSize(20); pdf.setTextColor(31, 55, 73);
  pdf.text(clean(title), 16, y); y += 9;
  pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(75, 85, 99);
  pdf.text(clean(subtitle), 16, y); y += 10;
  pdf.setDrawColor(200, 214, 223); pdf.line(16, y, pageWidth - 16, y); y += 8;
  return {
    pdf,
    addSection(heading, body, code = false) {
      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(code ? 9 : 12); pdf.setTextColor(31, 55, 73);
      if (y > pageHeight - 25) { pdf.addPage(); y = 18; }
      pdf.text(clean(heading), 16, y); y += code ? 5 : 6;
      pdf.setFont('courier', 'normal'); pdf.setFontSize(code ? 6.4 : 8.4); pdf.setTextColor(39, 48, 55);
      const width = pageWidth - 32;
      for (const sourceLine of body.split(/\r?\n/)) {
        const line = sourceLine.length ? sourceLine : ' ';
        const wrapped = pdf.splitTextToSize(clean(line), width);
        for (const part of wrapped) {
          if (y > pageHeight - 14) { pdf.addPage(); y = 16; }
          pdf.text(part, 16, y); y += code ? 3.1 : 4.1;
        }
      }
      y += code ? 4 : 6;
    },
    save(file) { fs.writeFileSync(path.join(outputDir, file), Buffer.from(pdf.output('arraybuffer'))); },
  };
}

const documentation = fs.readFileSync(path.join(outputDir, 'SYSTEM_DOCUMENTATION.md'), 'utf8');
const functional = makePdf('DocuMind AI - System Documentation', 'Functional and operational guide | Updated 28 November 2026');
functional.addSection('System documentation', documentation);
functional.save('SYSTEM_FUNCTIONAL_DOCUMENTATION.pdf');

function walk(directory) {
  const found = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && skippedDirs.has(entry.name)) continue;
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...walk(absolute));
    else if (allowed.has(path.extname(entry.name).toLowerCase()) && !entry.name.toLowerCase().startsWith('.env')) found.push(absolute);
  }
  return found;
}

const files = walk(root).filter(file => !file.startsWith(outputDir + path.sep));
const source = makePdf('DocuMind AI - Complete Source Reference', `Source code and project files | ${files.length} text files | Updated 28 November 2026`);
for (const file of files.sort()) {
  const relative = path.relative(root, file).replaceAll(path.sep, '/');
  let contents = fs.readFileSync(file, 'utf8');
  if (contents.includes('\0')) continue;
  source.addSection(relative, contents, true);
}
source.save('PROJECT_COMPLETE_SOURCE.pdf');
console.log(`Updated documentation PDFs from ${files.length} text files.`);
