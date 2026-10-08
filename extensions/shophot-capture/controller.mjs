import {TTL, LOCAL_URL, targetIdentity, buildCapture, isLocalSender, isPopupSender, CaptureError} from './capture.mjs';

export function createController(chrome, reader, clock = () => Date.now()) {
  // All mutations are serialized by worker.mjs; storage survives MV3 worker suspension.
  const session = chrome.storage.session;
  const getState = async () => ({pending:{}, last:{code:'idle'}, ...await session.get(['pending','last'])});
  const write = async state => session.set(state);
  async function prune() {
    const state = await getState();
    for (const [id, entry] of Object.entries(state.pending)) {
      if (clock() - entry.created >= TTL || clock() < entry.created) {
        delete state.pending[id];
        if (state.last.tabId === Number(id)) state.last = {code:'expired'};
      }
    }
    await write(state); return state;
  }
  async function capture() {
    const state = await prune();
    if (Object.keys(state.pending).length >= 3) throw new CaptureError('pending_limit');
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!Number.isInteger(tab?.id) || !tab.url) throw new CaptureError('page');
    if (/_____tmd_____|\/splashui\/challenge|\/captcha|\/challenge/.test(new URL(tab.url).pathname)) throw new CaptureError('challenge');
    if (/\/login|\/signin|\/sign-in|\/accounts\//.test(new URL(tab.url).pathname)) throw new CaptureError('login_external');
    const original = targetIdentity(tab.url);
    let results;
    try { results = await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[0]},func:reader}); }
    catch { throw new CaptureError('permission'); }
    if (results.length !== 1 || results[0].frameId !== 0) throw new CaptureError('page');
    const payload = buildCapture(results[0].result, new Date(clock()));
    const captured = targetIdentity(payload.url);
    if (original.platform !== captured.platform || original.productId !== captured.productId ||
        new URL(original.url).hostname !== new URL(captured.url).hostname) throw new CaptureError('identity');
    // Bind the payload to a new tab before its local document can request it.
    const local = await chrome.tabs.create({url:'about:blank',active:true});
    state.pending[local.id] = {created:clock(),phase:'waiting',payload};
    state.last = {code:'waiting',tabId:local.id,created:clock()}; await write(state);
    try { await chrome.tabs.update(local.id,{url:LOCAL_URL}); }
    catch {
      delete state.pending[local.id]; state.last = {code:'offline'}; await write(state);
      throw new CaptureError('offline');
    }
    return {ok:true,code:'waiting'};
  }
  async function handle(message, sender) {
    if (!message || typeof message !== 'object') return {ok:false,code:'sender'};
    if (isPopupSender(sender,chrome.runtime)) {
      if (message.type === 'capture') {
        try { return await capture(); }
        catch (e) {
          const code = e instanceof CaptureError ? e.code : 'page';
          await session.set({last:{code}}); return {ok:false,code};
        }
      }
      if (message.type === 'status') {
        const state = await prune();
        const last = state.last;
        return {ok:true,code:['waiting','submitted'].includes(last.code) && clock()-last.created > 15000 ? 'no_response' : last.code};
      }
      return {ok:false,code:'sender'};
    }
    const login = isLocalSender(sender,chrome.runtime.id,'/accounts/login/');
    if (!isLocalSender(sender,chrome.runtime.id) && !login) return {ok:false,code:'sender'};
    // Both sender document and current top-level tab must be a known local surface.
    try {
      const tabUrl = new URL(sender.tab.url);
      if (tabUrl.origin !== new URL(LOCAL_URL).origin || tabUrl.pathname !== new URL(sender.url).pathname)
        return {ok:false,code:'sender'};
    } catch { return {ok:false,code:'sender'}; }
    const state = await prune(), entry = state.pending[sender.tab.id];
    if (!entry) return {ok:false,code:'no_capture'};
    if (login) {
      delete state.pending[sender.tab.id]; state.last={code:'login_local'}; await write(state);
      return {ok:false,code:'login_local'};
    }
    if (message.type === 'ready' && entry.phase === 'waiting') {
      const payload = entry.payload;
      // Consume before responding: reloads and duplicate requests can never resubmit.
      entry.phase='delivered'; delete entry.payload; state.last={code:'submitted',tabId:sender.tab.id,created:clock()};
      await write(state); return {ok:true,payload};
    }
    if (message.type === 'preview' && entry.phase === 'delivered') {
      delete state.pending[sender.tab.id]; state.last={code:'preview'}; await write(state);
      return {ok:true,code:'preview'};
    }
    if (message.type === 'bridge_error') {
      delete state.pending[sender.tab.id]; state.last={code:'bridge_error'}; await write(state);
      return {ok:false,code:'bridge_error'};
    }
    return {ok:false,code:'duplicate'};
  }
  async function removed(tabId) {
    const state=await getState();
    if (state.pending[tabId]) {
      delete state.pending[tabId];
      if (state.last.tabId === tabId) state.last={code:'closed'};
      await write(state);
    }
  }
  async function navigated(tabId, url) {
    if (!url) return;
    const state=await getState();
    if (!state.pending[tabId]) return;
    let allowed=false;
    try {
      const u=new URL(url);
      allowed=u.origin === new URL(LOCAL_URL).origin && ['/browser/capture/','/accounts/login/'].includes(u.pathname);
    } catch { /* error page */ }
    if (!allowed && url !== 'about:blank') {
      delete state.pending[tabId]; state.last={code:'offline'}; await write(state);
    }
  }
  return {handle,prune,removed,navigated};
}
