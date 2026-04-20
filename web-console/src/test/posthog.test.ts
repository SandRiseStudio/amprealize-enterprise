/**
 * Unit tests for src/lib/posthog.ts
 *
 * Tests the wrapper contract:
 * - No-op when VITE_POSTHOG_KEY is absent
 * - No-op on localhost without VITE_POSTHOG_ENABLED=true
 * - No-op when user has opted out via localStorage
 * - identifyUser / resetUser forward to posthog-js
 * - capture merges ambient props
 * - resetUser clears ambient props
 * - optOut / optIn toggle posthog-js capturing
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock posthog-js before importing the module under test
// ---------------------------------------------------------------------------

const mockPosthog = {
  init: vi.fn(),
  identify: vi.fn(),
  reset: vi.fn(),
  capture: vi.fn(),
  setPersonProperties: vi.fn(),
  opt_out_capturing: vi.fn(),
  opt_in_capturing: vi.fn(),
  register_once: vi.fn(),
};

vi.mock('posthog-js', () => ({
  default: mockPosthog,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setEnv(key: string, value: string | undefined) {
  if (value === undefined) {
    delete (import.meta.env as Record<string, string | undefined>)[key];
  } else {
    (import.meta.env as Record<string, string>)[key] = value;
  }
}

function resetModule() {
  vi.resetModules();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('posthog wrapper', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear localStorage opt-out key
    try { window.localStorage.removeItem('amprealize.posthog'); } catch { /* jsdom */ }
    resetModule();
  });

  afterEach(() => {
    setEnv('VITE_POSTHOG_KEY', undefined);
    setEnv('VITE_POSTHOG_ENABLED', undefined);
    setEnv('VITE_GIT_SHA', undefined);
  });

  it('is a no-op when VITE_POSTHOG_KEY is absent', async () => {
    setEnv('VITE_POSTHOG_KEY', undefined);
    const { initPostHog, capture } = await import('../lib/posthog');
    initPostHog();
    capture('some_event');
    expect(mockPosthog.init).not.toHaveBeenCalled();
    expect(mockPosthog.capture).not.toHaveBeenCalled();
  });

  it('is a no-op on localhost without VITE_POSTHOG_ENABLED', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    // jsdom sets window.location.hostname to 'localhost' by default
    const { initPostHog, capture } = await import('../lib/posthog');
    initPostHog();
    capture('some_event');
    expect(mockPosthog.init).not.toHaveBeenCalled();
    expect(mockPosthog.capture).not.toHaveBeenCalled();
  });

  it('initialises when VITE_POSTHOG_ENABLED=true on localhost', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog } = await import('../lib/posthog');
    initPostHog();
    expect(mockPosthog.init).toHaveBeenCalledOnce();
    expect(mockPosthog.init).toHaveBeenCalledWith(
      'phc_testkey',
      expect.objectContaining({ api_host: 'https://us.i.posthog.com' }),
    );
  });

  it('is a no-op when user has opted out via localStorage', async () => {
    window.localStorage.setItem('amprealize.posthog', 'off');
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog, capture } = await import('../lib/posthog');
    initPostHog();
    expect(mockPosthog.init).not.toHaveBeenCalled();
    capture('should_be_swallowed');
    expect(mockPosthog.capture).not.toHaveBeenCalled();
  });

  it('capture merges ambient surface prop after init', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog, capture } = await import('../lib/posthog');
    initPostHog();
    capture('test_event', { foo: 'bar' });
    expect(mockPosthog.capture).toHaveBeenCalledWith(
      'test_event',
      expect.objectContaining({ surface: 'web-console', foo: 'bar' }),
    );
  });

  it('capture merges git_sha when VITE_GIT_SHA is set', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    setEnv('VITE_GIT_SHA', 'abc123');
    const { initPostHog, capture } = await import('../lib/posthog');
    initPostHog();
    capture('test_event');
    expect(mockPosthog.capture).toHaveBeenCalledWith(
      'test_event',
      expect.objectContaining({ git_sha: 'abc123' }),
    );
  });

  it('identifyUser calls posthog.identify with id and properties', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog, identifyUser } = await import('../lib/posthog');
    initPostHog();
    identifyUser({ id: 'user-42', email: 'alice@example.com', displayName: 'Alice', tenantId: 't-1', edition: 'premium' });
    expect(mockPosthog.identify).toHaveBeenCalledWith('user-42', {
      email: 'alice@example.com',
      name: 'Alice',
      tenant_id: 't-1',
      edition: 'premium',
    });
  });

  it('resetUser calls posthog.reset and removes ambient tenant_id/edition', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog, identifyUser, resetUser, capture } = await import('../lib/posthog');
    initPostHog();
    identifyUser({ id: 'u1', tenantId: 'tenant-x', edition: 'starter' });
    resetUser();
    expect(mockPosthog.reset).toHaveBeenCalledOnce();
    // After reset, ambient tenant_id + edition should be gone.
    mockPosthog.capture.mockClear();
    capture('after_reset');
    const lastCall = mockPosthog.capture.mock.calls[0][1] as Record<string, unknown>;
    expect(lastCall).not.toHaveProperty('tenant_id');
    expect(lastCall).not.toHaveProperty('edition');
  });

  it('optOut calls posthog.opt_out_capturing and sets localStorage', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    const { initPostHog, optOut } = await import('../lib/posthog');
    initPostHog();
    optOut();
    expect(mockPosthog.opt_out_capturing).toHaveBeenCalledOnce();
    expect(window.localStorage.getItem('amprealize.posthog')).toBe('off');
  });

  it('optIn removes localStorage key and calls posthog.opt_in_capturing when already initialised', async () => {
    setEnv('VITE_POSTHOG_KEY', 'phc_testkey');
    setEnv('VITE_POSTHOG_ENABLED', 'true');
    // Init without opt-out so _initialized = true, then opt out in-flight,
    // then opt back in.
    const { initPostHog, optOut, optIn } = await import('../lib/posthog');
    initPostHog();
    optOut(); // sets localStorage + calls opt_out_capturing
    mockPosthog.opt_in_capturing.mockClear();
    optIn(); // should clear localStorage + call opt_in_capturing
    expect(mockPosthog.opt_in_capturing).toHaveBeenCalledOnce();
    expect(window.localStorage.getItem('amprealize.posthog')).toBeNull();
  });
});
