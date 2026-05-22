"""
AI 跑步教练 —— 使用 Claude API + COROS 完整生理数据
"""
import json
import os
from anthropic import Anthropic


def analyze_single_run(run_summary: dict, hr_zones_data: dict,
                       profile: dict = None, evolab: dict = None,
                       time_series_metrics: dict = None) -> str:
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = _build_single_prompt(run_summary, hr_zones_data, profile, evolab,
                                  time_series_metrics)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3072,
        system=_coach_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b for b in resp.content if getattr(b, "type", None) == "text"]
    return text_blocks[0].text if text_blocks else str(resp.content)


def analyze_trends(trends: dict, recent_runs: list, profile: dict = None) -> str:
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = _build_trends_prompt(trends, recent_runs, profile)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3072,
        system=_coach_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b for b in resp.content if getattr(b, "type", None) == "text"]
    return text_blocks[0].text if text_blocks else str(resp.content)


def _coach_system_prompt():
    return (
        "你是一名精通运动生理学的专业跑步教练（NSCA-CSCS认证级别）。分析时：\n"
        "1. 基于跑者的真实生理数据（VO2max、心率区间、HRV、训练负荷）给出判断\n"
        "2. 所有建议必须可量化（具体配速、心率值、距离、频率）\n"
        "3. 先肯定做得好的地方，再指优化点\n"
        "4. 用中文，简洁有力，不要废话\n"
        "5. 伤病风险明确警告"
    )


def _format_ts_metrics_section(metrics: dict) -> str:
    """Format per-second time series metrics as a markdown section."""
    if not metrics:
        return ""

    lines = ["\n## 逐秒深度指标"]

    # === Splits table ===
    splits = metrics.get("splits")
    if splits:
        lines.append("\n### 每公里分段")
        lines.append("| km | 配速 | 配速波动(s) | 平均心率 | 最大心率 | 步频 | 爬升(m) |")
        lines.append("|----|------|------------|---------|---------|------|---------|")
        for sp in splits:
            lines.append(
                f"| {sp.get('km', '?')} "
                f"| {sp.get('pace_min_per_km', '?')} "
                f"| {sp.get('pace_std_sec', '?')} "
                f"| {sp.get('avg_hr', '-')} "
                f"| {sp.get('max_hr', '-')} "
                f"| {sp.get('avg_cadence', '-')} "
                f"| {sp.get('elev_gain_m', '-')} |"
            )

    # === Pace Stability ===
    ps = metrics.get("pace_stability")
    if ps:
        lines.append("\n### 配速稳定性")
        lines.append(f"- 逐秒配速标准差: {ps.get('overall_std_sec', '?')}秒")
        lines.append(f"- 变异系数(CV): {ps.get('cv_pct', '?')}%")
        lines.append(f"- 评价: {ps.get('label', '?')}")

    # === HR Drift ===
    hd = metrics.get("hr_drift")
    if hd:
        lines.append("\n### 心率漂移")
        lines.append(f"- 漂移率: {hd.get('drift_bpm_per_hour', '?')} bpm/小时")
        lines.append(f"- R²: {hd.get('r_squared', '?')}")
        lines.append(f"- 评价: {hd.get('label', '?')}")

    # === Cadence ===
    cd = metrics.get("cadence")
    if cd:
        lines.append("\n### 步频")
        lines.append(f"- 平均: {cd.get('mean', '?')} spm | 标准差: {cd.get('std', '?')} | CV: {cd.get('cv_pct', '?')}%")
        lines.append(f"- 评价: {cd.get('label', '?')}")

    # === Aerobic Decoupling ===
    ad = metrics.get("aerobic_decoupling")
    if ad:
        lines.append("\n### 有氧解耦")
        lines.append(f"- 解耦率: {ad.get('decoupling_pct', '?')}%")
        lines.append(f"- 评价: {ad.get('label', '?')}")

    # === Efficiency Trend ===
    et = metrics.get("efficiency_trend")
    if et:
        lines.append("\n### 效率趋势 (配速/心率比)")
        lines.append(f"- 起始: {et.get('start_ratio', '?')} → 结束: {et.get('end_ratio', '?')}")
        lines.append(f"- 变化: {et.get('change_pct', '?')}%")
        lines.append(f"- 评价: {et.get('trend', '?')}")

    # === Pace Distribution ===
    pd = metrics.get("pace_distribution")
    if pd:
        lines.append("\n### 配速分布")
        lines.append("| 区间 | 时长(秒) | 占比 |")
        lines.append("|------|---------|------|")
        for zone, data in pd.items():
            lines.append(f"| {zone} | {data.get('seconds', 0)} | {data.get('pct', 0)}% |")

    # === Elevation ===
    elev = metrics.get("elevation")
    if elev:
        lines.append("\n### 海拔")
        lines.append(f"- 累计爬升: {elev.get('total_ascent_m', '?')}m"
                     f" | 累计下降: {elev.get('total_descent_m', '?')}m")

    # === Optional: Temperature ===
    temp = metrics.get("temperature")
    if temp:
        lines.append("\n### 温度")
        if isinstance(temp, dict):
            for k, v in temp.items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append(f"- 温度: {temp}")

    # === Optional: Power ===
    power = metrics.get("power")
    if power:
        lines.append("\n### 功率")
        if isinstance(power, dict):
            for k, v in power.items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append(f"- 功率: {power}")

    return "\n".join(lines)


def _build_single_prompt(s: dict, hr_zones_data: dict,
                         profile: dict, evolab: dict,
                         time_series_metrics: dict = None) -> str:
    parts = []

    # === 跑者档案 ===
    if profile:
        parts.append("## 跑者生理档案")
        parts.append(f"- 安静心率: {profile.get('rhr')} bpm | 最大心率: {profile.get('max_hr')} bpm")
        parts.append(f"- VO2max: {profile.get('vo2max')} ml/kg/min")
        parts.append(f"- 乳酸阈值心率(LTHR): {profile.get('lthr')} bpm | LT配速: {profile.get('ltsp')}")
        parts.append(f"- HRV基线: {profile.get('hrv_baseline')}ms | 当前HRV: {profile.get('hrv_latest')}ms")
        parts.append(f"- 恢复状态: {profile.get('recovery_pct')}% | 体力等级: {profile.get('stamina_level')}")
        parts.append(f"- 有氧耐力分: {profile.get('aerobic_endurance')} | 阈能力分: {profile.get('lactate_threshold_capacity')}")
        if profile.get("hr_zones"):
            parts.append("- COROS心率区间:")
            for z in profile["hr_zones"]:
                parts.append(f"  Z{z.get('index', '')+1 if z.get('index') is not None else ''}: "
                             f"{z.get('hr')}bpm ({z.get('ratio')}%)")

    # === 本次跑步 ===
    parts.append("\n## 本次跑步数据")
    parts.append(f"- 距离: {s.get('distance_km')} km | 时长: {s.get('duration_min')} 分钟")
    parts.append(f"- 平均配速: {s.get('pace_min_per_km')}/km")
    parts.append(f"- 平均心率: {s.get('avg_hr_bpm')} bpm | 最大心率: {s.get('max_hr_bpm')} bpm")
    parts.append(f"- 步频: {s.get('avg_cadence')} | 步幅: {s.get('avg_stride_length_cm')} cm")
    if s.get("avg_vertical_oscillation_mm"):
        parts.append(f"- 垂直振幅: {s['avg_vertical_oscillation_mm']}mm | 触地时间: {s.get('avg_ground_time_ms')}ms")
    if s.get("avg_power_w"):
        parts.append(f"- 平均功率: {s['avg_power_w']}W")
    if s.get("training_load"):
        parts.append(f"- 训练负荷: {s['training_load']}")

    # 心率区间
    if hr_zones_data:
        parts.append("\n## 本次心率区间分布")
        for zone, data in hr_zones_data.items():
            parts.append(f"- {zone}: {data['pct']}%")

    # 逐秒深度指标
    if time_series_metrics:
        parts.append(_format_ts_metrics_section(time_series_metrics))

    # 近7天趋势
    if profile and profile.get("trend_7d"):
        parts.append("\n## 近7天训练趋势")
        for d in profile["trend_7d"]:
            parts.append(f"  {d['date']}: load={d['load']}, tired={d['tired']}%, perf={d['perf']}, RHR={d['rhr']}")

    parts.append("\n## 请分析")
    parts.append("1. 结合跑者的VO2max({}ml/kg/min)和乳酸阈值心率({}bpm)，这次训练在什么强度区间？是否合理？".format(
        profile.get("vo2max", "?") if profile else "?", profile.get("lthr", "?") if profile else "?"))

    # Question 2: HR-drift / pace-HR matching
    if time_series_metrics:
        hd = time_series_metrics.get("hr_drift")
        if hd:
            parts.append("2. 心率漂移为{} bpm/小时(R²={})，有氧能力如何？".format(
                hd.get("drift_bpm_per_hour", "?"), hd.get("r_squared", "?")))
        else:
            parts.append("2. 心率-配速匹配度如何？心率漂移是否有问题？")
    else:
        parts.append("2. 心率-配速匹配度如何？心率漂移是否有问题？")

    # Question 3: Cadence / running form
    if time_series_metrics:
        cd = time_series_metrics.get("cadence")
        if cd:
            parts.append("3. 步频均值{}spm(CV={}%)，步频是否理想？跑姿效率（垂直振幅、触地时间）如何？".format(
                cd.get("mean", "?"), cd.get("cv_pct", "?")))
        else:
            parts.append("3. 步频和跑姿效率（垂直振幅、触地时间）如何？")
    else:
        parts.append("3. 步频和跑姿效率（垂直振幅、触地时间）如何？")

    # Question 4: HRV + recovery + aerobic decoupling + efficiency trend
    if time_series_metrics:
        ad = time_series_metrics.get("aerobic_decoupling")
        et = time_series_metrics.get("efficiency_trend")
        decoupling_str = ad.get("decoupling_pct", "?") if ad else "?"
        trend_str = et.get("trend", "?") if et else "?"
        parts.append("4. 结合HRV({}ms)、恢复状态({}%)、有氧解耦({}%)和效率趋势({})，接下来应该做什么训练？".format(
            profile.get("hrv_latest", "?") if profile else "?",
            profile.get("recovery_pct", "?") if profile else "?",
            decoupling_str, trend_str))
    else:
        parts.append("4. 结合HRV({}ms)和恢复状态({}%)，接下来应该做什么训练？".format(
            profile.get("hrv_latest", "?") if profile else "?",
            profile.get("recovery_pct", "?") if profile else "?"))

    parts.append("5. 有没有伤病隐患？")

    return "\n".join(parts)


def _build_trends_prompt(trends: dict, recent_runs: list, profile: dict) -> str:
    parts = []

    # 档案
    if profile:
        parts.append("## 跑者生理档案")
        parts.append(f"VO2max: {profile.get('vo2max')} | RHR: {profile.get('rhr')} | MaxHR: {profile.get('max_hr')}")
        parts.append(f"LTHR: {profile.get('lthr')} | 体力: {profile.get('stamina_level')}")
        parts.append(f"HRV: {profile.get('hrv_baseline')}→{profile.get('hrv_latest')} | 恢复: {profile.get('recovery_pct')}%")
        parts.append(f"有氧耐力: {profile.get('aerobic_endurance')} | 无氧能力: {profile.get('anaerobic_capacity')} | 阈能力: {profile.get('lactate_threshold_capacity')}")
        if profile.get("trend_7d"):
            parts.append("近7天: " + " | ".join(
                f"{d['date'][-4:]}: load={d['load']} tired={d['tired']}% RHR={d['rhr']}"
                for d in profile["trend_7d"]))

    # 趋势统计
    parts.append(f"\n## 30次跑步趋势")
    parts.append(f"总次数: {trends.get('total_runs')} | 平均距离: {trends.get('avg_distance_km')}km")
    parts.append(f"平均配速: {trends.get('avg_pace_min_per_km')}/km | 最佳配速: {trends.get('best_pace')}/km")
    parts.append(f"最长: {trends.get('longest_run_km')}km | 平均心率: {trends.get('avg_hr_bpm')}bpm")
    weeks = trends.get("weekly_summary", {})
    if weeks:
        parts.append("周统计:")
        for wk, data in sorted(weeks.items()):
            parts.append(f"  {wk}: {data['runs']}次/{data['distance']:.1f}km/{data['duration']:.0f}min")

    # 最近列表
    parts.append("\n## 最近记录")
    for r in recent_runs[:20]:
        parts.append(f"- {r.get('start_time', '?')[:10]}: {r.get('distance_km')}km "
                     f"配速{r.get('pace_min_per_km')}/km 心率{r.get('avg_hr_bpm')}bpm "
                     f"步频{r.get('avg_cadence')} 负荷{r.get('training_load')}")

    parts.append("\n## 请分析")
    parts.append("1. 结合VO2max({})和乳酸阈值({}bpm)，当前训练强度分布是否合理？".format(
        profile.get("vo2max", "?") if profile else "?", profile.get("lthr", "?") if profile else "?"))
    parts.append("2. 训练负荷趋势如何？是否有过度训练或训练不足？")
    parts.append("3. 有氧/无氧/阈值三项能力分是否均衡？需要重点补哪项？")
    parts.append("4. 给出接下来2-4周的周期化训练计划（含具体配速、心率、距离）")
    parts.append("5. 基于HRV和恢复数据，是否需要调整训练量？")

    return "\n".join(parts)
