"""定时任务: 设备掉线扫描 + 服药提醒扫描 + 媒体文件清理, 由 APScheduler 周期拉起。

Owner: Person A (阶段 2 的两个定时任务 + 阶段 3 的媒体清理)

暴露四个函数:
    sweep_offline_devices(timeout_seconds=120)  心跳超时 -> status='offline', 返回受影响台数
    scan_medicine_reminders(window_minutes=1)   到点的启用计划 -> 推送提醒, 返回推送条数
    cleanup_media(stream_days, video_days)      删除过期的跌倒截图/录像, 返回清理统计
    start_scheduler() / shutdown_scheduler()    在 main.py lifespan 里启动/关闭 APScheduler

设计要点:
    1. 每个任务自己开 Session(不共用请求的 session): 定时任务是独立线程,
       复用 Web 线程的 Session 会踩"session 已被别的线程使用"的坑。
    2. 任务里捕获所有异常: 一次数据库抖动不能让整个调度器停摆。
    3. 服药提醒按 (plan_id, 日期, 时分) 去重: 调度器每 60 秒跑一次,
       取时间范围是"最近 N 分钟", 不去重就会对同一剂药重复推送。
    4. 只提醒"启用(status=1)"的计划, 且当天已经确认过服药(medicine_record)的不再提醒;
       cycle='two_day'(隔天) 的计划按日期奇偶跳过一次。
    5. 媒体清理只删文件, 保留 alert / work_order 这些业务记录(历史要能查),
       但会把指向已删文件的 alert.screenshot_path 置空, 前端就不会显示裂图。
"""
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

import config.settings as settings
from infrastructure.push.notify import notify
from models import Alert, Device, MedicinePlan, MedicineRecord, User

# ---------------------------------------------------------------- 掉线扫描

def sweep_offline_devices(
    db: Session | None = None,
    timeout_seconds: int | None = None,
    now: datetime | None = None,
) -> int:
    """把心跳超时的设备置为 offline, 返回被置离线的台数。

    判定: status='online' 且 last_online_time 早于 (now - timeout_seconds)。
    last_online_time 为空但状态还是 online 的脏数据也一并置离线。
    db / now 只是给测试注入用, 正常调用不传。
    """
    from db import session as dbs

    own_session = db is None
    if own_session:
        db = dbs.SessionLocal()
    now = now or datetime.now()
    timeout = timeout_seconds if timeout_seconds is not None else settings.DEVICE_OFFLINE_TIMEOUT
    deadline = now - timedelta(seconds=timeout)

    try:
        stale = (
            db.query(Device)
            .filter(Device.status == "online")
            .filter(
                (Device.last_online_time == None)  # noqa: E711 SQLAlchemy 里要写 == None
                | (Device.last_online_time < deadline)
            )
            .all()
        )
        for device in stale:
            device.status = "offline"
            print(
                f"[定时任务] 设备心跳超时置离线: {device.device_sn} "
                f"last_online={device.last_online_time} (> {timeout}s)",
                flush=True,
            )
        db.commit()
        return len(stale)
    except Exception as exc:  # noqa: BLE001 定时任务不能把调度器带崩
        db.rollback()
        print(f"[定时任务] 掉线扫描失败: {exc}", flush=True)
        return 0
    finally:
        if own_session:
            db.close()


# ---------------------------------------------------------------- 服药提醒

# (plan_id, yyyy-mm-dd, HH:MM) -> 已推送, 防止 60 秒一次的轮询重复提醒
_fired_reminders: set[tuple[int, str, str]] = set()


def _should_skip_by_cycle(plan: MedicinePlan, today: date) -> bool:
    """cycle='two_day' 的计划隔天提醒一次: 用一年的第几天奇偶做判断。"""
    if (plan.cycle or "daily") != "two_day":
        return False
    return today.toordinal() % 2 == 1


def _minute_of_day(t: time) -> int:
    """把 time 折成"当天第几分钟"(0~1439), 忽略秒和微秒。"""
    return t.hour * 60 + t.minute


def _in_window(take: time, now: datetime, window_minutes: int) -> bool:
    """take_time 是否落在 [now - window_minutes, now] 这个分钟区间内。

    服药计划的时间只精确到分钟(前端填的就是 HH:MM), 所以这里按分钟比较:
    直接比 time 对象会因为秒/微秒截断出现"take_time 比 now 大 1 秒就不匹配"的漏提醒。
    """
    now_min = now.hour * 60 + now.minute
    take_min = _minute_of_day(take)
    start_min = now_min - max(window_minutes, 0)
    if start_min < 0:
        # 窗口跨过 00:00: 接受"今天凌晨到现在"以及"昨夜 23:xx"
        return take_min <= now_min or take_min >= 1440 + start_min
    return start_min <= take_min <= now_min


def scan_medicine_reminders(
    db: Session | None = None,
    now: datetime | None = None,
    window_minutes: int = 1,
) -> int:
    """扫描"到点该吃药"的计划并推送提醒, 返回推送条数。

    判定: status=1, take_time 落在 [now - window_minutes, now] 这个区间;
    当天已有 medicine_record 的不推; 隔天周期当天跳过; 同一剂药只推一次。
    推送对象: 该老人绑定的所有账号(老人本人 + 家属), 社康账号(elder_id 为空)不推。
    """
    from db import session as dbs

    own_session = db is None
    if own_session:
        db = dbs.SessionLocal()
    now = now or datetime.now()
    today = now.date()

    try:
        # 允许回溯 window_minutes 分钟, 避免调度器启动瞬间错过刚过点的那一剂
        plans = db.query(MedicinePlan).filter(MedicinePlan.status == 1).all()

        sent = 0
        for plan in plans:
            if plan.take_time is None:
                continue
            take = plan.take_time
            if not isinstance(take, time):  # 兼容 drive 返回字符串的极端情况
                continue
            if not _in_window(take, now, window_minutes):
                continue
            if _should_skip_by_cycle(plan, today):
                continue

            # 当天已经确认服药(已服/未服都算"已处理"), 不再提醒
            confirmed = (
                db.query(MedicineRecord)
                .filter(MedicineRecord.plan_id == plan.id)
                .filter(MedicineRecord.remind_date == today)
                .first()
            )
            if confirmed:
                continue

            key = (plan.id, today.isoformat(), take.strftime("%H:%M"))
            if key in _fired_reminders:
                continue

            title = "服药提醒"
            content = f"该服用「{plan.medicine_name}」了({take.strftime('%H:%M')})"
            receivers = (
                db.query(User).filter(User.elder_id == plan.elder_id).all()
            )
            if not receivers:
                # 没有账号可推也写一条日志, 方便核对"计划到点了但没人收"
                notify(None, title, content + f" [elder_id={plan.elder_id} 无绑定账号]")
                sent += 1
            for user in receivers:
                notify(user.id, title, content)
                sent += 1

            _fired_reminders.add(key)

        return sent
    except Exception as exc:  # noqa: BLE001 定时任务不能把调度器带崩
        print(f"[定时任务] 服药提醒扫描失败: {exc}", flush=True)
        return 0
    finally:
        if own_session:
            db.close()


def reset_reminder_cache() -> None:
    """清空"已推送"缓存(测试用)。"""
    _fired_reminders.clear()


# ---------------------------------------------------------------- 媒体清理

# 与 domains/device/service.py 的 STREAM_DIR / VIDEO_DIR 同一路径。
# 这里不 import domains(架构约束: infrastructure 不能被 domains 反向依赖), 所以自己拼。
STATIC_DIR = Path("static")
MEDIA_DIRS = {"stream": STATIC_DIR / "stream", "videos": STATIC_DIR / "videos"}
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".mp4", ".avi", ".mov", ".mkv"}


def _purge_dir(root: Path, cutoff: datetime, protected: set[Path] | None = None) -> tuple[int, int]:
    """删除 root 下修改时间早于 cutoff 的媒体文件, 返回 (文件数, 释放字节数)。

    protected: 绝对路径集合, 命中的文件一律不删(例如还没处置的告警截图)。
    """
    if not root.is_dir():
        return 0, 0

    count = 0
    freed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        if protected and path.resolve() in protected:
            continue
        try:
            stat = path.stat()
            if datetime.fromtimestamp(stat.st_mtime) >= cutoff:
                continue
            path.unlink()
            count += 1
            freed += stat.st_size
        except OSError as exc:
            print(f"[清理] 删除失败 {path}: {exc}", flush=True)

    # 顺手清掉空目录(static/stream/CAM-xxx 这种), 免得越积越多
    for sub in sorted(root.rglob("*"), reverse=True):
        if sub != root and sub.is_dir():
            try:
                sub.rmdir()
            except OSError:
                pass
    return count, freed


def cleanup_media(
    now: datetime | None = None,
    stream_days: int | None = None,
    video_days: int | None = None,
    db: Session | None = None,
    keep_unhandled: bool = True,
) -> dict:
    """删除过期的跌倒截图和录像文件, 返回清理统计。

    为什么需要: 一个摄像头每个时段都传录像 + 偶发跌倒截图, 不清理磁盘一周就满。
    策略(可用环境变量调整):
        static/stream/  跌倒截图   已处置的保留 7 天(MEDIA_STREAM_RETENTION_DAYS)
        static/videos/  录像片段   保留 3 天(MEDIA_VIDEO_RETENTION_DAYS)
        <=0 表示这一类不清理
    关键规则(keep_unhandled):
        **还没处置的告警, 它的截图一律不删**。因为这张图是待办证据,
        社康还没看/还没处理, 删了家属和社康就再也看不到事故现场了。
        只有"已处置"的告警截图才会按保留天数清理。
    只删文件, 保留 alert / work_order 业务记录(历史要能查);
    文件确实被删的告警, screenshot_path 置空, 前端据此显示"历史图片已清理"
    而不是一个裂图。

    实时画面不在这里: 它只存在内存里, 15 秒没人推就自然失效(domains/device/live.py)。
    """
    from db import session as dbs

    own_session = db is None
    if own_session:
        db = dbs.SessionLocal()
    now = now or datetime.now()
    stream_days = settings.MEDIA_STREAM_RETENTION_DAYS if stream_days is None else stream_days
    video_days = settings.MEDIA_VIDEO_RETENTION_DAYS if video_days is None else video_days

    result = {"stream_deleted": 0, "video_deleted": 0, "bytes_freed": 0,
              "alerts_cleared": 0, "protected": 0}
    try:
        # 未处置告警的截图标为"受保护", 即使超过保留期也不删
        protected: set[Path] = set()
        rows = (
            db.query(Alert.screenshot_path, Alert.is_handled)
            .filter(Alert.screenshot_path != None)  # noqa: E711
            .all()
        )
        if keep_unhandled:
            protected = {
                (STATIC_DIR / path).resolve() for path, handled in rows if not handled
            }
        result["protected"] = len(protected)

        if stream_days > 0:
            n, freed = _purge_dir(MEDIA_DIRS["stream"], now - timedelta(days=stream_days), protected)
            result["stream_deleted"] += n
            result["bytes_freed"] += freed
        if video_days > 0:
            n, freed = _purge_dir(MEDIA_DIRS["videos"], now - timedelta(days=video_days), protected)
            result["video_deleted"] += n
            result["bytes_freed"] += freed

        # 截图文件确实不在的告警: 把路径置空(告警本身保留)
        for alert in db.query(Alert).filter(Alert.screenshot_path != None).all():  # noqa: E711
            if not (STATIC_DIR / alert.screenshot_path).exists():
                alert.screenshot_path = None
                result["alerts_cleared"] += 1
        db.commit()

        if result["stream_deleted"] or result["video_deleted"] or result["alerts_cleared"]:
            print(
                f"[清理] 截图 {result['stream_deleted']} 张 / 录像 {result['video_deleted']} 段, "
                f"释放 {result['bytes_freed'] / 1024 / 1024:.1f} MB, "
                f"清空 {result['alerts_cleared']} 条告警的截图路径, "
                f"保护未处置告警截图 {result['protected']} 张",
                flush=True,
            )
        return result
    except Exception as exc:  # noqa: BLE001 定时任务不能把调度器带崩
        db.rollback()
        print(f"[清理] 媒体清理失败: {exc}", flush=True)
        return result
    finally:
        if own_session:
            db.close()


# ---------------------------------------------------------------- 调度器

_scheduler = None


def start_scheduler() -> bool:
    """启动 APScheduler: 掉线扫描 30 秒一次, 服药提醒 60 秒一次。

    返回是否启动成功。apscheduler 没装 / SCHEDULER_ENABLED=0 时返回 False,
    由 main.py 打印提示, 不阻塞服务启动(接口依然可用, 只是没有定时任务)。
    """
    global _scheduler

    if not settings.SCHEDULER_ENABLED:
        print("[定时任务] SCHEDULER_ENABLED=0, 跳过调度器", flush=True)
        return False

    if _scheduler is not None:
        return True

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print(
            "[定时任务] 未安装 apscheduler, 定时任务不会运行; "
            "执行 pip install apscheduler 后重启即可",
            flush=True,
        )
        return False

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        sweep_offline_devices,
        "interval",
        seconds=30,
        id="sweep_offline_devices",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        scan_medicine_reminders,
        "interval",
        seconds=60,
        id="scan_medicine_reminders",
        max_instances=1,
        coalesce=True,
    )
    if settings.MEDIA_CLEANUP_INTERVAL_SECONDS > 0:
        scheduler.add_job(
            cleanup_media,
            "interval",
            seconds=settings.MEDIA_CLEANUP_INTERVAL_SECONDS,
            id="cleanup_media",
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    _scheduler = scheduler
    cleanup_desc = (
        f" / 媒体清理 {settings.MEDIA_CLEANUP_INTERVAL_SECONDS}s"
        if settings.MEDIA_CLEANUP_INTERVAL_SECONDS > 0
        else " / 媒体清理 已关闭"
    )
    print(
        f"[定时任务] 调度器已启动: 掉线扫描 30s / 服药提醒 60s{cleanup_desc} "
        f"(掉线阈值 {settings.DEVICE_OFFLINE_TIMEOUT}s, "
        f"截图保留 {settings.MEDIA_STREAM_RETENTION_DAYS} 天, "
        f"录像保留 {settings.MEDIA_VIDEO_RETENTION_DAYS} 天)",
        flush=True,
    )
    return True


def shutdown_scheduler() -> None:
    """关闭调度器(main.py lifespan 退出时调用)。"""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        print("[定时任务] 调度器已关闭", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[定时任务] 关闭调度器出错: {exc}", flush=True)
    finally:
        _scheduler = None
