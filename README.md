# COROS + AI 跑步教练

通过 COROS API 获取跑步数据，自动下载 FIT 文件进行逐秒深度分析，结合 Claude AI 提供专业级训练指导。

## 快速开始

```bash
pip install -r requirements.txt

# 设置环境变量（PowerShell）
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:COROS_EMAIL = "your-email"
$env:COROS_PASSWORD = "your-password"

# 使用
python main.py sync              # 同步跑步数据
python main.py analyze           # 深度分析最近一次跑步
python main.py analyze <id>      # 分析指定跑步
python main.py report            # 趋势报告
```

## 一条命令完成秒级深度分析

`python main.py analyze` 自动执行：

1. **自动同步** — 从 COROS 拉取最新记录入库
2. **FIT 下载** — 下载原始 FIT 文件（`data/fit/<id>.fit`），缓存复用
3. **逐秒解析** — 解析 FIT 获取每一秒的配速、心率、步频、海拔
4. **深度指标计算** — 10 项专业跑步指标
5. **AI 分析** — 将具体数据喂给 AI 教练，给出可量化建议

FIT 下载失败时自动降级为汇总数据分析。

## 逐秒深度指标

| 指标 | 计算方法 | 说明 |
|------|---------|------|
| 每公里分段 | 累计距离积分 → 按 km 切片 | 每 km 的配速、心率、步频、爬升、配速波动 |
| 配速稳定性 | 逐秒配速标准差 + 变异系数(CV) | 整体 + 逐 km，评估配速控制能力 |
| 心率漂移 | 线性回归 HR vs 时间 | 漂移率(bpm/h) + R²，评估有氧耐力 |
| 步频统计 | 均值 + 标准差 + CV | 步频是否在理想区间(170-185spm) |
| 有氧解耦 | 前后半程心率/配速比差异 | 评估有氧效率稳定性 |
| 效率趋势 | 滑动窗口配速/心率比 | 起始 vs 结束效率变化 |
| 配速分布 | 按自定义配速区间分桶 | 间歇/阈值/中等/轻松/恢复的时间占比 |

配速区间基于该跑者实际水平：
- 间歇 <5:30/km | 阈值 5:30-6:30 | 中等 6:30-7:30 | 轻松 7:30-8:30 | 恢复 >8:30

## AI 教练 Prompt 设计

`ai_coach.py` 使用 Claude API，系统提示词定位为 NSCA-CSCS 级专业教练，所有建议必须可量化。分析维度：

1. 强度区间评估（基于 VO2max + 乳酸阈值心率）
2. 心率漂移与有氧能力（逐秒数据支撑）
3. 步频与跑姿效率（垂直振幅/触地时间 + 步频 CV）
4. 有氧解耦 + 效率趋势 + HRV + 恢复 → 训练建议
5. 伤病风险预警

趋势分析包含训练负荷趋势判断和 2-4 周周期化训练计划。

## 项目结构

| 文件 | 用途 |
|------|------|
| `main.py` | CLI 入口（sync/analyze/report） |
| `coros_client.py` | COROS Training Hub API 客户端（中国区） |
| `ai_coach.py` | Claude AI 教练（单次深度分析 + 趋势） |
| `run_metrics.py` | 逐秒深度指标计算 |
| `data_normalizer.py` | API 原始数据 → 标准化跑步摘要 |
| `run_db.py` | SQLite 本地存储与趋势统计 |
| `fit_parser.py` | Garmin FIT 文件解析（逐秒序列） |
| `profile_client.py` | 生理档案获取（VO2max/HRV/LTHR） |

## COROS API 说明

`coros_client.py` 封装了 COROS Training Hub 中国区 API (`teamcnapi.coros.com`)：

- `login()` — MD5 密码登录，本地缓存 token（`data/.coros_token`）
- `get_recent_runs()` — 获取最近跑步列表
- `get_activity_detail()` — 获取单次活动详细 lap 数据
- `get_evolab()` — 获取 EvoLab 分析（训练负荷/VO2max）
- `download_fit()` — 下载 FIT 原始文件

## 数据隐私

所有个人数据存储在 `data/` 目录，已通过 `.gitignore` 排除：

```
data/runs.db          # SQLite 跑步数据库
data/fit/*.fit        # FIT 原始文件缓存
data/.coros_token     # COROS 登录 token
data/.profile         # 生理档案缓存
```
