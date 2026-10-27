"""查看已落盘的事件日志。

用法：
    python tools/query_events.py                      # 最近 20 条
    python tools/query_events.py --limit 100
    python tools/query_events.py --out out           # 指定日志目录
    python tools/query_events.py --json               # 输出原始 JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fallwatch import config  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="查看跌倒事件日志")
    parser.add_argument("--out", default=config.DEFAULT_OUT_DIR, help="日志目录")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="输出原始 JSON 行")
    args = parser.parse_args(argv)

    db_path = os.path.join(args.out, "events.db")
    jsonl_path = os.path.join(args.out, "events.jsonl")

    if not os.path.exists(db_path):
        print(f"[提示] 找不到 {db_path}")
        if os.path.exists(jsonl_path):
            print(f"       改用 JSONL: {jsonl_path}\n")
            with open(jsonl_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-args.limit:]
            for line in lines:
                print(line.rstrip())
            return 0
        print("       还没有任何事件记录。先跑一次判定模式。")
        return 1

    if args.json:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[-args.limit:]:
                print(line.rstrip())
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT event_id, ts, video_time, conf, track_id, scene_index,
               fall_frames, window_frames, duration_ms, trace, snapshot
        FROM events ORDER BY ts DESC LIMIT ?
        """,
        (args.limit,),
    ).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"{db_path}  累计事件 {total} 条，显示最近 {len(rows)} 条\n")

    if not rows:
        print("（尚无记录）")
        return 0

    for r in rows:
        trace = r["trace"]
        try:
            trace = " -> ".join(json.loads(trace))
        except Exception:
            pass
        print(f"[{r['event_id']}] {r['ts']}")
        print(f"    视频时刻 {r['video_time']}s  置信度 {r['conf']}  "
              f"轨迹#{r['track_id']}  片段#{r['scene_index']}")
        print(f"    窗口 {r['window_frames']} 帧 / falldown {r['fall_frames']} 帧 / "
              f"持续 {r['duration_ms']} ms")
        print(f"    轨迹: {trace}")
        print(f"    抓拍: {r['snapshot']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
