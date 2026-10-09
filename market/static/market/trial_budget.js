/* Enable optional inputs immediately; the server independently validates amounts. */
(() => {
  const fields = ['trial_quantity', 'trial_sample_cost', 'trial_setup_cost', 'trial_compliance_cost', 'trial_reserve_cost'];
  const explicit = ['ad_cost', 'other_cost', 'payment_fee_rate', 'payment_fixed'];
  function sync(open) {
    const form = document.getElementById('profit-form');
    const checkbox = form?.elements.trial_enabled;
    if (!checkbox) return;
    fields.forEach(name => { const field = form.elements[name]; field.disabled = !checkbox.checked; field.required = checkbox.checked; });
    explicit.forEach(name => { form.elements[name].required = checkbox.checked; });
    if (open && checkbox.checked) document.getElementById('trial-budget-details').open = true;
    const button = form.querySelector('.calculate-button');
    const text = checkbox.checked ? '计算利润与测品预算 ' : '计算单件利润 ';
    if (button?.firstChild?.nodeType === Node.TEXT_NODE) button.firstChild.textContent = text;
  }
  document.addEventListener('DOMContentLoaded', () => sync(true));
  document.addEventListener('htmx:afterSwap', () => sync(true));
  document.addEventListener('change', event => { if (event.target.id === 'id_trial_enabled') sync(true); });
})();
