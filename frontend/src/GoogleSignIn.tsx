import { useEffect, useRef, useState } from "react";

type GoogleCredential = { credential: string };
type GoogleIdentityApi = {
  accounts: {
    id: {
      initialize: (options: { client_id: string; callback: (response: GoogleCredential) => void }) => void;
      renderButton: (element: HTMLElement, options: { theme: "outline"; size: "large"; text: "continue_with"; shape: "rectangular"; width: number }) => void;
    };
  };
};

declare global {
  interface Window { google?: GoogleIdentityApi }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

export default function GoogleSignIn({ onCredential }: { onCredential: (credential: string) => void }) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const callbackRef = useRef(onCredential);
  const [loadError, setLoadError] = useState("");
  callbackRef.current = onCredential;

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !buttonRef.current) return;
    let cancelled = false;
    const renderButton = () => {
      if (cancelled || !buttonRef.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          if (response.credential) callbackRef.current(response.credential);
          else setLoadError("Google did not return a sign-in credential. Please try again.");
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        width: Math.min(400, Math.max(220, buttonRef.current.clientWidth)),
      });
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

    return () => { cancelled = true; };
  }, []);

  if (!GOOGLE_CLIENT_ID) return null;
  return (
    <div className="google-signin-wrap">
      <div className="auth-divider"><span>or</span></div>
      <div className="google-signin-button" ref={buttonRef} />
      {loadError && <p className="error google-signin-error" role="alert">{loadError}</p>}
    </div>
  );
}
