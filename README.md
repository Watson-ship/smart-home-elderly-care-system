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
├── .gitignore                       ← 密码/权重/截图等忽略
│
├── config/                          ← 基础设施配置 (不属于业务)
│   ├── settings.py                  ← 统一配置 (模板, 会上传)
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
│   ├── common_schema.py             ← 统一响应格式 BaseResp、HealthResp
│   ├── elder_schema.py              ← 老人档案请求/响应
│   └── auth_schema.py               ← 登录请求/响应
│   └── placeholder.py               ← 设备/告警/用药/工单的 schema 后面写接口时再加
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

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置数据库密码

项目根目录下创建 `config/settings_local.py`（已被 gitignore 忽略，不会上传）：

```python
DATABASE_URL = "mysql+pymysql://root:你的密码@127.0.0.1:3306/elderly_care?charset=utf8mb4&serverTimezone=Asia/Shanghai"
```

密码里如果有 `@ : / #` 等特殊字符，需要 URL 编码（例如 `@` 写成 `%40`）。

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
