# fall-watch · 跌倒识别与截图（C 部分）

> **归档说明**：本文是原 `fall-watch` 项目的 README，模块现已并入
> `smart-home-elderly-care-system` 根目录。文中 `fall-watch/` 前缀请忽略；
> `model/best.pt` 已随主仓库提供，`out/` 为运行时自动生成。
> 最新的安装/运行方式以根目录 [README.md](../../README.md) 的「跌倒检测模块」一节为准。

「居家老人监测系统」的 AI 识别模块：读视频文件或摄像头 → YOLOv8 识别人体动作 → 状态机确认跌倒 → 写事件 + 存截图。
后端（`smart-home-elderly-care-system`）的 `alert` 表拿这里的事件和截图生成告警，推送给家属 / 社康。

## 目录

```
smart-home-elderly-care-system/     ← 原 fall-watch/ 的内容现在都在项目根目录
├── app.py                 PyCharm 里直接右键运行（会自己处理相对导入和工作目录）
├── run.cmd                命令行启动器（自动用 .venv 里的 Python，UTF-8 不乱码）
├── 1-标定.cmd             只看模型输出分布，不判事件（调 --conf-min 用）
├── 2-跑视频.cmd           跑一个视频并判定跌倒
├── 3-看日志.cmd           查 out/events.db 里已记录的事件
├── fallwatch/
│   ├── config.py          所有阈值集中在这里，改判定灵敏度只改这个文件
│   ├── detector.py        YOLOv8 推理封装：图片 → Detection 列表
│   ├── state_machine.py   跌倒状态机（窗口内帧数 + 置信度 + 防抖 + 冷却 + 场景切换）
│   ├── logger.py          事件落库：SQLite(out/events.db) + JSONL + 截图
│   └── cli.py             命令行主流程
├── tools/                 辅助脚本（dry_run / fetch_model / query_events）
├── model/                 权重目录（best.pt 已随主仓库提供）
└── out/                   运行时产物（不入库）
```

## 快速开始

1. **模型权重**：`model/best.pt`（约 22 MB）已随主仓库提供；如被删除，可执行 `python tools/fetch_model.py` 重新下载。
2. **装依赖**：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt        # ultralytics 会自动带 torch / opencv
   ```
3. **跑一个视频**：
   ```bash
   run.cmd -m fallwatch.cli --source "D:\videos\test.mp4"
   ```
   或者用 PyCharm 右键 `app.py` → Run，参数填在 Run 配置的 Parameters 里。
4. **看结果**：`out/events.jsonl`（一行一个事件）、`out/snapshots/*.jpg`（命中时的截图）、`3-看日志.cmd`。

## 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--source` | `0` | 视频路径，或摄像头序号（`0` = 默认摄像头） |
| `--conf-min` | `0.45` | falldown 置信度门槛，调高更严 |
| `--fall-frames` | 见 config | 窗口内 falldown 观测数下限，调高更不容易误报 |
| `--window` | `3.0` | 判定窗口（秒） |
| `--debounce` | 见 config | 连续多少帧才确认，防抖 |
| `--cooldown` | 见 config | 一次告警后的冷却秒数，防重复推送 |
| `--every` | `1` | 每 N 帧推理一次；摄像头实时建议 `3` 省 CPU |
| `--device` | `cpu` | 有显卡可改 `cuda` |
| `--dry-run` | — | 只打检测分布、不判事件（标定阈值用） |
| `--preview` | — | 实时显示画面 |
| `--no-snapshot` | — | 不存截图 |

先用 `1-标定.cmd` 在真实场景视频上跑一遍，看 falldown 的置信度分布，再定 `--conf-min` 和 `--fall-frames`。

## 事件格式（给后端同学）

`out/events.jsonl` 每行一个 JSON，关键字段：

```json
{
  "event_id": "E00001",
  "ts": "2026-10-25T15:10:13.482+08:00",
  "type": "fall",
  "conf": 0.87,
  "track_id": 3,
  "source": "D:\\videos\\test.mp4",
  "fall_frames": 21,
  "window_frames": 45,
  "window_span": 2.98,
  "duration_ms": 812,
  "snapshot": "out/snapshots/20261025T151013_E00001.jpg"
}
```

`out/events.db` 是同内容的 SQLite（`events` 表 + `frames` 表），方便直接 SQL 查。

## 和后端怎么接（现阶段）

两种方式，选一种即可，推荐第二种：

1. **松耦合（现在就能用）**：后端起一个定时任务，读 `out/events.jsonl` 的新增行 → 调 `POST /alerts` 生成告警，`snapshot` 字段指向截图路径。
2. **紧耦合（贴合课程设计的目录）**：把 `detector.py` 的 `Detector.infer()` 包一层，放到后端的 `infrastructure/ai/inference.py`，对外只暴露「输入一帧 → 是否跌倒」；`domains/alert/service.py` 直接调用它，符合文档里「domains 可以调 infrastructure，反过来不行」的规则。

## 说明

- 本模块当前是**独立进程 + 独立 SQLite**，不碰后端的 MySQL；后端只认事件字段，不认这里的库。
- 权重、`out/`、`.venv/`、`.idea/` 都不入库；并入主仓库后，`model/best.pt` 已随仓库提供，方便队友直接运行。
