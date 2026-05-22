"""
从FIT逐秒数据计算深度跑步指标
"""
import math
from collections import defaultdict


def compute_all_metrics(time_series: dict) -> dict:
    """从fit_parser.parse_fit()返回的time_series计算所有深度指标"""
    hr = time_series.get("heart_rate", [])
    speeds = time_series.get("speed_ms", [])
    cadences = time_series.get("cadence", [])
    alts = time_series.get("altitude_m", [])
    temps = time_series.get("temperature", [])
    powers = time_series.get("power_w", [])

    metrics = {}

    # 配速数组: m/s -> min/km
    paces = [_speed_to_pace(s) for s in speeds]

    metrics["splits"] = _compute_splits(paces, hr, cadences, alts, speeds)
    metrics["pace_stability"] = _pace_stability(paces)
    metrics["hr_drift"] = _hr_drift(hr)
    metrics["cadence"] = _cadence_stats(cadences)
    metrics["aerobic_decoupling"] = _aerobic_decoupling(paces, hr)
    metrics["efficiency_trend"] = _efficiency_trend(paces, hr)
    metrics["pace_distribution"] = _pace_distribution(paces)
    metrics["elevation"] = {
        "total_ascent_m": _total_ascent(alts),
        "total_descent_m": _total_descent(alts),
    }
    if temps:
        metrics["temperature"] = {
            "avg_c": round(sum(temps) / len(temps), 1),
            "min_c": round(min(temps), 1),
            "max_c": round(max(temps), 1),
        }
    if powers:
        metrics["power"] = {
            "avg_w": round(sum(powers) / len(powers)),
            "max_w": max(powers),
        }

    return metrics


def _speed_to_pace(speed_ms: float) -> float:
    if speed_ms and speed_ms > 0.3:
        return (1000 / speed_ms) / 60
    return None


# --- 配速区间 ---
PACE_ZONES = [
    ("间歇", 0, 5.5),
    ("阈值", 5.5, 6.5),
    ("中等", 6.5, 7.5),
    ("轻松", 7.5, 8.5),
    ("恢复", 8.5, 99),
]

PACE_ZONE_LABELS = ["间歇 (<5:30)", "阈值 (5:30-6:30)", "中等 (6:30-7:30)", "轻松 (7:30-8:30)", "恢复 (>8:30)"]


# --- 每公里分段 ---
def _compute_splits(paces, hr, cadences, alts, speeds):
    """按累计距离切片，计算每公里指标"""
    if not speeds:
        return []

    distance_m = 0
    km_idx = 1
    km_paces = []
    km_hrs = []
    km_cadences = []
    km_alts = []

    splits = []
    for i, s in enumerate(speeds):
        if s is None or s <= 0:
            continue
        dist_step = s  # 1秒的距离增量(m)
        distance_m += dist_step

        # 收集该秒的指标
        p = _speed_to_pace(s)
        if p:
            km_paces.append(p)
        if i < len(hr) and hr[i]:
            km_hrs.append(hr[i])
        if i < len(cadences) and cadences[i]:
            km_cadences.append(cadences[i])
        if i < len(alts) and alts[i] is not None:
            km_alts.append(alts[i])

        if distance_m >= km_idx * 1000:
            split = _summarize_km(km_idx, km_paces, km_hrs, km_cadences, km_alts)
            splits.append(split)
            km_idx += 1
            km_paces = []
            km_hrs = []
            km_cadences = []
            km_alts = []

    # 最后不足1km的
    if km_paces:
        split = _summarize_km(km_idx, km_paces, km_hrs, km_cadences, km_alts)
        splits.append(split)

    return splits


def _summarize_km(idx, paces, hrs, cadences, alts):
    split = {"km": idx}
    if paces:
        avg_pace = sum(paces) / len(paces)
        split["pace_min_per_km"] = _format_pace(avg_pace)
        split["pace_std_sec"] = round(_std(paces) * 60, 1)
    else:
        split["pace_min_per_km"] = None
        split["pace_std_sec"] = None
    if hrs:
        split["avg_hr"] = round(sum(hrs) / len(hrs))
        split["max_hr"] = max(hrs)
    else:
        split["avg_hr"] = None
        split["max_hr"] = None
    if cadences:
        split["avg_cadence"] = round(sum(cadences) / len(cadences))
    else:
        split["avg_cadence"] = None
    if alts:
        gains = [alts[i] - alts[i - 1] for i in range(1, len(alts)) if alts[i] > alts[i - 1]]
        split["elev_gain_m"] = round(sum(gains), 1) if gains else 0
    else:
        split["elev_gain_m"] = 0
    return split


def _format_pace(min_per_km: float) -> str:
    minutes = int(min_per_km)
    seconds = int((min_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"


# --- 配速稳定性 ---
def _pace_stability(paces):
    valid = [p for p in paces if p]
    if len(valid) < 10:
        return {"overall_std_sec": None, "per_km_cv_list": None, "label": "数据不足"}

    std_sec = round(_std(valid) * 60, 1)
    cv_pct = round(_std(valid) / (sum(valid) / len(valid)) * 100, 1) if valid else None

    if cv_pct is None:
        label = "N/A"
    elif cv_pct < 5:
        label = "非常稳定"
    elif cv_pct < 8:
        label = "稳定"
    elif cv_pct < 12:
        label = "一般"
    else:
        label = "波动较大"

    return {"overall_std_sec": std_sec, "cv_pct": cv_pct, "label": label}


# --- 心率漂移 ---
def _hr_drift(hr):
    """线性回归心率 vs 时间，返回斜率"""
    valid = [(i, h) for i, h in enumerate(hr) if h]
    n = len(valid)
    if n < 60:
        return {"slope_bpm_per_min": None, "drift_bpm_per_hour": None,
                "r_squared": None, "label": "数据不足"}

    xs = [v[0] / 60 for v in valid]  # 秒→分钟
    ys = [v[1] for v in valid]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_yy = sum((y - mean_y) ** 2 for y in ys)

    if ss_xx == 0:
        return {"slope_bpm_per_min": None, "drift_bpm_per_hour": None,
                "r_squared": None, "label": "无法计算"}

    slope = ss_xy / ss_xx
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 0 else 0

    drift_per_hour = round(slope * 60, 1)

    # 判断漂移程度 (正漂移=心率上升)
    if abs(drift_per_hour) < 2:
        label = "无漂移，有氧基础扎实"
    elif drift_per_hour < 5:
        label = "轻微正向漂移，正常范围"
    elif drift_per_hour < 10:
        label = "明显正向漂移，有氧耐力有待提升"
    else:
        label = "严重正向漂移，建议降低强度或补水"

    return {
        "slope_bpm_per_min": round(slope, 4),
        "drift_bpm_per_hour": drift_per_hour,
        "r_squared": round(r_squared, 3),
        "label": label,
    }


# --- 步频统计 ---
def _cadence_stats(cadences):
    valid = [c for c in cadences if c and c > 30]
    if not valid:
        return {"mean": None, "std": None, "cv_pct": None, "label": "数据不足"}

    mean = sum(valid) / len(valid)
    std = _std(valid)
    cv_pct = round(std / mean * 100, 1) if mean > 0 else None

    if mean < 160:
        label = f"步频偏低({mean:.0f})，建议加快至170-180"
    elif mean < 170:
        label = f"步频适中({mean:.0f})"
    elif mean <= 185:
        label = f"步频理想({mean:.0f})"
    else:
        label = f"步频偏高({mean:.0f})"

    return {"mean": round(mean), "std": round(std, 1), "cv_pct": cv_pct, "label": label}


# --- 有氧解耦 ---
def _aerobic_decoupling(paces, hr):
    """前后半程心率/配速比差异"""
    valid = [(p, h) for p, h in zip(paces, hr) if p and h]
    if len(valid) < 60:
        return {"decoupling_pct": None, "label": "数据不足"}

    mid = len(valid) // 2
    first = valid[:mid]
    second = valid[mid:]

    def ratio(data):
        return sum(h / p for p, h in data) / len(data)

    r1 = ratio(first)
    r2 = ratio(second)

    if r1 == 0:
        return {"decoupling_pct": None, "label": "无法计算"}

    dec_pct = round((r2 - r1) / r1 * 100, 1)

    if dec_pct < 2:
        label = "无解耦，有氧效率稳定"
    elif dec_pct < 5:
        label = "轻微解耦，正常范围"
    elif dec_pct < 8:
        label = "中度解耦，有氧耐力不足"
    else:
        label = "严重解耦，需加强有氧基础"

    return {"decoupling_pct": dec_pct, "label": label}


# --- 效率趋势 ---
def _efficiency_trend(paces, hr):
    """滑动窗口配速/心率比，看起始 vs 结束"""
    valid = [(p, h) for p, h in zip(paces, hr) if p and h]
    if len(valid) < 120:
        return {"start_ratio": None, "end_ratio": None, "trend": "数据不足"}

    window = max(len(valid) // 6, 30)
    first_win = valid[:window]
    last_win = valid[-window:]

    def avg_ratio(data):
        total = sum(p / h for p, h in data)
        return total / len(data)

    start_r = avg_ratio(first_win)
    end_r = avg_ratio(last_win)

    if start_r == 0:
        return {"start_ratio": None, "end_ratio": None, "trend": "无法计算"}

    change = (end_r - start_r) / start_r * 100

    if change > 1:
        trend = "效率提升 (negative split)"
    elif change > -2:
        trend = "效率平稳"
    elif change > -5:
        trend = "效率轻微下降"
    else:
        trend = "效率明显下降，后半程掉速"

    return {
        "start_ratio": round(start_r, 3),
        "end_ratio": round(end_r, 3),
        "change_pct": round(change, 1),
        "trend": trend,
    }


# --- 配速分布 ---
def _pace_distribution(paces):
    """按自定义配速区间分桶"""
    valid = [p for p in paces if p]
    if not valid:
        return {label: 0 for label in PACE_ZONE_LABELS}

    counts = defaultdict(int)
    for p in valid:
        for zone_name, lo, hi in PACE_ZONES:
            if lo <= p < hi:
                counts[zone_name] += 1
                break

    total = len(valid)
    result = {}
    for label, (zone_name, lo, hi) in zip(PACE_ZONE_LABELS, PACE_ZONES):
        c = counts.get(zone_name, 0)
        result[label] = {
            "seconds": c,
            "pct": round(c / total * 100, 1),
        }
    return result


# --- 海拔 ---
def _total_ascent(alts):
    if not alts or len(alts) < 2:
        return 0
    gain = 0
    for i in range(1, len(alts)):
        if alts[i] is not None and alts[i - 1] is not None and alts[i] > alts[i - 1]:
            gain += alts[i] - alts[i - 1]
    return round(gain, 1)


def _total_descent(alts):
    if not alts or len(alts) < 2:
        return 0
    loss = 0
    for i in range(1, len(alts)):
        if alts[i] is not None and alts[i - 1] is not None and alts[i] < alts[i - 1]:
            loss += alts[i - 1] - alts[i]
    return round(loss, 1)


def _std(values):
    n = len(values)
    if n < 2:
        return 0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)
