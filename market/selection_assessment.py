"""Read-only assessment of validated unit economics, not market demand."""
from decimal import Decimal
from .profit_references import reference_money


def assess_selection(result, data, trial=None, reference=None):
    revenue, net, target = result['revenue'], result['net'], data['target_margin']
    required_net = revenue * target / Decimal('100')
    reasons = []
    if not data['assessment_costs_confirmed']:
        status, title = 'unconfirmed', '先核对成本'
        reasons.append('成本和费率尚未确认，当前金额仅为假设，不能判定条件达标。')
    elif revenue == 0 or net <= 0:
        status, title = 'adjust', '先调整售价或成本'
    elif net < required_net:
        status, title = 'below_target', '尚未达到目标'
        reasons.append('当前单件净利低于收入乘目标利润率，请调整或核实假设。')
    elif trial and trial['net'] < 0:
        status, title = 'batch_shortfall', '本批尚未覆盖一次性费用'
        reasons.append('单件已达到目标，但原预算的批次净利仍为负。')
    else:
        status, title = 'meets_target', '账面条件达到目标，可继续核实测品条件'
        reasons.append('单件净利为正且不低于收入乘目标利润率。')
    if revenue == 0:
        reasons.append('收入为 0，不计算利润比例。')
    if net < 0:
        reasons.append('当前单件亏损。')
    elif net == 0:
        reasons.append('单件净利为 0，没有利润缓冲。')
    if trial:
        if trial['net'] == 0:
            reasons.append('本批仅覆盖费用，没有批次利润缓冲。')
        if trial['recovery'] is not None and trial['recovery'] > trial['quantity']:
            reasons.append('摊回一次性费用所需件数超过本批数量。')
    else:
        reasons.append('尚未启用测品预算，仍需估算数量与一次性费用。')
    unknowns = []
    changed = False
    if reference:
        price, currency = reference_money(reference)
        capture = reference.get('data', {})
        changed = data['selling_price'] != price or data['sale_currency'] != currency
        if reference['kind'] == 'observation':
            if not capture.get('sku_id'):
                unknowns.append('规格编号未知，待核对。')
            if not capture.get('market_country'):
                unknowns.append('收货国家未知，待核对。')
            if not capture.get('conditions'):
                unknowns.append('优惠、税运等报价条件未知，待核对；空记录不表示没有条件。')
        else:
            unknowns.append('公共报价未提供本次测算的明确规格、收货国家及优惠 / 税运条件，待核对。')
        source_note = ('本次售价或售价币种已修改，测算使用用户假设。' if changed
                       else '本次引用保存报价作为假设售价，仍须核对时效和条件。')
    else:
        source_note = '无引用报价：本次为手填成本与售价情景。'
    return dict(status=status, title=title, reasons=reasons, unknowns=unknowns,
                revenue=revenue, net=net, target=target, required_net=required_net,
                currency=result['cost_currency'], trial=trial, source_note=source_note,
                changed=changed)
