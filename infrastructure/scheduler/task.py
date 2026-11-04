"""定时任务: 设备掉线扫描 + 服药提醒扫描, 由 APScheduler 周期拉起。

Owner: Person A (阶段 2 的两个定时任务)

暴露三个函数:
    sweep_offline_devices(timeout_seconds=120)  心跳超时 -> status='offline', 返回受影响台数
    scan_medicine_reminders(window_minutes=1)   到点的启用计划 -> 推送提醒, 返回推送条数
    start_scheduler() / shutdown_scheduler()    在 main.py lifespan 里启动/关闭 APScheduler

设计要点:
    1. 每个任务自己开 Session(不共用请求的 session): 定时任务是独立线程,
       复用 Web 线程的 Session 会踩"session 已被别的线程使用"的坑。
    2. 任务里捕获所有异常: 一次数据库抖动不能让整个调度器停摆。
    3. 服药提醒按 (plan_id, 日期, 时分) 去重: 调度器每 60 秒跑一次,
       取时间范围是"最近 N 分钟", 不去重就会对同一剂药重复推送。
    4. 只提醒"启用(status=1)"的计划, 且当天已经确认过服药(medicine_record)的不再提醒;
       cycle='two_day'(隔天) 的计划按日期奇偶跳过一次。
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

import config.settings as settings
from infrastructure.push.notify import notify
from models import Device, MedicinePlan, MedicineRecord, User

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
    scheduler.start()
    _scheduler = scheduler
    print(
        "[定时任务] 调度器已启动: 掉线扫描 30s / 服药提醒 60s "
        f"(掉线阈值 {settings.DEVICE_OFFLINE_TIMEOUT}s)",
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
