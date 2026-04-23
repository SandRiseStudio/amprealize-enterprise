/**
 * Cloudflare Worker entry-point — routes WebSocket upgrades to WhiteboardDO instances.
 *
 * Each tldraw room is staked to a Durable Object keyed by the room ID.  The Worker
 * acts purely as a routing layer; all WebSocket state lives in the DO.
 */

export { WhiteboardDO } from "./WhiteboardDO.js";

interface Env {
  WHITEBOARD_ROOM: DurableObjectNamespace;
  PYTHON_API_BASE: string;
  WHITEBOARD_SERVICE_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/healthz") {
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // WebSocket upgrade: /ws/:roomId
    const wsMatch = url.pathname.match(/^\/ws\/([^/]+)$/);
    if (wsMatch) {
      const roomId = decodeURIComponent(wsMatch[1]);
      return routeToDO(request, env, roomId, "/ws");
    }

    // Canvas snapshot: /rooms/:roomId/canvas
    const snapshotMatch = url.pathname.match(/^\/rooms\/([^/]+)\/canvas$/);
    if (snapshotMatch) {
      const roomId = decodeURIComponent(snapshotMatch[1]);
      return routeToDO(request, env, roomId, "/snapshot");
    }

    return new Response("Not found", { status: 404 });
  },
};

function routeToDO(
  request: Request,
  env: Env,
  roomId: string,
  doPath: string,
): Promise<Response> {
  const id = env.WHITEBOARD_ROOM.idFromName(roomId);
  const stub = env.WHITEBOARD_ROOM.get(id);
  const doUrl = new URL(request.url);
  doUrl.pathname = doPath;
  return stub.fetch(new Request(doUrl.toString(), request));
}
