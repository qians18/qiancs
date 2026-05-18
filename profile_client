"""获取并缓存COROS生理档案数据"""
import json, os, time, requests
from coros_client import BASE_URL

PROFILE_FILE = os.path.join(os.path.dirname(__file__), "data", ".profile")


def fetch_profile(client) -> dict:
    """从COROS获取完整生理档案"""
    headers = {
        "accessToken": client.access_token,
        "yfheader": json.dumps({"userId": client.user_id}),
    }

    # Dashboard
    dash = requests.get(f"{BASE_URL}/dashboard/query", headers=headers).json()
    s = dash.get("data", {}).get("summaryInfo", {})

    # Analyse
    an = requests.get(f"{BASE_URL}/analyse/query", headers=headers).json()
    an_data = an.get("data", {})
    t7 = an_data.get("t7dayList", [])

    # 取最新有vo2max的天
    vo2max = None
    for d in reversed(t7):
        if d.get("vo2max"):
            vo2max = d["vo2max"]
            break

    hrv = s.get("sleepHrvData", {})

    profile = {
        "rhr": s.get("rhr"),                    # 安静心率
        "max_hr": s.get("fitnessMaxHr"),         # 最大心率
        "lthr": s.get("lthr"),                   # 乳酸阈值心率
        "ltsp": s.get("ltsp"),                   # 乳酸阈值配速(COROS单位)
        "vo2max": vo2max,                         # 最大摄氧量
        "hrv_baseline": hrv.get("sleepHrvBase"),  # HRV基线
        "hrv_latest": hrv.get("avgSleepHrv"),     # HRV当前
        "recovery_pct": s.get("recoveryPct"),     # 恢复百分比
        "recovery_state": s.get("recoveryState"), # 恢复状态(4=完全恢复)
        "full_recovery_hours": s.get("fullRecoveryHours"),
        "stamina_level": s.get("staminaLevel"),     # 体力等级
        "stamina_change": s.get("staminaLevelChange"),
        "stamina_ranking": s.get("staminaLevelRanking"),
        "aerobic_endurance": s.get("aerobicEnduranceScore"),
        "anaerobic_capacity": s.get("anaerobicCapacityScore"),
        "anaerobic_endurance": s.get("anaerobicEnduranceScore"),
        "lactate_threshold_capacity": s.get("lactateThresholdCapacityScore"),
        "running_level_hr": s.get("runningLevelHr"),
        # COROS心率区间
        "hr_zones": s.get("lthrZone", []),
        # 近7天趋势
        "trend_7d": [
            {"date": str(d.get("happenDay")), "vo2max": d.get("vo2max"),
             "rhr": d.get("rhr"), "load": d.get("trainingLoad"),
             "tired": d.get("tiredRateNew"), "perf": d.get("performance")}
            for d in t7[-7:]
        ],
        "updated_at": time.time(),
    }
    # 缓存
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return profile


def load_cached_profile() -> dict:
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE) as f:
                p = json.load(f)
            if time.time() - p.get("updated_at", 0) < 86400:  # 24h有效
                return p
        except Exception:
            pass
    return None
