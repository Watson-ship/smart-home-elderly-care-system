"""告警接口。

后面写:
- POST   /api/alert/sos          老人一键求助(生成告警)
- POST   /api/alert/sos/cancel   老人取消求助
- GET    /api/alert              家属/社康查看告警列表
- GET    /api/alert/{id}         查看单条告警详情(含截图)
- POST   /api/alert/{id}/handle  家属标记已处置
- POST   /api/alert/ai-detect    AI 推理结果回调(内部用)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/alert", tags=["告警"])
