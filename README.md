# COROS + AI 跑步教练

通过 COROS API 获取跑步数据，结合 Claude AI 提供专业训练分析。

## 快速开始

```bash
pip install -r requirements.txt
python main.py sync     # 同步跑步数据
python main.py analyze  # AI 分析最近一次跑步
python main.py report   # 趋势报告
```

## 环境变量

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:COROS_EMAIL = "your-email"
$env:COROS_PASSWORD = "your-password"
```

## 项目结构

| 文件 | 用途 |
|------|------|
| `main.py` | CLI 入口 |
| `coros_client.py` | COROS Training Hub API 客户端（中国区） |
| `ai_coach.py` | Claude AI 教练分析（单次+趋势） |
| `data_normalizer.py` | API 原始数据 → 标准化跑步摘要 |
| `run_db.py` | SQLite 本地存储与趋势统计 |
| `fit_parser.py` | Garmin FIT 文件解析 |
| `profile_client.py` | 生理档案获取（VO2max/HRV/LTHR） |

## COROS API 说明

`coros_client.py` 封装了 COROS Training Hub 中国区 API (`teamcnapi.coros.com`)：

- `login()` — MD5 密码登录，本地缓存 token
- `list_activities()` — 按日期范围查询活动列表
- `get_activity_detail()` — 获取单次活动详细 lap 数据
- `get_evolab()` — 获取 EvoLab 分析（训练负荷/VO2max）
- `download_fit()` — 下载 FIT 原始文件

## AI 教练 Prompt 设计

`ai_coach.py` 使用 Claude API，系统提示词定位为 NSCA-CSCS 级专业教练，要求输出可量化建议。分析维度：

1. 强度区间评估（基于 VO2max + 乳酸阈值心率）
2. 心率-配速匹配度与心率漂移
3. 跑姿效率（步频/垂直振幅/触地时间）
4. HRV + 恢复状态 → 下一步训练建议
5. 伤病风险预警

趋势分析额外包含训练负荷趋势判断和 2-4 周周期化训练计划。

## 数据隐私

个人数据（token/跑步记录/生理档案）存储在 `data/`，已通过 `.gitignore` 排除。
