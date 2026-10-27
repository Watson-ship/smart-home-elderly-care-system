# 居家老人监测系统（后端 API）

大学生课程作业。监控摄像头上传视频流 → 服务端 AI 识别跌倒/长时间静止 → 生成告警推送家属和社康；支持老人一键 SOS、服药提醒确认、社康工单派单归档。

## 技术栈

- Python 3.10+ / FastAPI / Uvicorn
- SQLAlchemy 2.0（原生 ORM）+ PyMySQL（驱动）
- Pydantic 2（请求/响应校验 + 自动接口文档）

## 目录结构

```
smart-home-elderly-care-system/
│
├── main.py                          ← 启动入口: 连库建表 + 注册所有路由
├── requirements.txt                 ← 依赖清单
├── .gitignore                       ← 密码/虚拟环境/运行产物等忽略
│
├── config/                          ← 基础设施配置 (不属于业务)
│   ├── settings.py                  ← 统一配置 (模板, 会上传)
│   ├── settings_local.example.py    ← 本地配置模板 (复制后改名使用)
│   └── settings_local.py            ← 你的本地密码 (gitignore 了, 不上传)
│
├── db/                              ← 数据库基础设施
│   ├── base.py                      ← SQLAlchemy 基类 Base
│   └── session.py                   ← engine + SessionLocal + get_db() 依赖注入
│
├── models/                          ← ORM 模型 (贫血模型: 只有字段, 一文件一表)
│   ├── __init__.py                  ← 统一导出, 用法: from models import Elder, User ...
│   ├── elder.py
│   ├── user.py
│   ├── device.py
│   ├── medicine_plan.py
│   ├── medicine_record.py
│   ├── alert.py
│   └── work_order.py
│
├── schemas/                         ← Pydantic 请求/响应校验
│   ├── common_schema.py             ← 统一响应格式 BaseResp、ok() 快捷函数
│   ├── elder_schema.py              ← 老人档案请求/响应
│   └── auth_schema.py               ← 登录请求/响应
│
├── domains/                         ← ✅ 业务领域层 (核心)
│   ├── auth/                        ← 登录注册
│   │   ├── routes.py                ←   HTTP 接口 (APIRouter)
│   │   └── service.py               ←   业务逻辑
│   ├── elder/                       ← 老人档案
│   │   ├── routes.py
│   │   └── service.py
│   ├── device/                      ← 摄像头设备
│   │   ├── routes.py
│   │   └── service.py
│   ├── alert/                       ← 告警 (AI + SOS + 家属处置)
│   │   ├── routes.py
│   │   └── service.py
│   ├── medicine/                    ← 用药计划 + 服药确认
│   │   ├── routes.py
│   │   └── service.py
│   └── work_order/                  ← 社康工单
│       ├── routes.py
│       └── service.py
│
├── infrastructure/                  ← ✅ 基础设施 (和业务解耦, 换了不影响 domains)
│   ├── ai/                          ←   AI 推理 (独立!)
│   │   ├── model_loader.py          ←     加载 PyTorch 权重
│   │   └── inference.py             ←     推理函数: 输入图片 → 是否跌倒
│   ├── scheduler/                   ←   APScheduler 定时任务
│   │   └── task.py                  ←     服药提醒扫描
│   ├── storage/                     ←   文件存储
│   │   └── file_store.py            ←     保存告警截图
│   ├── security/                    ←   安全
│   │   ├── jwt_tool.py              ←     JWT 签发/解析
│   │   └── password.py              ←     密码哈希
│   └── push/                        ←   消息推送
│       └── notify.py                ←     课设可简化为打印日志
│
├── utils/                           ← 通用小工具 (尽量少放)
│   └── time_util.py
│
├── static/                          ← 静态资源 (告警截图等运行时生成)
├── ai_training/                     ← 完全独立: 数据集 + 训练脚本, 不和后端混
│   ├── dataset/
│   ├── train.py
│   └── weights/                     ← gitignore 忽略, 权重太大
│
└── sql/
    └── init.sql                     ← 手动建库建表脚本 (可选, 程序也能自动建)
```

## 每层怎么协作

```
浏览器 / 手机 App / 摄像头
        ↓ HTTP 请求
domains/auth/routes.py          ← 入口层: 收请求、用 Pydantic 校验参数、调 service
        ↓ 业务逻辑
domains/auth/service.py         ← 业务层: 直接操作 SQLAlchemy ORM (models.User)
        ↓ 数据库
models/user.py                  ← ORM 模型: 只定义字段, 没有方法 (贫血模型)
        ↓
db/session.py                   ← 提供 engine + SessionLocal 依赖注入
```

**infrastructure 层** 是反向依赖规则：domains 业务逻辑层可以调用 infrastructure，但 infrastructure 不能反过来 import domains。比如 `alert/service.py` 生成告警时调用 `infrastructure/ai/inference.py` 的推理函数，这没问题；但 inference.py 里不能 import alert/service.py。

## 接口返回格式（三人必须统一）

所有接口外层都是 `code / msg / data` 三件套，前端只看 `code` 判断成败：

```json
// 成功
{"code": 0, "msg": "ok", "data": {"device_sn": "CAM-001", "status": "online"}}

// 失败（code 直接用 HTTP 状态码：400 参数错 / 404 不存在 / 422 校验失败 / 500 服务端错）
{"code": 404, "msg": "老人 999 不存在", "data": null}
```

写接口的固定套路（照抄 `domains/device/routes.py`）：

```python
from schemas.common_schema import BaseResp, ok

@router.post("/x", response_model=BaseResp[XxxResp], summary="接口名")
def x(...):
    return ok(XxxResp(...))          # 成功：外面自动包 code=0
    raise HTTPException(404, "...")   # 失败：main.py 的异常处理器自动包 404
```

两个要点：

1. `response_model` 必须写成 `BaseResp[XxxResp]` 这种**带泛型的版本**，这样 Swagger 里还能看到 `data` 的具体字段；写成 `BaseResp` 文档里 data 就是空的。
2. 抛 `HTTPException` 就行，不要自己拼 `{"code": ...}` 字典——`main.py` 里统一注册了异常处理器，错误响应也会自动变成三件套。

## 快速开始

> 刚 clone 下来的仓库**不包含** `.venv/`、`config/settings_local.py`、`out/`，需要按下面步骤在本地生成。

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置数据库密码

复制模板文件：

```powershell
Copy-Item config\settings_local.example.py config\settings_local.py
```

然后把 `config/settings_local.py` 里的「你的密码」改成你自己的 MySQL 密码（该文件已被 gitignore 忽略，不会上传）：

```python
DATABASE_URL = "mysql+pymysql://root:你的密码@127.0.0.1:3306/elderly_care?charset=utf8mb4"
```

密码里如果有 `@ : / #` 等特殊字符，需要 URL 编码（例如 `@` 写成 `%40`）。如果没有配置，启动时会直接提示“数据库未配置……”，而不是抛出一长串连接错误。

### 3. 创建数据库

只建空库，表交给程序自动建：

```sql
CREATE DATABASE elderly_care DEFAULT CHARACTER SET utf8mb4;
```

（或者 Navicat 直接执行 `sql/init.sql`，一步建库建表）

### 4. 启动

```bash
python main.py
```

控制台看到以下输出即启动成功：

```
[启动] 数据库连接成功: mysql+pymysql://...
[启动] 已自动建表, 共 7 张
INFO:     Uvicorn running on http://127.0.0.1:5000
```

启动后可以访问：

| 地址 | 说明 |
|---|---|
| `http://127.0.0.1:5000/health` | 健康检查，验证数据库连通 |
| **`http://127.0.0.1:5000/docs`** | **自动生成的 Swagger 接口文档**（核心！B/C 同学直接打开浏览器看文档就能调接口） |
| `http://127.0.0.1:5000/redoc` | 另一种格式的文档 |

## 数据库设计（7 张表）

| 表 | 谁写 | 对应功能 |
|---|---|---|
| elder | 社康 | 新增/编辑/查询老人档案 |
| user | 注册 | 三种角色共用（elder / family / social 用 role 字段区分） |
| device | 摄像头/家属 | 心跳上报、绑定老人 |
| medicine_plan | 家属 | 新增/编辑/删除用药计划 |
| medicine_record | 老人 | 确认已服/未服 |
| alert | AI + SOS | 生成告警、保存截图、家属标记已处置 |
| work_order | 社康 | 派单 → 处置 → 归档 |

全库采用**逻辑外键**——表之间用 `elder_id`、`plan_id` 等普通字段 + 索引关联，没有数据库物理外键约束，关联正确性由业务代码保证。删除父记录前代码里要先删掉子记录（例如删用药计划前先删该计划的服药记录）。

改了模型字段后，删掉数据库里对应的表，重启 `python main.py` 即可自动重建。

## 跌倒检测模块（fallwatch）

原 `fall-watch` 项目已融入本仓库，**保留其原始包布局**，直接平铺在项目根目录；原有后端目录没有移动、改名或删除。新增内容如下：

```
smart-home-elderly-care-system/
├── fallwatch/                ← 跌倒判定包
│   ├── config.py             ←   所有可调阈值集中在此
│   ├── detector.py           ←   YOLOv8 模型加载与推理
│   ├── state_machine.py      ←   滑动窗口 + 轨迹跟踪 + 场景切换 + 冷却
│   ├── logger.py             ←   JSONL + SQLite 双写与抓拍
│   └── cli.py                ←   命令行入口
├── model/best.pt             ← 跌倒/姿态分类权重（约 22 MB，随仓库提供）
├── out/                      ← 运行产物 events.jsonl / events.db / snapshots/
├── tools/                    ← dry_run.py 标定、fetch_model.py 拉权重、query_events.py 查日志
├── app.py                    ← PyCharm 直接运行入口
├── 1-标定.cmd / 2-跑视频.cmd / 3-看日志.cmd / run.cmd
└── infrastructure/ai/
    ├── model_loader.py       ← 加载 fallwatch.Detector（供后端复用）
    └── inference.py          ← 后端调用封装：单帧检测 + 有状态 FallMonitor
```

### 安装依赖

`requirements.txt` 已合并 `ultralytics` / `opencv-python`，模型 `model/best.pt` 也已随仓库提供：

```bash
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> `out/` 是运行产物目录（事件日志、SQLite、抓拍图），仓库里不包含，第一次运行时会自动创建。如果模型文件被删了，可以执行 `python tools/fetch_model.py` 重新下载。

### 命令行使用

```bash
# 1) 标定：只看模型输出分布，不判事件
python tools/dry_run.py "视频.mp4" --truth 50

# 2) 判定并写日志
python -m fallwatch.cli --source "视频.mp4" --conf-min 0.50 --fall-frames 20 --debounce 5 --no-require-transition --cooldown 5

# 3) 查看已记录事件
python tools/query_events.py --limit 50
```

Windows 下也可直接双击 `1-标定.cmd` / `2-跑视频.cmd` / `3-看日志.cmd`。其中前两个需要把视频文件拖到脚本上，或把视频路径作为第一个参数传入，例如：

```bat
2-跑视频.cmd "D:\videos\demo.mp4"
```

### 在后端代码里调用

```python
from infrastructure.ai.inference import FallMonitor, infer_frame

# 单帧：检测 + 是否跌倒
result = infer_frame(frame_bgr)
if result.is_fall:
    ...

# 视频流：带滑动窗口 / 轨迹 / 冷却的有状态判定
monitor = FallMonitor(conf_min=0.5, fall_frames_min=20)
result = monitor.process(frame_bgr, t=timestamp_seconds)
for event in result.events:
    ...
```

模型路径默认取 `model/best.pt`，可用环境变量 `AI_MODEL_PATH` 覆盖（见 `config/settings.py`）。
