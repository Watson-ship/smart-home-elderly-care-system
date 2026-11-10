"""告警业务逻辑: 一键求助(SOS) + 取消求助 + 我的告警。

Owner: Person A (阶段 2 核心联动)

业务闭环:
    POST /api/alert/sos          -> 插 alert(type=sos) + 同一事务插 work_order(pending)
                                    -> 推送家属/老人 -> 返回两个 id
    POST /api/alert/sos/cancel   -> 老人最近一条未处置的 sos 置 is_handled=1
                                    并把对应工单一并归档(社康不用再白跑一趟)
    GET  /api/alert/my           -> 按 elder_id 倒序返回告警列表

说明:
    - alert 与 work_order 是逻辑外键, 所以必须**同一次 commit** 才保证"有告警必有工单";
      写工单失败就整体回滚, 不会留下一条没人处理的 SOS 告警。
    - 推送先走 infrastructure.push.notify(控制台 + 日志文件), 接 WebSocket 时只改 notify 内部。
"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from infrastructure.push.notify import notify
from infrastructure.storage.file_store import resolve_static_path
from models import Alert, Device, Elder, User, WorkOrder


def _get_elder(db: Session, elder_id: int) -> Elder:
    elder = db.get(Elder, elder_id)
    if elder is None:
        raise HTTPException(status_code=404, detail=f"老人 {elder_id} 不存在")
    return elder


def _notify_guardians(db: Session, elder: Elder, title: str, content: str) -> None:
    """推给该老人绑定的所有账号(老人本人 + 家属), 社康账号(elder_id 为空)不在内。"""
    receivers = db.query(User).filter(User.elder_id == elder.id).all()
    for user in receivers:
        notify(user.id, title, content)
    if not receivers:
        notify(None, title, content + f" [elder_id={elder.id} 无绑定账号]")


def create_sos(db: Session, elder_id: int, device_id: int | None = None) -> dict:
    """发起一键求助: 生成 sos 告警 + 自动建一条待派单工单(同一事务)。"""
    elder = _get_elder(db, elder_id)

    device = None
    if device_id is not None:
        device = db.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail=f"设备 {device_id} 不存在")
        # 设备存在但绑的不是这位老人, 属于前端传错, 直接拒绝
        if device.elder_id is not None and device.elder_id != elder_id:
            raise HTTPException(
                status_code=400,
                detail=f"设备 {device_id} 绑定的老人是 {device.elder_id}, 与当前老人不一致",
            )

    try:
        alert = Alert(
            elder_id=elder_id,
            device_id=device_id,
            alert_type="sos",
            is_handled=0,
        )
        db.add(alert)
        db.flush()  # 先拿到 alert.id, 工单要用

        order = WorkOrder(
            alert_id=alert.id,
            elder_id=elder_id,
            order_status="pending",
        )
        db.add(order)
        db.commit()  # 告警 + 工单一起落库: 要么都成功, 要么都回滚
        db.refresh(alert)
        db.refresh(order)
    except Exception as exc:
        db.rollback()
        print(f"[SOS] 创建失败已回滚: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="发起求助失败, 请稍后重试")

    print(f"[SOS] elder={elder.elder_name} alert={alert.id} work_order={order.id}", flush=True)
    _notify_guardians(
        db,
        elder,
        "一键求助",
        f"{elder.elder_name} 发起了一键求助, 工单 #{order.id} 已创建, 请立即联系老人({elder.phone})",
    )

    return {
        "alert_id": alert.id,
        "work_order_id": order.id,
        "elder_id": elder_id,
        "elder_name": elder.elder_name,
        "order_status": order.order_status,
        "create_time": alert.create_time,
    }


# ==================== C同学补充：AI 告警生成 ====================
def create_ai_alert(db: Session, elder_id: int, device_id: int, alert_type: str = "fall",
                    image_path: str = None) -> Alert:
    """
    生成 AI 告警记录，并自动生成一条待派单工单（同一事务）。
    """
    elder = _get_elder(db, elder_id)  # 复用队友写的检查老人是否存在的函数

    try:
        alert = Alert(
            elder_id=elder_id,
            device_id=device_id,
            alert_type=alert_type,
            is_handled=0,
            screenshot_path=image_path
        )
        db.add(alert)
        db.flush()  # 拿到 alert.id

        order = WorkOrder(
            alert_id=alert.id,
            elder_id=elder_id,
            order_status="pending",
        )
        db.add(order)
        db.commit()
        db.refresh(alert)
        db.refresh(order)
    except Exception as exc:
        db.rollback()  # 【关键】如果工单插入失败，把告警也撤销掉
        print(f"[AI告警] 创建失败已回滚: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="生成AI告警失败")

    print(f"[AI告警] elder={elder.elder_name} alert={alert.id} work_order={order.id}", flush=True)

    # 【关键】直接复用队友写好的推送逻辑，推给家属！
    _notify_guardians(
        db,
        elder,
        "AI跌倒告警",
        f"AI 检测到 {elder.elder_name} 发生跌倒，工单 #{order.id} 已自动创建，请立即联系老人({elder.phone})！",
    )

    return alert

def cancel_latest_sos(db: Session, elder_id: int, user_id: int | None = None) -> dict:
    """取消该老人最近一条未处置的 sos 告警。

    没有可取消的求助时不是报错, 而是返回 cancelled=False 让前端提示"当前没有求助";
    取消成功后同时把对应的待处理工单归档, 避免社康继续处置一条已被撤销的求助。
    """
    alert = (
        db.query(Alert)
        .filter(Alert.elder_id == elder_id)
        .filter(Alert.alert_type == "sos")
        .filter(Alert.is_handled == 0)
        .order_by(Alert.create_time.desc(), Alert.id.desc())
        .first()
    )
    if alert is None:
        return {"cancelled": False, "alert_id": None, "work_order_id": None,
                "message": "当前没有待处理的求助"}

    alert.is_handled = 1
    alert.handled_by = user_id
    alert.handle_time = datetime.now()

    order = db.query(WorkOrder).filter(WorkOrder.alert_id == alert.id).first()
    if order is not None and order.order_status != "archived":
        order.order_status = "archived"
        order.archive_time = datetime.now()

    db.commit()
    db.refresh(alert)

    print(f"[SOS] 已取消求助 alert={alert.id} work_order={order.id if order else None}", flush=True)
    return {
        "cancelled": True,
        "alert_id": alert.id,
        "work_order_id": order.id if order else None,
        "message": "求助已取消",
    }


# ---------------- Person B 追加: 告警列表(支持未处置过滤) / 告警详情 ----------------


def _to_item(alert: Alert) -> dict:
    """告警 -> 列表项字典(screenshot_path 存的是相对 static 的路径)。"""
    return {
        "id": alert.id,
        "elder_id": alert.elder_id,
        "device_id": alert.device_id,
        "alert_type": alert.alert_type,
        "screenshot_path": alert.screenshot_path,
        "screenshot_url": f"/static/{alert.screenshot_path}" if alert.screenshot_path else None,
        "is_handled": alert.is_handled,
        "handled_by": alert.handled_by,
        "handle_time": alert.handle_time,
        "create_time": alert.create_time,
    }


def list_alerts_filtered(
    db: Session, elder_id: int, handled: int | None = None, limit: int = 50
) -> list[dict]:
    """按 elder_id 倒序返回告警; handled=0/1 时只返回未处置/已处置的。"""
    query = db.query(Alert).filter(Alert.elder_id == elder_id)
    if handled is not None:
        query = query.filter(Alert.is_handled == handled)
    rows = query.order_by(Alert.create_time.desc(), Alert.id.desc()).limit(limit).all()
    return [_to_item(alert) for alert in rows]


def get_alert_detail(db: Session, alert_id: int, elder_id: int) -> dict:
    """告警详情: 基础信息 + 关联工单状态 + 处置人姓名。

    404: 告警不存在; 403: 告警属于别的老人(防止跨老人查看)。
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 不存在")
    if alert.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权查看该告警")

    order = db.query(WorkOrder).filter(WorkOrder.alert_id == alert.id).first()
    handler = db.get(User, alert.handled_by) if alert.handled_by else None
    elder = db.get(Elder, alert.elder_id)

    item = _to_item(alert)
    item.update(
        {
            "elder_name": elder.elder_name if elder else None,
            "order_id": order.id if order else None,
            "order_status": order.order_status if order else None,
            # user 表没有姓名字段, 处置人姓名用账号名展示
            "handled_by_name": handler.username if handler else None,
        }
    )
    return item


def handle_alert(db: Session, alert_id: int, elder_id: int, user_id: int) -> dict:
    """标记告警已处置: is_handled=1, handled_by=当前用户, handle_time=当前时间。

    404: 告警不存在; 403: 告警属于别的老人; 400: 已经被处置过(不覆盖原处置人)。
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 不存在")
    if alert.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权处置该告警")
    if alert.is_handled == 1:
        raise HTTPException(status_code=400, detail=f"告警 {alert_id} 已处置, 无需重复操作")

    alert.is_handled = 1
    alert.handled_by = user_id
    alert.handle_time = datetime.now()
    db.commit()
    db.refresh(alert)

    handler = db.get(User, user_id)
    print(f"[ALERT] 告警 {alert.id} 已处置 by user={user_id}", flush=True)
    return {
        "alert_id": alert.id,
        "is_handled": alert.is_handled,
        "handled_by": alert.handled_by,
        "handled_by_name": handler.username if handler else None,
        "handle_time": alert.handle_time,
    }


def get_screenshot_path(db: Session, alert_id: int, elder_id: int):
    """取告警截图的可访问文件路径。

    404: 告警不存在 / 没有截图 / 文件已被清理; 403: 告警属于别的老人。
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 不存在")
    if alert.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权查看该告警")
    if not alert.screenshot_path:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 没有截图")

    path = resolve_static_path(alert.screenshot_path)
    if path is None:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 的截图文件不存在")
    return path


def get_alert_stats(db: Session, elder_id: int, days: int = 7) -> dict:
    """近 N 天告警统计: 按类型、按日期聚合, 供家属首页卡片使用。

    没有告警的日期也会出现在 by_date 里(数值为 0), 前端画图不用自己补轴。
    """
    end_day = date.today()
    start_day = end_day - timedelta(days=days - 1)
    start_dt = datetime.combine(start_day, time.min)

    rows = db.query(Alert).filter(
        Alert.elder_id == elder_id,
        Alert.create_time >= start_dt
    ).all()

    by_date = {}
    for offset in range(days):
        day_key = (start_day + timedelta(days=offset)).strftime("%Y-%m-%d")
        by_date[day_key] = {"date": day_key, "total": 0, "handled": 0, "unhandled": 0}

    by_type = {}
    total = handled = unhandled = 0
    for alert in rows:
        if alert.create_time is None:
            continue
        day_key = alert.create_time.strftime("%Y-%m-%d")
        if day_key not in by_date:     # 兜底: 超出统计区间的记录不计入
            continue

        type_stat = by_type.setdefault(
            alert.alert_type,
            {"alert_type": alert.alert_type, "total": 0, "handled": 0, "unhandled": 0}
        )
        key = "handled" if alert.is_handled == 1 else "unhandled"

        for stat in (by_date[day_key], type_stat):
            stat["total"] += 1
            stat[key] += 1
        total += 1
        if key == "handled":
            handled += 1
        else:
            unhandled += 1

    return {
        "elder_id": elder_id,
        "days": days,
        "start_date": start_day.strftime("%Y-%m-%d"),
        "end_date": end_day.strftime("%Y-%m-%d"),
        "total": total,
        "handled": handled,
        "unhandled": unhandled,
        "by_type": [by_type[name] for name in sorted(by_type)],
        "by_date": [by_date[name] for name in sorted(by_date)],
    }


def list_alerts(db: Session, elder_id: int, limit: int = 50) -> list[dict]:
    """按时间倒序返回某位老人的告警(含截图可访问地址)。"""
    rows = (
        db.query(Alert)
        .filter(Alert.elder_id == elder_id)
        .order_by(Alert.create_time.desc(), Alert.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for alert in rows:
        items.append(
            {
                "id": alert.id,
                "elder_id": alert.elder_id,
                "device_id": alert.device_id,
                "alert_type": alert.alert_type,
                "screenshot_path": alert.screenshot_path,
                # screenshot_path 存的是相对 static 的路径, 前端拼 /static/ 即可
                "screenshot_url": f"/static/{alert.screenshot_path}" if alert.screenshot_path else None,
                "is_handled": alert.is_handled,
                "handled_by": alert.handled_by,
                "handle_time": alert.handle_time,
                "create_time": alert.create_time,
            }
        )
    return items
