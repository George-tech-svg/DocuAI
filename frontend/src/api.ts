/**
 * Shared HTTP helper for requests to the DocuMind AI backend.
 * The server URL can be configured when building the frontend.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "https://docuai-6301.onrender.com/api/v1";

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
  const headers = new Headers(options.headers);
  const isFileUpload = options.body instanceof FormData;

  if (options.body && !isFileUpload) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const controller = new AbortController();
  const timeoutMs = path === "/chat"
    // The backend can make three AI-provider attempts, each with a 90s read
    // timeout. Leave room for retries and model/database work before failing.
    ? 5 * 60_000
    : options.body instanceof FormData
      ? 30 * 60_000
      // Render may need around 40 seconds to cold start this service after it
      // has been idle. Keep ordinary API requests alive long enough for that
      // startup to finish and for the first database connection to complete.
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
        ? "The answer is taking longer than expected. Please try again; if this keeps happening, check the Render service logs."
        : "The server took too long to respond. Please try again; if this keeps happening, check the Render service logs.");
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request was cancelled.");
    }
    if (error instanceof TypeError) {
      throw new Error("Cannot reach the DocuMind API. The Render service may be offline, still starting, or missing the production CORS configuration.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }
}
