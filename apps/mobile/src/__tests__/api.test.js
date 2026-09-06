import { apiFetch } from '../api';

describe('apiFetch', () => {
  const originalEnv = process.env.EXPO_PUBLIC_API_BASE_URL;
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_BASE_URL = 'https://api.example.com/';
  });

  afterEach(() => {
    process.env.EXPO_PUBLIC_API_BASE_URL = originalEnv;
    global.fetch = originalFetch;
    jest.resetAllMocks();
  });

  function mockFetchOnce({ ok, status, json }) {
    global.fetch = jest.fn().mockResolvedValue({
      ok,
      status,
      json: async () => json,
    });
  }

  it('strips a trailing slash from the base URL before building the request', async () => {
    mockFetchOnce({ ok: true, status: 200, json: { token: 'abc' } });

    await apiFetch('/auth/dev-token', { method: 'POST', body: { role: 'admin' } });

    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.example.com/auth/dev-token',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('returns parsed JSON on success', async () => {
    mockFetchOnce({ ok: true, status: 200, json: { action: 'ALLOW' } });
    const result = await apiFetch('/guardrail/evaluate');
    expect(result).toEqual({ action: 'ALLOW' });
  });

  it('maps a 401 to an auth-type ApiError', async () => {
    mockFetchOnce({ ok: false, status: 401, json: { detail: 'expired' } });
    await expect(apiFetch('/guardrail/evaluate')).rejects.toMatchObject({
      status: 401,
      type: 'auth',
    });
  });

  it('maps a 404 to a validation-type ApiError, preferring the server detail message', async () => {
    mockFetchOnce({ ok: false, status: 404, json: { detail: 'Route not found' } });
    await expect(apiFetch('/nope')).rejects.toMatchObject({
      status: 404,
      type: 'validation',
      message: 'Route not found',
    });
  });

  it('maps a 503 to an unavailable-type ApiError and preserves the response body', async () => {
    mockFetchOnce({ ok: false, status: 503, json: { detail: 'LLM down', action: 'ALLOW' } });
    await expect(apiFetch('/guardrail/evaluate')).rejects.toMatchObject({
      status: 503,
      type: 'unavailable',
      body: { detail: 'LLM down', action: 'ALLOW' },
    });
  });

  it('maps an unrecognized error status to a server-type ApiError', async () => {
    mockFetchOnce({ ok: false, status: 500, json: null });
    await expect(apiFetch('/guardrail/evaluate')).rejects.toMatchObject({
      status: 500,
      type: 'server',
      message: 'Server error (500).',
    });
  });

  it('maps a thrown fetch (network failure) to a network-type ApiError with status 0', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await expect(apiFetch('/guardrail/evaluate')).rejects.toMatchObject({
      status: 0,
      type: 'network',
    });
  });

  it('attaches an Authorization header when a token is provided', async () => {
    mockFetchOnce({ ok: true, status: 200, json: {} });
    await apiFetch('/guardrail/evaluate', { token: 'jwt-123' });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-123' }),
      })
    );
  });

  it('does not set a JSON Content-Type header when the body is FormData', async () => {
    mockFetchOnce({ ok: true, status: 200, json: {} });
    const formData = new FormData();
    formData.append('conversation_id', 'abc');

    await apiFetch('/guardrail/evaluate-image', { method: 'POST', body: formData });

    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBeUndefined();
    expect(options.body).toBe(formData);
  });
});
