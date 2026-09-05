/**
 * Centralized API client.
 *
 * Attaches Authorization: Bearer <token> when present, centralizes base URL
 * (VITE_API_BASE_URL when set, otherwise same-origin; proxied in dev via vite.config),
 * and normalizes error handling into a consistent shape components can render.
 */

/**
 * @typedef {Object} ApiError
 * @property {number} status      - HTTP status code (0 for network errors)
 * @property {string} message     - Human-readable error message
 * @property {string} type        - 'network' | 'auth' | 'validation' | 'server' | 'unavailable'
 * @property {Object|null} body   - Parsed JSON body from the server, if any
 */

/**
 * Make a JSON API call.
 *
 * @param {string} path          - e.g. '/guardrail/evaluate'
 * @param {Object} options
 * @param {string} [options.method='GET']
 * @param {Object|null} [options.body=null]
 * @param {string|null} [options.token=null]
 * @param {Object|null} [options.headers=null] - Extra headers (merged, not replaced)
 * @returns {Promise<Object>}    - Parsed JSON on success
 * @throws {ApiError}
 */
export async function apiFetch(path, { method = 'GET', body = null, token = null, headers = null } = {}) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');
  const hdrs = { ...(headers || {}) };
  if (token) hdrs['Authorization'] = `Bearer ${token}`;
  if (body && !(body instanceof FormData)) {
    hdrs['Content-Type'] = 'application/json';
  }

  let res;
  try {
    res = await fetch(`${baseUrl}${path}`, {
      method,
      headers: hdrs,
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw { status: 0, message: err.message || 'Network error — is the backend running?', type: 'network', body: null };
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON response — ok for some error codes
  }

  if (res.ok) return data;

  if (res.status === 401) {
    throw { status: 401, message: 'Authentication failed — your session may have expired.', type: 'auth', body: data };
  }
  if (res.status === 404) {
    throw { status: 404, message: data?.detail || 'Not found.', type: 'validation', body: data };
  }
  if (res.status === 400) {
    throw { status: 400, message: data?.detail || 'Invalid request.', type: 'validation', body: data };
  }
  if (res.status === 503) {
    throw {
      status: 503,
      message: data?.detail || 'Service temporarily unavailable.',
      type: 'unavailable',
      body: data,
    };
  }
  throw {
    status: res.status,
    message: data?.detail || `Server error (${res.status}).`,
    type: 'server',
    body: data,
  };
}

export function requestRephrase({ token, requestId, conversationId, prompt }) {
  return apiFetch('/guardrail/rephrase', {
    method: 'POST',
    token,
    body: { request_id: requestId, conversation_id: conversationId, prompt },
  });
}

export function requestHumanReview({ token, requestId, conversationId, note }) {
  return apiFetch('/guardrail/review-requests', {
    method: 'POST',
    token,
    body: { request_id: requestId, conversation_id: conversationId, note },
  });
}

export function reportDecision({ token, requestId, conversationId, comment }) {
  return apiFetch('/guardrail/decision-reports', {
    method: 'POST',
    token,
    body: { request_id: requestId, conversation_id: conversationId, comment },
  });
}
