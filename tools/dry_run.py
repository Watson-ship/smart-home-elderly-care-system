"""独立标定工具：分析一段视频里模型输出的置信度分布，用来定 --conf-min。

比 cli 的 --dry-run 多一件事：把每个类别的置信度分布和"你肉眼数的跌倒次数"
做对照，并直接给出参数建议。

用法：
    python tools/dry_run.py "C:\\path\\video.mp4"
    python tools/dry_run.py "C:\\path\\video.mp4" --truth 50
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fallwatch import config  # noqa: E402
from fallwatch.detector import Detector  # noqa: E402


def quantile(values, p):
    if not values:
        return 0.0
    return values[min(len(values) - 1, int(len(values) * p))]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="模型置信度分布标定工具")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--model", default=config.DEFAULT_MODEL)
    parser.add_argument("--imgsz", type=int, default=config.IMGSZ)
    parser.add_argument("--detect-conf", type=float, default=0.05,
                        help="故意放宽，为了看到完整分布")
    parser.add_argument("--truth", type=int, default=0,
                        help="你肉眼数出的这段视频里跌倒次数，用于估召回")
    parser.add_argument("--every", type=int, default=1, help="每 N 帧推理一次")
    parser.add_argument("--limit", type=int, default=0, help="只分析前 N 帧")
    args = parser.parse_args(argv)

    if not os.path.exists(args.video):
        print(f"[错误] 找不到视频: {args.video}")
        return 2

    detector = Detector(
        model_path=args.model, imgsz=args.imgsz, conf=args.detect_conf, device="cpu"
    )
    print(f"模型类别: {detector.names}")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[错误] 无法打开视频: {args.video}")
        return 2

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1 or fps > 240:
        fps = 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    print(f"fps={fps:.3f}  总帧数={total}  时长约 {total / fps:.1f} 秒")
    print("-" * 72)

    conf_hist = defaultdict(list)   # 类别 -> 该类别最高框的置信度
    per_frame_cls = []              # 每帧主类别，用于数"疑似跌倒次数"
    fall_runs = 0                   # falldown 连续段数（粗略估计跌倒次数）
    prev_fall = False

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if args.limit and idx > args.limit:
            break

        if args.every > 1 and idx % args.every != 0:
            continue

        dets = detector.infer(frame)
        if dets:
            top = dets[0]
            conf_hist[top.cls_name].append(top.conf)
            per_frame_cls.append(top.cls_name)
            is_fall = detector.is_fall(top.cls_name)
        else:
            per_frame_cls.append(None)
            is_fall = False

        if is_fall and not prev_fall:
            fall_runs += 1
        prev_fall = is_fall

        if idx % 200 == 0:
            print(f"  {idx}{f'/{total}' if total else ''} ...", flush=True)

    cap.release()

    print("-" * 72)
    print(f"分析帧数: {len(per_frame_cls)}")

    print("\n各主类别出现帧数:")
    for name, cnt in Counter(per_frame_cls).most_common():
        pct = 100.0 * cnt / max(1, len(per_frame_cls))
        print(f"  {str(name):>12s} : {cnt:6d} 帧 ({pct:5.1f}%)")

    if not conf_hist:
        print("\n没有检出任何目标。可再降低 --detect-conf，或检查视频内容。")
        return 0

    print(f"\n{'类别':>12s} {'n':>7s} {'min':>6s} {'p10':>6s} {'p25':>6s} "
          f"{'中位':>6s} {'p75':>6s} {'max':>6s}")
    for name, confs in sorted(conf_hist.items(), key=lambda kv: -len(kv[1])):
        confs = sorted(confs)
        print(f"  {name:>12s} {len(confs):7d} {confs[0]:6.3f} "
              f"{quantile(confs, .10):6.3f} {quantile(confs, .25):6.3f} "
              f"{quantile(confs, .50):6.3f} {quantile(confs, .75):6.3f} "
              f"{confs[-1]:6.3f}")

    print(f"\n检测到 falldown 的连续段数（粗略估计跌倒次数）: {fall_runs}")
    if args.truth:
        recall_hint = min(1.0, fall_runs / args.truth) if args.truth else 0.0
        print(f"你提供的真实跌倒次数: {args.truth}")
        print(f"粗略召回估计: {recall_hint:.2%}")
        if recall_hint < 0.7:
            print("  ⚠ 召回偏低。模型对这段素材覆盖不足，问题在模型而非阈值：")
            print("    可尝试降低 --detect-conf、调低 --conf-min，或换更合适的素材/模型。")

    fall_like = [k for k in conf_hist if "fall" in k.lower()]
    if fall_like:
        name = fall_like[0]
        confs = sorted(conf_hist[name])
        med, p25 = quantile(confs, .50), quantile(confs, .25)
        print("\n参数建议:")
        print(f"  falldown 中位 {med:.3f} / p25 {p25:.3f}")
        print(f"  --conf-min 建议 {max(0.05, p25 * 0.85):.2f} ~ {med * 0.9:.2f}")

        for other in ("sitting", "standing", "walking"):
            if conf_hist.get(other):
                ocs = sorted(conf_hist[other])
                print(f"  {other} 中位 {quantile(ocs, .50):.3f}")
        if conf_hist.get("sitting"):
            sit_med = quantile(sorted(conf_hist["sitting"]), .50)
            if abs(sit_med - med) < 0.15:
                print("  ⚠ sitting 与 falldown 置信度接近，坐姿易误判；")
                print("    建议保留转换要求（不要加 --no-require-transition）。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
