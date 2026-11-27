import { ArrowLeft, BookOpen, FileText, LockKeyhole } from "lucide-react";

type LegalDocument = "terms" | "privacy";

export default function TermsPrivacy({
  document,
  onBack,
  onOpen,
}: {
  document: LegalDocument;
  onBack: () => void;
  onOpen: (document: LegalDocument) => void;
}) {
  const isPrivacy = document === "privacy";
  const sections = isPrivacy
    ? ["Information we use", "How information is used", "Service providers", "Storage and security", "Your choices", "Children", "Policy updates", "Contact and complaints"]
    : ["Using DocuMind", "Your files and content", "AI answers", "Accounts and security", "Plans and payments", "Availability and changes", "Suspension and termination", "Liability", "Contact"];

  return (
    <main className="legal-wrap">
      <article className="legal-card">
        <header className="legal-header">
          <div className="brand"><BookOpen /> DocuMind <span>AI</span></div>
          <button className="legal-back" type="button" onClick={onBack}><ArrowLeft size={17} /> Back</button>
        </header>
        <div className="legal-title">
          {isPrivacy ? <LockKeyhole size={23} /> : <FileText size={23} />}
          <div><h1>{isPrivacy ? "Privacy notice" : "Terms of service"}</h1><p>Last updated 27 November 2026</p></div>
        </div>
        <nav className="legal-switch" aria-label="Legal documents">
          <button className={!isPrivacy ? "selected" : ""} onClick={() => onOpen("terms")}>Terms</button>
          <button className={isPrivacy ? "selected" : ""} onClick={() => onOpen("privacy")}>Privacy</button>
        </nav>

        {isPrivacy ? (
          <>
            <p className="legal-lead">This notice explains how DocuMind AI handles account, document, chat, and payment information when you use the service. Please avoid uploading information you do not have permission to use.</p>
            <nav className="legal-contents" aria-label="Privacy notice contents"><strong>On this page</strong>{sections.map((name, index) => <a key={name} href={`#privacy-${index}`}>{name}</a>)}</nav>
            <section id="privacy-0"><h2>1. Information we use</h2><p>We use your name, email address, and authentication data to create and secure your account. We store the files you upload, extracted document text and search data, your questions and saved conversations, and settings needed to provide the workspace. If you start a subscription payment, we also process the phone number and transaction details needed to request and reconcile that payment.</p></section>
            <section id="privacy-1"><h2>2. How information is used</h2><p>We use this information to operate your account, organize and search your files, answer questions about selected documents, save your chat history, provide support, prevent misuse, and administer subscriptions and payments. We do not claim ownership of your uploaded content.</p></section>
            <section id="privacy-2"><h2>3. Service providers</h2><p>Uploaded originals are stored with Cloudinary. Account records, extracted text, embeddings, and conversations are stored in the configured Neon database. When you ask a question, the relevant excerpts and your question are sent to DeepSeek to generate an answer. For a follow-up question, recent turns from that conversation may also be sent to DeepSeek to rewrite the question into a standalone search query; the rewritten query is used to search your documents, while your original question is used to generate the answer. If you request an M-Pesa payment, payment details are sent to Safaricom to process the prompt and callback. These providers process information to deliver their services under their own terms and privacy notices.</p></section>
            <section id="privacy-3"><h2>4. Storage and security</h2><p>We use access controls and authenticated requests to protect account data. No internet service can promise perfect security. Information may be processed or stored in countries where our providers operate, subject to applicable safeguards. We keep information for as long as needed to provide the service, meet operational needs, resolve disputes, and comply with applicable law. Deleting a file or conversation removes it from the workspace; backups or provider records may take additional time to expire.</p></section>
            <section id="privacy-4"><h2>5. Your choices and rights</h2><p>You can edit, archive, or delete files and conversations using their menus, and you can sign out at any time. You may request access to or correction or deletion of personal information by contacting the service operator through the support contact provided with your account or subscription. Applicable rights depend on your location and law. You may also contact the <a href="https://www.odpc.go.ke/rights-of-a-data-subject/" target="_blank" rel="noreferrer">Kenya Office of the Data Protection Commissioner</a>.</p></section>
            <section id="privacy-5"><h2>6. Children</h2><p>DocuMind AI is not designed for children to create accounts without appropriate parent, guardian, or institutional permission. Do not upload a child’s personal information unless you have authority and a lawful reason to do so.</p></section>
            <section id="privacy-6"><h2>7. Policy updates</h2><p>We may update this notice as the service changes. We will change the date above when we publish an update. Continued use after an update means the new notice applies to future use.</p></section>
            <section id="privacy-7"><h2>8. Contact and complaints</h2><p>For a privacy request, use the service operator’s support contact provided with the service. You can read the <a href="https://new.kenyalaw.org/akn/ke/act/2019/24/eng%402022-12-31/source.pdf" target="_blank" rel="noreferrer">Kenya Data Protection Act</a> and contact the <a href="https://www.odpc.go.ke/" target="_blank" rel="noreferrer">ODPC</a> for information about complaints.</p></section>
          </>
        ) : (
          <>
            <p className="legal-lead">These terms explain the basic rules for using DocuMind AI. By creating an account or using the service, you agree to these terms. If you do not agree, do not use the service.</p>
            <nav className="legal-contents" aria-label="Terms contents"><strong>On this page</strong>{sections.map((name, index) => <a key={name} href={`#terms-${index}`}>{name}</a>)}</nav>
            <section id="terms-0"><h2>1. Using DocuMind</h2><p>You must provide accurate account details, keep your sign-in credentials private, and use the service lawfully. You are responsible for activity through your account. Do not probe, disrupt, or attempt to gain unauthorized access to the service or another person’s account.</p></section>
            <section id="terms-1"><h2>2. Your files and content</h2><p>You retain your rights to files, questions, and other content you submit. You confirm that you have the rights and permission needed to upload and process that content. You allow DocuMind AI and its service providers to process it only as needed to store, retrieve, and answer questions through the service. You can delete files and conversations from their menus.</p></section>
            <section id="terms-2"><h2>3. AI answers</h2><p>Answers are generated automatically from document excerpts and may be incomplete, incorrect, or out of date. Check important information against the original document. DocuMind AI is a study and productivity aid, not professional legal, medical, financial, or other expert advice. You are responsible for how you use or share generated answers.</p></section>
            <section id="terms-3"><h2>4. Accounts and security</h2><p>Keep your password secure and notify the service operator if you believe your account has been accessed without permission. We may restrict accounts that violate these terms or threaten the service or its users.</p></section>
            <section id="terms-4"><h2>5. Plans and payments</h2><p>Available plan prices and billing periods are shown before you subscribe. If you request M-Pesa billing, each payment prompt must be approved on your device; a subscription renews only after the payment is confirmed. An unsuccessful or unapproved payment does not count as payment. Any cancellation or refund rights required by law continue to apply.</p></section>
            <section id="terms-5"><h2>6. Availability and changes</h2><p>We work to keep the service available, but features may change and outages may occur. We may update these terms when the service or applicable requirements change and will update the date above.</p></section>
            <section id="terms-6"><h2>7. Suspension and termination</h2><p>You can stop using the service and sign out at any time. We may suspend access where reasonably needed to protect users, investigate misuse, comply with law, or address unpaid subscriptions. Deleting your account is not currently a self-service feature; contact the service operator for assistance.</p></section>
            <section id="terms-7"><h2>8. Liability</h2><p>To the extent permitted by law, the service is provided without a promise that every AI answer will be accurate or uninterrupted. Nothing in these terms excludes rights or liability that cannot lawfully be excluded.</p></section>
            <section id="terms-8"><h2>9. Contact</h2><p>For account or subscription questions, use the support contact provided by the service operator with your account or subscription.</p></section>
          </>
        )}
        <footer className="legal-footer"><button type="button" onClick={() => onOpen(isPrivacy ? "terms" : "privacy")}>Read {isPrivacy ? "Terms of service" : "Privacy notice"}</button><button className="legal-back" type="button" onClick={onBack}><ArrowLeft size={17} /> Back to DocuMind</button></footer>
      </article>
    </main>
  );
}
