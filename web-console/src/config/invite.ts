/**
 * Invite-only UX (must match API `AMPREALIZE_INVITE_ONLY` for first-time OAuth).
 *
 * Set `VITE_INVITE_ONLY=1` on console Pages builds when the cloud is closed
 * to self-serve sign-up. Unset or `0` for open registration / local dev.
 */

const TRUE = new Set(['1', 'true', 'yes', 'on']);

export function isInviteOnlyUi(): boolean {
  const raw = import.meta.env.VITE_INVITE_ONLY;
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    return false;
  }
  return TRUE.has(String(raw).trim().toLowerCase());
}

/** Public marketing apex — request access / waitlist messaging. */
export const MARKETING_REQUEST_ACCESS_URL = 'https://amprealize.ai/';
