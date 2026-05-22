"""
FIT文件解析器 —— 从Garmin FIT格式提取跑步指标
"""
import datetime
from fitparse import FitFile


def parse_fit(file_path: str) -> dict:
    """解析FIT文件，返回结构化跑步数据"""
    fit = FitFile(file_path)

    records = []
    laps = []
    sessions = []

    for record in fit.get_messages("record"):
        data = {}
        for field in record:
            data[field.name] = field.value
        records.append(data)

    for lap in fit.get_messages("lap"):
        data = {}
        for field in lap:
            data[field.name] = field.value
        laps.append(data)

    for session in fit.get_messages("session"):
        data = {}
        for field in session:
            data[field.name] = field.value
        sessions.append(data)

    # --- 提取逐秒数据 ---
    timestamps = []
    heart_rates = []
    speeds = []          # m/s
    cadences = []
    altitudes = []
    temperatures = []
    powers = []

    for r in records:
        ts = r.get("timestamp")
        if ts:
            timestamps.append(ts)
        hr = r.get("heart_rate")
        if hr is not None:
            heart_rates.append(hr)
        spd = r.get("speed")
        if spd is not None:
            speeds.append(spd)
        cad = r.get("cadence")
        if cad is not None:
            cadences.append(cad)
        alt = r.get("altitude")
        if alt is not None:
            altitudes.append(alt)
        temp = r.get("temperature")
        if temp is not None:
            temperatures.append(temp)
        pwr = r.get("power")
        if pwr is not None:
            powers.append(pwr)

    # --- 汇总指标 ---
    total_elapsed = 0
    total_distance = 0  # meters
    avg_hr = None
    max_hr = None
    avg_speed = None
    max_speed = None
    avg_cadence = None
    total_calories = None
    total_ascent = None
    total_descent = None
    avg_power = None
    max_power = None
    training_effect = None

    if sessions:
        s = sessions[0]
        total_elapsed = s.get("total_elapsed_time", 0) or 0
        total_distance = (s.get("total_distance", 0) or 0) / 100  # cm -> m
        avg_hr = s.get("avg_heart_rate")
        max_hr = s.get("max_heart_rate")
        avg_speed = s.get("avg_speed")
        max_speed = s.get("max_speed")
        total_calories = s.get("total_calories")
        total_ascent = s.get("total_ascent")
        total_descent = s.get("total_descent")
        avg_power = s.get("avg_power")
        max_power = s.get("max_power")
        training_effect = s.get("total_training_effect")

    if not avg_cadence and cadences:
        avg_cadence = sum(cadences) / len(cadences)

    if heart_rates:
        max_hr = max_hr or max(heart_rates)
        avg_hr = avg_hr or (sum(heart_rates) / len(heart_rates))

    # --- 配速计算 ---
    pace_per_km = None
    if avg_speed and avg_speed > 0:
        pace_per_km = (1000 / avg_speed) / 60  # min/km

    # --- 心率区间 ---
    hr_zones = _compute_hr_zones(heart_rates, max_hr)

    # --- 时间格式化 ---
    duration_min = total_elapsed / 60 if total_elapsed else 0

    return {
        "summary": {
            "duration_sec": round(total_elapsed, 1),
            "duration_min": round(duration_min, 1),
            "distance_km": round(total_distance / 1000, 2),
            "pace_min_per_km": round(pace_per_km, 2) if pace_per_km else None,
            "avg_hr_bpm": round(avg_hr) if avg_hr else None,
            "max_hr_bpm": round(max_hr) if max_hr else None,
            "avg_cadence": round(avg_cadence) if avg_cadence else None,
            "avg_speed_ms": round(avg_speed, 2) if avg_speed else None,
            "max_speed_ms": round(max_speed, 2) if max_speed else None,
            "calories": total_calories,
            "ascent_m": round(total_ascent, 1) if total_ascent else 0,
            "descent_m": round(total_descent, 1) if total_descent else 0,
            "avg_power_w": round(avg_power) if avg_power else None,
            "max_power_w": round(max_power) if max_power else None,
            "training_effect": round(training_effect, 1) if training_effect else None,
            "start_time": str(timestamps[0]) if timestamps else None,
        },
        "hr_zones": hr_zones,
        "time_series": {
            "timestamps": [str(t) for t in timestamps],
            "heart_rate": heart_rates,
            "speed_ms": speeds,
            "cadence": cadences,
            "altitude_m": altitudes,
            "temperature": temperatures,
            "power_w": powers,
        },
        "lap_count": len(laps),
        "raw_laps": _extract_laps(laps),
    }


def _compute_hr_zones(heart_rates: list, max_hr) -> dict:
    """估算心率区间分布"""
    if not max_hr or max_hr == 0:
        max_hr = max(heart_rates) if heart_rates else 180
    zones = {
        "zone1_恢复 (<60%)": 0,
        "zone2_有氧耐力 (60-70%)": 0,
        "zone3_有氧动力 (70-80%)": 0,
        "zone4_阈值 (80-90%)": 0,
        "zone5_无氧 (>90%)": 0,
    }
    for hr in heart_rates:
        pct = hr / max_hr
        if pct < 0.6:
            zones["zone1_恢复 (<60%)"] += 1
        elif pct < 0.7:
            zones["zone2_有氧耐力 (60-70%)"] += 1
        elif pct < 0.8:
            zones["zone3_有氧动力 (70-80%)"] += 1
        elif pct < 0.9:
            zones["zone4_阈值 (80-90%)"] += 1
        else:
            zones["zone5_无氧 (>90%)"] += 1
    total = len(heart_rates)
    return {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in zones.items() if total > 0}


def _extract_laps(laps: list) -> list:
    result = []
    for i, lap in enumerate(laps):
        result.append({
            "lap": i + 1,
            "distance_m": lap.get("total_distance"),
            "duration_sec": lap.get("total_elapsed_time"),
            "avg_hr": lap.get("avg_heart_rate"),
            "max_hr": lap.get("max_heart_rate"),
            "avg_speed_ms": round(lap.get("avg_speed"), 2) if lap.get("avg_speed") else None,
            "avg_cadence": lap.get("avg_cadence"),
        })
    return result
