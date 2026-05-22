"""
COROS + AI 跑步教练 —— CLI入口
用法:
  python main.py sync              同步最近跑步数据
  python main.py analyze [label_id] 分析跑步（最近一次或指定记录）
  python main.py report             趋势报告
"""
import sys
import os
import json
from getpass import getpass

from coros_client import CorosClient
from data_normalizer import normalize_activity
from run_db import save_run, get_recent_runs, get_trends, get_run, get_db
from ai_coach import analyze_single_run, analyze_trends
from profile_client import fetch_profile, load_cached_profile
from fit_parser import parse_fit
from run_metrics import compute_all_metrics

FIT_DIR = os.path.join(os.path.dirname(__file__), "data", "fit")


def get_credentials():
    email = os.environ.get("COROS_EMAIL")
    password = os.environ.get("COROS_PASSWORD")
    if not email:
        email = input("COROS邮箱/手机号: ").strip()
    if not password:
        password = getpass("COROS密码: ").strip()
    if not email or not password:
        print("错误: 需要提供COROS账号和密码")
        sys.exit(1)
    return email, password


def ensure_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("错误: 请设置 ANTHROPIC_API_KEY 环境变量")
        print("  PowerShell: $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
        sys.exit(1)


def _sync_recent(client, count=5):
    """拉取最近 N 条记录，新记录自动入库。返回新入库的 label_id 列表。"""
    runs = client.get_recent_runs(count=count)
    new_ids = []
    for run in runs:
        label_id = str(run["labelId"])
        sport_type = run["sportType"]

        if get_run(label_id):
            continue

        dist_km = (run.get("distance") or 0) / 1000
        print(f"  新记录: {run.get('startTime', '?')} - "
              f"{client.sport_type_name(sport_type)} ({dist_km:.2f}km)")

        try:
            detail = client.get_activity_detail(label_id, sport_type)
            parsed = normalize_activity(run, detail)
            evolab = client.get_evolab(label_id, sport_type)
            save_run(label_id, sport_type, parsed["summary"], parsed["hr_zones"], evolab)
            new_ids.append(label_id)
        except Exception as e:
            print(f"    同步失败: {e}")

    if not new_ids:
        print("  没有新的跑步记录")
    else:
        print(f"  同步完成: {len(new_ids)} 条新记录")

    return new_ids


def _get_or_download_fit(client, label_id, sport_type):
    """下载FIT文件到本地缓存，已存在则跳过。返回文件路径或 None。"""
    fit_path = os.path.join(FIT_DIR, f"{label_id}.fit")

    if os.path.exists(fit_path):
        print(f"  FIT文件已缓存: {fit_path}")
        return fit_path

    try:
        os.makedirs(FIT_DIR, exist_ok=True)
        print(f"  下载FIT文件: {label_id}...")
        client.download_fit(label_id, sport_type, fit_path)
        print(f"  已保存: {fit_path}")
        return fit_path
    except Exception as e:
        print(f"  FIT下载失败: {e}")
        return None


def cmd_sync():
    email, password = get_credentials()
    client = CorosClient(email, password)
    print("登录中...")
    client.login()
    print("登录成功！获取跑步列表...")

    runs = client.get_recent_runs(count=30)
    print(f"找到 {len(runs)} 条跑步记录")

    new_count = 0
    for run in runs:
        label_id = str(run["labelId"])
        sport_type = run["sportType"]

        if get_run(label_id):
            continue

        dist_km = (run.get("distance") or 0) / 1000  # API返回米
        print(f"  同步: {run.get('startTime', '?')} - {client.sport_type_name(sport_type)} "
              f"({dist_km:.2f}km)")

        try:
            detail = client.get_activity_detail(label_id, sport_type)
            parsed = normalize_activity(run, detail)
            evolab = client.get_evolab(label_id, sport_type)

            save_run(label_id, sport_type, parsed["summary"], parsed["hr_zones"], evolab)
            new_count += 1
        except Exception as e:
            print(f"    失败: {e}")

    print(f"同步完成: {new_count} 条新记录")

    # 刷新生理档案缓存
    try:
        fetch_profile(client)
        print("生理档案已刷新")
    except Exception as e:
        print(f"生理档案获取失败: {e}")


def cmd_analyze(target_id=None):
    ensure_api_key()
    email, password = get_credentials()
    client = CorosClient(email, password)
    print("登录中...")
    client.login()
    print("登录成功！")

    # 自动同步最近记录
    print("\n同步最近记录...")
    _sync_recent(client, count=5)

    # 刷新生理档案
    try:
        fetch_profile(client)
        print("生理档案已刷新")
    except Exception as e:
        print(f"生理档案获取失败: {e}")

    # 获取目标跑步记录
    if target_id:
        run = get_run(target_id)
        if not run:
            print(f"错误: 未找到跑步记录 {target_id}")
            return
    else:
        runs = get_recent_runs(1)
        if not runs:
            print("暂无跑步数据，请先运行 sync")
            return
        run = runs[0]

    label_id = run["label_id"]
    sport_type = run["sport_type"]
    summary = json.loads(run["summary_json"])
    evolab = json.loads(run["evolab_data"]) if run["evolab_data"] else None

    conn = get_db()
    try:
        hr_rows = conn.execute(
            "SELECT * FROM hr_zones WHERE label_id=?", (label_id,)
        ).fetchall()
    finally:
        conn.close()
    hr_zones = {r["zone_name"]: {"count": r["count"], "pct": r["pct"]} for r in hr_rows}

    # 加载生理档案
    profile = load_cached_profile()

    print(f"\n{'='*50}")
    print(f"  跑步分析: {run['start_time']}")
    print(f"  距离: {run['distance_km']}km | 配速: {run['pace_min_per_km']}/km "
          f"| 心率: {run['avg_hr_bpm']}bpm")
    print(f"{'='*50}\n")

    # FIT 下载 + 解析 + 逐秒指标计算
    ts_metrics = None
    fit_path = _get_or_download_fit(client, label_id, sport_type)
    if fit_path:
        try:
            print("  解析FIT逐秒数据...")
            fit_data = parse_fit(fit_path)
            ts_metrics = compute_all_metrics(fit_data["time_series"])
            print("  逐秒指标计算完成")
        except Exception as e:
            print(f"  FIT解析失败: {e}，降级使用仅概要分析")

    print("AI教练分析中...\n")
    result = analyze_single_run(summary, hr_zones, profile, evolab, ts_metrics)
    print(result)


def cmd_report():
    ensure_api_key()
    trends = get_trends()
    recent = get_recent_runs(30)

    # 加载生理档案
    profile = load_cached_profile()

    print(f"\n{'='*50}")
    print(f"  跑步趋势报告")
    print(f"  总跑量: {trends.get('total_runs', 0)} 次")
    print(f"  平均距离: {trends.get('avg_distance_km', 0)} km")
    print(f"  平均配速: {trends.get('avg_pace_min_per_km', 0)} /km")
    print(f"  最佳配速: {trends.get('best_pace', 'N/A')} /km")
    print(f"  最长距离: {trends.get('longest_run_km', 0)} km")
    print(f"{'='*50}\n")
    print("AI教练分析趋势中...\n")
    result = analyze_trends(trends, recent, profile)
    print(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("可用命令: sync, analyze [label_id], report")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "sync":
        cmd_sync()
    elif cmd == "analyze":
        target_id = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_analyze(target_id)
    elif cmd == "report":
        cmd_report()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: sync, analyze [label_id], report")
        sys.exit(1)
