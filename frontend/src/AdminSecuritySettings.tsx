import { useEffect, useState } from 'react';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { getErrorMessage, request } from './api';

export default function AdminSecuritySettings({token}:{token:string}) {
  const [enabled,setEnabled]=useState(false); const [secret,setSecret]=useState(''); const [uri,setUri]=useState('');
  const [code,setCode]=useState(''); const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [busy,setBusy]=useState(false);
  async function refresh(){try{const result=await request<{enabled:boolean}>('/auth/admin-2fa/status',token);setEnabled(result.enabled);}catch(e){setError(getErrorMessage(e));}}
  useEffect(()=>{void refresh();},[token]);
  async function setup(){setBusy(true);setError('');setNotice('');try{const result=await request<{secret:string;otpauth_uri:string}>('/auth/admin-2fa/setup',token,{method:'POST'});setSecret(result.secret);setUri(result.otpauth_uri);}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
  async function enable(){setBusy(true);setError('');try{await request('/auth/admin-2fa/enable',token,{method:'POST',body:JSON.stringify({secret,code})});setEnabled(true);setSecret('');setUri('');setCode('');setNotice('Two-factor authentication is enabled. Keep your authenticator app available at sign-in.');}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
  async function disable(){setBusy(true);setError('');try{await request('/auth/admin-2fa/disable',token,{method:'POST',body:JSON.stringify({code})});setEnabled(false);setCode('');setNotice('Two-factor authentication is disabled.');}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
  return <section className="admin-security-settings"><div><h2><ShieldCheck size={18}/> Administrator two-factor authentication</h2><p>{enabled?'An authenticator code is required every time you sign in as platform administrator.':'Optional extra sign-in protection. You can use any TOTP authenticator app.'}</p></div>
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!enabled&&!secret&&<button className="admin-secondary" type="button" disabled={busy} onClick={()=>void setup()}><KeyRound size={15}/> Set up authenticator</button>}
    {!enabled&&secret&&<div className="admin-security-enroll"><p>In your authenticator app, add an account using this secret key (or enter the URI as a manual key):</p><code>{secret}</code><small>{uri}</small><label>Enter the current six-digit code<input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))}/></label><button className="admin-primary" disabled={busy||code.length!==6} onClick={()=>void enable()}>{busy?'Verifying…':'Enable two-factor authentication'}</button></div>}
    {enabled&&<div className="admin-security-enroll"><label>Authenticator code<input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))}/></label><button className="admin-secondary" disabled={busy||code.length!==6} onClick={()=>void disable()}>{busy?'Checking…':'Disable two-factor authentication'}</button></div>}
  </section>;
}
