/**
 * Shared HTTP helper for requests to the DocuMind AI backend.
 * The server URL can be configured when building the frontend.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "/api/v1";

/** Turn unknown JavaScript exceptions into readable messages. */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

/**
 * Send a request and parse the JSON response.
 * FormData requests intentionally omit Content-Type so the browser sets
 * the multipart boundary automatically.
 */
export async function request<T>(
  path: string,
  token = "",
  options: RequestInit = {}
): Promise<T> {
  void token; // Auth is an HttpOnly cookie; never attach a browser-readable JWT.
  const headers = new Headers(options.headers);
  const isFileUpload = options.body instanceof FormData;
  const method = (options.method ?? "GET").toUpperCase();

  if (options.body && !isFileUpload) {
    headers.set("Content-Type", "application/json");
  }

  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    let csrf = document.cookie.split('; ').find((part) => part.startsWith('documind_csrf='))?.split('=').slice(1).join('=');
    if (!csrf) {
      const csrfController = new AbortController();
      const csrfTimeout = window.setTimeout(() => csrfController.abort(), 10_000);
      try {
        const csrfResponse = await fetch(`${API_BASE_URL}/auth/csrf`, {
          credentials: 'include',
          signal: csrfController.signal,
        });
        if (!csrfResponse.ok) {
          let detail = '';
          try {
            const body = await csrfResponse.json() as { detail?: unknown };
            if (typeof body.detail === 'string') detail = body.detail;
          } catch { /* Use the clear status-based message below. */ }
          throw new Error(detail || (csrfResponse.status >= 500
            ? 'The authentication service is temporarily unavailable. Please try again later.'
            : 'Could not start secure sign-in. Refresh the page and try again.'));
        }
        const body = await csrfResponse.json() as { csrf_token?: string };
        csrf = body.csrf_token;
        if (!csrf) throw new Error('Could not start secure sign-in. Refresh the page and try again.');
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          throw new Error('The authentication service took too long to respond. Please try again.');
        }
        if (error instanceof TypeError) {
          throw new Error('Network error. Please check your connection and try again.');
        }
        throw error;
      } finally {
        window.clearTimeout(csrfTimeout);
      }
    }
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }

  const controller = new AbortController();
  const timeoutMs = path === "/chat"
    // The backend makes at most two provider attempts with a 60s read timeout.
    // Leave room for embedding, retrieval, and persistence before failing.
    ? 3 * 60_000
    : options.body instanceof FormData
      ? 30 * 60_000
      // Allow time for a cold start and the first database connection.
      : 90_000;
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const callerSignal = options.signal;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) {
    abortFromCaller();
  } else {
    callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: 'include',
      signal: controller.signal,
    });

    if (!response.ok) {
      let message = `Request failed (${response.status})`;

      try {
        const data: { detail?: string | Array<{ loc?: Array<string | number>; msg?: string }> } =
          await response.json();

        if (typeof data.detail === "string") {
          message = data.detail;
        } else if (Array.isArray(data.detail) && data.detail.length > 0) {
          message = data.detail
            .map((issue) => {
              const field = issue.loc?.[issue.loc.length - 1];
              const label =
                typeof field === "string"
                  ? field.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase())
                  : "Request";
              return `${label}: ${issue.msg ?? "Invalid value"}`;
            })
            .join(". ");
        }
      } catch {
        // Keep the HTTP status message if the server did not return JSON.
      }

      if (response.status >= 500 && (message.startsWith("Request failed") || message === "Internal Server Error")) {
        message = "Something went wrong on our end. Please try again later.";
      }

      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    // Keep the request deadline active while consuming the body as well as
    // while waiting for response headers, so a stalled body cannot leave the
    // UI's busy state active forever.
    return await response.json() as T;
  } catch (error) {
    if (timedOut) {
      throw new Error(path === "/chat"
        ? "The answer is taking longer than expected. Please try again, then check the backend service logs if this continues."
        : "The server took too long to respond. Please try again, then check the backend service logs if this continues.");
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request was cancelled.");
    }
    if (error instanceof TypeError) {
      throw new Error("Network error. Please check your connection and try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }
}
