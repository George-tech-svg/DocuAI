import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { FileText, MessageCircle, Search, X } from "lucide-react";
import { getErrorMessage, request } from "./api";

export type FileSearchHit = {
  type: "file" | "public_document";
  id: string;
  file_id: string | null;
  folder_id: string | null;
  folder_name: string | null;
  organization_id: string | null;
  organization_name: string | null;
  path: string;
  title: string;
  excerpt: string;
  page_number: number | null;
  is_archived: boolean;
  collection_id?: string;
  source_url?: string;
  publisher?: string;
};

export type ChatSearchHit = {
  id: string;
  title: string;
  folder_id: string | null;
  folder_name: string | null;
  organization_id: string | null;
  organization_name: string | null;
  document_id: string | null;
  scope_type: "document" | "folder" | "library" | "folder_library";
  visibility: "private" | "shared";
  library_collection_id: string | null;
  path: string;
  excerpt: string;
  created_at: string;
  is_archived: boolean;
};

type SearchResults = { files: FileSearchHit[]; public_documents: FileSearchHit[]; chats: ChatSearchHit[] };
type Props = {
  token: string;
  initialQuery?: string | null;
  onClose: () => void;
  onOpenFile: (hit: FileSearchHit) => void;
  onOpenPublicDocument: (hit: FileSearchHit) => void;
  onOpenChat: (hit: ChatSearchHit) => void;
};

export default function WorkspaceFinder({ token, initialQuery, onClose, onOpenFile, onOpenPublicDocument, onOpenChat }: Props) {
  const [query, setQuery] = useState(initialQuery ?? "");
  const [kind, setKind] = useState<"all" | "files" | "chats">("all");
  const [results, setResults] = useState<SearchResults>({ files: [], public_documents: [], chats: [] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  useEffect(() => {
    if (!initialQuery?.trim()) return;
    let cancelled = false;
    setQuery(initialQuery);
    setKind("all");
    setBusy(true); setError("");
    void request<SearchResults>("/discovery/search", token, {
      method: "POST", body: JSON.stringify({ query: initialQuery.trim(), kind: "all" }),
    }).then((value) => { if (!cancelled) setResults(value); })
      .catch((reason) => { if (!cancelled) setError(getErrorMessage(reason)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [initialQuery, token]);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) { setError("Type at least two letters or words."); return; }
    setBusy(true); setError("");
    try {
      const value = await request<SearchResults>("/discovery/search", token, {
        method: "POST", body: JSON.stringify({ query: query.trim(), kind }),
      });
      setResults(value);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(false); }
  }

  const visibleFiles = kind === "chats" ? [] : results.files;
  const visiblePublicDocuments = kind === "chats" ? [] : results.public_documents;
  const visibleChats = kind === "files" ? [] : results.chats;
  const hasResults = visibleFiles.length + visiblePublicDocuments.length + visibleChats.length > 0;
  return <div className="finder-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="finder-panel" role="dialog" aria-modal="true" aria-labelledby="finder-title">
      <header className="finder-heading"><div><h2 id="finder-title"><Search size={20}/> Find files or chats</h2><p>Describe what you remember. Exact file names are not needed.</p></div><button className="icon-button" type="button" aria-label="Close search" onClick={onClose}><X size={19}/></button></header>
      <form className="finder-form" onSubmit={(event) => void search(event)}>
        <input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="For example: the letter about a payment deadline" maxLength={500}/>
        <button className="admin-primary" type="submit" disabled={busy || query.trim().length < 2}>{busy ? "Searching…" : "Search"}</button>
      </form>
      <div className="finder-filters" role="group" aria-label="What to search">
        {([ ["all", "Everything"], ["files", "Files"], ["chats", "Old chats"] ] as const).map(([value, label]) => <button type="button" key={value} className={kind === value ? "selected" : ""} aria-pressed={kind === value} onClick={() => setKind(value)}>{label}</button>)}
      </div>
      {error && <p className="admin-error" role="alert">{error}</p>}
      {busy && <p className="finder-status" role="status">Looking through your files and saved chats…</p>}
      {!busy && hasResults && <div className="finder-results" aria-live="polite">
        {visibleFiles.length > 0 && <section><h3>Your files</h3>{visibleFiles.map((hit) => <button className="finder-result" key={hit.id} type="button" onClick={() => onOpenFile(hit)}><FileText size={19}/><span><strong>{hit.title}{hit.is_archived ? " · Archived" : ""}</strong><small>{hit.path}</small><small>{hit.excerpt}{hit.page_number ? ` · page ${hit.page_number}` : ""}</small></span></button>)}</section>}
        {visiblePublicDocuments.length > 0 && <section><h3>Public documents</h3>{visiblePublicDocuments.map((hit) => <article className="finder-result finder-public-result" key={hit.id}><FileText size={19}/><span><strong>{hit.title}</strong><small>{hit.path}{hit.page_number ? ` · page ${hit.page_number}` : ""}</small><small>{hit.excerpt}</small><span className="finder-result-actions"><a href={hit.source_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>Open original</a><button type="button" onClick={() => onOpenPublicDocument(hit)}>Ask about this group</button></span></span></article>)}</section>}
        {visibleChats.length > 0 && <section><h3>Saved chats</h3>{visibleChats.map((hit) => <button className="finder-result" key={hit.id} type="button" onClick={() => onOpenChat(hit)}><MessageCircle size={19}/><span><strong>{hit.title}{hit.is_archived ? " · Archived" : ""}</strong><small>{hit.path} · {new Date(hit.created_at).toLocaleDateString()}</small><small>{hit.excerpt}</small></span></button>)}</section>}
      </div>}
      {!busy && !error && query.trim().length >= 2 && !hasResults && <p className="finder-empty">No close matches. Try describing the file or chat in a different way.</p>}
      <p className="finder-privacy-note">Search results only include files and chats you are allowed to see.</p>
    </section>
  </div>;
}
