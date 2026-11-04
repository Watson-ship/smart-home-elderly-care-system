"""消息推送: 阶段 2 先用"控制台 + 日志文件"模拟, 前端做好后换成 WebSocket。

Owner: Person A (阶段 2 定时任务 + 推送)

设计:
    notify(user_id, title, content)
        - 控制台打印一行, 方便联调时肉眼确认
        - 追加写 logs/push.log (JSON Lines, 一行一条), 前端/演示可直接 tail 查看
        - 返回是否推送成功(目前恒为 True)

为什么先不接 WebSocket:
    课设阶段前端还没做消息页, 推送"发出去没人收"会让接口报错;
    这里把发送动作抽象成一个函数, 之后接 WebSocket 只需要改这一个文件的实现,
    scheduler / alert 的调用方不用动。
"""
import json
from datetime import datetime
from pathlib import Path

# 日志文件: 运行时生成, 已在 .gitignore 中忽略
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "push.log"


def notify(user_id: int | None, title: str, content: str) -> bool:
    """给指定用户 push 一条通知。

    user_id 可以为 None(例如"不知道该推给谁"的系统广播), 此时日志里记为 0。
    任何写日志的异常都被吃掉并打印, 绝不能因为推送失败把定时任务/业务接口带崩。
    """
    record = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "title": title,
        "content": content,
    }

    print(f"[推送] user={user_id} {title} | {content}", flush=True)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 推送失败不能影响业务
        print(f"[推送失败] 写日志出错: {exc}", flush=True)

    return True
