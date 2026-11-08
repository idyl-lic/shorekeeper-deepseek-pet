import {mkdirSync, writeFileSync, renameSync, statSync} from 'node:fs';
import {join} from 'node:path';
import {homedir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {PetState, safeBalance} from './state.js';

export const name = 'shorekeeper-pet';
export const inject = ['sessions', 'deepseekAccount'];

export function apply(ctx) {
  const home = process.env.DSH_HOME || join(homedir(), '.dsh');
  const dir = join(home, 'shorekeeper-pet');
  const path = join(dir, 'desktop.json'), request = join(dir, 'refresh');
  const state = new PetState(), instance = randomUUID();
  let balance = {status: 'loading', wallets: [], bonus: []}, updated = 0;
  let disposed = false, busy = false, lastBalance = 0, lastRequest = 0, accountEpoch = 0;
  let catalogRows = [], catalogBusy = false, catalogSignature = '';

  // Cordis exposes an injected service directly on ctx; other services are optional
  // here so the pet keeps working on a host that does not provide them.
  function service(name) {
    for (const probe of [() => ctx[name], () => ctx.reflect?.get?.(name), () => ctx.get?.(name)]) {
      try { const value = probe(); if (value) return value; } catch { /* not provided */ }
    }
    return undefined;
  }
  // Titles, running flags and timestamps only: the pet never receives prompts,
  // messages, arguments, results or workspace paths of a conversation.
  // Archived ids live on the host workspace registry, not in the session list,
  // so they are read separately and passed down to drop those conversations.
  function archivedIds() {
    try {
      const ids = service('workspaceRegistry')?.archivedSessionIds;
      if (ids instanceof Set) return [...ids].map(String);
      if (Array.isArray(ids)) return ids.map(String);
      return [];
    } catch { return []; }
  }
  // The host `sessions` service is the live session manager, not the client list, so
  // the complete catalog comes from the session controller. Both are read defensively
  // and the live manager stays as a fallback.
  async function readCatalog() {
    const archived = new Set(archivedIds());
    const rows = [];
    const accept = (item) => {
      const id = item && (item.sessionId || item.id);
      if (!id) return;
      if (item.parentSessionId !== undefined || item.parentId !== undefined) return;
      if (item.origin === 'subagent' || item.blank) return;
      if (archived.has(String(id))) return;
      // The host list keeps the title in its title projection, not on the row.
      const title = String(item.title || item.displayTitle
        || item.projections?.values?.title || item.projectionValues?.title || '').trim();
      rows.push({id: String(id), title: title.slice(0, 120), running: Boolean(item.running),
        updatedAt: Number(item.updatedAt) || 0});
    };
    const controller = service('sessionController');
    if (controller && typeof controller.list === 'function') {
      try {
        const result = await controller.list({});
        const items = Array.isArray(result?.items) ? result.items : [];
        for (const item of items) accept(item);
        return rows;
      } catch { /* fall back to the live session manager */ }
    }
    try {
      const live = service('sessions');
      const values = live && typeof live.values === 'function' ? [...live.values()] : [];
      for (const session of values) {
        accept({sessionId: session?.id, title: session?.header?.title,
          updatedAt: Number(session?.header?.createdAt) || 0});
      }
    } catch { /* keep the previous catalog */ }
    return rows;
  }
  function flush(connected = true) {
    if (disposed && connected) return;
    try {
      mkdirSync(dir, {recursive: true});
      const archived = new Set(archivedIds());
      writeFileSync(path + '.tmp', JSON.stringify({schema: 1, backend: 'deepseek-harness',
        instance, connected, updated_at: Date.now() / 1000, ...state.snapshot(catalogRows, archived),
        balance: {...balance, updated_at: updated}}), {mode: 0o600});
      renameSync(path + '.tmp', path);
    } catch { /* A pet export failure must never interrupt a user's task. */ }
  }
  async function refreshCatalog() {
    if (catalogBusy || disposed) return;
    catalogBusy = true;
    try {
      const rows = await readCatalog();
      const signature = rows.map(row => `${row.id}\u0000${row.title}\u0000${row.running}`).join('\u0001');
      const changed = signature !== catalogSignature;
      catalogSignature = signature; catalogRows = rows;
      if (changed) flush();
    } catch { /* a catalog read failure must not stop the heartbeat */ }
    finally { catalogBusy = false; }
  }
  async function refresh() {
    if (busy || disposed) return;
    busy = true; lastBalance = Date.now();
    const epoch = accountEpoch;
    try {
      const value = await ctx.deepseekAccount.getBalance({version: '0.2.0-rc.2', locale: 'zh-CN',
        timezoneOffsetSeconds: -new Date().getTimezoneOffset() * 60});
      if (!disposed && epoch === accountEpoch) { balance = safeBalance(value); updated = Date.now() / 1000; }
    } catch { if (!disposed && epoch === accountEpoch) balance = {status: 'unavailable', wallets: [], bonus: []}; }
    finally { busy = false; flush(); }
  }
  ctx.on('session/event', (session, event) => {
    try { state.accept(session, event); } catch { /* Ignore unsupported event shape. */ }
    // A turn changed activity: refresh the catalog soon so titles and order follow.
    if (event?.type === 'turn/start' || event?.type === 'turn/end') void refreshCatalog();
  });
  ctx.on('deepseek-account/signed-out', () => {
    accountEpoch++;
    balance = {status: 'signed-out', wallets: [], bonus: []}; updated = Date.now() / 1000; flush();
  });
  ctx.effect(() => {
    flush(); void refresh(); void refreshCatalog();
    let ticks = 0;
    const timer = setInterval(() => {
      let requested = 0;
      try { requested = statSync(request).mtimeMs; } catch {}
      if (Date.now() - lastBalance > 120000 || (requested > lastRequest && Date.now() - lastBalance > 5000)) {
        lastRequest = requested; void refresh();
      }
      // Full session reads hit persistence, so poll them less often than the write beat.
      if (++ticks % 6 === 0) void refreshCatalog();
      flush();
    }, 500);
    timer.unref();
    return () => { disposed = true; clearInterval(timer); flush(false); };
  });
}
