"""事件落盘：JSONL + SQLite 双写，外加抓拍图。

两条通道各有用处：
  JSONL  —— 追加写、永不改，适合 cat / jq 直接看，进程崩了也不丢
  SQLite —— 便于按时间范围查询、统计、后续接界面

抓拍图落盘刻意用 imencode + tofile，不用 cv2.imwrite：
后者在 Windows 上遇到非 ASCII 路径会静默失败（lyh 的 fall_detector.py 就用了
cv2.imwrite 写 app/static/img/alerts/，路径带中文时同样有风险）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from . import config
from .state_machine import FallEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,       -- ISO8601，带时区
    video_time    REAL,                -- 相对视频起点的秒数
    type          TEXT NOT NULL,
    conf          REAL,
    track_id      INTEGER,
    source        TEXT,
    scene_index   INTEGER,
    fall_frames   INTEGER,
    window_frames INTEGER,
    window_span   REAL,
    duration_ms   INTEGER,
    trace         TEXT,
    snapshot      TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS frames (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT,
    source    TEXT,
    cls_name  TEXT,
    conf      REAL,
    box       TEXT
);
"""


def local_iso(ts: Optional[float] = None) -> str:
    """本地时区的 ISO8601 字符串。"""

    dt = datetime.fromtimestamp(ts if ts is not None else time.time())
    return dt.astimezone().isoformat(timespec="milliseconds")


class EventLogger:
    """线程安全的事件写入器。"""

    def __init__(
        self,
        out_dir: str = None,
        source: str = "unknown",
        *,
        write_jsonl: bool = None,
        write_sqlite: bool = None,
        write_frame_detail: bool = None,
    ) -> None:
        self.out_dir = out_dir or config.DEFAULT_OUT_DIR
        self.snapshot_dir = os.path.join(self.out_dir, "snapshots")
        self.source = source

        self.write_jsonl = config.LOG_JSONL if write_jsonl is None else write_jsonl
        self.write_sqlite = config.LOG_SQLITE if write_sqlite is None else write_sqlite
        self.write_frame_detail = (
            config.LOG_FRAME_DETAIL if write_frame_detail is None else write_frame_detail
        )

        os.makedirs(self.out_dir, exist_ok=True)
        if config.SAVE_SNAPSHOT:
            os.makedirs(self.snapshot_dir, exist_ok=True)

        self.jsonl_path = os.path.join(self.out_dir, "events.jsonl")
        self.db_path = os.path.join(self.out_dir, "events.db")

        self._lock = threading.Lock()
        self._jsonl_fp = None
        self._conn: Optional[sqlite3.Connection] = None
        self._conn_thread: Optional[int] = None
        self._conn_pid: int = os.getpid()
        self._conn_file: Optional[str] = None

        if self.write_jsonl:
            self._jsonl_fp = open(self.jsonl_path, "a", encoding="utf-8")

        if self.write_sqlite:
            self._ensure_conn()

    # ------------------------------------------------------------ 连接管理

    def _ensure_conn(self) -> sqlite3.Connection:
        """拿到一个可用的 SQLite 连接。

        注意：sqlite3 连接默认不能跨线程使用。如果本对象在别的线程里被调用，
        这里会重新建立连接，避免 "SQLite objects created in a thread can only be
        used in that same thread" 报错。
        """

        pid = os.getpid()
        tid = threading.get_ident()

        need_new = (
            self._conn is None
            or pid != self._conn_pid
            or tid != self._conn_thread
            or self._conn_file != self.db_path
        )

        if not need_new:
            try:
                self._conn.execute("SELECT 1")
            except Exception:
                need_new = True

        if need_new:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass

            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.executescript(SCHEMA)
            conn.commit()

            self._conn = conn
            self._conn_thread = tid
            self._conn_pid = pid
            self._conn_file = self.db_path

        return self._conn

    # ------------------------------------------------------------ 抓拍

    def save_snapshot(self, frame: np.ndarray, event: FallEvent, wall_ts: float) -> Optional[str]:
        """把帧存成 JPEG，返回相对路径。失败返回 None。"""

        if frame is None or frame.size == 0:
            return None

        name = f"{datetime.fromtimestamp(wall_ts).strftime('%Y%m%dT%H%M%S')}_{event.event_id}.jpg"
        abs_path = os.path.join(self.snapshot_dir, name)
        rel_path = os.path.join("snapshots", name)

        try:
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.SNAPSHOT_QUALITY]
            )
            if not ok:
                return None
            # 用 tofile 而不是 imwrite，规避 Windows 非 ASCII 路径问题
            buf.tofile(abs_path)
            return rel_path
        except Exception as exc:
            print(f"[警告] 抓拍保存失败: {exc}")
            return None

    # ------------------------------------------------------------ 写事件

    def log_event(
        self,
        event: FallEvent,
        *,
        wall_ts: float,
        video_time: Optional[float] = None,
        snapshot: Optional[str] = None,
    ) -> Dict[str, Any]:
        """落一条跌倒事件，返回写出去的记录。"""

        record: Dict[str, Any] = {
            "event_id": event.event_id,
            "ts": local_iso(wall_ts),
            "video_time": round(video_time, 3) if video_time is not None else None,
            "type": "fall_detected",
            "conf": round(event.conf, 4),
            "track_id": event.track_id,
            "source": self.source,
            "scene_index": event.scene_index,
            "fall_frames": event.fall_frames,
            "window_frames": event.window_frames,
            "window_span": round(event.window_span, 3),
            "duration_ms": event.duration_ms,
            "trace": event.trace,
            "snapshot": snapshot,
        }

        with self._lock:
            if self._jsonl_fp is not None:
                self._jsonl_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
                self._jsonl_fp.flush()

            if self.write_sqlite:
                conn = self._ensure_conn()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events
                    (event_id, ts, video_time, type, conf, track_id, source, scene_index,
                     fall_frames, window_frames, window_span, duration_ms, trace, snapshot)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record["event_id"],
                        record["ts"],
                        record["video_time"],
                        record["type"],
                        record["conf"],
                        record["track_id"],
                        record["source"],
                        record["scene_index"],
                        record["fall_frames"],
                        record["window_frames"],
                        record["window_span"],
                        record["duration_ms"],
                        json.dumps(record["trace"], ensure_ascii=False),
                        record["snapshot"],
                    ),
                )
                conn.commit()

        return record

    def log_frame_detail(self, wall_ts: float, detections) -> None:
        """记录每帧检测明细（默认关闭，数据量增长很快）。"""

        if not self.write_frame_detail or not self.write_sqlite or not detections:
            return

        with self._lock:
            conn = self._ensure_conn()
            conn.executemany(
                "INSERT INTO frames (ts, source, cls_name, conf, box) VALUES (?,?,?,?,?)",
                [
                    (
                        local_iso(wall_ts),
                        self.source,
                        d.cls_name,
                        float(d.conf),
                        json.dumps(list(d.box)),
                    )
                    for d in detections
                ],
            )
            conn.commit()

    # ------------------------------------------------------------ 查询

    def statistics(self) -> Dict[str, Any]:
        """本次运行的统计摘要（只统计本进程写过的事件）。"""

        stats: Dict[str, Any] = {
            "out_dir": self.out_dir,
            "jsonl": self.jsonl_path if self.write_jsonl else None,
            "db": self.db_path if self.write_sqlite else None,
        }

        if self.write_sqlite:
            try:
                conn = self._ensure_conn()
                cur = conn.execute("SELECT COUNT(*), AVG(conf), MAX(conf) FROM events")
                cnt, avg_conf, max_conf = cur.fetchone()
                stats["event_count"] = int(cnt or 0)
                stats["avg_conf"] = round(float(avg_conf), 4) if avg_conf else None
                stats["max_conf"] = round(float(max_conf), 4) if max_conf else None
            except Exception as exc:
                stats["error"] = str(exc)

        return stats

    def query_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """按时间倒序取事件，给命令行回顾用。"""

        if not self.write_sqlite:
            return []
        conn = self._ensure_conn()
        cur = conn.execute(
            """
            SELECT event_id, ts, video_time, conf, track_id, scene_index,
                   fall_frames, window_frames, duration_ms, trace, snapshot
            FROM events ORDER BY ts DESC LIMIT ?
            """,
            (limit,),
        )
        cols = [
            "event_id", "ts", "video_time", "conf", "track_id", "scene_index",
            "fall_frames", "window_frames", "duration_ms", "trace", "snapshot",
        ]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ------------------------------------------------------------ 收尾

    def close(self) -> None:
        with self._lock:
            if self._jsonl_fp is not None:
                try:
                    self._jsonl_fp.close()
                except Exception:
                    pass
                self._jsonl_fp = None
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __enter__(self) -> "EventLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
