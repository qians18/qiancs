"""
COROS + AI 跑步教练 —— CLI入口
用法:
  python main.py sync    同步最近跑步数据
  python main.py analyze  分析最近一次跑步
  python main.py report   趋势报告
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


def cmd_analyze():
    ensure_api_key()
    runs = get_recent_runs(1)
    if not runs:
        print("暂无跑步数据，请先运行 sync")
        return

    run = runs[0]
    summary = json.loads(run["summary_json"])
    evolab = json.loads(run["evolab_data"]) if run["evolab_data"] else None

    conn = get_db()
    hr_rows = conn.execute(
        "SELECT * FROM hr_zones WHERE label_id=?", (run["label_id"],)
    ).fetchall()
    conn.close()
    hr_zones = {r["zone_name"]: {"count": r["count"], "pct": r["pct"]} for r in hr_rows}

    # 加载生理档案
    profile = load_cached_profile()

    print(f"\n{'='*50}")
    print(f"  跑步分析: {run['start_time']}")
    print(f"  距离: {run['distance_km']}km | 配速: {run['pace_min_per_km']}/km "
          f"| 心率: {run['avg_hr_bpm']}bpm")
    print(f"{'='*50}\n")
    print("AI教练分析中...\n")
    result = analyze_single_run(summary, hr_zones, profile, evolab)
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
        print("可用命令: sync, analyze, report")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "sync":
        cmd_sync()
    elif cmd == "analyze":
        cmd_analyze()
    elif cmd == "report":
        cmd_report()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: sync, analyze, report")
        sys.exit(1)
