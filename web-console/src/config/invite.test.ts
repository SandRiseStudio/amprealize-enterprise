import { describe, it, expect, vi, afterEach } from 'vitest';

describe('isInviteOnlyUi', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns false when VITE_INVITE_ONLY is unset', async () => {
    vi.stubEnv('VITE_INVITE_ONLY', '');
    vi.resetModules();
    const { isInviteOnlyUi } = await import('./invite');
    expect(isInviteOnlyUi()).toBe(false);
  });

  it.each(['1', 'true', 'yes', 'on', 'TRUE'])('returns true when VITE_INVITE_ONLY=%s', async (val) => {
    vi.stubEnv('VITE_INVITE_ONLY', val);
    vi.resetModules();
    const { isInviteOnlyUi } = await import('./invite');
    expect(isInviteOnlyUi()).toBe(true);
  });

  it('returns false when explicitly disabled', async () => {
    vi.stubEnv('VITE_INVITE_ONLY', '0');
    vi.resetModules();
    const { isInviteOnlyUi } = await import('./invite');
    expect(isInviteOnlyUi()).toBe(false);
  });
});
