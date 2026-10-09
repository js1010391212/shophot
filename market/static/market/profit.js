/* 币种变化只更新单位提示，不猜汇率；旧结果在输入改变时明确标记。 */
(() => {
  let pair = null;
  function updateCurrency(changed) {
    const form = document.getElementById('profit-form');
    if (!form) return;
    const sale = form.elements.sale_currency.value;
    const cost = form.elements.cost_currency.value;
    const rate = form.elements.exchange_rate;
    const nextPair = `${sale}/${cost}`;
    if (changed && pair !== nextPair) rate.value = '';
    if (sale === cost) { rate.value = '1'; rate.readOnly = true; }
    else rate.readOnly = false;
    pair = nextPair;
    document.getElementById('exchange-direction').textContent = `1 ${sale} = 多少 ${cost}？`;
    form.querySelectorAll('[data-cost-currency]').forEach(node => node.textContent = `· ${cost}`);
    const labels = {selling_price: `商品售价（${sale}）`, cost: `单件采购成本（${cost}）`, shipping: `单件履约运费（${cost}）`,
      ad_cost: `单件广告成本（${cost}）`, other_cost: `单件其他成本（${cost}）`, payment_fixed: `单笔固定支付手续费（${cost}）`};
    Object.entries(labels).forEach(([name, label]) => {
      const target = form.querySelector(`label[for="id_${name}"]`);
      if (target) target.textContent = label;
    });
  }
  // Only this module's marked reference errors can replace the profit workspace.
  document.addEventListener('htmx:beforeSwap', event => {
    const detail = event.detail;
    if (detail?.target?.id !== 'profit-workspace' || ![400, 404].includes(detail.xhr?.status)
        || detail.xhr.getResponseHeader('X-ShopHot-Profit-Workspace-Error') !== '1') return;
    detail.shouldSwap = true;
    detail.isError = false;
  });
  document.addEventListener('DOMContentLoaded', () => updateCurrency(false));
  document.addEventListener('htmx:afterSwap', () => updateCurrency(false));
  document.addEventListener('input', event => {
    if (!event.target.closest('#profit-form')) return;
    const output = document.getElementById('profit-result');
    if (output && output.dataset.hasResult === 'true') document.getElementById('profit-stale').hidden = false;
  });
  document.addEventListener('change', event => {
    if (event.target.matches('#id_sale_currency, #id_cost_currency')) updateCurrency(true);
  });
})();
