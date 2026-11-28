import { useEffect, useState } from 'react';
import { getErrorMessage, request } from './api';

type AnswerLanguage = 'auto' | 'en' | 'sw';
export default function AnswerLanguageSettings({ token }: { token: string }) {
  const [language,setLanguage]=useState<AnswerLanguage>('auto'); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [saved,setSaved]=useState('');
  useEffect(()=>{let active=true;void request<{answer_language:AnswerLanguage}>('/auth/preferences',token).then(v=>{if(active)setLanguage(v.answer_language);}).catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};},[token]);
  async function save(value:AnswerLanguage){setLanguage(value);setBusy(true);setError('');setSaved('');try{const result=await request<{answer_language:AnswerLanguage}>('/auth/preferences',token,{method:'PUT',body:JSON.stringify({answer_language:value})});setLanguage(result.answer_language);setSaved('Answer language preference saved.');}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
  return <section className="settings-detail"><h2>Answer language</h2><p>Automatic follows your question in English, Kiswahili, or a mix. You can also choose a fixed answer language. Ask “Translate this to Kiswahili” to translate information found in your selected document.</p><label>Preferred answer language<select value={language} disabled={busy} onChange={e=>void save(e.target.value as AnswerLanguage)}><option value="auto">Automatic</option><option value="en">English</option><option value="sw">Kiswahili</option></select></label>{busy&&<p role="status">Saving…</p>}{error&&<p role="alert" className="error">{error}</p>}{saved&&<p role="status">{saved}</p>}</section>;
}
