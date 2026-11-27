import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { CalendarDays, Check, Download, Pencil, X } from 'lucide-react';
import { API_BASE_URL, getErrorMessage, request } from './api';

export interface ImportantEvent {
  id: string; document_id: string; document_name: string; kind: string; title: string;
  due_at: string; source_page: number | null; source_excerpt: string; confidence: number; status: string;
}
interface InAppNotification { id: string; event_id: string; title: string; document_name: string; channel: string; remind_at: string; sent_at: string | null; status: string; error: string | null; }
interface Preferences { channels: { email: boolean; in_app: boolean }; lead_days: number[]; quiet_start: string; quiet_end: string; timezone: string; }

export default function ImportantDates({ token, documentId, upcoming = false, onBack }: { token: string; documentId?: string; upcoming?: boolean; onBack?: () => void }) {
  const [items, setItems] = useState<ImportantEvent[]>([]);
  const [notifications, setNotifications] = useState<InAppNotification[]>([]);
  const [preferences, setPreferences] = useState<Preferences>({ channels: { email: true, in_app: true }, lead_days: [14, 7, 1], quiet_start: '', quiet_end: '', timezone: 'Africa/Nairobi' });
  const [preferenceSaved, setPreferenceSaved] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ title: '', kind: 'deadline', due_at: '' });
  async function load() {
    if (!upcoming && !documentId) { setItems([]); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const path = upcoming ? '/events/upcoming' : `/documents/${documentId}/events`;
      const data = await request<{ items: ImportantEvent[] }>(path, token);
      setItems(data.items);
      if (upcoming) {
        const notices = await request<{ items: InAppNotification[] }>('/notifications', token);
        setNotifications(notices.items);
        const savedPreferences = await request<Preferences>('/notification-preferences', token);
        setPreferences({ ...savedPreferences, quiet_start: savedPreferences.quiet_start ?? '', quiet_end: savedPreferences.quiet_end ?? '' });
      }
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [token, documentId, upcoming]);
  async function action(id: string, suffix: string, body?: unknown) {
    setBusy(id); setError('');
    try {
      await request(`/events/${id}/${suffix}`, token, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) });
      await load(); setEditing(null);
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setBusy(''); }
  }
  function beginEdit(event: ImportantEvent) {
    setEditing(event.id);
    setDraft({ title: event.title, kind: event.kind, due_at: new Date(new Date(event.due_at).getTime() - new Date(event.due_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16) });
  }
  function localDateTime(value: Date) {
    return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  async function downloadIcs(id: string) {
    setBusy(id); setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/events/${id}/ics`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error('Calendar export could not be downloaded. Please try again.');
      const blob = await response.blob(); const href = URL.createObjectURL(blob); const link = document.createElement('a');
      link.href = href; link.download = 'documind-event.ics'; link.click(); URL.revokeObjectURL(href);
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setBusy(''); }
  }
  async function savePreferences(event: FormEvent) {
    event.preventDefault(); setBusy('preferences'); setError(''); setPreferenceSaved('');
    try {
      const result = await request<Preferences>('/notification-preferences', token, { method: 'PUT', body: JSON.stringify(preferences) });
      setPreferences({ ...result, quiet_start: result.quiet_start ?? '', quiet_end: result.quiet_end ?? '' });
      setPreferenceSaved('Reminder preferences saved.');
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setBusy(''); }
  }
  return <section className={`important-dates ${upcoming ? 'upcoming-page' : ''}`}>
    {upcoming ? <header className="upcoming-heading"><button type="button" onClick={onBack}>← Workspace</button><div><span>YOUR DOCUMENTS</span><h1>Upcoming dates</h1></div><button type="button" onClick={() => void load()}>Refresh</button></header> : <h3><CalendarDays size={18} /> Important dates</h3>}
    {upcoming && <p>Suggested dates need your review. Confirmed reminders use the source shown with each date.</p>}
    {error && <div className="error banner" role="alert">{error}</div>}
    {upcoming && notifications.length > 0 && <section className="in-app-notifications" aria-label="Reminder delivery"><h2>Reminders &amp; delivery</h2>{notifications.map(note => <div key={note.id}><strong>{note.title}</strong><span>{note.document_name} · {note.channel.replace('_', ' ')} · {new Date(note.remind_at).toLocaleString()} · {note.status}</span>{note.error && <small role="alert">{note.error}</small>}</div>)}</section>}
    {upcoming && <form className="notification-preferences" onSubmit={savePreferences}><h2>Reminder preferences</h2><div className="preference-channels"><label><input type="checkbox" checked={preferences.channels.email} onChange={e => setPreferences({ ...preferences, channels: { ...preferences.channels, email: e.target.checked } })} /> Email</label><label><input type="checkbox" checked={preferences.channels.in_app} onChange={e => setPreferences({ ...preferences, channels: { ...preferences.channels, in_app: e.target.checked } })} /> In-app</label></div><label>Remind me (days before)<input value={preferences.lead_days.join(', ')} onChange={e => setPreferences({ ...preferences, lead_days: e.target.value.split(',').map(v => Number(v.trim())).filter(v => Number.isInteger(v) && v >= 0 && v <= 365) })} /></label><label>Timezone<input value={preferences.timezone} onChange={e => setPreferences({ ...preferences, timezone: e.target.value })} placeholder="Africa/Nairobi" /></label><label>Quiet hours start<input type="time" value={preferences.quiet_start} onChange={e => setPreferences({ ...preferences, quiet_start: e.target.value })} /></label><label>Quiet hours end<input type="time" value={preferences.quiet_end} onChange={e => setPreferences({ ...preferences, quiet_end: e.target.value })} /></label><button type="submit" disabled={busy === 'preferences'}>{busy === 'preferences' ? 'Saving…' : 'Save preferences'}</button>{preferenceSaved && <span role="status">{preferenceSaved}</span>}</form>}
    {loading ? <p role="status">Loading important dates…</p> : items.length === 0 ? <p className="muted">{upcoming ? 'No upcoming dates have been found yet.' : 'No important dates found yet. Dates appear here after this document finishes indexing.'}</p> : items.map(event => <article className="important-event" key={event.id}>
      <div className="important-event-top"><div><strong>{event.title}</strong><span>{new Date(event.due_at).toLocaleString()} · {event.kind.replace('_', ' ')}{upcoming ? ` · ${event.document_name}` : ''}</span></div><span className={`event-status ${event.status}`}>{event.status}</span></div>
      {editing === event.id ? <div className="event-edit-fields"><label>Title<input value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label><label>Type<select value={draft.kind} onChange={e => setDraft({ ...draft, kind: e.target.value })}>{['deadline','expiry','hearing','payment_due','renewal','other'].map(k => <option key={k}>{k}</option>)}</select></label><label>Due date<input type="datetime-local" value={draft.due_at} onChange={e => setDraft({ ...draft, due_at: e.target.value })} /></label></div> : null}
      <blockquote>{event.source_excerpt}</blockquote><small>{event.source_page ? `Page ${event.source_page}` : 'Page not identified'} · AI confidence {Math.round(event.confidence * 100)}%</small>
      <p className="event-source-caution">Check this date against the original document. This is an AI suggestion and may need correction.</p>
      <div className="event-actions">
        {event.status === 'suggested' && <>
          {editing === event.id ? <button type="button" disabled={busy === event.id} onClick={() => void action(event.id, 'confirm', { title: draft.title, kind: draft.kind, due_at: new Date(draft.due_at).toISOString() })}><Check size={15} /> Confirm date</button> : <button type="button" disabled={!!busy} onClick={() => { setDraft({ title: event.title, kind: event.kind, due_at: '' }); void action(event.id, 'confirm', { title: event.title, kind: event.kind, due_at: event.due_at }); }}><Check size={15} /> Confirm</button>}
          <button type="button" disabled={!!busy} onClick={() => beginEdit(event)}><Pencil size={15} /> Edit</button>
          <button type="button" disabled={!!busy} onClick={() => void action(event.id, 'dismiss')}><X size={15} /> Dismiss</button>
        </>}
        {event.status === 'confirmed' && <><button type="button" disabled={!!busy} onClick={() => void action(event.id, 'done')}>Mark as done</button><button type="button" disabled={!!busy} onClick={() => { const suggestion = new Date(Date.now() + 86400000); suggestion.setMinutes(0,0,0); const entered = window.prompt('Snooze until (local time, YYYY-MM-DDTHH:mm):', localDateTime(suggestion)); if (entered) void action(event.id, 'snooze', { remind_at: new Date(entered).toISOString() }); }}>Snooze</button><button type="button" disabled={!!busy} onClick={() => void downloadIcs(event.id)}><Download size={15} /> Calendar</button></>}
      </div>
    </article>)}
  </section>;
}
