/**
 * Shared HTTP helper for requests to the DocuMind AI backend.
 * The server URL can be configured when building the frontend.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
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

  return response.json() as Promise<T>;
}
