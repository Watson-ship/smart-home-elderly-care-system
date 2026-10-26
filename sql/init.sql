-- ============================================================
-- 居家老人监测系统 - 数据库初始化脚本
-- 环境: MySQL 8.0+, 字符集 utf8mb4
-- 用法: 方式一: 在 Navicat / 命令行里直接执行本文件(建库+建表+初始化数据)
--      方式二: 不执行也行, 项目首次运行会通过模型自动建表
--
-- 设计: 全库用「逻辑外键」—— 表之间只用字段(如 elder_id)关联并建索引,
--       不建数据库物理外键约束, 关联是否正确由 Python 代码自己保证
-- ============================================================

CREATE DATABASE IF NOT EXISTS elderly_care
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci;

USE elderly_care;

-- ------------------------------------------------------------
-- 1. elder 老人档案表 (社康工作人员录入/维护)
-- ------------------------------------------------------------
CREATE TABLE elder (
    id                      INT AUTO_INCREMENT COMMENT '老人id' PRIMARY KEY,
    elder_name              VARCHAR(50)  NOT NULL COMMENT '老人姓名',
    gender                  TINYINT      NULL COMMENT '性别 0-女 1-男',
    age                     INT          NULL COMMENT '年龄',
    phone                   VARCHAR(20)  NULL COMMENT '老人联系电话',
    address                 VARCHAR(200) NULL COMMENT '住址',
    emergency_contact_name  VARCHAR(50)  NULL COMMENT '紧急联系人姓名',
    emergency_contact_phone VARCHAR(20)  NULL COMMENT '紧急联系人电话',
    create_time             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '老人档案表';

-- ------------------------------------------------------------
-- 2. user 用户表 (同一张表分角色: elder老人 / family家属 / social社康)
-- ------------------------------------------------------------
CREATE TABLE `user` (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL COMMENT '登录账号',
    password    VARCHAR(255) NOT NULL COMMENT '密码哈希(用 werkzeug 的 generate_password_hash 加密后存储, 不存明文)',
    role        ENUM('elder', 'family', 'social') NOT NULL COMMENT '角色: elder老人 / family家属 / social社康',
    elder_id    INT          NULL COMMENT '关联老人id: 家属=被绑定的老人; 老人=本人; 社康为空',
    phone       VARCHAR(20)  NULL COMMENT '手机号',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_username (username),
    KEY idx_elder_id (elder_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '用户表(老人/家属/社康工作人员)';

-- ------------------------------------------------------------
-- 3. device 摄像头设备表
-- ------------------------------------------------------------
CREATE TABLE device (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    device_sn        VARCHAR(64)  NOT NULL COMMENT '设备序列号(摄像头联网上报时的唯一身份标识, 防止只靠自增id被冒充)',
    device_name      VARCHAR(100) NOT NULL COMMENT '设备名称',
    elder_id         INT          NULL COMMENT '绑定的老人id',
    status           ENUM('online', 'offline') NOT NULL DEFAULT 'offline' COMMENT '在线状态',
    last_online_time DATETIME     NULL COMMENT '最后在线时间(摄像头定期上报, 超时未收到心跳就置为offline)',
    create_time      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_device_sn (device_sn),
    KEY idx_elder_id (elder_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '摄像头设备表';

-- ------------------------------------------------------------
-- 4. medicine_plan 用药计划表 (家属新增/编辑/删除)
-- ------------------------------------------------------------
CREATE TABLE medicine_plan (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    elder_id      INT          NOT NULL COMMENT '老人id',
    medicine_name VARCHAR(100) NOT NULL COMMENT '药品名',
    take_time     TIME         NOT NULL COMMENT '每天几点服药',
    cycle         ENUM('daily', 'two_day') NOT NULL DEFAULT 'daily' COMMENT '周期: daily每天 / two_day隔天',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    create_time   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    KEY idx_elder_id (elder_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '用药计划表';

-- ------------------------------------------------------------
-- 5. medicine_record 服药确认记录表 (老人点已服/未服时生成)
--    remind_date + 联合唯一索引: 保证「某计划某一天」只有一条记录, 防重复确认
--    逻辑外键注意: 删除用药计划时, 代码里要先把该计划的服药记录删掉
-- ------------------------------------------------------------
CREATE TABLE medicine_record (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    plan_id     INT      NOT NULL COMMENT '关联用药计划id',
    elder_id    INT      NOT NULL COMMENT '老人id',
    remind_date DATE     NOT NULL COMMENT '这剂药属于哪一天(用来区分每天的提醒)',
    take_result ENUM('taken', 'untaken') NOT NULL COMMENT 'taken已服药 / untaken未服药',
    record_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '确认时间',
    UNIQUE KEY uk_plan_date (plan_id, remind_date),
    KEY idx_elder_id (elder_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '服药确认记录表';

-- ------------------------------------------------------------
-- 6. alert 告警表 (AI跌倒/长时间静止 + 老人一键SOS)
-- ------------------------------------------------------------
CREATE TABLE alert (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    elder_id        INT          NOT NULL COMMENT '老人id',
    device_id       INT          NULL COMMENT '触发告警的摄像头id(SOS告警可能为空)',
    alert_type      ENUM('fall', 'static', 'sos') NOT NULL COMMENT 'fall跌倒 / static长时间静止 / sos一键求助',
    screenshot_path VARCHAR(500) NULL COMMENT '告警截图保存路径(存项目内相对路径, 不存系统绝对路径)',
    is_handled      TINYINT      NOT NULL DEFAULT 0 COMMENT '0未处置 1已处置(家属标记)',
    handled_by      INT          NULL COMMENT '处置人用户id(家属或社康)',
    handle_time     DATETIME     NULL COMMENT '处置时间',
    create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    KEY idx_elder_time (elder_id, create_time),
    KEY idx_device_id (device_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '告警表';

-- ------------------------------------------------------------
-- 7. work_order 社康工单表 (派单 -> 处置 -> 归档)
--    alert_id 加唯一索引: 一条告警只生成一张工单
-- ------------------------------------------------------------
CREATE TABLE work_order (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    alert_id       INT      NOT NULL COMMENT '关联告警id',
    elder_id       INT      NOT NULL COMMENT '老人id',
    order_status   ENUM('pending', 'processing', 'archived') NOT NULL DEFAULT 'pending' COMMENT 'pending待派单 / processing处置中 / archived已归档',
    handler_id     INT      NULL COMMENT '处理社工的用户id',
    handle_content TEXT     NULL COMMENT '工单处置记录内容',
    assign_time    DATETIME NULL COMMENT '派单时间',
    archive_time   DATETIME NULL COMMENT '归档时间',
    create_time    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_alert_id (alert_id),
    KEY idx_handler_id (handler_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '社康工单表';


-- ============================================================
-- 初始化演示数据
-- 所有账号密码统一为: 123456  (werkzeug scrypt 哈希)
-- ============================================================

-- ---------- elder 老人档案 10 条 ----------
INSERT INTO elder (id, elder_name, gender, age, phone, address, emergency_contact_name, emergency_contact_phone, create_time) VALUES
(1, '张建国', 1, 78, '13800000001', '北京市朝阳区望京花园1号楼', '张伟', '13811110001', NOW()),
(2, '李秀英', 0, 75, '13800000002', '上海市浦东新区张江高科路88号', '李明', '13822220002', NOW()),
(3, '王德顺', 1, 82, '13800000003', '广州市天河区珠江新城A座', '王芳', '13833330003', NOW()),
(4, '赵桂兰', 0, 71, '13800000004', '深圳市南山区科技园5栋', '赵强', '13844440004', NOW()),
(5, '刘德柱', 1, 69, '13800000005', '杭州市西湖区文三路100号', '刘洋', '13855550005', NOW()),
(6, '陈淑芬', 0, 85, '13800000006', '成都市武侯区天府大道168号', '陈静', '13866660006', NOW()),
(7, '周大福', 1, 73, '13800000007', '南京市鼓楼区中山路77号', '周杰', '13877770007', NOW()),
(8, '吴巧云', 0, 77, '13800000008', '武汉市武昌区中南路99号', '吴明', '13888880008', NOW()),
(9, '郑长寿', 1, 80, '13800000009', '西安市雁塔区小寨路33号', '郑华', '13899990009', NOW()),
(10, '孙雪梅', 0, 68, '13800000010', '天津市和平区南京路56号', '孙磊', '13800000010', NOW());

-- ---------- user 用户 10 条 ----------
-- 密码统一 123456
INSERT INTO `user` (id, username, password, role, elder_id, phone, create_time) VALUES
(1,  'admin',      'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'social', NULL, '13900000000', NOW()),
(2,  'elder_zhang', 'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'elder', 1,    '13800000001', NOW()),
(3,  'fam_zhang',   'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 1,    '13811110001', NOW()),
(4,  'fam_li',      'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 2,    '13822220002', NOW()),
(5,  'fam_wang',    'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 3,    '13833330003', NOW()),
(6,  'fam_zhao',    'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 4,    '13844440004', NOW()),
(7,  'fam_liu',     'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 5,    '13855550005', NOW()),
(8,  'fam_chen',    'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 6,    '13866660006', NOW()),
(9,  'fam_zhou',    'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 7,    '13877770007', NOW()),
(10, 'fam_wu',      'scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e', 'family', 8,    '13888880008', NOW());

-- ---------- device 摄像头 10 条 ----------
INSERT INTO device (id, device_sn, device_name, elder_id, status, last_online_time, create_time) VALUES
(1, 'CAM-SN-20240101-001', '客厅摄像头-望京花园', 1, 'online',  '2026-10-26 09:05:00', NOW()),
(2, 'CAM-SN-20240101-002', '卧室摄像头-张江高科', 2, 'online',  '2026-10-26 09:03:00', NOW()),
(3, 'CAM-SN-20240101-003', '客厅摄像头-珠江新城', 3, 'offline', NULL,                 NOW()),
(4, 'CAM-SN-20240101-004', '玄关摄像头-科技园',   4, 'online',  '2026-10-26 09:01:00', NOW()),
(5, 'CAM-SN-20240101-005', '客厅摄像头-文三路',   5, 'online',  '2026-10-26 08:58:00', NOW()),
(6, 'CAM-SN-20240101-006', '卧室摄像头-天府大道', 6, 'online',  '2026-10-26 08:55:00', NOW()),
(7, 'CAM-SN-20240101-007', '客厅摄像头-中山路',   7, 'offline', '2026-10-25 22:30:00', NOW()),
(8, 'CAM-SN-20240101-008', '客厅摄像头-中南路',   8, 'online',  '2026-10-26 09:04:00', NOW()),
(9, 'CAM-SN-20240101-009', '玄关摄像头-小寨路',   9, 'online',  '2026-10-26 09:02:00', NOW()),
(10,'CAM-SN-20240101-010', '客厅摄像头-南京路',   10,'online',  '2026-10-26 08:59:00', NOW());

-- ---------- medicine_plan 用药计划 10 条 ----------
INSERT INTO medicine_plan (id, elder_id, medicine_name, take_time, cycle, status, create_time) VALUES
(1,  1, '硝苯地平缓释片(降压)',  '08:00:00', 'daily',   1, NOW()),
(2,  1, '二甲双胍(降糖)',        '18:00:00', 'daily',   1, NOW()),
(3,  2, '阿司匹林肠溶片',        '07:30:00', 'daily',   1, NOW()),
(4,  3, '辛伐他汀(降脂)',        '20:00:00', 'daily',   1, NOW()),
(5,  3, '硝酸甘油片(应急)',      '08:00:00', 'two_day', 1, NOW()),
(6,  4, '氨氯地平(降压)',        '09:00:00', 'daily',   1, NOW()),
(7,  5, '氯吡格雷(抗血栓)',      '11:00:00', 'daily',   1, NOW()),
(8,  6, '华法林(抗凝)',          '21:00:00', 'daily',   0, NOW()),
(9,  7, '缬沙坦(降压)',          '08:30:00', 'daily',   1, NOW()),
(10, 8, '阿托伐他汀(降脂)',      '19:30:00', 'daily',   1, NOW());

-- ---------- medicine_record 服药记录 10 条 ----------
INSERT INTO medicine_record (id, plan_id, elder_id, remind_date, take_result, record_time) VALUES
(1,  1,  1, '2026-10-26', 'taken',   '2026-10-26 08:05:00'),
(2,  2,  1, '2026-10-25', 'taken',   '2026-10-25 18:10:00'),
(3,  3,  2, '2026-10-26', 'taken',   '2026-10-26 07:35:00'),
(4,  4,  3, '2026-10-25', 'taken',   '2026-10-25 20:00:00'),
(5,  5,  3, '2026-10-25', 'untaken', '2026-10-25 08:00:00'),
(6,  6,  4, '2026-10-26', 'taken',   '2026-10-26 09:02:00'),
(7,  7,  5, '2026-10-26', 'untaken', '2026-10-26 11:00:00'),
(8,  9,  7, '2026-10-26', 'taken',   '2026-10-26 08:33:00'),
(9,  10, 8, '2026-10-25', 'taken',   '2026-10-25 19:40:00'),
(10, 1,  1, '2026-10-25', 'taken',   '2026-10-25 08:03:00');

-- ---------- alert 告警 10 条 ----------
INSERT INTO alert (id, elder_id, device_id, alert_type, screenshot_path, is_handled, handled_by, handle_time, create_time) VALUES
(1,  1,  1, 'fall',   'screenshots/alert_20261025_001.jpg', 1, 3, '2026-10-25 14:30:00', '2026-10-25 14:15:00'),
(2,  2,  2, 'static', 'screenshots/alert_20261025_002.jpg', 0, NULL, NULL,                   '2026-10-25 16:20:00'),
(3,  4,  4, 'sos',    NULL,                                  1, 6, '2026-10-26 07:45:00', '2026-10-26 07:30:00'),
(4,  5,  5, 'fall',   'screenshots/alert_20261026_001.jpg', 0, NULL, NULL,                   '2026-10-26 06:00:00'),
(5,  6,  6, 'static', 'screenshots/alert_20261026_002.jpg', 0, NULL, NULL,                   '2026-10-26 08:15:00'),
(6,  7,  NULL,'sos',   NULL,                                  1, 9, '2026-10-25 20:00:00', '2026-10-25 19:45:00'),
(7,  8,  8, 'fall',   'screenshots/alert_20261024_001.jpg', 1, 10,'2026-10-24 10:30:00', '2026-10-24 10:15:00'),
(8,  9,  9, 'static', 'screenshots/alert_20261025_003.jpg', 0, NULL, NULL,                   '2026-10-25 11:00:00'),
(9,  10, 10,'fall',   'screenshots/alert_20261026_003.jpg', 0, NULL, NULL,                   '2026-10-26 05:30:00'),
(10, 3,  NULL,'sos',   NULL,                                  0, NULL, NULL,                   '2026-10-26 07:00:00');

-- ---------- work_order 工单 10 条 ----------
INSERT INTO work_order (id, alert_id, elder_id, order_status, handler_id, handle_content, assign_time, archive_time, create_time) VALUES
(1, 1,  1,  'archived',  1, '已上门确认, 老人轻微擦伤, 已送社区医院处理完毕, 家属到场。', '2026-10-25 14:20:00', '2026-10-25 17:00:00', '2026-10-25 14:16:00'),
(2, 2,  2,  'processing',1, NULL, '2026-10-25 16:30:00', NULL,                   '2026-10-25 16:21:00'),
(3, 3,  4,  'archived',  1, '老人误触 SOS 按钮, 视频确认无异常已告知家属。',        '2026-10-26 07:35:00', '2026-10-26 08:30:00', '2026-10-26 07:31:00'),
(4, 4,  5,  'pending',   NULL, NULL, NULL,                   NULL,                   '2026-10-26 06:01:00'),
(5, 5,  6,  'pending',   NULL, NULL, NULL,                   NULL,                   '2026-10-26 08:16:00'),
(6, 6,  7,  'archived',  1, '老人身体不适自行按下求助, 已联系 120 送医, 诊断为低血糖。', '2026-10-25 19:50:00', '2026-10-26 09:00:00', '2026-10-25 19:46:00'),
(7, 7,  8,  'archived',  1, '老人早晨起身滑倒, 左臂淤青, 已做检查无大碍。',          '2026-10-24 10:20:00', '2026-10-24 14:00:00', '2026-10-24 10:16:00'),
(8, 8,  9,  'pending',   NULL, NULL, NULL,                   NULL,                   '2026-10-25 11:01:00'),
(9, 9,  10, 'processing',1, NULL, '2026-10-26 05:45:00', NULL,                   '2026-10-26 05:31:00'),
(10,10, 3,  'pending',   NULL, NULL, NULL,                   NULL,                   '2026-10-26 07:01:00');
