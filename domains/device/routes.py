"""摄像头设备接口。

Owner 划分 (两人共用本文件, 不要动对方的部分):
    Person A (硬件方向) —— 本文件当前内容
        POST /api/device/register    手动注册设备 (先登记 SN 和设备名)
        POST /api/device/heartbeat   设备心跳上报, 刷新最后在线时间
        POST /api/device/video       设备上传录制好的视频片段, 存 static/videos/{sn}/
                                     可选 auto_detect=true: 后台自动跑跌倒检测并生成截图/告警
        POST /api/device/stream      设备上传"跌倒截图", 存 static/stream/{sn}/ 并生成告警
        POST /api/device/detect      提交一整段视频, 后端离线跑 AI 并截取跌倒帧(联调/验收用)
        POST /api/device/detect/latest  不用重传: 直接检测该设备最新上传的那段视频
        POST /api/device/bind        绑定设备与老人
        GET  /api/device/stream/{sn} 家属端查看最新跌倒截图(FileResponse, 直接给 img src)
    Person B (家属方向) —— 阶段 2 追加
        GET  /api/device                 家属查看自己老人绑定的摄像头列表

注意: 摄像头是机器, 靠 device_sn 认身份, 以上接口不需要登录。
      设备必须先手动注册, 心跳/上传视频/上传截图才被接受。

分工调整 (阶段 1): 跌倒判定放在**摄像端** —— 摄像端用
infrastructure/ai/inference.py 的 FallMonitor 边录边判, 只有确认跌倒时才把
那一帧截图传到 /stream, 后端存图并写 alert; 同时把按时切段的录像传到 /video
作为事后查证用的证据视频。
"""
from pathlib import Path
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.session import get_db
from domains.device import service
from schemas.common_schema import BaseResp, ok
from schemas.device_schema import (
    BindReq,
    BindResp,
    DetectResp,
    DeviceRegisterReq,
    DeviceRegisterResp,
    DetectedShot,
    HeartbeatReq,
    HeartbeatResp,
    StreamUploadResp,
    VideoUploadResp,
)

router = APIRouter(prefix="/api/device", tags=["摄像头设备"])

# 单段视频大小上限: 50 MB, 防止误传超大文件把磁盘写满
MAX_VIDEO_SIZE = 50 * 1024 * 1024

# 单张跌倒截图上限: 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024


@router.post("/register", response_model=BaseResp[DeviceRegisterResp], summary="手动注册设备")
def register(req: DeviceRegisterReq, db: Session = Depends(get_db)):
    """家属/管理员先登记设备 SN 和设备名, 设备才能接入。

    注册后状态为 offline, 设备第一次心跳成功才会变成 online。
    重复注册同一个 SN 返回 400。
    """
    try:
        device = service.register_device(db, req.device_sn, req.device_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ok(
        DeviceRegisterResp(
            device_sn=device.device_sn,
            device_name=device.device_name,
            status=device.status,
            elder_id=device.elder_id,
        )
    )


@router.post("/heartbeat", response_model=BaseResp[HeartbeatResp], summary="设备心跳上报")
def heartbeat(req: HeartbeatReq, db: Session = Depends(get_db)):
    """设备定期调用(建议 10 秒一次)。

    只接受已手动注册的设备: 未注册返回 404, 需先调 /register。
    已注册设备刷新最后在线时间并置为 online;
    服务端超过 DEVICE_HEARTBEAT_TIMEOUT 秒没收到心跳就会把设备置为 offline。
    """
    try:
        device = service.heartbeat(db, req.device_sn)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return ok(
        HeartbeatResp(
            device_sn=device.device_sn,
            status=device.status,
            last_online_time=device.last_online_time,
        )
    )


@router.post("/video", response_model=BaseResp[VideoUploadResp], summary="设备上传视频片段")
async def upload_video(
    device_sn: str = Form(..., description="设备序列号"),
    file: UploadFile = File(..., description="摄像头连续录制后切分的一段视频(mp4)"),
    auto_detect: bool = Form(
        False,
        description="上传后是否排进后台跌倒检测队列; 默认关(摄像端已本地判定, 服务端只存证据)",
    ),
    db: Session = Depends(get_db),
):
    """设备把实时画面按时间切成一段段视频, 每录完一段就上传一次。

    服务端保存为 static/videos/{device_sn}/{时间戳}.mp4, 每段独立文件, 不覆盖。
    设备必须先手动注册, 否则返回 404。

    默认只"收录像 + 存证据", 不做 AI(生产上判定在摄像端, 见 /stream)。
    要让**服务端自动处理这段视频**, 传 auto_detect=true:
        上传接口立刻返回; 这段视频进入后台**单线程队列**, 按上传顺序一段一段检测,
        跑完把跌倒帧写到 static/stream/, 设备已绑定老人时生成 alert 记录
        (控制台会打印 [自动检测] 结果)。串行队列是为了避免多段同时推理抢满 CPU。
    只想事后单独检测某一段(不用重新上传)可以调 /api/device/detect/latest。
    """
    video_bytes = await file.read()

    if not video_bytes:
        raise HTTPException(status_code=400, detail="上传内容为空")
    if len(video_bytes) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"视频过大, 上限 {MAX_VIDEO_SIZE // 1024 // 1024} MB",
        )

    # 从上传文件名取扩展名, service 层会做白名单校验
    suffix = Path(file.filename or "").suffix.lower()

    try:
        saved = service.save_video(db, device_sn, video_bytes, suffix)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    queued = False
    msg = "ok"
    if auto_detect:
        queued = service.enqueue_video_detection(device_sn, saved)
        if queued:
            print(f"[视频上传] device={device_sn} -> {saved.as_posix()} (已排入后台检测队列)")
        else:
            msg = "视频已保存, 但后台检测队列已满(50 段), 本次未排入检测"
            print(f"[视频上传] {msg}: {saved.as_posix()}")

    return ok(
        VideoUploadResp(
            device_sn=device_sn,
            file_path=saved.as_posix(),
            file_url=f"/{saved.as_posix()}",
            size=len(video_bytes),
            auto_detect=queued,
        ),
        msg=msg,
    )


@router.post("/stream", response_model=BaseResp[StreamUploadResp], summary="设备上传跌倒截图")
async def upload_stream_snapshot(
    device_sn: str = Form(..., description="设备序列号"),
    file: UploadFile = File(..., description="摄像端 AI 确认跌倒时截取的那一帧(jpg/png)"),
    fall_conf: float = Form(0.0, description="摄像端跌倒判定的置信度(可选, 仅用于日志)"),
    db: Session = Depends(get_db),
):
    """摄像端 AI 判定为跌倒后, 把当时那一帧截图传上来(不是每帧都传)。

    服务端保存为 static/stream/{device_sn}/{毫秒时间戳}.jpg, 每次跌倒单独一个文件。
    设备已绑定老人时, 同时生成一条 alert 告警记录(alert_type='fall',
    screenshot_path 指向这张截图), 家属/社康端可以直接查到并处理。
    设备未绑定老人时只存图不生成告警, 响应 msg 会说明。

    设备必须先手动注册, 否则返回 404。
    """
    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传内容为空")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"截图过大, 上限 {MAX_IMAGE_SIZE // 1024 // 1024} MB",
        )

    suffix = Path(file.filename or "").suffix.lower()

    try:
        saved, alert = service.save_fall_screenshot(db, device_sn, image_bytes, suffix)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    print(f"[跌倒截图] device={device_sn} conf={fall_conf:.2f} -> {saved.as_posix()}")

    msg = "ok" if alert is not None else "设备未绑定老人, 截图已保存但未生成告警"
    return ok(
        StreamUploadResp(
            device_sn=device_sn,
            file_path=saved.as_posix(),
            file_url=f"/{saved.as_posix()}",
            size=len(image_bytes),
            alert_id=alert.id if alert is not None else None,
            elder_id=alert.elder_id if alert is not None else None,
        ),
        msg=msg,
    )


def _detect_response(
    db: Session,
    device_sn: str,
    video: Path,
    *,
    infer_every: int,
    max_frames: int,
    require_transition: bool,
    conf_min: float,
    cooldown_sec: float = 5.0,
    per_track_cooldown_sec: float = 5.0,
) -> DetectResp:
    """跑一遍离线检测并组装响应(同步函数, 由路由用 run_in_threadpool 包一层)。

    /detect(上传视频) 和 /detect/latest(复用已上传视频) 共用这一份逻辑;
    service 抛的异常在这里统一翻译成 HTTP 状态码。
    """
    started = time.perf_counter()
    try:
        result = service.detect_falls_in_video(
            db,
            device_sn,
            video,
            infer_every=infer_every,
            max_frames=max_frames,
            require_transition=require_transition,
            conf_min=conf_min,
            cooldown_sec=cooldown_sec,
            per_track_cooldown_sec=per_track_cooldown_sec,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(
        f"[离线检测] device={device_sn} video={video.as_posix()} "
        f"frames={result['frames_processed']} events={result['fall_events']} "
        f"cost={elapsed_ms}ms"
    )

    return DetectResp(
        device_sn=device_sn,
        frames_processed=result["frames_processed"],
        fps=result["fps"],
        infer_every=result["infer_every"],
        fall_events=result["fall_events"],
        elapsed_ms=elapsed_ms,
        video_path=video.as_posix(),
        video_url=f"/{video.as_posix()}",
        screenshots=[DetectedShot(**item) for item in result["screenshots"]],
    )


@router.post("/detect", response_model=BaseResp[DetectResp], summary="提交视频检测跌倒帧")
async def detect_video_falls(
    device_sn: str = Form(..., description="设备序列号(需先注册)"),
    file: UploadFile = File(..., description="要检测的视频文件(mp4/avi/mov/mkv)"),
    infer_every: int = Form(3, ge=1, le=10, description="每 N 帧推理一次; 1 最准也最慢, 3 是默认折中"),
    max_frames: int = Form(900, description="最多处理多少帧(<=0 表示整段视频), 防止长视频把接口拖死"),
    require_transition: bool = Form(True, description="要求'由站到倒'的转换; 视频一开头就是躺着的片段请传 false"),
    conf_min: float = Form(0.45, ge=0.0, le=1.0, description="falldown 置信度门槛"),
    cooldown_sec: float = Form(
        5.0, ge=0.0, le=120.0,
        description="全局冷却(秒), 默认 5; 调大会上会漏掉同一段视频里接连发生的多次跌倒",
    ),
    per_track_cooldown_sec: float = Form(
        5.0, ge=0.0, le=120.0,
        description="同一个人两次告警的最小间隔(秒), 默认 5(实时模式配置是 20)",
    ),
    db: Session = Depends(get_db),
):
    """提交一整段视频, 后端用 infrastructure/ai 的判定模型离线跑一遍, 把跌倒帧截下来。

    与摄像端实时判定的区别:
        - /stream: 摄像端自己判定, 只把确认跌倒的那一帧传上来 (生产用法);
        - /detect: 直接把整段视频交给后端, 后端逐帧推理并自己截图 (联调/验收用法)。

    返回的 screenshots 里每一项就是截到的一帧跌倒画面:
        file_url 可直接在浏览器打开 (例如 /static/stream/{sn}/xxx_t12000.jpg);
        设备已绑定老人时还会顺带生成一条 alert 告警记录, alert_id 可查。
    本接口会把上传视频存到 static/videos/{sn}/ 作为证据, 检测完不会自动删除。

    调参提示: 视频一开头人就已经躺/倒在地上时, 状态机的"由站到倒"要求会让它漏报,
    此时传 require_transition=false 提高召回; 误报多就把 conf_min 调高(如 0.6)。
    **一段视频里跌倒过多次却只截到一张**: 是冷却时间(实时默认 30s)把后面的吞了,
    cooldown_sec/per_track_cooldown_sec 调小(默认 5)就能把每次都截下来。

    设备必须先手动注册(未注册 404); 视频打不开/超过 50MB 返回 400/413;
    模型加载失败返回 503。
    """
    video_bytes = await file.read()

    if not video_bytes:
        raise HTTPException(status_code=400, detail="上传内容为空")
    if len(video_bytes) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"视频过大, 上限 {MAX_VIDEO_SIZE // 1024 // 1024} MB",
        )

    suffix = Path(file.filename or "").suffix.lower()

    # 先落盘(顺便校验设备是否已注册), 再从磁盘读帧检测
    try:
        saved = service.save_video(db, device_sn, video_bytes, suffix)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 推理是纯 CPU 的重活, 丢到线程池里跑, 避免把事件循环堵死
    resp = await run_in_threadpool(
        _detect_response,
        db,
        device_sn,
        saved,
        infer_every=infer_every,
        max_frames=max_frames,
        require_transition=require_transition,
        conf_min=conf_min,
        cooldown_sec=cooldown_sec,
        per_track_cooldown_sec=per_track_cooldown_sec,
    )

    return ok(resp, msg="ok" if resp.screenshots else "未检测到跌倒, 没有截图")


@router.post(
    "/detect/latest",
    response_model=BaseResp[DetectResp],
    summary="检测该设备最新上传的视频(不用再传一遍)",
)
async def detect_latest_video(
    device_sn: str = Form(..., description="设备序列号(需先注册, 且至少上传过一段视频)"),
    infer_every: int = Form(3, ge=1, le=10, description="每 N 帧推理一次"),
    max_frames: int = Form(900, description="最多处理多少帧(<=0 表示整段视频)"),
    require_transition: bool = Form(True, description="要求'由站到倒'的转换; 视频开头就倒地请传 false"),
    conf_min: float = Form(0.45, ge=0.0, le=1.0, description="falldown 置信度门槛"),
    cooldown_sec: float = Form(5.0, ge=0.0, le=120.0, description="全局冷却(秒), 默认 5"),
    per_track_cooldown_sec: float = Form(
        5.0, ge=0.0, le=120.0, description="同一个人两次告警的最小间隔(秒), 默认 5"
    ),
    db: Session = Depends(get_db),
):
    """拿 static/videos/{device_sn}/ 里**最新的一段**视频来跑跌倒检测。

    典型用法: 已经调过 POST /api/device/video 上传了视频, 不想用 /detect 再传一遍,
    就调这个接口(只需要 device_sn), 它会自动找到刚上传的那段文件并截图。

    响应里的 video_path 就是它实际检测的那个文件, 可以核对是不是你想测的那段。
    """
    try:
        video = service.find_latest_video(db, device_sn)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    resp = await run_in_threadpool(
        _detect_response,
        db,
        device_sn,
        video,
        infer_every=infer_every,
        max_frames=max_frames,
        require_transition=require_transition,
        conf_min=conf_min,
        cooldown_sec=cooldown_sec,
        per_track_cooldown_sec=per_track_cooldown_sec,
    )

    return ok(resp, msg="ok" if resp.screenshots else "未检测到跌倒, 没有截图")


@router.get(
    "/stream/{device_sn}",
    summary="家属查看摄像头最新画面(跌倒截图)",
    response_class=FileResponse,
)
def get_stream_snapshot(device_sn: str, name: str | None = None):
    """返回该设备最新的一张跌倒截图文件(直接给 <img src> 用)。

    为什么不用 /static/stream/... 直接访问:
        浏览器拿不到"最新一张"这个语义, 文件名带毫秒时间戳, 前端无法拼接;
        这个接口每次取目录里 mtime 最新的 jpg, 前端换 src 就能"刷新画面"。
    name 参数可选: 想指定某一张(例如告警列表里点开某条)时传完整文件名。

    目录不存在 / 没有截图时返回 404(前端可显示占位图)。
    """
    safe_sn = "".join(ch for ch in device_sn if ch.isalnum() or ch in "-_")
    if not safe_sn:
        raise HTTPException(status_code=400, detail="设备序列号不合法")

    device_dir = service.STREAM_DIR / safe_sn
    if not device_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"设备 {device_sn} 还没有上传过截图")

    if name:
        # 只接受纯文件名, 挡住 ../ 路径穿越
        file_name = Path(name).name
        target = device_dir / file_name
        if not target.is_file() or target.suffix.lower() not in service.STREAM_SUFFIXES:
            raise HTTPException(status_code=404, detail=f"截图 {file_name} 不存在")
    else:
        shots = [
            p for p in device_dir.iterdir()
            if p.is_file() and p.suffix.lower() in service.STREAM_SUFFIXES
        ]
        if not shots:
            raise HTTPException(status_code=404, detail=f"设备 {device_sn} 还没有上传过截图")
        target = max(shots, key=lambda p: p.stat().st_mtime)

    return FileResponse(target, media_type="image/jpeg", filename=target.name)


@router.post("/bind", response_model=BaseResp[BindResp], summary="绑定设备与老人")
def bind(req: BindReq, db: Session = Depends(get_db)):
    """家属把摄像头绑定到老人: 更新 device.elder_id。

    阶段 1 暂不校验登录身份, 阶段 2 会改成"只能绑定自己家的老人"。
    """
    try:
        device = service.bind_device(db, req.device_sn, req.elder_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return ok(
        BindResp(
            device_sn=device.device_sn,
            device_name=device.device_name,
            elder_id=device.elder_id,
        )
    )
