import { useEffect, useState } from 'react';
import { ArrowLeft, ShieldCheck } from 'lucide-react';
import { getErrorMessage, request } from './api';

type Notice = {terms_version:string;privacy_version:string;company_name:string;company_address:string;odpc_registration_number:string;notice:string;providers:{name:string;purpose:string}[]};
export default function DataProcessingPage({token,onBack}:{token:string;onBack:()=>void}) {
  const [notice,setNotice]=useState<Notice|null>(null); const [error,setError]=useState('');
  useEffect(()=>{let active=true;void request<Notice>('/privacy/notices',token).then(v=>{if(active)setNotice(v);}).catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};},[token]);
  return <main className="settings-wrap"><section className="settings-card data-processing-page">
    <button className="legal-back" type="button" onClick={onBack}><ArrowLeft size={17}/> Back to settings</button>
    <div className="settings-heading"><ShieldCheck size={24}/><div><h1>Data processing</h1><p>Plain-language summary of the providers that process information to run DocuMind AI.</p></div></div>
    <p className="privacy-legal-note">This page describes engineering behavior, not legal advice. The platform operator must complete the company and registration details below and confirm them with a qualified adviser.</p>
    {error&&<p className="error" role="alert">{error}</p>}
    <section className="settings-detail"><h2>Platform operator details</h2><p><strong>Company name</strong><span>{notice?.company_name??'Loading…'}</span></p><p><strong>Company address</strong><span>{notice?.company_address??'Loading…'}</span></p><p><strong>ODPC registration number</strong><span>{notice?.odpc_registration_number??'Loading…'}</span></p></section>
    <section className="settings-detail"><h2>Service providers and purpose</h2>{notice?.providers.map(provider=><p key={provider.name}><strong>{provider.name}</strong><span>{provider.purpose}</span></p>)}</section>
    <p className="muted">{notice?.notice}</p>
  </section></main>;
}
