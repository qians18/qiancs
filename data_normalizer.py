"""
将高驰API原始数据转为标准化跑步摘要
"""
import datetime


def normalize_activity(activity_list_item: dict, detail: dict) -> dict:
    """从活动列表项+详情提取标准化摘要"""
    sport_type = activity_list_item.get("sportType", 0)
    laps = detail.get("lapList", [])

    # 计算总体指标
    all_items = []
    for lap in laps:
        for item in lap.get("lapItemList", []):
            all_items.append(item)

    if not all_items:
        return _fallback_summary(activity_list_item)

    # 距离和时间：取最后一个lap的最后一个segment的累积值
    last_lap = laps[-1]
    last_lap_items = last_lap.get("lapItemList", [])
    last_seg = last_lap_items[-1] if last_lap_items else {}
    total_distance_cm = last_seg.get("totalDistance") or last_seg.get("distance") or 0
    total_time_cs = last_seg.get("totalLength") or last_seg.get("time") or 0

    # Fallback: 用活动列表数据
    if total_distance_cm <= 0:
        total_distance_cm = (activity_list_item.get("distance") or 0) * 100  # m → cm
    if total_time_cs <= 0:
        total_time_cs = (activity_list_item.get("totalTime") or 0)  # 已经厘秒

    # 心率（只从最后一个lap取，避免跨lap重复）
    hrs = [it.get("avgHr", 0) for it in last_lap_items if it.get("avgHr")]
    max_hrs = [it.get("maxHr", 0) for it in last_lap_items if it.get("maxHr")]
    avg_hr = round(sum(hrs) / len(hrs)) if hrs else None
    max_hr = max(max_hrs) if max_hrs else None

    # 配速 = 总时间 / 总距离
    pace_min_per_km = None
    if total_distance_cm > 0 and total_time_cs > 0:
        pace_sec_per_km = (total_time_cs / 100) / (total_distance_cm / 100000)
        pace_min_per_km = round(pace_sec_per_km / 60, 2)

    # 步频（最后一个lap的segments）
    cadences = [it.get("avgCadence", 0) for it in last_lap_items if it.get("avgCadence")]
    avg_cadence = round(sum(cadences) / len(cadences)) if cadences else None

    # 步幅 cm
    strides = [it.get("avgStrideLength", 0) for it in last_lap_items if it.get("avgStrideLength")]
    avg_stride = round(sum(strides) / len(strides)) if strides else None

    # 垂直振幅 mm
    oscillations = [it.get("strideHeight", 0) for it in last_lap_items if it.get("strideHeight")]
    avg_oscillation = round(sum(oscillations) / len(oscillations)) if oscillations else None

    # 触地时间 ms
    ground_times = [it.get("groundTime", 0) for it in last_lap_items if it.get("groundTime")]
    avg_ground_time = round(sum(ground_times) / len(ground_times)) if ground_times else None

    # 功率
    powers = [it.get("avgPower", 0) for it in last_lap_items if it.get("avgPower")]
    avg_power = round(sum(powers) / len(powers)) if powers else None

    # 累计爬升/下降（跨所有lap）
    elev_gains = []
    descents = []
    for lap in laps:
        for it in lap.get("lapItemList", []):
            if it.get("elevGain"):
                elev_gains.append(it["elevGain"])
            if it.get("totalDescent"):
                descents.append(it["totalDescent"])
    total_ascent = round(sum(elev_gains), 1) if elev_gains else 0
    total_descent = round(sum(descents), 1) if descents else 0

    # 心率区间（最后一个lap的segments）
    hr_zones = _compute_hr_zones(last_lap_items)

    # 时间戳（COROS返回秒级Unix时间戳）
    start_time = activity_list_item.get("startTime")
    if start_time:
        try:
            start_time = datetime.datetime.fromtimestamp(
                int(start_time)
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return {
        "summary": {
            "start_time": start_time,
            "duration_sec": round(total_time_cs / 100, 1),
            "duration_min": round(total_time_cs / 100 / 60, 1),
            "distance_km": round(total_distance_cm / 100000, 2),
            "pace_min_per_km": pace_min_per_km,
            "avg_hr_bpm": avg_hr,
            "max_hr_bpm": max_hr,
            "avg_cadence": avg_cadence,
            "avg_stride_length_cm": avg_stride,
            "avg_vertical_oscillation_mm": avg_oscillation,
            "avg_ground_time_ms": avg_ground_time,
            "avg_power_w": avg_power,
            "ascent_m": total_ascent,
            "descent_m": total_descent,
            "calories": activity_list_item.get("calorie"),
            "training_load": activity_list_item.get("trainingLoad"),
        },
        "hr_zones": hr_zones,
        "segment_count": len(all_items),
        "lap_count": len(laps),
    }


def _compute_hr_zones(items: list) -> dict:
    max_hr = max((it.get("maxHr") or 0 for it in items), default=180)
    zones = {
        "Z1_恢复 (<60%)": 0,
        "Z2_有氧耐力 (60-70%)": 0,
        "Z3_有氧动力 (70-80%)": 0,
        "Z4_阈值 (80-90%)": 0,
        "Z5_无氧 (>90%)": 0,
    }
    for it in items:
        hr = it.get("avgHr", 0)
        if not hr or max_hr == 0:
            continue
        pct = hr / max_hr
        if pct < 0.6:
            zones["Z1_恢复 (<60%)"] += 1
        elif pct < 0.7:
            zones["Z2_有氧耐力 (60-70%)"] += 1
        elif pct < 0.8:
            zones["Z3_有氧动力 (70-80%)"] += 1
        elif pct < 0.9:
            zones["Z4_阈值 (80-90%)"] += 1
        else:
            zones["Z5_无氧 (>90%)"] += 1
    total = sum(zones.values())
    return {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in zones.items() if total > 0}


def _fallback_summary(activity: dict) -> dict:
    ts = activity.get("startTime")
    try:
        ts = datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = str(ts)
    dist = (activity.get("distance") or 0) / 1000  # API活动列表返回米
    dur = (activity.get("totalTime") or 0) / 100
    pace = round(dur / 60 / dist, 2) if dist > 0 else None
    return {
        "summary": {
            "start_time": ts,
            "duration_sec": round(dur, 1),
            "duration_min": round(dur / 60, 1),
            "distance_km": round(dist, 2),
            "pace_min_per_km": pace,
            "avg_hr_bpm": activity.get("avgHr"),
            "max_hr_bpm": activity.get("maxHr"),
            "calories": activity.get("calorie"),
        },
        "hr_zones": {},
        "segment_count": 0,
        "lap_count": 0,
    }
