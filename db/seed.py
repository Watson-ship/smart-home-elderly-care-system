"""种子数据: 首次启动时自动插入演示数据。

设计: 用 ORM 插入, 不解析 raw SQL —— 表结构变动时代码自动适配。
所有账号密码统一为 123456 (werkzeug scrypt 哈希)。
"""
from sqlalchemy.orm import Session

from models import Elder, User, Device, MedicinePlan, MedicineRecord, Alert, WorkOrder


# werkzeug generate_password_hash('123456') 生成
_HASH_123456 = "scrypt:32768:8:1$QOL8L3b9MHonwsdh$973064d8dee71544c33098bc697c6a6a6a4fcebe14b668b8452c8d5698f9b543770a95420eee5ee044a3a7dc45c19fbeaae87f65cca9473c36f6a05a12bd747e"


def seed_if_empty(session: Session) -> None:
    """7 张表任意一张为空就全量插入, 全部有数据则跳过。"""
    if session.query(Elder).count() > 0:
        print("[种子] 数据库已有数据, 跳过初始化")
        return

    print("[种子] 开始插入演示数据...")

    # ---- elder 10 条 ----
    elders = [
        Elder(id=1, elder_name="张建国", gender=1, age=78, phone="13800000001",
              address="北京市朝阳区望京花园1号楼", emergency_contact_name="张伟", emergency_contact_phone="13811110001"),
        Elder(id=2, elder_name="李秀英", gender=0, age=75, phone="13800000002",
              address="上海市浦东新区张江高科路88号", emergency_contact_name="李明", emergency_contact_phone="13822220002"),
        Elder(id=3, elder_name="王德顺", gender=1, age=82, phone="13800000003",
              address="广州市天河区珠江新城A座", emergency_contact_name="王芳", emergency_contact_phone="13833330003"),
        Elder(id=4, elder_name="赵桂兰", gender=0, age=71, phone="13800000004",
              address="深圳市南山区科技园5栋", emergency_contact_name="赵强", emergency_contact_phone="13844440004"),
        Elder(id=5, elder_name="刘德柱", gender=1, age=69, phone="13800000005",
              address="杭州市西湖区文三路100号", emergency_contact_name="刘洋", emergency_contact_phone="13855550005"),
        Elder(id=6, elder_name="陈淑芬", gender=0, age=85, phone="13800000006",
              address="成都市武侯区天府大道168号", emergency_contact_name="陈静", emergency_contact_phone="13866660006"),
        Elder(id=7, elder_name="周大福", gender=1, age=73, phone="13800000007",
              address="南京市鼓楼区中山路77号", emergency_contact_name="周杰", emergency_contact_phone="13877770007"),
        Elder(id=8, elder_name="吴巧云", gender=0, age=77, phone="13800000008",
              address="武汉市武昌区中南路99号", emergency_contact_name="吴明", emergency_contact_phone="13888880008"),
        Elder(id=9, elder_name="郑长寿", gender=1, age=80, phone="13800000009",
              address="西安市雁塔区小寨路33号", emergency_contact_name="郑华", emergency_contact_phone="13899990009"),
        Elder(id=10, elder_name="孙雪梅", gender=0, age=68, phone="13800000010",
              address="天津市和平区南京路56号", emergency_contact_name="孙磊", emergency_contact_phone="13800000010"),
    ]
    session.add_all(elders)

    # ---- user 10 条 ----
    users = [
        User(id=1, username="admin", password=_HASH_123456, role="social", elder_id=None, phone="13900000000"),
        User(id=2, username="elder_zhang", password=_HASH_123456, role="elder", elder_id=1, phone="13800000001"),
        User(id=3, username="fam_zhang", password=_HASH_123456, role="family", elder_id=1, phone="13811110001"),
        User(id=4, username="fam_li", password=_HASH_123456, role="family", elder_id=2, phone="13822220002"),
        User(id=5, username="fam_wang", password=_HASH_123456, role="family", elder_id=3, phone="13833330003"),
        User(id=6, username="fam_zhao", password=_HASH_123456, role="family", elder_id=4, phone="13844440004"),
        User(id=7, username="fam_liu", password=_HASH_123456, role="family", elder_id=5, phone="13855550005"),
        User(id=8, username="fam_chen", password=_HASH_123456, role="family", elder_id=6, phone="13866660006"),
        User(id=9, username="fam_zhou", password=_HASH_123456, role="family", elder_id=7, phone="13877770007"),
        User(id=10, username="fam_wu", password=_HASH_123456, role="family", elder_id=8, phone="13888880008"),
    ]
    session.add_all(users)

    # ---- device 10 条 ----
    devices = [
        Device(id=1, device_sn="CAM-SN-20240101-001", device_name="客厅摄像头-望京花园", elder_id=1, status="online", last_online_time="2026-10-26 09:05:00"),
        Device(id=2, device_sn="CAM-SN-20240101-002", device_name="卧室摄像头-张江高科", elder_id=2, status="online", last_online_time="2026-10-26 09:03:00"),
        Device(id=3, device_sn="CAM-SN-20240101-003", device_name="客厅摄像头-珠江新城", elder_id=3, status="offline", last_online_time=None),
        Device(id=4, device_sn="CAM-SN-20240101-004", device_name="玄关摄像头-科技园", elder_id=4, status="online", last_online_time="2026-10-26 09:01:00"),
        Device(id=5, device_sn="CAM-SN-20240101-005", device_name="客厅摄像头-文三路", elder_id=5, status="online", last_online_time="2026-10-26 08:58:00"),
        Device(id=6, device_sn="CAM-SN-20240101-006", device_name="卧室摄像头-天府大道", elder_id=6, status="online", last_online_time="2026-10-26 08:55:00"),
        Device(id=7, device_sn="CAM-SN-20240101-007", device_name="客厅摄像头-中山路", elder_id=7, status="offline", last_online_time="2026-10-25 22:30:00"),
        Device(id=8, device_sn="CAM-SN-20240101-008", device_name="客厅摄像头-中南路", elder_id=8, status="online", last_online_time="2026-10-26 09:04:00"),
        Device(id=9, device_sn="CAM-SN-20240101-009", device_name="玄关摄像头-小寨路", elder_id=9, status="online", last_online_time="2026-10-26 09:02:00"),
        Device(id=10, device_sn="CAM-SN-20240101-010", device_name="客厅摄像头-南京路", elder_id=10, status="online", last_online_time="2026-10-26 08:59:00"),
    ]
    session.add_all(devices)

    # ---- medicine_plan 10 条 ----
    plans = [
        MedicinePlan(id=1, elder_id=1, medicine_name="硝苯地平缓释片(降压)", take_time="08:00:00", cycle="daily", status=1),
        MedicinePlan(id=2, elder_id=1, medicine_name="二甲双胍(降糖)", take_time="18:00:00", cycle="daily", status=1),
        MedicinePlan(id=3, elder_id=2, medicine_name="阿司匹林肠溶片", take_time="07:30:00", cycle="daily", status=1),
        MedicinePlan(id=4, elder_id=3, medicine_name="辛伐他汀(降脂)", take_time="20:00:00", cycle="daily", status=1),
        MedicinePlan(id=5, elder_id=3, medicine_name="硝酸甘油片(应急)", take_time="08:00:00", cycle="two_day", status=1),
        MedicinePlan(id=6, elder_id=4, medicine_name="氨氯地平(降压)", take_time="09:00:00", cycle="daily", status=1),
        MedicinePlan(id=7, elder_id=5, medicine_name="氯吡格雷(抗血栓)", take_time="11:00:00", cycle="daily", status=1),
        MedicinePlan(id=8, elder_id=6, medicine_name="华法林(抗凝)", take_time="21:00:00", cycle="daily", status=0),
        MedicinePlan(id=9, elder_id=7, medicine_name="缬沙坦(降压)", take_time="08:30:00", cycle="daily", status=1),
        MedicinePlan(id=10, elder_id=8, medicine_name="阿托伐他汀(降脂)", take_time="19:30:00", cycle="daily", status=1),
    ]
    session.add_all(plans)

    # ---- medicine_record 10 条 ----
    records = [
        MedicineRecord(id=1, plan_id=1, elder_id=1, remind_date="2026-10-26", take_result="taken", record_time="2026-10-26 08:05:00"),
        MedicineRecord(id=2, plan_id=2, elder_id=1, remind_date="2026-10-25", take_result="taken", record_time="2026-10-25 18:10:00"),
        MedicineRecord(id=3, plan_id=3, elder_id=2, remind_date="2026-10-26", take_result="taken", record_time="2026-10-26 07:35:00"),
        MedicineRecord(id=4, plan_id=4, elder_id=3, remind_date="2026-10-25", take_result="taken", record_time="2026-10-25 20:00:00"),
        MedicineRecord(id=5, plan_id=5, elder_id=3, remind_date="2026-10-25", take_result="untaken", record_time="2026-10-25 08:00:00"),
        MedicineRecord(id=6, plan_id=6, elder_id=4, remind_date="2026-10-26", take_result="taken", record_time="2026-10-26 09:02:00"),
        MedicineRecord(id=7, plan_id=7, elder_id=5, remind_date="2026-10-26", take_result="untaken", record_time="2026-10-26 11:00:00"),
        MedicineRecord(id=8, plan_id=9, elder_id=7, remind_date="2026-10-26", take_result="taken", record_time="2026-10-26 08:33:00"),
        MedicineRecord(id=9, plan_id=10, elder_id=8, remind_date="2026-10-25", take_result="taken", record_time="2026-10-25 19:40:00"),
        MedicineRecord(id=10, plan_id=1, elder_id=1, remind_date="2026-10-25", take_result="taken", record_time="2026-10-25 08:03:00"),
    ]
    session.add_all(records)

    # ---- alert 10 条 ----
    alerts = [
        Alert(id=1, elder_id=1, device_id=1, alert_type="fall", screenshot_path="screenshots/alert_20261025_001.jpg",
              is_handled=1, handled_by=3, handle_time="2026-10-25 14:30:00", create_time="2026-10-25 14:15:00"),
        Alert(id=2, elder_id=2, device_id=2, alert_type="static", screenshot_path="screenshots/alert_20261025_002.jpg",
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-25 16:20:00"),
        Alert(id=3, elder_id=4, device_id=4, alert_type="sos", screenshot_path=None,
              is_handled=1, handled_by=6, handle_time="2026-10-26 07:45:00", create_time="2026-10-26 07:30:00"),
        Alert(id=4, elder_id=5, device_id=5, alert_type="fall", screenshot_path="screenshots/alert_20261026_001.jpg",
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-26 06:00:00"),
        Alert(id=5, elder_id=6, device_id=6, alert_type="static", screenshot_path="screenshots/alert_20261026_002.jpg",
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-26 08:15:00"),
        Alert(id=6, elder_id=7, device_id=None, alert_type="sos", screenshot_path=None,
              is_handled=1, handled_by=9, handle_time="2026-10-25 20:00:00", create_time="2026-10-25 19:45:00"),
        Alert(id=7, elder_id=8, device_id=8, alert_type="fall", screenshot_path="screenshots/alert_20261024_001.jpg",
              is_handled=1, handled_by=10, handle_time="2026-10-24 10:30:00", create_time="2026-10-24 10:15:00"),
        Alert(id=8, elder_id=9, device_id=9, alert_type="static", screenshot_path="screenshots/alert_20261025_003.jpg",
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-25 11:00:00"),
        Alert(id=9, elder_id=10, device_id=10, alert_type="fall", screenshot_path="screenshots/alert_20261026_003.jpg",
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-26 05:30:00"),
        Alert(id=10, elder_id=3, device_id=None, alert_type="sos", screenshot_path=None,
              is_handled=0, handled_by=None, handle_time=None, create_time="2026-10-26 07:00:00"),
    ]
    session.add_all(alerts)

    # ---- work_order 10 条 ----
    orders = [
        WorkOrder(id=1, alert_id=1, elder_id=1, order_status="archived", handler_id=1,
                  handle_content="已上门确认, 老人轻微擦伤, 已送社区医院处理完毕, 家属到场。",
                  assign_time="2026-10-25 14:20:00", archive_time="2026-10-25 17:00:00", create_time="2026-10-25 14:16:00"),
        WorkOrder(id=2, alert_id=2, elder_id=2, order_status="processing", handler_id=1,
                  handle_content=None, assign_time="2026-10-25 16:30:00", archive_time=None, create_time="2026-10-25 16:21:00"),
        WorkOrder(id=3, alert_id=3, elder_id=4, order_status="archived", handler_id=1,
                  handle_content="老人误触 SOS 按钮, 视频确认无异常已告知家属。",
                  assign_time="2026-10-26 07:35:00", archive_time="2026-10-26 08:30:00", create_time="2026-10-26 07:31:00"),
        WorkOrder(id=4, alert_id=4, elder_id=5, order_status="pending", handler_id=None,
                  handle_content=None, assign_time=None, archive_time=None, create_time="2026-10-26 06:01:00"),
        WorkOrder(id=5, alert_id=5, elder_id=6, order_status="pending", handler_id=None,
                  handle_content=None, assign_time=None, archive_time=None, create_time="2026-10-26 08:16:00"),
        WorkOrder(id=6, alert_id=6, elder_id=7, order_status="archived", handler_id=1,
                  handle_content="老人身体不适自行按下求助, 已联系 120 送医, 诊断为低血糖。",
                  assign_time="2026-10-25 19:50:00", archive_time="2026-10-26 09:00:00", create_time="2026-10-25 19:46:00"),
        WorkOrder(id=7, alert_id=7, elder_id=8, order_status="archived", handler_id=1,
                  handle_content="老人早晨起身滑倒, 左臂淤青, 已做检查无大碍。",
                  assign_time="2026-10-24 10:20:00", archive_time="2026-10-24 14:00:00", create_time="2026-10-24 10:16:00"),
        WorkOrder(id=8, alert_id=8, elder_id=9, order_status="pending", handler_id=None,
                  handle_content=None, assign_time=None, archive_time=None, create_time="2026-10-25 11:01:00"),
        WorkOrder(id=9, alert_id=9, elder_id=10, order_status="processing", handler_id=1,
                  handle_content=None, assign_time="2026-10-26 05:45:00", archive_time=None, create_time="2026-10-26 05:31:00"),
        WorkOrder(id=10, alert_id=10, elder_id=3, order_status="pending", handler_id=None,
                  handle_content=None, assign_time=None, archive_time=None, create_time="2026-10-26 07:01:00"),
    ]
    session.add_all(orders)

    session.commit()
    print("[种子] ✅ 演示数据插入完成, 共 7 张表 x 10 条")
    print("[种子] 所有账号密码统一为: 123456")
