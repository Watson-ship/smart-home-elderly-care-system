"""命令行入口。

用法示例见 README.md。最常用的三条：

    # 1) 标定：只看模型输出分布，不判事件
    python -m fallwatch.cli --dry-run --source "C:\\path\\video.mp4"

    # 2) 跑视频，判定并落日志
    python -m fallwatch.cli --source "C:\\path\\video.mp4"

    # 3) 摄像头实时
    python -m fallwatch.cli --source 0 --every 3 --preview
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional

import cv2
import numpy as np

from . import config
from .detector import Detector
from .logger import EventLogger
from .state_machine import FallStateMachine


# ================================================================ 参数


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fallwatch",
        description="单机跌倒检测与日志系统（笔记本摄像头 / 视频文件）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument("--source", default="0",
                   help="视频文件路径，或摄像头序号（0 表示默认摄像头）")
    p.add_argument("--model", default=config.DEFAULT_MODEL, help="模型权重路径")
    p.add_argument("--out", default=config.DEFAULT_OUT_DIR, help="输出目录")
    p.add_argument("--imgsz", type=int, default=config.IMGSZ, help="推理输入尺寸")
    p.add_argument("--every", type=int, default=config.INFER_EVERY_N,
                   help="每 N 帧推理一次；离线视频建议 1，摄像头建议 3")
    p.add_argument("--device", default="cpu", help="cpu 或 cuda")
    p.add_argument("--detect-conf", type=float, default=config.DETECT_CONF,
                   help="送进状态机的检测置信度下限")

    p.add_argument("--conf-min", type=float, default=config.CONF_MIN,
                   help="falldown 置信度门槛")
    p.add_argument("--window", type=float, default=config.WINDOW_SEC,
                   help="判定窗口时长（秒）")
    p.add_argument("--fall-frames", type=int, default=config.FALL_FRAMES_MIN,
                   help="窗口内 falldown 观测数下限；防抖动建议 15~25")
    p.add_argument("--debounce", type=int, default=config.DEBOUNCE_FRAMES,
                   help="类别多数表决帧数，压制 Falldown/Sitting 横跳；1 表示关闭")
    p.add_argument("--cooldown", type=float, default=config.COOLDOWN_SEC,
                   help="同类事件全局冷却（秒）")

    p.add_argument("--require-transition", dest="require_transition",
                   action="store_true", default=config.REQUIRE_TRANSITION,
                   help="要求窗口内存在活动类（由站到倒的转换）")
    p.add_argument("--no-require-transition", dest="require_transition",
                   action="store_false",
                   help="关闭转换要求，提高召回（合集视频建议先这样跑）")

    p.add_argument("--scene-cut", type=float, default=config.SCENE_CUT_DIFF,
                   help="场景切换相似度阈值；设 -1 关闭")
    p.add_argument("--no-scene-cut", dest="scene_cut", action="store_const", const=None,
                   help="完全关闭场景切换检测")

    p.add_argument("--dry-run", action="store_true",
                   help="只统计模型输出分布，不判定事件、不写日志")
    p.add_argument("--save-annotated", default=None,
                   help="把带检测框的视频写到该路径（仅视频源有效）")
    p.add_argument("--preview", action="store_true",
                   help="实时弹窗预览（按 q 退出）")
    p.add_argument("--no-snapshot", dest="save_snapshot", action="store_false",
                   default=config.SAVE_SNAPSHOT, help="关闭抓拍")
    p.add_argument("--limit-frames", type=int, default=0,
                   help="只处理前 N 帧（0 表示全部），调试用")
    p.add_argument("--seek", type=float, default=0.0,
                   help="视频起始秒数，跳到指定位置开始")
    p.add_argument("--quiet", action="store_true", help="少打日志，只报事件")

    return p


def is_camera_source(source: str) -> bool:
    """'0' / '1' 之类当作摄像头序号。"""

    return source.isdigit()


# ================================================================ 主流程


def run(args: argparse.Namespace) -> int:
    # 命令行覆盖 config
    config.DETECT_CONF = args.detect_conf
    config.SAVE_SNAPSHOT = args.save_snapshot
    config.DRAW_BOXES = True

    source_is_cam = is_camera_source(args.source)

    # ------------------------------------------------ 打开输入
    cap_source = int(args.source) if source_is_cam else args.source
    if not source_is_cam and not os.path.exists(args.source):
        print(f"[错误] 找不到视频文件: {args.source}")
        return 2

    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        print(f"[错误] 无法打开输入源: {args.source}")
        if source_is_cam:
            print("       请检查摄像头是否被其他程序占用，或换一个序号（如 --source 1）")
        return 2

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1 or fps > 240:
        fps = 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if source_is_cam:
        total_frames = 0

    if args.seek > 0 and not source_is_cam:
        cap.set(cv2.CAP_PROP_POS_MSEC, args.seek * 1000.0)

    duration = (total_frames / fps) if total_frames else 0.0
    print("=" * 72)
    print(f"输入源    : {args.source}{'  (摄像头)' if source_is_cam else ''}")
    print(f"帧率      : {fps:.3f} fps")
    if total_frames:
        print(f"总帧数    : {total_frames}   时长约 {duration:.1f} 秒")
    print(f"模型      : {args.model}")
    print(f"推理设置  : imgsz={args.imgsz} 每 {args.every} 帧一次  device={args.device}")
    print(f"判定参数  : conf_min={args.conf_min} window={args.window}s "
          f"fall_frames>={args.fall_frames} cooldown={args.cooldown}s")
    print(f"转换要求  : {'开（误报少，可能漏报一开头就倒地的片段）' if args.require_transition else '关（召回高）'}")
    print(f"场景切换  : {'关闭' if args.scene_cut is None else f'阈值 {args.scene_cut}'}")
    print(f"模式      : {'DRY-RUN（只统计，不判定）' if args.dry_run else '判定模式'}")
    print("=" * 72)

    # ------------------------------------------------ 加载模型
    try:
        detector = Detector(
            model_path=args.model,
            imgsz=args.imgsz,
            conf=args.detect_conf,
            device=args.device,
        )
    except Exception as exc:
        print(f"[错误] 模型加载失败: {exc}")
        return 3

    print(f"模型类别  : {detector.names}")
    fall_names = [n for n in detector.names.values() if detector.is_fall(n)]
    if not fall_names:
        print("[错误] 模型里没有跌倒类，无法工作。请检查 config.FALL_CLASS_NAMES")
        return 3
    print(f"跌倒类    : {fall_names}")
    print("-" * 72)

    # ------------------------------------------------ 状态机 / 日志
    machine = FallStateMachine(
        conf_min=args.conf_min,
        window_sec=args.window,
        fall_frames_min=args.fall_frames,
        require_transition=args.require_transition,
        cooldown_sec=args.cooldown,
        debounce_frames=args.debounce,
        scene_cut_diff=args.scene_cut,
    )

    logger: Optional[EventLogger] = None
    if not args.dry_run:
        logger = EventLogger(args.out, source=str(args.source))

    # ------------------------------------------------ dry-run 统计容器
    conf_hist: Dict[str, List[float]] = defaultdict(list)
    frame_cls_counter: Counter = Counter()

    # ------------------------------------------------ 输出视频
    writer: Optional[cv2.VideoWriter] = None
    if args.save_annotated:
        if source_is_cam:
            print("[提示] 摄像头源无法预知尺寸，--save-annotated 将在首帧后开始写入")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    # ------------------------------------------------ 主循环
    frame_idx = 0
    processed = 0
    event_count = 0
    last_dets = []
    start_wall = time.time()
    t0 = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            frame_idx += 1
            if args.limit_frames and frame_idx > args.limit_frames:
                break

            # 时间戳：视频用帧号/FPS，摄像头用墙钟
            if source_is_cam:
                t = time.time() - start_wall + args.seek
            else:
                t = frame_idx / fps

            run_infer = (args.every <= 1) or (frame_idx % args.every == 1)

            if run_infer:
                detections = detector.infer(frame)
                last_dets = detections
                processed += 1

                if args.dry_run:
                    if detections:
                        top = detections[0]
                        conf_hist[top.cls_name].append(top.conf)
                        frame_cls_counter[top.cls_name] += 1
                    else:
                        frame_cls_counter["(无检测)"] += 1
            else:
                detections = last_dets

            # 状态机
            if args.dry_run:
                result = None
            else:
                result = machine.process(t, frame, detections, run_inference=run_infer)

                for event in result.events:
                    event_count += 1
                    wall_ts = time.time()

                    snapshot = None
                    if args.save_snapshot:
                        snapshot = logger.save_snapshot(frame, event, wall_ts)

                    rec = logger.log_event(
                        event, wall_ts=wall_ts, video_time=t, snapshot=snapshot
                    )

                    print(
                        f"\n[跌倒 #{event_count}] {rec['ts']}"
                        f"  视频时刻 {t:.2f}s"
                        f"  置信度 {event.conf:.2f}"
                        f"  轨迹#{event.track_id}"
                        f"  片段#{event.scene_index}\n"
                        f"           窗口 {event.window_frames} 帧 / "
                        f"falldown {event.fall_frames} 帧 / "
                        f"持续 {event.duration_ms} ms\n"
                        f"           轨迹: {' -> '.join(event.trace)}\n"
                        f"           抓拍: {snapshot or '(未保存)'}"
                    )

                if result.scene_cut and not args.quiet:
                    print(f"\n[场景切换] 视频时刻 {t:.2f}s -> 片段 #{machine.scene_index}，"
                          f"轨迹与冷却已清零")

                logger.log_frame_detail(time.time(), detections)

            # 绘制（只有需要看的时候才画，省一点 CPU）
            need_draw = args.preview or bool(args.save_annotated)
            annotated = detector.draw(frame.copy(), detections) if need_draw else frame
            if need_draw and not args.dry_run and result is not None:
                _draw_status(annotated, machine, event_count)

            # 进度
            if not args.quiet and frame_idx % 100 == 0:
                if total_frames:
                    pct = 100.0 * frame_idx / total_frames
                    speed = frame_idx / max(1e-6, time.time() - t0)
                    print(
                        f"  ... {frame_idx}/{total_frames} ({pct:5.1f}%) "
                        f"{speed:5.1f} fps  轨迹={machine.active_tracks}  "
                        f"事件={event_count}",
                        flush=True,
                    )
                else:
                    print(
                        f"  ... 已处理 {frame_idx} 帧  轨迹={machine.active_tracks}  "
                        f"事件={event_count}",
                        flush=True,
                    )

            # 输出视频
            if args.save_annotated:
                if writer is None:
                    h, w = annotated.shape[:2]
                    writer = cv2.VideoWriter(args.save_annotated, fourcc, fps, (w, h))
                writer.write(annotated)

            # 预览
            if args.preview:
                cv2.imshow("fall-watch", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("\n[提示] 用户按 q 退出")
                    break

    except KeyboardInterrupt:
        print("\n[提示] 收到 Ctrl+C，正在收尾……")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if args.preview:
            cv2.destroyAllWindows()

    elapsed = time.time() - t0
    print("\n" + "=" * 72)

    # ------------------------------------------------ dry-run 报告
    if args.dry_run:
        _print_dry_run_report(frame_cls_counter, conf_hist, processed, frame_idx, elapsed, fps)
    else:
        print(f"处理完成: {frame_idx} 帧（实际推理 {processed} 帧），耗时 {elapsed:.1f} 秒")
        print(f"检出跌倒事件: {event_count} 次")
        if logger is not None:
            stats = logger.statistics()
            print(f"事件日志(JSONL): {stats.get('jsonl')}")
            print(f"事件日志(SQLite): {stats.get('db')}")
            print(f"数据库内累计事件数: {stats.get('event_count')}")
            if stats.get("event_count"):
                print(f"置信度 平均 {stats.get('avg_conf')} / 最高 {stats.get('max_conf')}")
            logger.close()

    if args.save_annotated and writer is not None:
        print(f"标注视频: {args.save_annotated}")

    print("=" * 72)
    return 0


def _draw_status(frame: np.ndarray, machine: FallStateMachine, event_count: int) -> None:
    """左上角叠加运行状态。"""

    lines = [
        f"片段 #{machine.scene_index}",
        f"轨迹 {machine.active_tracks}",
        f"事件 {event_count}",
    ]
    y = 22
    for line in lines:
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
        y += 24


def _print_dry_run_report(
    frame_cls: Counter,
    conf_hist: Dict[str, List[float]],
    processed: int,
    total: int,
    elapsed: float,
    fps: float,
) -> None:
    """dry-run 报告：给出定阈值所需的分布信息。"""

    print("DRY-RUN 报告（不判定事件，只看模型输出）")
    print("-" * 72)
    print(f"处理帧数: {total}（实际推理 {processed} 帧），耗时 {elapsed:.1f} 秒")
    if not total:
        print("没有读到任何帧。")
        return

    if fps:
        print(f"视频时长约 {total / fps:.1f} 秒")

    print("\n各主类别出现帧数（每帧取置信度最高的一个框）:")
    for name, cnt in frame_cls.most_common():
        pct = 100.0 * cnt / total
        print(f"  {name:>12s} : {cnt:6d} 帧  ({pct:5.1f}%)")

    if not conf_hist:
        print("\n没有检出任何目标。可能原因：视频分辨率/角度不合适，")
        print("或 detect-conf 过高。可尝试 --detect-conf 0.05 再看一次。")
        return

    print("\n各类别置信度分布（用于确定 --conf-min）:")
    print(f"  {'类别':>12s} {'n':>7s} {'min':>6s} {'p25':>6s} {'中位':>6s} "
          f"{'p75':>6s} {'max':>6s}")
    for name, confs in sorted(conf_hist.items(), key=lambda kv: -len(kv[1])):
        confs = sorted(confs)

        def q(p: float) -> float:
            return confs[min(len(confs) - 1, int(len(confs) * p))]

        print(f"  {name:>12s} {len(confs):7d} {confs[0]:6.2f} {q(.25):6.2f} "
              f"{q(.5):6.2f} {q(.75):6.2f} {confs[-1]:6.2f}")

    # 给出建议
    fall_like = [k for k in conf_hist if "fall" in k.lower()]
    if fall_like:
        name = fall_like[0]
        confs = sorted(conf_hist[name])
        median = confs[len(confs) // 2]
        p25 = confs[len(confs) // 4]
        print("\n建议:")
        print(f"  falldown 中位置信度 = {median:.2f}，p25 = {p25:.2f}")
        print(f"  建议 --conf-min 取 {(p25 * 0.9):.2f} ~ {(median * 0.9):.2f} 之间，")
        print("  具体看你是更怕漏报（取低）还是更怕误报（取高）。")

        if "sitting" in conf_hist and conf_hist["sitting"]:
            sit = sorted(conf_hist["sitting"])
            sit_med = sit[len(sit) // 2]
            if abs(sit_med - median) < 0.15:
                print(f"  ⚠ sitting 中位置信度 {sit_med:.2f} 与 falldown 接近，")
                print("    坐姿很可能被误判为跌倒 —— 建议开启转换要求")
                print("    （去掉 --no-require-transition）。")
    else:
        print(f"\n⚠ 没检出任何 falldown。实际检出的类别: {list(conf_hist)}")
        print("  请确认模型类别与 config.FALL_CLASS_NAMES 是否一致。")


# ================================================================ 入口


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.scene_cut is not None and args.scene_cut < 0:
        args.scene_cut = None

    try:
        return run(args)
    except Exception as exc:  # pragma: no cover
        print(f"[错误] 运行失败: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
