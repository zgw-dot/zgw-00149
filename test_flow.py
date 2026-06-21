import os
import sys
import json
import shutil
import tempfile
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, STATUS_FLOW
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
        assert_true(dm3.settings.filter_person == "李工", "6.8 筛选条件(负责人)已持久化")
        assert_true(dm3.settings.filter_status == "已预约", "6.9 筛选条件(状态)已持久化")
        assert_true(dm3.settings.current_role == UserRole.ADMIN, "6.10 角色已持久化")

        # ------------------------------------------------------------------
        separator("✓ 全部测试通过！")
        # ------------------------------------------------------------------
        print(f"\n  共执行了 30+ 项断言，覆盖：")
        print("    ✅ 初始样例数据（4台仪器，1台校准过期）")
        print("    ✅ 失败路径拦截（校准过期、时间重叠、冻结预约、普通用户解冻、非法流转）")
        print("    ✅ 失败时不改变原有状态")
        print("    ✅ 主流程完整状态流转（草稿→待确认→已预约→使用中→待复核→已完成）")
        print("    ✅ 预约编辑、草稿修改")
        print("    ✅ 冻结/解冻日志（角色、原因、时间）")
        print("    ✅ 按负责人/状态筛选")
        print("    ✅ CSV / JSON 导出")
        print("    ✅ 全量持久化（仪器、预约、校准记录、设置）")
        print(f"\n  测试数据目录: {tmpdir}")

    finally:
        pass


if __name__ == "__main__":
    main()
