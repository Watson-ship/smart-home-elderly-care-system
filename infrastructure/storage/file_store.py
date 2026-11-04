"""保存/读取告警截图等文件。

Owner: Person B (阶段 B-3)
- save_screenshot(image_bytes, alert_id): 存 AI 生成的告警截图, 返回相对 static 的路径
- delete_screenshot(alert_id): 工单归档时清理截图
- resolve_static_path(relative_path): 把数据库里的相对路径安全解析成绝对路径

约定: 数据库里 screenshot_path 一律存"相对 static"的路径, 前端用 /static/{path} 访问。
      摄像端上传的图落在 stream/{device_sn}/ 下 (Person A 的 save_fall_screenshot),
      AI 生成的告警图落在 screenshots/{alert_id}.jpg;
      读取接口按库里的实际路径取文件, 两种来源都能兼容。
"""
from pathlib import Path

STATIC_DIR = Path("static")
SCREENSHOT_DIR = STATIC_DIR / "screenshots"


def save_screenshot(image_bytes: bytes, alert_id: int) -> str:
    """把一张告警截图存成 static/screenshots/{alert_id}.jpg, 返回相对 static 的路径。

    同一告警重复调用会覆盖旧图(一条告警只保留一张证据图)。
    调用方负责把返回的路径写进 alert.screenshot_path。
    """
    if not image_bytes:
        raise ValueError("截图内容为空")
    if alert_id <= 0:
        raise ValueError("alert_id 不合法")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    target = SCREENSHOT_DIR / f"{int(alert_id)}.jpg"
    target.write_bytes(image_bytes)
    return f"screenshots/{int(alert_id)}.jpg"


def delete_screenshot(alert_id: int) -> bool:
    """删除该告警的截图, 返回是否真的删掉了文件(文件不存在返回 False, 不抛异常)。

    工单归档时调用, 属于可选的清理动作, 失败不应影响主流程。
    """
    target = SCREENSHOT_DIR / f"{int(alert_id)}.jpg"
    if not target.is_file():
        return False
    target.unlink()
    return True


def resolve_static_path(relative_path: str) -> Path | None:
    """把数据库里的相对路径(相对 static)解析成绝对路径。

    返回 None 表示路径越界或不是普通文件, 调用方统一按 404 处理,
    避免把 static 目录以外的东西暴露出去。
    """
    if not relative_path:
        return None

    root = STATIC_DIR.resolve()
    candidate = (STATIC_DIR / relative_path).resolve()
    if not candidate.is_relative_to(root):
        return None
    if not candidate.is_file():
        return None
    return candidate
