/* 只控制输入与单位提示，计费结果由 Python 服务端计算。 */
(() => {
  let fxPair = null;
  function update(resetRate = false) {
    const form = document.getElementById('profit-form') || document.getElementById('shipping-estimate-form');
    if (!form) return;
    const quoteMode = !form.elements.shipping_mode || form.elements.shipping_mode.value === 'quote';
    const panel = form.querySelector('[data-shipping-panel]');
    if (panel) panel.hidden = !quoteMode;
    const manual = form.querySelector('[data-shipping-manual]');
    if (manual) manual.hidden = quoteMode;
    if (form.elements.shipping) { form.elements.shipping.disabled = quoteMode; form.elements.shipping.required = !quoteMode; }
    const metadataNode = document.getElementById('shipping-quote-metadata');
    const quotes = metadataNode ? JSON.parse(metadataNode.textContent) : {};
    const quote = quotes[form.elements.shipping_quote.value];
    const costCurrency = form.elements.cost_currency.value;
    form.querySelectorAll('[data-shipping-inputs] input, [data-shipping-inputs] select').forEach(input => {
      if (input.name !== 'cost_currency') input.disabled = !quoteMode;
    });
    ['shipping_quote', 'package_weight', 'package_units', 'fuel_rate', 'shipping_extra'].forEach(name => form.elements[name].required = quoteMode);
    ['package_length', 'package_width', 'package_height'].forEach(name => form.elements[name].required = quoteMode && Boolean(quote?.volume_divisor));
    const description = form.querySelector('[data-quote-description]');
    const source = form.querySelector('[data-quote-source]');
    const rate = form.elements.shipping_exchange_rate;
    const nextPair = quote ? `${quote.currency}/${costCurrency}` : '';
    if (resetRate && nextPair !== fxPair) rate.value = '';
    fxPair = nextPair;
    rate.readOnly = Boolean(quote && quote.currency === costCurrency);
    rate.required = Boolean(quoteMode && quote && quote.currency !== costCurrency);
    if (rate.readOnly) rate.value = '1';
    if (quote) {
      description.textContent = `${quote.source} · ${quote.route} · ${quote.currency}\n计费范围 ${quote.min_weight}–${quote.max_weight} kg，进位 ${quote.step_weight} kg，${quote.volume_divisor ? `体积重系数 ${quote.volume_divisor}` : '合同不计体积重'}。\n生效 ${quote.effective_from}${quote.checked_at ? `，资料查阅 ${quote.checked_at}` : ''}。\n${quote.notes}`;
      form.querySelector('[data-shipping-extra-help]').textContent = `以 ${quote.currency} 填写整个包裹的费用。`;
      form.querySelector('[data-shipping-fx-help]').textContent = `1 ${quote.currency} = 多少 ${costCurrency}？这是物流汇率，与售价汇率分开。`;
    } else description.textContent = '请选择实际发货地、目的地及适用条件一致的物流报价。';
    source.hidden = !quote?.source_url;
    if (quote?.source_url) source.href = quote.source_url;
  }
  function updateMethod() {
    const form = document.getElementById('shipping-rate-form');
    if (!form) return;
    const perKg = form.elements.method.value === 'per_kg';
    ['per_kg', 'first_weight', 'first_price', 'step_price'].forEach(name => {
      const field = form.elements[name];
      const relevant = name === 'per_kg' ? perKg : !perKg;
      field.disabled = !relevant;
      field.required = relevant;
      field.closest('.field-grid>div').hidden = !relevant;
    });
  }
  document.addEventListener('DOMContentLoaded', () => { update(); updateMethod(); });
  document.addEventListener('htmx:afterSwap', () => { update(); updateMethod(); });
  const markStale = event => {
    if (!event.target.closest('#shipping-estimate-form')) return;
    const output = document.getElementById('shipping-result');
    if (output?.dataset.hasResult === 'true') {
      document.getElementById('shipping-stale').hidden = false;
      output.querySelector('[data-shipping-profit-link]').hidden = true;
    }
  };
  document.addEventListener('input', markStale);
  document.addEventListener('change', markStale);
  document.addEventListener('change', event => {
    if (event.target.matches('#id_shipping_mode, #id_shipping_quote, #id_cost_currency')) update(true);
    if (event.target.matches('#shipping-rate-form #id_method')) updateMethod();
  });
})();
