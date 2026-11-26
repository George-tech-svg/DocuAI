import type { ReactNode } from "react";

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const pattern = /(\*\*.+?\*\*|__.+?__|(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_)|`[^`\n]+`)/g;
  const parts: ReactNode[] = [];
  let cursor = 0;
  let matchIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const value = match[0];
    const index = match.index ?? 0;
    if (index > cursor) parts.push(text.slice(cursor, index));

    const key = `${keyPrefix}-${matchIndex++}`;
    if (value.startsWith("**") || value.startsWith("__")) {
      parts.push(<strong key={key}>{value.slice(2, -2)}</strong>);
    } else if (value.startsWith("`")) {
      parts.push(<code key={key}>{value.slice(1, -1)}</code>);
    } else {
      parts.push(<em key={key}>{value.slice(1, -1)}</em>);
    }
    cursor = index + value.length;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

/** Render the common Markdown used by answers as semantic, readable text. */
export default function AssistantMessage({ content }: { content: string }) {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: { kind: "unordered" | "ordered"; text: string }[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) blocks.push(<p key={`p-${blocks.length}`}>{renderInline(text, `p-${blocks.length}`)}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (!list.length) return;
    const kind = list[0].kind;
    const Tag = kind === "ordered" ? "ol" : "ul";
    blocks.push(
      <Tag key={`list-${blocks.length}`}>
        {list.map((item, index) => (
          <li key={`item-${index}`}>{renderInline(item.text, `item-${blocks.length}-${index}`)}</li>
        ))}
      </Tag>,
    );
    list = [];
  };

  for (const rawLine of content.replace(/\r\n?/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line || /^---+$/.test(line)) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(/^#{1,3}\s+(.+)$/) ?? line.match(/^\*\*(.+)\*\*$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push(<h4 key={`h-${blocks.length}`}>{renderInline(heading[1], `h-${blocks.length}`)}</h4>);
      continue;
    }

    const bullet = line.match(/^[-*+]\s+(.+)$/);
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      const kind = numbered ? "ordered" : "unordered";
      if (list.length && list[0].kind !== kind) flushList();
      list.push({ kind, text: (bullet ?? numbered)![1] });
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return <div className="assistant-content">{blocks}</div>;
}
