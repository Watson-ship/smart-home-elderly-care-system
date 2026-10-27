"""集中配置。所有可调阈值都在这里，改这个文件即可，不用动逻辑代码。

来源说明：FALL_CLASS_NAMES / ACTIVITY_CLASS_NAMES 的取值来自 lyh 仓库的
rk3588lyh/model/coco_80_labels_list.txt（内容是 falldown / sitting / standing / walking），
并与 convert/yolov8s_humanaction_250/args.yaml 的训练配置（4 类，250 epochs，imgsz 640）一致。
运行时仍以权重内嵌的 model.names 为准，这里只做交叉校验。
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------- 路径

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "model")
DEFAULT_MODEL = os.path.join(MODEL_DIR, "best.pt")
LABELS_FILE = os.path.join(MODEL_DIR, "labels.txt")
DEFAULT_OUT_DIR = os.path.join(BASE_DIR, "out")

# ---------------------------------------------------------------- 模型推理

IMGSZ = 640

# 推理用的最低置信度。比 CONF_MIN 低一些，让状态机能看到更多候选框，
# 真正的判定门槛由 CONF_MIN 把关。
DETECT_CONF = 0.15

# 每 N 帧推理一次。离线跑视频建议 1（全帧，最准）；摄像头实时建议 3（省 CPU）。
# 注意：状态机按真实时间戳统计，不按帧号，所以跳帧不会破坏时间逻辑。
INFER_EVERY_N = 1

# 检测框最小面积占比，过滤掉噪声小框
MIN_BOX_AREA_RATIO = 0.0008

# ---------------------------------------------------------------- 类别

# 跌倒类（触发源）
FALL_CLASS_NAMES = {"falldown", "fall", "fallen", "fall_down"}

# 活动类（用于"由站到倒"的转换判定）
ACTIVITY_CLASS_NAMES = {"sitting", "standing", "walking", "sit", "stand", "walk"}

# ---------------------------------------------------------------- 判定阈值

# falldown 置信度门槛
CONF_MIN = 0.45

# 判定窗口时长（秒）。窗口内所有观测参与判定。
WINDOW_SEC = 3.0

# 窗口内 falldown 观测数下限
FALL_FRAMES_MIN = 3

# 是否要求窗口内出现过活动类（"由站到倒"的转换）。
# True  -> 误报大幅减少，但对"一开头就已经倒地"的片段会漏报
# False -> 召回高，但静止误判（坐/躺被认成跌倒）会报出来
# 建议：先用 False 把链路跑通并数清告警次数，再打开对比误报。
REQUIRE_TRANSITION = True

# 类别平滑（多数表决）帧数。模型经常在同一段动作里反复横跳
# （Falldown -> Sitting -> Falldown），导致一次跌倒被切成很多短段。
# 取最近 N 帧的多数类别作为"当前类别"，能显著减少抖动。
# 设 1 表示关闭平滑（完全信任单帧结果）。
# 30fps 素材建议 5~9（约 0.17~0.3 秒）。
DEBOUNCE_FRAMES = 5

# 同类事件冷却时间（秒）。
# 常规场景 30；跑"50种摔倒方式"这类剪辑合集时建议 5，
# 或者靠 SCENE_CUT_DIFF 做场景切换清零（两种手段可叠加）。
COOLDOWN_SEC = 30.0

# ---------------------------------------------------------------- 轨迹跟踪

# 两个框的 IoU 超过此值即认为是同一个人的前后帧
IOU_MATCH_THRESHOLD = 0.30

# 轨迹存活时间（秒）：超过这么久没被匹配上就丢弃
TRACK_TTL_SEC = 2.0

# 轨迹被匹配多少帧后才有资格触发告警，避免噪声框凭空造出事件
TRACK_MIN_HITS = 3

# 同一个人两次告警之间的最小间隔（秒）。防止一次跌倒被拆成多次。
PER_TRACK_ALERT_COOLDOWN_SEC = 20.0

# 告警后，连续多少帧不再是 falldown 才允许该轨迹再次告警
PER_TRACK_RESET_FRAMES = 10

# ---------------------------------------------------------------- 场景切换检测

# 合集/剪辑视频用。帧直方图相似度低于此值 -> 判定为场景切换，
# 清空所有轨迹和冷却，让新片段能立即独立判定。
# 设成 None 可关闭该功能。
SCENE_CUT_DIFF = 0.55

# 场景切换后的短暂静默（秒），丢掉切换瞬间的糊帧
SCENE_CUT_BLANK_SEC = 0.3

# 参与直方图比较的缩略图尺寸（越小越快）
SCENE_CUT_THUMB = 64

# ---------------------------------------------------------------- 抓拍

# 触发的瞬间是否抓拍一张图
SAVE_SNAPSHOT = True

# JPEG 质量
SNAPSHOT_QUALITY = 85

# 抓拍图在事件时刻往前推多少秒取帧（0 = 用当前帧）
SNAPSHOT_BACK_SEC = 0.0

# ---------------------------------------------------------------- 日志

# 是否写 JSONL
LOG_JSONL = True

# 是否写 SQLite
LOG_SQLITE = True

# 是否记录每一帧的检测明细（调试用；数据量增长很快，默认关闭）
LOG_FRAME_DETAIL = False

# ---------------------------------------------------------------- 绘制

DRAW_BOXES = True

# 各状态的颜色（BGR）
COLOR_FALL = (0, 0, 255)      # 红
COLOR_ACTIVITY = (0, 200, 0)  # 绿
COLOR_OTHER = (200, 200, 0)   # 青
COLOR_TEXT = (255, 255, 255)
