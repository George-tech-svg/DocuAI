import { useEffect, useState } from 'react';
import { ArrowLeft, BookOpen, Search } from 'lucide-react';
import { getErrorMessage, request } from './api';

type Collection = { id: string; slug: string; name: string; description: string; category: string; ready_document_count: number };
type LibraryDocument = { id: string; collection_id: string; collection_name: string; title: string; short_name: string; publisher: string; source_url: string; version_label: string; document_date: string | null; effective_from: string | null; page_count: number | null };
type SearchResult = { document_id: string; collection_id: string; title: string; version_label: string; publisher: string; collection_name: string; page_number: number | null; section_title: string | null; excerpt: string; source_url: string };

export default function LibraryPage({ token, onBack, onAsk }: { token: string; onBack: () => void; onAsk: (collectionId: string | null) => void }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [collectionId, setCollectionId] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { void request<Collection[]>('/library/collections', token).then(setCollections).catch((e) => setError(getErrorMessage(e))); }, [token]);
  useEffect(() => { const timer = window.setTimeout(() => { const params = new URLSearchParams(); if (collectionId) params.set('collection_id', collectionId); if (query.trim().length >= 2) { params.set('q', query.trim()); void request<SearchResult[]>(`/library/search?${params}`, token).then(setResults).catch((e) => setError(getErrorMessage(e))); } else { void request<LibraryDocument[]>(`/library/documents?${params}`, token).then(setDocuments).catch((e) => setError(getErrorMessage(e))); setResults([]); } }, 250); return () => window.clearTimeout(timer); }, [token, collectionId, query]);
  return <main className="library-page"><header><button type="button" className="legal-back" onClick={onBack}><ArrowLeft size={17}/> Workspace</button><h1><BookOpen/> Kenyan public library</h1><p>Search read-only official documents and ask questions using cited source passages.</p></header>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="library-actions"><label>Collection<select value={collectionId} onChange={(e) => setCollectionId(e.target.value)}><option value="">All collections</option>{collections.map(c => <option key={c.id} value={c.id}>{c.name} ({c.ready_document_count})</option>)}</select></label><label className="library-search"><Search size={18}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search document titles, publishers, or topics"/></label><button type="button" className="primary" onClick={()=>onAsk(collectionId || null)}>Ask {collectionId ? 'this collection' : 'the library'}</button></div>
    <section className="library-collections"><h2>Collections</h2><div>{collections.map(c=><button key={c.id} className={collectionId===c.id?'selected':''} type="button" onClick={()=>setCollectionId(collectionId===c.id?'':c.id)}><strong>{c.name}</strong><span>{c.ready_document_count} available documents</span></button>)}</div></section>
    <section className="library-documents"><h2>{query.trim().length >= 2 ? 'Matching passages' : 'Official documents'}</h2>{query.trim().length >= 2 ? results.length ? results.map((result,index)=><article key={`${result.document_id}-${index}`}><div><h3>{result.title} · {result.version_label}</h3><p>{result.publisher} · {result.collection_name}{result.section_title ? ` · ${result.section_title}` : ''}{result.page_number ? ` · page ${result.page_number}` : ''}</p><p>{result.excerpt}</p><a href={result.source_url} target="_blank" rel="noreferrer">Official source</a></div><button type="button" onClick={()=>onAsk(result.collection_id)}>Ask collection</button></article>) : <p>No passages match this search yet.</p> : documents.length ? documents.map(d=><article key={d.id}><div><h3>{d.title}</h3><p>{d.publisher} · {d.version_label} · {d.collection_name}</p><a href={d.source_url} target="_blank" rel="noreferrer">Official source</a></div><button type="button" onClick={()=>onAsk(d.collection_id)}>Ask collection</button></article>) : <p>No ready library documents are available yet.</p>}</section>
  </main>;
}
