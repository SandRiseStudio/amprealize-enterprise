/**
 * WhiteboardDO — Cloudflare Durable Object for real-time whiteboard sync.
 *
 * Architecture (enterprise tier):
 *   - Each tldraw room maps to one DO instance.  Room isolation is therefore
 *     guaranteed by the CF platform.
 *   - Snapshots are persisted to DO storage (fast, consistent) and optionally
 *     back-synced to the Python API on room close.
 *   - WebSocket upgrade requests arrive at the Worker, which stubs the right DO
 *     via `WHITEBOARD_ROOM.idFromName(roomId)` and forwards the connection.
 *
 * SyncBackend contract: The Worker entry-point in `index.ts` implements the
 * HTTP-to-DO routing; the DO itself handles the WebSocket lifecycle.
 */

import { TLSocketRoom } from "@tldraw/sync";
import type { UnknownRecord } from "@tldraw/store";

interface Env {
  PYTHON_API_BASE: string;
  WHITEBOARD_SERVICE_TOKEN: string;
  SNAPSHOT_STORAGE: string;
}

interface StoredSnapshot {
  state: unknown;
  clock: number;
  savedAt: string;
}

const SNAPSHOT_KEY = "snapshot";
const PERSIST_INTERVAL_MS = 30_000;
const IDLE_TIMEOUT_MS = 5 * 60_000;

export class WhiteboardDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  private tlRoom: TLSocketRoom<UnknownRecord> | null = null;
  private connections = new Set<WebSocket>();
  private persistAlarm = false;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
    // Restore alarm if set (ensures we don't lose inflight data across restarts)
    this.state.blockConcurrencyWhile(async () => {
      // Nothing to restore synchronously — room is lazy-loaded on first connect
    });
  }

  // -------------------------------------------------------------------------
  // fetch — entry point for all HTTP requests forwarded from the Worker
  // -------------------------------------------------------------------------

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/ws") {
      return this.handleWebSocket(request);
    }

    if (url.pathname === "/snapshot" && request.method === "GET") {
      return this.handleGetSnapshot();
    }

    if (url.pathname === "/snapshot" && request.method === "DELETE") {
      return this.handleDeleteSnapshot();
    }

    return new Response("Not found", { status: 404 });
  }

  // -------------------------------------------------------------------------
  // alarm — called by CF runtime to flush pending snapshot
  // -------------------------------------------------------------------------

  async alarm(): Promise<void> {
    await this.persistSnapshot();
    this.persistAlarm = false;
    // Re-schedule if there are still active connections (periodic save)
    if (this.connections.size > 0) {
      this.scheduleAlarm();
    }
  }

  // -------------------------------------------------------------------------
  // WebSocket handling
  // -------------------------------------------------------------------------

  private async handleWebSocket(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();
    server.accept();

    // Lazy room creation
    if (!this.tlRoom) {
      await this.initRoom();
    }

    const sessionId = `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    this.connections.add(server);
    this.scheduleAlarm();

    this.tlRoom!.handleSocketConnect({
      sessionId,
      socket: server as unknown as Parameters<
        TLSocketRoom<UnknownRecord>["handleSocketConnect"]
      >[0]["socket"],
    });

    server.addEventListener("close", () => {
      this.connections.delete(server);
      this.tlRoom?.handleSocketClose(sessionId);
      if (this.connections.size === 0) {
        // Final persist before going idle
        this.scheduleAlarm(IDLE_TIMEOUT_MS);
      }
    });

    return new Response(null, { status: 101, webSocket: client });
  }

  private async initRoom(): Promise<void> {
    const stored = await this.state.storage.get<StoredSnapshot>(SNAPSHOT_KEY);
    this.tlRoom = new TLSocketRoom<UnknownRecord>({
      initialSnapshot: (stored?.state as
        | Parameters<typeof TLSocketRoom<UnknownRecord>>[0]["initialSnapshot"]
        | undefined) ?? undefined,
    });
  }

  // -------------------------------------------------------------------------
  // Snapshot persistence
  // -------------------------------------------------------------------------

  private scheduleAlarm(delayMs = PERSIST_INTERVAL_MS): void {
    if (this.persistAlarm) return;
    this.persistAlarm = true;
    const alarmTime = Date.now() + delayMs;
    this.state.storage.setAlarm(alarmTime);
  }

  private async persistSnapshot(): Promise<void> {
    if (!this.tlRoom) return;
    const snapshot = this.tlRoom.getCurrentSnapshot();
    const stored: StoredSnapshot = {
      state: snapshot,
      clock: (snapshot as { clock?: number }).clock ?? 0,
      savedAt: new Date().toISOString(),
    };
    await this.state.storage.put(SNAPSHOT_KEY, stored);

    // Best-effort back-sync to Python API (enterprise environments have PYTHON_API_BASE)
    if (this.env.PYTHON_API_BASE && this.connections.size === 0) {
      await this.syncToPythonApi(stored);
    }
  }

  private async syncToPythonApi(snapshot: StoredSnapshot): Promise<void> {
    // Extract roomId from the DO name (set during Worker routing)
    const roomId = this.state.id.toString();
    const url = `${this.env.PYTHON_API_BASE}/whiteboard/rooms/${encodeURIComponent(roomId)}/canvas`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Amprealize-Internal": "1",
    };
    if (this.env.WHITEBOARD_SERVICE_TOKEN) {
      headers["Authorization"] = `Bearer ${this.env.WHITEBOARD_SERVICE_TOKEN}`;
    }
    try {
      await fetch(url, {
        method: "PUT",
        headers,
        body: JSON.stringify({ canvas_state: snapshot.state, clock: snapshot.clock }),
      });
    } catch {
      // Non-fatal — DO storage is the source of truth; Python API sync is best-effort
    }
  }

  private async handleGetSnapshot(): Promise<Response> {
    const stored = await this.state.storage.get<StoredSnapshot>(SNAPSHOT_KEY);
    if (!stored) {
      return new Response(JSON.stringify({ canvas_state: null }), {
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({ canvas_state: stored.state, clock: stored.clock }),
      { headers: { "Content-Type": "application/json" } },
    );
  }

  private async handleDeleteSnapshot(): Promise<Response> {
    await this.state.storage.delete(SNAPSHOT_KEY);
    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  }
}
