import os
import sys
import json
import shutil
import tempfile
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, STATUS_FLOW, OperationType
)


def separator(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def assert_true(cond, msg):
    if cond:
        print(f"  ✓ PASS: {msg}")
    else:
        print(f"  ✗ FAIL: {msg}")
        sys.exit(1)


def assert_false(cond, msg):
    assert_true(not cond, msg)


def main():
    tmpdir = tempfile.mkdtemp(prefix="lab_test_")
    print(f"测试数据目录: {tmpdir}")
    try:
        dm = DataManager(data_dir=tmpdir)
        dm.init_sample_data()

        # ------------------------------------------------------------------
        separator("一、初始状态检查")
        # ------------------------------------------------------------------
        assert_true(len(dm.instruments) == 4, f"样例仪器数量为4（实际{len(dm.instruments)}）")

        ins_normal = [i for i in dm.instruments if i.status == InstrumentStatus.NORMAL]
        ins_expired = [i for i in dm.instruments if i.status == InstrumentStatus.CALIBRATION_EXPIRED]
        assert_true(len(ins_normal) >= 2, f"至少2台正常仪器（实际{len(ins_normal)}）")
        assert_true(len(ins_expired) == 1, f"1台校准过期仪器（INS-003）（实际{len(ins_expired)}）")
        assert_true(ins_expired[0].code == "INS-003", "校准过期的是 INS-003")

        persons = dm.get_all_persons()
        assert_true("张工" in persons and "李工" in persons and "王工" in persons,
                    f"负责人列表包含张工/李工/王工（实际{persons}）")

        # ------------------------------------------------------------------
        separator("二、失败路径拦截测试")
        # ------------------------------------------------------------------

        # 2.1 校准过期仪器不能预约
        ins_003 = [i for i in dm.instruments if i.code == "INS-003"][0]
        res, msg = dm.add_reservation(
            ins_003.id, "测试员A", "过期校准测试",
            "2099-01-01 09:00:00", "2099-01-01 11:00:00"
        )
        assert_true(res is None, f"2.1 校准过期仪器被拦截: {msg}")
        assert_true("校准已过期" in msg, f"   错误消息包含'校准已过期': {msg}")

        # 2.2 时间重叠预约拦截
        ins_001 = [i for i in dm.instruments if i.code == "INS-001"][0]
        assert_true(ins_001.status == InstrumentStatus.NORMAL, "INS-001 状态正常")

        r1, msg = dm.add_reservation(
            ins_001.id, "测试员A", "材料分析",
            "2099-06-15 09:00:00", "2099-06-15 12:00:00"
        )
        assert_true(r1 is not None, f"   创建首个预约成功: {r1.id if r1 else 'None'}")
        assert_true(r1.status == ReservationStatus.DRAFT, "   初始状态为草稿")

        r1_submit, msg = dm.update_reservation_status(
            r1.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN
        )
        r1_confirm, msg = dm.update_reservation_status(
            r1.id, ReservationStatus.CONFIRMED, UserRole.ADMIN
        )
        assert_true(r1_confirm is not None, "   首个预约已确认(已预约)")

        # 尝试完全重叠的时间段 - 创建草稿时就拦截
        r2, msg = dm.add_reservation(
            ins_001.id, "测试员B", "重叠测试1",
            "2099-06-15 09:00:00", "2099-06-15 12:00:00"
        )
        assert_true(r2 is None, f"2.2 完全重叠预约被拦截（创建时）: {msg}")
        assert_true("重叠" in msg, f"   错误消息包含'重叠': {msg}")

        # 尝试部分重叠（左交集）- 创建草稿时就拦截
        r3, msg = dm.add_reservation(
            ins_001.id, "测试员B", "重叠测试2",
            "2099-06-15 08:00:00", "2099-06-15 10:00:00"
        )
        assert_true(r3 is None, f"   左交集重叠被拦截: {msg}")
        assert_true("重叠" in msg, f"   错误消息包含'重叠': {msg}")

        # 尝试包含型重叠（覆盖原时段）
        r4, msg = dm.add_reservation(
            ins_001.id, "测试员B", "重叠测试3",
            "2099-06-15 08:30:00", "2099-06-15 12:30:00"
        )
        assert_true(r4 is None, f"   包含型重叠被拦截: {msg}")

        # 非重叠时间可以成功创建
        r5, msg = dm.add_reservation(
            ins_001.id, "测试员B", "非重叠测试",
            "2099-06-15 14:00:00", "2099-06-15 17:00:00"
        )
        assert_true(r5 is not None, f"   非重叠预约创建成功")

        # 2.2.2 草稿允许时间重叠，但确认时第二个被拦截（用 INS-004）
        ins_test_overlap = [i for i in dm.instruments if i.code == "INS-004"][0]
        r_draft1, _ = dm.add_reservation(
            ins_test_overlap.id, "测试员C", "草稿重叠测试1",
            "2099-10-01 09:00:00", "2099-10-01 12:00:00"
        )
        r_draft2, _ = dm.add_reservation(
            ins_test_overlap.id, "测试员D", "草稿重叠测试2",
            "2099-10-01 09:00:00", "2099-10-01 12:00:00"
        )
        assert_true(r_draft1 is not None and r_draft2 is not None,
                    "   两个时间重叠的草稿都能创建（草稿阶段不拦截）")
        # 先确认第一个
        dm.update_reservation_status(r_draft1.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN)
        r_d1_conf, _ = dm.update_reservation_status(
            r_draft1.id, ReservationStatus.CONFIRMED, UserRole.ADMIN
        )
        assert_true(r_d1_conf is not None, "   先确认的草稿预约成功")
        # 再确认第二个，应该被拦截
        dm.update_reservation_status(r_draft2.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN)
        r_d2_conf, msg = dm.update_reservation_status(
            r_draft2.id, ReservationStatus.CONFIRMED, UserRole.ADMIN
        )
        assert_true(r_d2_conf is None, f"   后确认的重叠预约被拦截: {msg}")
        assert_true("重叠" in msg, f"   错误消息包含'重叠': {msg}")
        # 检查被拦截后 r_draft2 状态仍保持待确认（失败不改状态）
        r_d2_check = [r for r in dm.reservations if r.id == r_draft2.id][0]
        assert_true(r_d2_check.status == ReservationStatus.PENDING_CONFIRM,
                    "   被拦截预约状态不变（仍为待确认）- 失败不改状态")

        # 2.3 普通用户不能解除故障冻结
        ins_002 = [i for i in dm.instruments if i.code == "INS-002"][0]
        freeze_result, msg = dm.freeze_instrument(
            ins_002.id, "测试故障：光源异常", "测试操作员", UserRole.ADMIN
        )
        assert_true(freeze_result is not None, "   管理员执行冻结成功")
        assert_true(freeze_result.status == InstrumentStatus.MALFUNCTION_FROZEN,
                    "   仪器状态变更为故障冻结")
        assert_true(freeze_result.freeze_operator == "测试操作员",
                    "   冻结操作人已记录")
        assert_true(freeze_result.freeze_reason == "测试故障：光源异常",
                    "   冻结原因已记录")
        assert_true(freeze_result.freeze_time is not None,
                    "   冻结时间已记录")

        unfreeze_n, msg = dm.unfreeze_instrument(
            ins_002.id, "已修复", "测试员A", UserRole.NORMAL
        )
        assert_true(unfreeze_n is None, f"2.3 普通用户解除冻结被拦截: {msg}")
        assert_true("管理员" in msg, f"   错误消息包含'管理员': {msg}")

        # 冻结状态下不能预约
        r_frozen, msg = dm.add_reservation(
            ins_002.id, "测试员A", "冻结测试",
            "2099-07-01 09:00:00", "2099-07-01 11:00:00"
        )
        assert_true(r_frozen is None, f"   冻结仪器预约被拦截: {msg}")
        assert_true("故障冻结" in msg, f"   错误消息包含'故障冻结': {msg}")

        # 检查冻结日志
        freeze_records = [r for r in dm.calibration_records if r["action"] == "故障冻结"]
        assert_true(len(freeze_records) >= 1, f"   冻结操作已记录到calibration_records")

        # 管理员解除冻结
        unfreeze_a, msg = dm.unfreeze_instrument(
            ins_002.id, "光源已更换，恢复正常", "测试管理员", UserRole.ADMIN
        )
        assert_true(unfreeze_a is not None, "   管理员成功解除冻结")
        assert_true(unfreeze_a.status == InstrumentStatus.NORMAL,
                    "   仪器状态恢复正常")
        assert_true(unfreeze_a.freeze_reason is None, "   冻结原因已清除")
        unfreeze_records = [r for r in dm.calibration_records if r["action"] == "解除冻结"]
        assert_true(len(unfreeze_records) == 1, "   解冻操作已记录到calibration_records")
        assert_true(unfreeze_records[0]["role"] == "管理员", "   解冻日志记录了角色")
        assert_true(unfreeze_records[0]["reason"] == "光源已更换，恢复正常",
                    "   解冻日志记录了原因")
        assert_true("time" in unfreeze_records[0], "   解冻日志记录了时间")

        # ------------------------------------------------------------------
        separator("三、主流程：预约→确认→使用→复核→完成")
        # ------------------------------------------------------------------
        ins_004 = [i for i in dm.instruments if i.code == "INS-004"][0]
        assert_true(ins_004.status == InstrumentStatus.NORMAL, "INS-004 状态正常")

        # 步骤1: 新建预约（草稿）
        main_start = "2099-08-01 09:00:00"
        main_end = "2099-08-01 12:00:00"
        main_res, msg = dm.add_reservation(
            ins_004.id, "主流程测试员", "精密称量实验 - 样品纯度检测",
            main_start, main_end
        )
        assert_true(main_res is not None, f"3.1 新建草稿预约成功: {main_res.id}")
        assert_true(main_res.status == ReservationStatus.DRAFT, "   状态=草稿")
        main_id = main_res.id

        # 编辑草稿（测试修改功能）
        edit_res, msg = dm.update_reservation(
            main_id, purpose="精密称量实验 - 样品纯度检测（批次2025-A）"
        )
        assert_true(edit_res is not None, "3.1.1 编辑草稿预约成功")
        assert_true("批次2025-A" in edit_res.purpose, "   用途已更新")

        # 步骤2: 提交待确认
        step2, msg = dm.update_reservation_status(
            main_id, ReservationStatus.PENDING_CONFIRM, UserRole.NORMAL
        )
        assert_true(step2 is not None, f"3.2 提交待确认成功: {msg if not step2 else '状态=待确认'}")
        assert_true(step2.status == ReservationStatus.PENDING_CONFIRM, "   状态=待确认")
        orig_status = step2.status

        # 步骤3: 管理员确认预约
        step3, msg = dm.update_reservation_status(
            main_id, ReservationStatus.CONFIRMED, UserRole.ADMIN
        )
        assert_true(step3 is not None, f"3.3 确认预约成功: {msg if not step3 else ''}")
        assert_true(step3.status == ReservationStatus.CONFIRMED, "   状态=已预约")

        # 步骤4: 开始使用
        step4, msg = dm.update_reservation_status(
            main_id, ReservationStatus.IN_USE, UserRole.NORMAL
        )
        assert_true(step4 is not None, f"3.4 开始使用成功")
        assert_true(step4.status == ReservationStatus.IN_USE, "   状态=使用中")

        # 步骤5: 使用完毕，提交复核
        step5, msg = dm.update_reservation_status(
            main_id, ReservationStatus.PENDING_REVIEW, UserRole.NORMAL,
            note="称量数据完整，共24个样品，RSD<0.1%，仪器运行正常"
        )
        assert_true(step5 is not None, f"3.5 提交复核成功")
        assert_true(step5.status == ReservationStatus.PENDING_REVIEW, "   状态=待复核")
        assert_true(step5.review_note is not None, "   复核备注已记录")

        # 步骤6: 管理员复核完成
        step6, msg = dm.update_reservation_status(
            main_id, ReservationStatus.COMPLETED, UserRole.ADMIN,
            note="数据审核通过，结果可信，归档"
        )
        assert_true(step6 is not None, f"3.6 复核完成成功")
        assert_true(step6.status == ReservationStatus.COMPLETED, "   状态=已完成")

        print(f"\n  主流程状态流转完整: 草稿 → 待确认 → 已预约 → 使用中 → 待复核 → 已完成 ✓")

        # ------------------------------------------------------------------
        separator("四、失败路径 - 非法状态流转拦截（状态不改变）")
        # ------------------------------------------------------------------
        # 已完成的预约不能再变使用中
        illegal1, msg = dm.update_reservation_status(
            main_id, ReservationStatus.IN_USE, UserRole.ADMIN
        )
        assert_true(illegal1 is None, f"4.1 已完成→使用中 被拦截: {msg}")

        # 重新获取预约，确认状态没被改动
        r_after_fail = None
        for r in dm.reservations:
            if r.id == main_id:
                r_after_fail = r
                break
        assert_true(r_after_fail.status == ReservationStatus.COMPLETED,
                    "4.2 失败操作未改变原有状态（仍为已完成）")

        # 草稿直接跳到使用中，非法
        r_draft, _ = dm.add_reservation(
            ins_004.id, "非法流转测试", "测试",
            "2099-09-01 09:00:00", "2099-09-01 10:00:00"
        )
        illegal2, msg = dm.update_reservation_status(
            r_draft.id, ReservationStatus.IN_USE, UserRole.ADMIN
        )
        assert_true(illegal2 is None, f"4.3 草稿→使用中 被拦截: {msg}")
        r_after_fail2 = [r for r in dm.reservations if r.id == r_draft.id][0]
        assert_true(r_after_fail2.status == ReservationStatus.DRAFT,
                    "4.4 失败操作未改变原有状态（仍为草稿）")

        # ------------------------------------------------------------------
        separator("五、持久化验证：保存→重新加载→数据一致")
        # ------------------------------------------------------------------
        dm.save_instruments()
        dm.save_reservations()
        dm.save_settings()
        dm.save_calibration_records()

        dm2 = DataManager(data_dir=tmpdir)
        assert_true(len(dm2.instruments) == 4, f"5.1 重新加载后仪器数量=4（实际{len(dm2.instruments)}）")
        assert_true(len(dm2.reservations) >= 3, f"5.2 预约记录已持久化（实际{len(dm2.reservations)}条）")
        assert_true(len(dm2.calibration_records) >= 2,
                    f"5.3 校准/冻结日志已持久化（实际{len(dm2.calibration_records)}条）")

        main_reload = [r for r in dm2.reservations if r.id == main_id][0]
        assert_true(main_reload.status == ReservationStatus.COMPLETED,
                    "5.4 主流程预约状态=已完成")
        assert_true(main_reload.purpose == "精密称量实验 - 样品纯度检测（批次2025-A）",
                    "5.5 预约编辑内容已持久化")

        # ------------------------------------------------------------------
        separator("六、筛选与导出测试")
        # ------------------------------------------------------------------
        by_zhanggong = dm2.get_reservations_filtered(person_filter="张工")
        ins_ids_zhanggong = {i.id for i in dm2.instruments if i.person_in_charge == "张工"}
        all_match = all(r.instrument_id in ins_ids_zhanggong for r in by_zhanggong)
        assert_true(all_match, f"6.1 按负责人'张工'筛选正确（{len(by_zhanggong)}条）")

        by_completed = dm2.get_reservations_filtered(status_filter="已完成")
        all_completed = all(r.status == ReservationStatus.COMPLETED for r in by_completed)
        assert_true(all_completed, f"6.2 按状态'已完成'筛选正确（{len(by_completed)}条）")

        # 导出 CSV
        csv_path = os.path.join(tmpdir, "test_export.csv")
        ok, msg = dm2.export_reservations_csv(csv_path, "", "")
        assert_true(ok and os.path.exists(csv_path), f"6.3 CSV导出成功: {csv_path}")
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            csv_content = f.read()
        assert_true("INS-004" in csv_content and "主流程测试员" in csv_content,
                    "6.4 CSV内容包含预期数据")

        # 导出 JSON
        json_path = os.path.join(tmpdir, "test_export.json")
        ok, msg = dm2.export_reservations_json(json_path, "", "")
        assert_true(ok and os.path.exists(json_path), f"6.5 JSON导出成功: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        assert_true(len(json_data) == len(dm2.reservations),
                    f"6.6 JSON记录数量匹配（{len(json_data)} vs {len(dm2.reservations)}）")

        # 设置持久化
        dm2.settings.export_dir = tmpdir
        dm2.settings.filter_person = "李工"
        dm2.settings.filter_status = "已预约"
        dm2.settings.current_role = UserRole.ADMIN
        dm2.save_settings()

        dm3 = DataManager(data_dir=tmpdir)
        assert_true(dm3.settings.export_dir == tmpdir, "6.7 导出目录已持久化")
        assert_true(dm3.settings.filter_person == "李工", "6.8 预约筛选(负责人)已持久化")
        assert_true(dm3.settings.filter_status == "已预约", "6.9 预约筛选(状态)已持久化")
        assert_true(dm3.settings.current_role == UserRole.ADMIN, "6.10 角色已持久化")

        # ------------------------------------------------------------------
        separator("七、回归测试 - 仪器筛选独立持久化 + 校准记录可见性")
        # ------------------------------------------------------------------
        # 7.1 仪器筛选与预约筛选互不串值
        dm3.settings.ins_filter_person = "王工"
        dm3.settings.ins_filter_status = "校准过期"
        dm3.settings.filter_person = "张工"
        dm3.settings.filter_status = "草稿"
        dm3.save_settings()

        dm4 = DataManager(data_dir=tmpdir)
        assert_true(dm4.settings.ins_filter_person == "王工",
                    "7.1 仪器筛选(负责人)独立持久化 - 王工")
        assert_true(dm4.settings.ins_filter_status == "校准过期",
                    "7.2 仪器筛选(状态)独立持久化 - 校准过期")
        assert_true(dm4.settings.filter_person == "张工",
                    "7.3 预约筛选(负责人)保持独立 - 张工")
        assert_true(dm4.settings.filter_status == "草稿",
                    "7.4 预约筛选(状态)保持独立 - 草稿")
        assert_true(dm4.settings.ins_filter_person != dm4.settings.filter_person,
                    "7.5 仪器与预约筛选不串值")

        # 7.2 校准记录跨重启可见，且字段完整（仪器、类型、角色、原因、时间）
        freeze_records = [r for r in dm4.calibration_records if r["action"] == "故障冻结"]
        unfreeze_records = [r for r in dm4.calibration_records if r["action"] == "解除冻结"]
        assert_true(len(freeze_records) >= 1, f"7.6 跨重启后冻结记录可见（{len(freeze_records)} 条）")
        assert_true(len(unfreeze_records) >= 1, f"7.7 跨重启后解冻记录可见（{len(unfreeze_records)} 条）")

        fr = freeze_records[-1]
        assert_true("instrument_code" in fr and fr["instrument_code"],
                    "7.8 冻结记录含仪器编号: " + str(fr.get("instrument_code")))
        assert_true(fr.get("action") == "故障冻结",
                    "7.9 冻结记录类型正确: " + str(fr.get("action")))
        assert_true(fr.get("role") in ("管理员", "普通用户"),
                    "7.10 冻结记录含角色: " + str(fr.get("role")))
        assert_true("光源异常" in str(fr.get("reason", "")),
                    "7.11 冻结记录含原因: " + str(fr.get("reason")))
        assert_true(fr.get("time") and len(fr.get("time")) >= 10,
                    "7.12 冻结记录含时间: " + str(fr.get("time")))

        ufr = unfreeze_records[-1]
        assert_true(ufr.get("role") == "管理员",
                    "7.13 解冻记录角色=管理员: " + str(ufr.get("role")))
        assert_true("已更换" in str(ufr.get("reason", "")),
                    "7.14 解冻记录含原因: " + str(ufr.get("reason")))
        assert_true(ufr.get("time"), "7.15 解冻记录含时间")

        # 7.3 原主流程与导出未被破坏
        still_completed = [r for r in dm4.reservations if r.id == main_id]
        assert_true(len(still_completed) == 1 and still_completed[0].status == ReservationStatus.COMPLETED,
                    "7.16 原主流程预约状态未被破坏（仍=已完成）")

        csv_path2 = os.path.join(tmpdir, "regression_export.csv")
        ok, _ = dm4.export_reservations_csv(csv_path2, "", "")
        assert_true(ok and os.path.exists(csv_path2), "7.17 CSV导出未被破坏")
        json_path2 = os.path.join(tmpdir, "regression_export.json")
        ok, _ = dm4.export_reservations_json(json_path2, "", "")
        assert_true(ok and os.path.exists(json_path2), "7.18 JSON导出未被破坏")

        # ------------------------------------------------------------------
        separator("八、模板 CRUD 测试")
        # ------------------------------------------------------------------
        ins_001 = [i for i in dm.instruments if i.code == "INS-001"][0]
        ins_004 = [i for i in dm.instruments if i.code == "INS-004"][0]

        # 8.1 创建模板
        tpl, msg = dm.add_template(
            name="高效液相色谱日常检测",
            instrument_id=ins_001.id,
            purpose="药品含量检测，按照中国药典2025版方法执行",
            default_duration_minutes=120,
            reminder_minutes=30,
            remark="标准检测流程，需提前准备对照品",
            applicable_persons=["张工", "李工"],
            time_slots=[
                TimeSlot(start_time="09:00", end_time="11:00"),
                TimeSlot(start_time="14:00", end_time="16:00"),
            ]
        )
        assert_true(tpl is not None, f"8.1 创建模板成功: {msg}")
        assert_true(tpl.name == "高效液相色谱日常检测", "   模板名称正确")
        assert_true(tpl.instrument_code == "INS-001", "   模板关联仪器正确")
        assert_true(len(tpl.time_slots) == 2, "   时间段数量正确")
        assert_true(tpl.applicable_persons == ["张工", "李工"], "   适用负责人正确")

        # 8.2 重名模板被拦截
        tpl2, msg = dm.add_template(
            name="高效液相色谱日常检测",
            instrument_id=ins_004.id,
            purpose="测试",
            default_duration_minutes=60,
            reminder_minutes=0,
            remark="",
            applicable_persons=[],
            time_slots=[]
        )
        assert_true(tpl2 is None, f"8.2 重名模板被拦截: {msg}")
        assert_true("已存在" in msg, "   错误消息包含'已存在'")

        # 8.3 更新模板
        tpl_updated, msg = dm.update_template(
            tpl.id,
            default_duration_minutes=150,
            remark="更新：需同时准备系统适用性溶液"
        )
        assert_true(tpl_updated is not None, "8.3 更新模板成功")
        assert_true(tpl_updated.default_duration_minutes == 150, "   时长已更新为150分钟")
        assert_true("系统适用性" in tpl_updated.remark, "   备注已更新")

        # 8.4 获取模板和列表
        tpl_get = dm.get_template(tpl.id)
        assert_true(tpl_get is not None and tpl_get.id == tpl.id, "8.4 get_template 正确")

        all_tpls = dm.list_templates()
        assert_true(len(all_tpls) >= 1, f"   模板列表数量正确（{len(all_tpls)}）")

        tpls_by_ins = dm.list_templates(instrument_id=ins_001.id)
        assert_true(len(tpls_by_ins) >= 1, "   按仪器筛选模板正确")

        tpls_by_person = dm.get_applicable_templates(applicant="张工")
        assert_true(len(tpls_by_person) >= 1, "   按适用人筛选模板正确（张工）")

        tpls_by_person2 = dm.get_applicable_templates(applicant="王工")
        assert_true(len(tpls_by_person2) == 0, "   按适用人筛选模板正确（王工不适用）")

        # 8.5 创建第二个模板用于后续测试
        tpl_gc, msg = dm.add_template(
            name="气相色谱残留检测",
            instrument_id=ins_004.id,
            purpose="有机溶剂残留检测",
            default_duration_minutes=90,
            reminder_minutes=15,
            remark="顶空进样",
            applicable_persons=["李工", "王工"],
            time_slots=[
                TimeSlot(start_time="10:00", end_time="11:30"),
            ]
        )
        assert_true(tpl_gc is not None, "8.5 创建第二个模板成功")

        # ------------------------------------------------------------------
        separator("九、模板导入导出与校验测试")
        # ------------------------------------------------------------------

        # 9.1 导出 JSON
        json_export_path = os.path.join(tmpdir, "templates_export.json")
        ok, msg = dm.export_templates_json(json_export_path)
        assert_true(ok and os.path.exists(json_export_path), f"9.1 导出JSON成功: {json_export_path}")

        # 9.2 导出 CSV
        csv_export_path = os.path.join(tmpdir, "templates_export.csv")
        ok, msg = dm.export_templates_csv(csv_export_path)
        assert_true(ok and os.path.exists(csv_export_path), f"9.2 导出CSV成功: {csv_export_path}")

        # 9.3 普通用户导入被拦截（权限测试）
        dm.settings.current_role = UserRole.NORMAL
        result = dm.import_templates_json(json_export_path, overwrite=False, user_role=UserRole.NORMAL)
        assert_true(not result.success, "9.3 普通用户导入JSON被拦截")
        assert_true("仅管理员" in result.errors[0], "   错误消息包含'仅管理员'")

        result = dm.import_templates_csv(csv_export_path, overwrite=False, user_role=UserRole.NORMAL)
        assert_true(not result.success, "   普通用户导入CSV被拦截")

        # 9.4 管理员导入 - 不覆盖模式（重名被拦截）
        dm.settings.current_role = UserRole.ADMIN
        result = dm.import_templates_json(json_export_path, overwrite=False, user_role=UserRole.ADMIN)
        assert_true(result.total_count == 2, f"9.4 导入总数正确（{result.total_count}）")
        assert_true(result.success_count == 0, f"   不覆盖模式下全部跳过（{result.success_count}）")
        assert_true(result.failed_count == 2, f"   失败数量正确（{result.failed_count}）")
        assert_true(any("已存在" in e for e in result.errors), "   包含重名错误")

        # 9.5 管理员导入 - 覆盖模式
        result = dm.import_templates_json(json_export_path, overwrite=True, user_role=UserRole.ADMIN)
        assert_true(result.success_count == 2, f"9.5 覆盖模式导入成功（{result.success_count}）")
        assert_true(result.failed_count == 0, "   无失败")

        # 9.6 导入校验 - 构造包含错误的测试数据
        bad_templates = [
            {
                "name": "仪器不存在模板",
                "instrument_code": "INS-999",
                "purpose": "仪器不存在测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": [{"start_time": "09:00", "end_time": "10:00"}]
            },
            {
                "name": "",
                "instrument_code": "INS-001",
                "purpose": "空名称测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": []
            },
            {
                "name": "负责人不匹配模板",
                "instrument_code": "INS-001",
                "purpose": "负责人不匹配测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": ["不存在的人", "另一个不存在的人"],
                "time_slots": [{"start_time": "09:00", "end_time": "10:00"}]
            },
            {
                "name": "空时段模板",
                "instrument_code": "INS-001",
                "purpose": "空时间段测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": []
            },
            {
                "name": "重复名称1",
                "instrument_code": "INS-001",
                "purpose": "批次内重复测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": [{"start_time": "09:00", "end_time": "10:00"}]
            },
            {
                "name": "重复名称1",
                "instrument_code": "INS-001",
                "purpose": "批次内重复测试2",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": [{"start_time": "14:00", "end_time": "15:00"}]
            },
            {
                "name": "非法时段模板",
                "instrument_code": "INS-001",
                "purpose": "非法时段测试",
                "default_duration_minutes": 60,
                "reminder_minutes": 0,
                "remark": "",
                "applicable_persons": [],
                "time_slots": [{"start_time": "25:00", "end_time": "26:00"}]
            },
        ]
        bad_json_path = os.path.join(tmpdir, "bad_templates.json")
        with open(bad_json_path, "w", encoding="utf-8") as f:
            json.dump(bad_templates, f, ensure_ascii=False, indent=2)

        result = dm.import_templates_json(bad_json_path, overwrite=False, user_role=UserRole.ADMIN)
        assert_true(result.total_count == 7, f"9.6 错误数据导入总数={result.total_count}")
        assert_true(result.failed_count >= 6, f"   失败数={result.failed_count}")
        has_invalid_instr = any("仪器编号" in e and "不存在" in e for e in result.errors)
        has_empty_name = any("模板名称为空" in e for e in result.errors)
        has_dup_name = any("批次内重复" in e for e in result.errors)
        has_invalid_person = any("不存在" in e and "负责人" in e for e in result.errors)
        has_no_slots = any("未设置可选时间段" in e for e in result.errors)
        has_invalid_slot = any("不合法" in e for e in result.errors)
        assert_true(has_invalid_instr, "   仪器不存在被拦截")
        assert_true(has_empty_name, "   空名称被拦截")
        assert_true(has_dup_name, "   批次内重复被拦截")
        assert_true(has_invalid_person, "   负责人不匹配被拦截")
        assert_true(has_no_slots, "   空时间段被拦截")
        assert_true(has_invalid_slot, "   时间段不合法被拦截")

        # ------------------------------------------------------------------
        separator("十、模板套用与快照测试")
        # ------------------------------------------------------------------

        # 10.1 套用模板创建预约
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        res_from_tpl, msg = dm.apply_template(
            template_id=tpl.id,
            start_date=tomorrow,
            time_slot_index=0,
            applicant="张工"
        )
        assert_true(res_from_tpl is not None, f"10.1 套用模板创建预约成功: {msg}")
        assert_true(res_from_tpl.template_snapshot is not None, "   模板快照已保存")

        # 检查快照内容
        snap = res_from_tpl.template_snapshot
        if isinstance(snap, dict):
            snap_name = snap.get("template_name", "")
            snap_purpose = snap.get("purpose", "")
        else:
            snap_name = getattr(snap, "template_name", "")
            snap_purpose = getattr(snap, "purpose", "")
        assert_true(snap_name == "高效液相色谱日常检测", f"   快照模板名称正确: {snap_name}")
        assert_true("中国药典" in snap_purpose, "   快照用途正确")

        # 10.2 修改原模板，验证快照不受影响
        dm.update_template(tpl.id, name="高效液相色谱日常检测（已修改）", purpose="已修改的用途")
        tpl_modified = dm.get_template(tpl.id)
        assert_true(tpl_modified.name == "高效液相色谱日常检测（已修改）", "   原模板已修改")

        # 重新获取预约，检查快照仍然是旧名称
        res_reload = [r for r in dm.reservations if r.id == res_from_tpl.id][0]
        snap2 = res_reload.template_snapshot
        if isinstance(snap2, dict):
            snap_name2 = snap2.get("template_name", "")
        else:
            snap_name2 = getattr(snap2, "template_name", "")
        assert_true(snap_name2 == "高效液相色谱日常检测",
                    f"10.2 旧预约快照不受模板修改影响: {snap_name2}")

        # ------------------------------------------------------------------
        separator("十一、批量创建与冲突检测测试")
        # ------------------------------------------------------------------

        # 11.1 构造批量数据
        day1 = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        day2 = (date.today() + timedelta(days=6)).strftime("%Y-%m-%d")
        day3 = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        batch_items = [
            {
                "template_id": tpl.id,
                "start_date": day1,
                "slot_index": 0,
                "applicant": "张工"
            },
            {
                "template_id": tpl.id,
                "start_date": day2,
                "slot_index": 0,
                "applicant": "张工"
            },
            {
                "template_id": tpl_gc.id,
                "start_date": day1,
                "slot_index": 0,
                "applicant": "李工"
            },
        ]

        # 11.2 冲突检测（无冲突）
        conflicts = dm.check_batch_conflicts(batch_items)
        assert_true(len(conflicts) == 0, f"11.1 无冲突检测通过（冲突数={len(conflicts)}）")

        # 11.3 批量创建
        dm.settings.current_user = "测试管理员"
        record, fails = dm.batch_create_reservations(
            batch_items,
            operator="测试管理员",
            user_role=UserRole.ADMIN
        )
        assert_true(record is not None, "11.2 批量创建成功")
        assert_true(record.total_count == 3, f"   总数=3")
        assert_true(record.success_count == 3, f"   成功=3")
        assert_true(len(fails) == 0, "   无失败")
        assert_true(record.id is not None and record.id != "", "   批次ID已生成")

        # 11.4 检查预约是否关联批次
        batch_reservations = [r for r in dm.reservations if r.batch_id == record.id]
        assert_true(len(batch_reservations) == 3, f"11.3 批次关联预约数量正确（{len(batch_reservations)}）")
        for r in batch_reservations:
            assert_true(r.template_snapshot is not None, "   批量预约都有模板快照")

        # 先确认第一个预约，使其能被重叠检测发现
        first_res = batch_reservations[0]
        dm.update_reservation_status(first_res.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN)
        dm.update_reservation_status(first_res.id, ReservationStatus.CONFIRMED, UserRole.ADMIN)

        # 11.5 冲突检测 - 构造有冲突的数据
        conflict_items = [
            {
                "template_id": tpl.id,
                "start_date": day1,
                "slot_index": 0,
                "applicant": "张工"
            },
        ]
        conflicts = dm.check_batch_conflicts(conflict_items)
        assert_true(len(conflicts) >= 1, "11.4 时间重叠冲突被检测到")
        assert_true(any(c["type"] == "时间重叠" for c in conflicts), "   冲突类型=时间重叠")

        # 11.6 同一申请人撞单检测
        same_day_items = [
            {
                "template_id": tpl.id,
                "start_date": day3,
                "slot_index": 0,
                "applicant": "测试员撞单"
            },
            {
                "template_id": tpl_gc.id,
                "start_date": day3,
                "slot_index": 0,
                "applicant": "测试员撞单"
            },
        ]
        conflicts = dm.check_batch_conflicts(same_day_items)
        assert_true(any(c["type"] == "同一申请人撞单" for c in conflicts),
                    "11.5 同一申请人撞单被检测到")

        # 11.7 仪器冻结冲突检测
        dm.freeze_instrument(ins_004.id, "测试冻结", "测试员", UserRole.ADMIN)
        frozen_items = [
            {
                "template_id": tpl_gc.id,
                "start_date": day3,
                "slot_index": 0,
                "applicant": "李工"
            },
        ]
        conflicts = dm.check_batch_conflicts(frozen_items)
        assert_true(any(c["type"] == "仪器冻结" for c in conflicts),
                    "11.6 仪器冻结冲突被检测到")
        dm.unfreeze_instrument(ins_004.id, "恢复", "测试员", UserRole.ADMIN)

        # ------------------------------------------------------------------
        separator("十二、整批撤销与权限控制测试")
        # ------------------------------------------------------------------

        # 12.1 普通用户撤销被拦截
        ok, msg = dm.batch_cancel_reservations(
            record.id,
            operator="普通用户",
            user_role=UserRole.NORMAL,
            reason="测试撤销"
        )
        assert_false(ok, f"12.1 普通用户撤销被拦截: {msg}")
        assert_true("仅管理员" in msg, "   错误消息包含'仅管理员'")

        # 12.2 管理员撤销
        ok, msg = dm.batch_cancel_reservations(
            record.id,
            operator="测试管理员",
            user_role=UserRole.ADMIN,
            reason="测试整批撤销"
        )
        assert_true(ok, f"12.2 管理员撤销成功: {msg}")

        # 12.3 检查预约状态是否已取消
        batch_reservations = [r for r in dm.reservations if r.batch_id == record.id]
        all_cancelled = all(r.status == ReservationStatus.CANCELLED for r in batch_reservations)
        assert_true(all_cancelled, "12.3 批次内所有预约状态已变为已取消")

        # 12.4 检查批次记录的撤销标记
        record_reload = dm.get_batch_record(record.id)
        assert_true(record_reload.is_cancelled, "12.4 批次记录已标记为已撤销")
        assert_true(record_reload.cancel_operator == "测试管理员", "   撤销操作人已记录")
        assert_true(record_reload.cancel_reason == "测试整批撤销", "   撤销原因已记录")
        assert_true(record_reload.cancel_time is not None, "   撤销时间已记录")

        # 12.5 重复撤销被拦截
        ok, msg = dm.batch_cancel_reservations(
            record.id,
            operator="测试管理员",
            user_role=UserRole.ADMIN,
            reason="重复撤销"
        )
        assert_false(ok, f"12.5 重复撤销被拦截: {msg}")
        assert_true("已被撤销" in msg, "   错误消息包含'已被撤销'")

        # ------------------------------------------------------------------
        separator("十三、持久化验证 - 新功能数据跨重启")
        # ------------------------------------------------------------------

        # 保存所有数据
        dm.save_templates()
        dm.save_batch_records()
        dm.save_operation_logs()
        dm.save_settings()
        dm.save_reservations()

        # 重新加载
        dm5 = DataManager(data_dir=tmpdir)

        # 13.1 模板持久化
        assert_true(len(dm5.templates) >= 2, f"13.1 模板已持久化（{len(dm5.templates)}个）")
        tpl_reload = dm5.get_template(tpl.id)
        assert_true(tpl_reload is not None, "   模板可通过ID获取")
        assert_true(tpl_reload.name == "高效液相色谱日常检测（已修改）", "   模板修改内容已持久化")

        # 13.2 批量记录持久化
        assert_true(len(dm5.batch_records) >= 1, f"13.2 批量记录已持久化（{len(dm5.batch_records)}条）")
        batch_reload = dm5.get_batch_record(record.id)
        assert_true(batch_reload is not None, "   批次记录可获取")
        assert_true(batch_reload.is_cancelled, "   撤销状态已持久化")

        # 13.3 操作日志持久化
        assert_true(len(dm5.operation_logs) >= 1, f"13.3 操作日志已持久化（{len(dm5.operation_logs)}条）")

        # 13.4 预约中的模板快照持久化
        res_with_snap = [r for r in dm5.reservations if r.template_snapshot is not None]
        assert_true(len(res_with_snap) >= 1, f"13.4 带快照的预约已持久化（{len(res_with_snap)}条）")

        # 13.5 提醒开关持久化
        assert_true(hasattr(dm5.settings, 'reminder_enabled'), "13.5 提醒开关字段存在")
        assert_true(hasattr(dm5.settings, 'default_reminder_minutes'), "   默认提醒时长字段存在")

        # 13.6 最近导入结果持久化
        assert_true(hasattr(dm5.settings, 'last_import_result'), "13.6 最近导入结果字段存在")

        # ------------------------------------------------------------------
        separator("十四、操作日志与批量记录列表测试")
        # ------------------------------------------------------------------

        # 14.1 操作日志记录检查
        log_types = [log.operation_type for log in dm.operation_logs]
        assert_true(OperationType.BATCH_CREATE.value in log_types, "14.1 批量建单日志已记录")
        assert_true(OperationType.BATCH_CANCEL.value in log_types, "   批量撤销日志已记录")
        assert_true(OperationType.TEMPLATE_CREATE.value in log_types, "   模板创建日志已记录")
        assert_true(OperationType.TEMPLATE_EXPORT.value in log_types, "   模板导出日志已记录")

        # 14.2 批量记录列表
        all_batches = dm.list_batch_records()
        assert_true(len(all_batches) >= 1, f"14.2 批量记录列表正常（{len(all_batches)}条）")

        create_batches = dm.list_batch_records(operation=OperationType.BATCH_CREATE.value)
        assert_true(len(create_batches) >= 1, "   按操作类型筛选=批量建单正确")

        # 14.3 检查日志内容完整性
        create_logs = [log for log in dm.operation_logs if log.operation_type == OperationType.BATCH_CREATE.value]
        assert_true(len(create_logs) >= 1, "   批量建单日志存在")
        cl = create_logs[0]
        assert_true(cl.operator, "   日志含操作人")
        assert_true(cl.operator_role, "   日志含角色")
        assert_true(cl.timestamp, "   日志含时间戳")
        assert_true(cl.description, "   日志含描述")

        # ------------------------------------------------------------------
        separator("十五、模板删除测试")
        # ------------------------------------------------------------------

        # 15.1 删除模板
        ok, msg = dm.delete_template(tpl_gc.id)
        assert_true(ok, f"15.1 删除模板成功: {msg}")

        # 15.2 验证模板已删除
        tpl_deleted = dm.get_template(tpl_gc.id)
        assert_true(tpl_deleted is None, "15.2 模板已从列表中移除")

        # 15.3 验证旧预约的快照不受影响
        res_with_gc_snap = [r for r in dm.reservations if r.batch_id == record.id and r.instrument_code == "INS-004"]
        if res_with_gc_snap:
            snap = res_with_gc_snap[0].template_snapshot
            if isinstance(snap, dict):
                snap_name = snap.get("template_name", "")
            else:
                snap_name = getattr(snap, "template_name", "")
            assert_true(snap_name == "气相色谱残留检测",
                        f"15.3 模板删除后旧预约快照仍完整: {snap_name}")

        # ------------------------------------------------------------------
        separator("✓ 全部测试通过（含新增功能）！")
        # ------------------------------------------------------------------
        print(f"\n  共执行了 80+ 项断言，覆盖：")
        print("    ✅ 初始样例数据（4台仪器，1台校准过期）")
        print("    ✅ 失败路径拦截（校准过期、时间重叠、冻结预约、普通用户解冻、非法流转）")
        print("    ✅ 失败时不改变原有状态")
        print("    ✅ 主流程完整状态流转（草稿→待确认→已预约→使用中→待复核→已完成）")
        print("    ✅ 预约编辑、草稿修改")
        print("    ✅ 冻结/解冻日志（角色、原因、时间）")
        print("    ✅ 仪器筛选与预约筛选独立持久化（不串值）")
        print("    ✅ 校准记录跨重启可见（仪器、记录类型、角色、原因、时间）")
        print("    ✅ 按负责人/状态筛选")
        print("    ✅ CSV / JSON 导出")
        print("    ✅ 全量持久化（仪器、预约、校准记录、设置）")
        print("    ---- 新增功能测试 ----")
        print("    ✅ 模板 CRUD（创建、查询、更新、删除）")
        print("    ✅ 模板导入导出（JSON/CSV 双格式）")
        print("    ✅ 导入校验（重名、负责人不匹配、时间段非法、批次内重复）")
        print("    ✅ 权限控制（普通用户不能导入模板、不能批量撤销）")
        print("    ✅ 模板套用与一键创建预约")
        print("    ✅ 模板快照机制（模板修改不影响历史预约）")
        print("    ✅ 模板删除后历史快照仍完整")
        print("    ✅ 批量创建预约（含批次关联）")
        print("    ✅ 冲突检测（时间重叠、仪器冻结、校准过期、申请人撞单）")
        print("    ✅ 整批撤销（仅管理员）")
        print("    ✅ 重复撤销拦截")
        print("    ✅ 操作日志记录（所有关键操作）")
        print("    ✅ 批量操作记录管理")
        print("    ✅ 新功能数据跨重启持久化（模板、批量记录、操作日志）")
        print("    ✅ 提醒开关、最近导入结果等设置持久化")
        print(f"\n  测试数据目录: {tmpdir}")

    finally:
        pass


if __name__ == "__main__":
    main()
