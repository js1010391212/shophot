// Isolated-world local content script. No window-message or external-page API.
(() => {
  if (window.top !== window || window.__shopHotBridgeStarted) return;
  window.__shopHotBridgeStarted=true;
  const messages={
    no_capture:'没有待接收的观测。请回到商品页点击扩展采集。',
    duplicate:'这次观测已发送。请核对预览；重新采集需回到商品页点击扩展。',
    login_local:'请先登录本地 ShopHot，再回到商品页重新点击采集。',
    bridge_error:'本地页面没有有效的接收表单，观测未保存。请更新 ShopHot 后重新采集。',
    extension:'扩展连接已失效，观测未保存。请刷新页面，并回到商品页重新采集。',
    sender:'本地接收地址不匹配，观测未发送。',
  };
  const show = code => {
    const p=document.createElement('p'); p.setAttribute('role','alert');
    p.textContent=messages[code] || messages.extension;
    p.style.cssText='padding:12px;border:1px solid #b45309;background:#fffbeb;color:#78350f;';
    (document.querySelector('main') || document.body).prepend(p);
  };
  const send = message => chrome.runtime.sendMessage(message);
  async function run() {
    if(location.origin !== 'http://127.0.0.1:8000') return;
    if(location.pathname === '/accounts/login/') {
      const response=await send({type:'login'});
      if(response.code === 'login_local') show('login_local'); return;
    }
    if(location.pathname !== '/browser/capture/') return;
    const form=document.querySelector('#browser-capture-form[data-browser-capture-bridge="ready"]');
    if (!form) {
      // Recognize preview structure without reading its signed token.
      const confirmation=[...document.querySelectorAll('form[method="post"]')].find(f=>
        /^\/products\/\d+\/browser\/confirm\/$/.test(new URL(f.action,location.href).pathname) &&
        new URL(f.action,location.href).origin === location.origin && f.querySelector('input[name="preview"]'));
      await send({type:confirmation ? 'preview' : 'bridge_error'}); return;
    }
    const target=form.elements.namedItem('target_url'), capture=form.elements.namedItem('capture');
    const csrf=form.elements.namedItem('csrfmiddlewaretoken');
    if (form.method.toLowerCase() !== 'post' || new URL(form.action,location.href).href !== location.origin+'/browser/capture/' ||
        !target || !capture || !csrf?.value || typeof form.requestSubmit !== 'function' ||
        form.querySelectorAll('[name="target_url"]').length !== 1 ||
        form.querySelectorAll('[name="capture"]').length !== 1 || form.querySelectorAll('[name="csrfmiddlewaretoken"]').length !== 1) {
      await send({type:'bridge_error'}); show('bridge_error'); return;
    }
    const response=await send({type:'ready'});
    if (!response?.ok || !response.payload) {show(response?.code);return;}
    const raw=JSON.stringify(response.payload);
    if (new TextEncoder().encode(raw).length > 16384 || typeof response.payload.url !== 'string') {
      await send({type:'bridge_error'});show('bridge_error');return;
    }
    target.value=response.payload.url; capture.value=raw;
    if (!form.checkValidity()) {await send({type:'bridge_error'});show('bridge_error');return;}
    // Keep existing CSRF, ordinary same-origin POST, and the server confirmation step.
    form.requestSubmit();
  }
  run().catch(()=>show('extension'));
})();
