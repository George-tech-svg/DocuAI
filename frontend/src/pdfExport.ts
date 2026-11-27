import type { jsPDF } from "jspdf";
import type { ChatMessage } from "./types";

const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
const LEFT = 20;
const RIGHT = 20;
const BOTTOM = 20;

function pdfText(value: string): string {
  return value
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/[*_`]/g, "")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[—–]/g, "-")
    .replace(/…/g, "...")
    .replace(/[^\u0000-\u00FF]/g, "?");
}

function addFooter(doc: jsPDF) {
  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page += 1) {
    doc.setPage(page);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(105, 119, 133);
    doc.text("DocuMind AI", LEFT, PAGE_HEIGHT - 10);
    doc.text(`${page} / ${pages}`, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 10, { align: "right" });
  }
}

function addParagraph(doc: jsPDF, value: string, y: number, options: { size?: number; indent?: number; color?: [number, number, number] } = {}): number {
  const size = options.size ?? 11;
  const indent = options.indent ?? 0;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(size);
  doc.setTextColor(...(options.color ?? [48, 61, 73]));
  const lines = doc.splitTextToSize(pdfText(value), PAGE_WIDTH - LEFT - RIGHT - indent);
  for (const line of lines) {
    if (y + size * 0.42 > PAGE_HEIGHT - BOTTOM) {
      doc.addPage();
      y = 20;
    }
    doc.text(line, LEFT + indent, y);
    y += size * 0.48;
  }
  return y + 2;
}

function addMarkdownAnswer(doc: jsPDF, content: string, startY: number): number {
  let y = startY;
  for (const rawLine of content.replace(/\r\n?/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line || /^---+$/.test(line)) {
      y += 2;
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      y += 3;
      const level = heading[1].length;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(level === 1 ? 16 : level === 2 ? 13 : 11);
      doc.setTextColor(34, 76, 112);
      if (y + 9 > PAGE_HEIGHT - BOTTOM) { doc.addPage(); y = 20; }
      doc.text(pdfText(heading[2]), LEFT, y);
      y += level === 1 ? 10 : 8;
      continue;
    }
    const bullet = line.match(/^[-*+]\s+(.+)$/);
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      y = addParagraph(doc, `-  ${(bullet ?? numbered)![1]}`, y, { indent: 4 });
    } else {
      y = addParagraph(doc, line, y);
    }
  }
  return y;
}

function addSources(doc: jsPDF, message: ChatMessage, y: number): number {
  if (!message.sources?.length) return y;
  y += 5;
  if (y + 10 > PAGE_HEIGHT - BOTTOM) { doc.addPage(); y = 20; }
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(34, 76, 112);
  doc.text("Sources", LEFT, y);
  y += 8;
  for (const [index, source] of message.sources.entries()) {
    const page = source.page_number == null ? "" : `, page ${source.page_number}`;
    y = addParagraph(doc, `[${index + 1}] ${source.filename}${page}: ${source.excerpt}`, y, { size: 9, indent: 4, color: [82, 101, 116] });
  }
  return y;
}

function makeSafeFilename(title: string): string {
  return title.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "documind-chat";
}

export async function downloadConversationPdf(title: string, messages: ChatMessage[]) {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  let y = 24;
  doc.setFont("helvetica", "bold");
  doc.setFontSize(21);
  doc.setTextColor(34, 76, 112);
  const titleLines = doc.splitTextToSize(pdfText(title), PAGE_WIDTH - LEFT - RIGHT);
  doc.text(titleLines, LEFT, y);
  y += titleLines.length * 9 + 4;
  y = addParagraph(doc, `Saved conversation · ${new Date().toLocaleString()}`, y, { size: 9, color: [105, 119, 133] });
  y += 4;

  for (const message of messages) {
    if (y + 12 > PAGE_HEIGHT - BOTTOM) { doc.addPage(); y = 20; }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(34, 76, 112);
    doc.text(message.role === "user" ? "Question" : "Answer", LEFT, y);
    y += 8;
    y = message.role === "assistant"
      ? addMarkdownAnswer(doc, message.content, y)
      : addParagraph(doc, message.content, y);
    if (message.role === "assistant") y = addSources(doc, message, y);
    y += 6;
  }

  addFooter(doc);
  doc.save(`${makeSafeFilename(title)}.pdf`);
}

export function downloadAnswerPdf(message: ChatMessage, title: string) {
  return downloadConversationPdf(title, [message]);
}
