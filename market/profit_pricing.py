"""零固定成本的定价边界：费率和目标精度0.01%，汇率精度0.000001。"""
from decimal import Decimal
from math import gcd

BASIS = 10000
FX_SCALE = 1000000


def _floor_sum(count, modulus, slope, offset):
    """用欧几里得转置计算 sum(floor((slope*i+offset)/modulus))。"""
    total = 0
    while True:
        quotient, slope = divmod(slope, modulus)
        total += quotient * count * (count - 1) // 2
        quotient, offset = divmod(offset, modulus)
        total += quotient * count
        top = slope * count + offset
        if top < modulus:
            return total
        count, offset = divmod(top, modulus)
        modulus, slope = slope, modulus


def zero_fixed_price(fee, payment_fee, target, rate):
    """非正连续分母仍可能因费用舍入达标，返回最小正收入的两位售价。

    仅处理已经由表单校验的精度；金额用整数分，比例用整数基点。
    分母为负时，两笔费用最多节省不足一分，收入搜索最多10000档。
    分母为零时，达标条件按收入分的10000余数重复；通过整数格点计数
    二分查找第一个达标售价，避免逐分遍历最高100亿分的精确周期。
    """
    a, b, t = (int(value * 100) for value in (fee, payment_fee, target))
    fx = int(rate * FX_SCALE)

    def revenue(price):
        return (2 * price * fx + FX_SCALE) // (2 * FX_SCALE)

    def qualifies(income):
        fees = (income * a + BASIS // 2) // BASIS + (income * b + BASIS // 2) // BASIS
        return income > 0 and (income - fees) * BASIS >= income * t

    def price_for(income):
        return ((2 * income - 1) * FX_SCALE + 2 * fx - 1) // (2 * fx)

    first = price_for(1)
    if qualifies(revenue(first)):
        return Decimal(first) / 100
    gap = a + b + t - BASIS
    if gap > 0:
        limit = (bool(a) + bool(b)) * (BASIS // 2) // gap
        income = 1
        while income <= limit:
            price = price_for(income)
            actual = revenue(price)
            if actual > limit:
                return None
            if qualifies(actual):
                return Decimal(price) / 100
            income = actual + 1
        return None

    # 分母为零：收入分余数r满足达标条件时，将相邻r合并为格点区间。
    runs, start = [], None
    for residue in range(BASIS + 1):
        good = residue < BASIS and (residue == 0 or qualifies(residue))
        if good and start is None:
            start = residue
        elif not good and start is not None:
            runs.append((start, residue - 1))
            start = None

    def has_price(last):
        count = last - first + 1
        slope, scale = 2 * fx, 2 * FX_SCALE
        offset = slope * first + FX_SCALE
        modulus = BASIS * scale
        return any(
            _floor_sum(count, modulus, slope, offset + (BASIS - low) * scale)
            > _floor_sum(count, modulus, slope, offset + (BASIS - high - 1) * scale)
            for low, high in runs
        )

    # 此周期使换算收入为10000分的整数倍，所有比例费用精确且目标达标。
    # 周期最多10^10分，始终低于表单最大售价999999999999分。
    low, high = first, BASIS * FX_SCALE // gcd(fx, BASIS * FX_SCALE)
    while low < high:
        middle = (low + high) // 2
        if has_price(middle):
            high = middle
        else:
            low = middle + 1
    return Decimal(low) / 100
