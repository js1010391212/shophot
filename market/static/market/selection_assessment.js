/* Coordinate required fields with trial_budget.js, never calculate money here. */
(() => {
  const shared = ['ad_cost', 'other_cost', 'payment_fee_rate', 'payment_fixed'];
  function sync() {
    const form = document.getElementById('profit-form');
    const assessment = form?.elements.assessment_enabled;
    if (!assessment) return;
    const enabled = assessment.checked;
    form.elements.assessment_costs_confirmed.disabled = !enabled;
    shared.forEach(name => { form.elements[name].required = enabled || form.elements.trial_enabled.checked; });
    ['discount_rate', 'target_margin'].forEach(name => { form.elements[name].required = enabled; });
    const button = form.querySelector('.calculate-button');
    if (button?.firstChild?.nodeType === Node.TEXT_NODE && enabled) {
      button.firstChild.textContent = '计算利润与选品判断 ';
    } else if (button?.firstChild?.nodeType === Node.TEXT_NODE) {
      button.firstChild.textContent = form.elements.trial_enabled.checked ? '计算利润与测品预算 ' : '计算单件利润 ';
    }
  }
  function clearFailedResult(event, networkFailure = false) {
    const detail = event.detail;
    const form = document.getElementById('profit-form');
    const workspace = document.getElementById('profit-workspace');
    // htmx 2.0.4 supplies the issuing element, resolved target and request config.
    // Ignore unrelated requests and responses for a workspace already replaced.
    if (!form || !workspace || detail?.elt !== form || detail.target !== workspace
        || detail.requestConfig?.verb !== 'post'
        || detail.requestConfig.path !== form.getAttribute('hx-post')) return;
    const status = detail.xhr?.status;
    if (!networkFailure && !(status === 403 || status === 429 || (status >= 500 && status <= 599))) return;
    const output = document.getElementById('profit-result');
    if (!output || !workspace.contains(output)) return;
    const notice = document.createElement('p');
    notice.className = 'notice error';
    notice.setAttribute('role', 'alert');
    notice.textContent = status === 403
      ? '本次计算失败：登录状态或安全校验已变更。请刷新页面，必要时重新登录，再计算。当前输入仍保留，旧结果已清除。'
      : '本次计算失败：服务暂时不可用或网络请求失败。当前输入仍保留，旧结果已清除；请稍后重新计算，或刷新页面重试。';
    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'button secondary';
    refresh.textContent = '刷新页面（刷新前可先记录当前输入）';
    refresh.addEventListener('click', () => window.location.reload());
    output.replaceChildren(notice, refresh);
    output.dataset.hasResult = 'false';
  }
  document.addEventListener('htmx:responseError', event => clearFailedResult(event));
  document.addEventListener('htmx:sendError', event => clearFailedResult(event, true));
  document.addEventListener('htmx:timeout', event => clearFailedResult(event, true));
  document.addEventListener('DOMContentLoaded', sync);
  document.addEventListener('htmx:afterSwap', sync);
  document.addEventListener('change', event => {
    if (['id_assessment_enabled', 'id_trial_enabled'].includes(event.target.id)) sync();
    if (['id_assessment_enabled', 'id_assessment_costs_confirmed'].includes(event.target.id)) {
      const output = document.getElementById('profit-result');
      if (output?.dataset.hasResult === 'true') document.getElementById('profit-stale').hidden = false;
    }
  });
})();
