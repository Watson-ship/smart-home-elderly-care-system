"""告警接口。

Owner: Person A (阶段 2)
- POST /api/alert/sos          老人一键求助(生成告警 + 自动建工单)
- POST /api/alert/sos/cancel   老人取消求助
- GET  /api/alert/my           查看自己的告警(老人本人 / 已绑定家属)

Person B 后续追加:
- GET    /api/alert/{id}         查看单条告警详情(含截图)
- POST   /api/alert/{id}/handle  家属/社康标记已处置
- POST   /api/alert/ai-detect    AI 推理结果回调(内部用)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_current_user, get_db
from domains.alert import service
from domains.alert.schema import AlertDetail, AlertItem, SosCancelResp, SosReq, SosResp
from schemas.common_schema import BaseResp, ok

router = APIRouter(prefix="/api/alert", tags=["告警"])


def _require_elder_id(current_user) -> int:
    """从当前登录用户取 elder_id: 老人本人是自己的 elder_id, 家属是绑定的老人。"""
    if current_user.elder_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"当前账号({current_user.role})未绑定老人, 无法操作",
        )
    return current_user.elder_id


@router.post("/sos", response_model=BaseResp[SosResp], summary="老人一键求助(自动建工单)")
def create_sos(
    body: SosReq | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """老人按下求助按钮: 生成一条 sos 告警, 并在同一事务里自动建一条 pending 工单。

    - 只有 role=elder 的账号可以发起(家属代发请走后续的家属代报接口)
    - device_id 可空; 传了就校验设备存在且绑定的确实是这位老人
    - 成功后会推送该老人绑定的所有账号(控制台 + logs/push.log)
    """
    if current_user.role != "elder":
        raise HTTPException(status_code=403, detail="仅老人本人可以发起一键求助")

    elder_id = _require_elder_id(current_user)
    device_id = body.device_id if body else None

    data = service.create_sos(db, elder_id, device_id)
    return ok(SosResp(**data))


@router.post("/sos/cancel", response_model=BaseResp[SosCancelResp], summary="老人取消一键求助")
def cancel_sos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """取消最近一条未处置的 sos 告警, 同时把对应工单归档。

    没有待处理的求助时返回 code=0、data.cancelled=false, 这属于正常业务状态而非错误。
    """
    if current_user.role != "elder":
        raise HTTPException(status_code=403, detail="仅老人本人可以取消求助")

    elder_id = _require_elder_id(current_user)
    data = service.cancel_latest_sos(db, elder_id, user_id=current_user.id)
    return ok(SosCancelResp(**data), msg=data["message"])


@router.get("/my", response_model=BaseResp[list[AlertItem]], summary="查看我的告警")
def my_alerts(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """按当前账号绑定的 elder_id 倒序返回告警(老人看到自己的, 家属看到绑定的那位老人的)。

    limit 默认 50, 最大 200。截图字段返回 screenshot_url, 前端直接 <img src> 即可。
    """
    elder_id = _require_elder_id(current_user)
    limit = max(1, min(limit, 200))
    items = service.list_alerts(db, elder_id, limit=limit)
    return ok([AlertItem(**item) for item in items])


# ---------------- Person B 追加: 告警列表 / 告警详情 ----------------


@router.get("", response_model=BaseResp[list[AlertItem]], summary="告警列表(可按处置状态过滤)")
def alert_list(
    handled: int | None = Query(None, ge=0, le=1, description="0只看未处置, 1只看已处置, 不传看全部"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """按当前账号绑定关系查告警: 老人看自己的, 家属看绑定的那位老人。

    截图字段返回 screenshot_url, 前端直接 <img src> 即可。
    """
    elder_id = _require_elder_id(current_user)
    items = service.list_alerts_filtered(db, elder_id, handled=handled, limit=limit)
    return ok([AlertItem(**item) for item in items])


@router.get("/{alert_id}", response_model=BaseResp[AlertDetail], summary="告警详情(含工单状态/处置人)")
def alert_detail(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """返回告警基础信息 + 关联工单状态 + 处置人姓名。

    404: 告警不存在; 403: 该告警属于别的老人。
    """
    elder_id = _require_elder_id(current_user)
    data = service.get_alert_detail(db, alert_id, elder_id)
    return ok(AlertDetail(**data))
