import { useEffect, useRef, useState } from "react";
import { request } from "./api";

type GoogleCredential = { credential: string };
type GoogleMode = "login" | "register";
type GoogleIdentityApi = {
  accounts: {
    id: {
      initialize: (options: { client_id: string; callback: (response: GoogleCredential) => void }) => void;
      renderButton: (element: HTMLElement, options: { theme: "outline"; size: "large"; text: "continue_with" | "signin_with" | "signup_with"; shape: "rectangular"; width: number }) => void;
    };
  };
};

declare global {
  interface Window { google?: GoogleIdentityApi }
}

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "").trim();

export default function GoogleSignIn({ mode, acceptedTerms, onCredential }: {
  mode: GoogleMode;
  acceptedTerms: boolean;
  onCredential: (credential: string, mode: GoogleMode, acceptedTerms: boolean) => void;
}) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef({ mode, acceptedTerms, onCredential });
  const [loadError, setLoadError] = useState("");
  const [clientId, setClientId] = useState(GOOGLE_CLIENT_ID);
  const canUseGoogle = mode === "login" || acceptedTerms;
  optionsRef.current = { mode, acceptedTerms, onCredential };

  useEffect(() => {
    if (clientId) return;
    let cancelled = false;
    void request<{ enabled: boolean; client_id: string | null }>("/auth/google/config", "")
      .then((config) => { if (!cancelled && config.enabled && config.client_id) setClientId(config.client_id); })
      .catch(() => { if (!cancelled) setLoadError("Google sign-in is not configured yet."); });
    return () => { cancelled = true; };
  }, [clientId]);

  useEffect(() => {
    if (!clientId || !canUseGoogle || !buttonRef.current) return;
    let cancelled = false;
    let buttonCheckTimer: number | undefined;
    const callback = (response: GoogleCredential) => {
      if (response.credential) {
        const options = optionsRef.current;
        options.onCredential(response.credential, options.mode, options.acceptedTerms);
      } else setLoadError("Google did not return a sign-in credential. Please try again.");
    };
    const renderButton = () => {
      if (cancelled || !buttonRef.current || !window.google) return;
      try {
        window.google.accounts.id.initialize({ client_id: clientId, callback });
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: "outline",
          size: "large",
          text: mode === "register" ? "signup_with" : "signin_with",
          shape: "rectangular",
          width: Math.min(400, Math.max(220, buttonRef.current.clientWidth)),
        });
        buttonCheckTimer = window.setTimeout(() => {
          if (!cancelled && buttonRef.current && !buttonRef.current.querySelector("iframe")) {
            setLoadError("Google did not display its sign-in button. Check the authorized site origin in Google Cloud Console.");
          }
        }, 5000);
      } catch {
        setLoadError("Google sign-in could not initialize. Check the client ID and authorized site origin.");
      }
    };

    if (window.google) {
      renderButton();
    } else {
      let script = document.getElementById("google-identity-services") as HTMLScriptElement | null;
      if (!script) {
        script = document.createElement("script");
        script.id = "google-identity-services";
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      script.addEventListener("load", renderButton);
      script.addEventListener("error", () => setLoadError("Google sign-in could not load. Check your connection and try again."), { once: true });
    }

    return () => {
      cancelled = true;
      if (buttonCheckTimer) window.clearTimeout(buttonCheckTimer);
    };
  }, [clientId, canUseGoogle, mode]);

  if (!clientId) return (
    <div className="google-signin-wrap">
      <div className="auth-divider"><span>or</span></div>
      <button className="google-signin-disabled" type="button" disabled>
        {loadError || "Loading Google sign-in…"}
      </button>
    </div>
  );
  return (
    <div className="google-signin-wrap">
      <div className="auth-divider"><span>or</span></div>
      <div className="google-signin-frame">
        {canUseGoogle && !loadError
          ? <div className="google-signin-button" ref={buttonRef} />
          : <button className="google-signin-disabled" type="button" disabled>{loadError || "Accept Terms and Privacy to continue with Google"}</button>}
      </div>
      {loadError && <p className="error google-signin-error" role="alert">{loadError}</p>}
    </div>
  );
}
