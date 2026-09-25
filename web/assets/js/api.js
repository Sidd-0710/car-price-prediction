// Talking to the FastAPI server (same origin).

export class ApiError extends Error {
  constructor(message, status, suggestions = []) {
    super(message);
    this.status = status;
    this.suggestions = suggestions;
  }
}

function describe(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = (item.loc || []).slice(1).join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return "";
}

/** "... Did you mean: ['Maruti Swift', 'Maruti Swift Dzire']?" -> ["Maruti Swift", "Maruti Swift Dzire"] */
function suggestionsFrom(message) {
  const match = /Did you mean: \[(.*?)\]/.exec(message || "");
  if (!match) return [];
  return [...match[1].matchAll(/'([^']+)'/g)].map((found) => found[1]);
}

export async function api(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Can't reach the prediction server. Is it still running?", 0);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    const message = describe(data?.detail) || `The server returned an error (${response.status}).`;
    throw new ApiError(message, response.status, suggestionsFrom(message));
  }
  return data;
}

const cache = new Map();

/** GET once, then reuse the answer (for data that never changes while the page is open). */
export function cached(path) {
  if (!cache.has(path)) {
    cache.set(
      path,
      api(path).catch((error) => {
        cache.delete(path);
        throw error;
      }),
    );
  }
  return cache.get(path);
}
