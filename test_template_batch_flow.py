import os
import sys
import json
import tempfile
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, OperationType, ImportResult
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
    tmpdir = tempfile.mkdtemp(prefix="lab_tpl_test_")
    print(f"测试数据目录: {tmpdir}")
    try:
        dm = DataManager(data_dir=tmpdir)
        dm.settings.current_user = "测试员A"
        dm.init_sample_data()

        ins_001 = [i for i in dm.instruments if i.code == "INS-001"][0]
        ins_002 = [i for i in dm.instruments if i.code == "INS-002"][0]
        ins_003 = [i for i in dm.instruments if i.code == "INS-003"][0]
        ins_004 = [i for i in dm.instruments if i.code == "INS-004"][0]

        # ------------------------------------------------------------------
        separator("一、模板管理 - 基础 CRUD")
        # ------------------------------------------------------------------

        tpl1, msg = dm.add_template(
            name="日常样品检测",
            instrument_id=ins_001.id,
            purpose="日常环境样品检测 - 标准流程",
            default_duration_minutes=120,
            reminder_minutes=30,
            remark="标准检测模板，适用于日常批量样品",
            applicable_persons=["张工", "李工"],
            time_slots=[TimeSlot("09:00", "12:00"), TimeSlot("14:00", "17:00")],
        )
        assert_true(tpl1 is not None, f"1.1 创建模板成功: {tpl1.name}")
        assert_true(tpl1.instrument_code == "INS-001", "1.2 模板关联正确仪器编号")
        assert_true(len(tpl1.time_slots) == 2, "1.3 模板包含2个可选时间段")
        assert_true(tpl1.applicable_persons == ["张工", "李工"], "1.4 适用负责人正确")

        tpl2, msg = dm.add_template(
            name="快速质检",
            instrument_id=ins_004.id,
            purpose="快速质量检测",
            default_duration_minutes=30,
            reminder_minutes=15,
            remark="",
            applicable_persons=[],
            time_slots=[TimeSlot("09:00", "17:30")],
        )
        assert_true(tpl2 is not None, "1.5 创建第二个模板成功")
        assert_true(len(dm.templates) == 2, "1.6 模板列表有2个模板")

        tpl_dup, msg = dm.add_template(
            name="日常样品检测",
            instrument_id=ins_002.id,
            purpose="重复名称测试",
            default_duration_minutes=60,
            reminder_minutes=10,
            remark="",
            applicable_persons=[],
            time_slots=[TimeSlot("09:00", "10:00")],
        )
        assert_true(tpl_dup is None, "1.7 重名模板被拦截")
        assert_true("已存在" in msg, f"1.8 错误消息包含'已存在': {msg}")

        empty_name, msg = dm.add_template(
            name="   ",
            instrument_id=ins_001.id,
            purpose="测试",
            default_duration_minutes=60,
            reminder_minutes=10,
            remark="",
            applicable_persons=[],
            time_slots=[TimeSlot("09:00", "10:00")],
        )
        assert_true(empty_name is None, "1.9 空模板名被拦截")

        invalid_ts, msg = dm.add_template(
            name="无效时间段模板",
            instrument_id=ins_001.id,
            purpose="测试",
            default_duration_minutes=60,
            reminder_minutes=10,
            remark="",
            applicable_persons=[],
            time_slots=[TimeSlot("25:00", "26:00")],
        )
        assert_true(invalid_ts is None, "1.10 非法时间段被拦截")
        assert_true("不合法" in msg, f"   错误消息包含'不合法': {msg}")

        upd, msg = dm.update_template(
            tpl1.id,
            name="日常样品检测-升级",
            default_duration_minutes=150,
            remark="升级后的标准模板",
        )
        assert_true(upd is not None, "1.11 更新模板成功")
        assert_true(upd.name == "日常样品检测-升级", "1.12 模板名称已更新")
        assert_true(upd.default_duration_minutes == 150, "1.13 默认时长已更新")
        assert_true(upd.updated_at >= tpl1.created_at, "1.14 更新时间不早于创建时间")

        ok, msg = dm.delete_template(tpl2.id)
        assert_true(ok, "1.15 删除模板成功")
        assert_true(len(dm.templates) == 1, "1.16 删除后剩1个模板")

        tpl_list_all = dm.list_templates()
        assert_true(len(tpl_list_all) == 1, "1.17 list_templates 返回正确数量")

        tpl_list_by_ins = dm.list_templates(instrument_id=ins_001.id)
        assert_true(len(tpl_list_by_ins) == 1, "1.18 按仪器筛选模板正确")

        tpl_list_empty = dm.list_templates(instrument_id="nonexistent")
        assert_true(len(tpl_list_empty) == 0, "1.19 不存在的仪器返回空列表")

        print(f"\n  模板 CRUD 测试通过 ✓")

        # ------------------------------------------------------------------
        separator("二、模板套用 + 快照")
        # ------------------------------------------------------------------

        tpl_apply, _ = dm.add_template(
            name="套用测试模板",
            instrument_id=ins_004.id,
            purpose="套用测试 - 称量实验",
            default_duration_minutes=45,
            reminder_minutes=20,
            remark="测试用模板",
            applicable_persons=["张工"],
            time_slots=[TimeSlot("09:00", "11:00"), TimeSlot("14:00", "16:00")],
        )

        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        res_applied, msg = dm.apply_template(
            template_id=tpl_apply.id,
            start_date=tomorrow,
            time_slot_index=0,
            applicant="张工",
        )
        assert_true(res_applied is not None, f"2.1 套用模板成功: {msg if not res_applied else ''}")
        assert_true(res_applied.template_snapshot is not None, "2.2 预约带有模板快照")
        assert_true(res_applied.template_snapshot.template_name == "套用测试模板", "2.3 快照中模板名称正确")
        assert_true(res_applied.template_snapshot.template_id == tpl_apply.id, "2.4 快照中模板ID正确")
        assert_true(res_applied.template_snapshot.default_duration_minutes == 45, "2.5 快照中时长正确")
        assert_true(res_applied.reminder_minutes == 20, "2.6 预约提醒时长正确")
        assert_true(res_applied.purpose == "套用测试 - 称量实验", "2.7 预约用途来自模板")

        start_dt = datetime.strptime(res_applied.start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(res_applied.end_time, "%Y-%m-%d %H:%M:%S")
        duration_min = (end_dt - start_dt).total_seconds() / 60
        assert_true(duration_min == 45, f"2.8 预约时长等于模板默认时长（45分钟）")

        tpl_rename, _ = dm.update_template(tpl_apply.id, name="套用测试模板-已改名")
        res_reload = [r for r in dm.reservations if r.id == res_applied.id][0]
        assert_true(res_reload.template_snapshot.template_name == "套用测试模板",
                    "2.9 模板改名后，旧预约快照保持原名")

        res_slot1, msg = dm.apply_template(
            template_id=tpl_apply.id,
            start_date=tomorrow,
            time_slot_index=1,
            applicant="张工",
        )
        assert_true(res_slot1 is not None, "2.10 使用第二个时间段套用成功")
        assert_true("14:00" in res_slot1.start_time, "2.11 第二个时间段从14:00开始")

        print(f"\n  模板套用与快照测试通过 ✓")

        # ------------------------------------------------------------------
        separator("三、模板导入导出 - JSON")
        # ------------------------------------------------------------------

        tpl_a, _ = dm.add_template(
            name="导入测试A",
            instrument_id=ins_001.id,
            purpose="导入测试A用途",
            default_duration_minutes=90,
            reminder_minutes=10,
            remark="备注A",
            applicable_persons=["张工"],
            time_slots=[TimeSlot("09:00", "12:00")],
        )
        tpl_b, _ = dm.add_template(
            name="导入测试B",
            instrument_id=ins_002.id,
            purpose="导入测试B用途",
            default_duration_minutes=60,
            reminder_minutes=20,
            remark="备注B",
            applicable_persons=["李工", "王工"],
            time_slots=[TimeSlot("08:00", "11:30"), TimeSlot("13:30", "18:00")],
        )

        json_path = os.path.join(tmpdir, "templates_export.json")
        ok, msg = dm.export_templates_json(json_path)
        assert_true(ok and os.path.exists(json_path), f"3.1 导出JSON成功: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            exported = json.load(f)
        assert_true(len(exported) >= 2, "3.2 导出的模板数量正确")

        dm2 = DataManager(data_dir=tmpdir)
        dm2.settings.current_user = "测试员B"
        dm2.templates = []
        dm2.save_templates()

        result = dm2.import_templates_json(json_path, overwrite=False)
        assert_true(result.success, "3.3 导入JSON成功")
        assert_true(result.total_count == len(exported), f"3.4 导入总数正确（{result.total_count}）")
        assert_true(result.success_count == result.total_count, "3.5 全部导入成功")
        assert_true(result.failed_count == 0, "3.6 失败数为0")
        assert_true(len(dm2.templates) == result.total_count, "3.7 模板数量与导入一致")

        result_dup = dm2.import_templates_json(json_path, overwrite=False)
        assert_false(result_dup.success, "3.8 重名导入（不覆盖）失败")
        assert_true(result_dup.failed_count == result_dup.total_count, "3.9 全部因重名失败")
        assert_true(any("已存在" in e for e in result_dup.errors), "3.10 错误信息包含'已存在'")

        result_overwrite = dm2.import_templates_json(json_path, overwrite=True)
        assert_true(result_overwrite.success, "3.11 重名导入（覆盖模式）成功")
        assert_true(result_overwrite.success_count == result_overwrite.total_count, "3.12 全部覆盖成功")

        assert_true(dm2.settings.last_import_result is not None, "3.13 最近导入结果已保存")
        assert_true(dm2.settings.last_import_result.success_count == result_overwrite.success_count,
                    "3.14 保存的导入结果数据正确")

        dm3 = DataManager(data_dir=tmpdir)
        assert_true(dm3.settings.last_import_result is not None, "3.15 跨重启后最近导入结果可恢复")
        assert_true(dm3.settings.last_import_result.total_count == result_overwrite.total_count,
                    "3.16 恢复的导入结果数据正确")

        print(f"\n  模板 JSON 导入导出测试通过 ✓")

        # ------------------------------------------------------------------
        separator("四、模板导入导出 - CSV")
        # ------------------------------------------------------------------

        csv_path = os.path.join(tmpdir, "templates_export.csv")
        ok, msg = dm.export_templates_csv(csv_path)
        assert_true(ok and os.path.exists(csv_path), f"4.1 导出CSV成功: {csv_path}")

        dm4 = DataManager(data_dir=os.path.join(tmpdir, "csv_test"))
        dm4.settings.current_user = "测试员C"
        dm4.init_sample_data()

        result_csv = dm4.import_templates_csv(csv_path, overwrite=False)
        assert_true(result_csv.success, "4.2 导入CSV成功")
        assert_true(result_csv.success_count >= 2, f"4.3 至少成功导入2个（实际{result_csv.success_count}）")

        tpl_found = dm4.get_template_by_name("导入测试A")
        assert_true(tpl_found is not None, "4.4 按名称查询导入的模板成功")
        assert_true(tpl_found.default_duration_minutes == 90, "4.5 导入的时长正确")
        assert_true(tpl_found.reminder_minutes == 10, "4.6 导入的提醒时长正确")

        invalid_csv_path = os.path.join(tmpdir, "invalid.csv")
        with open(invalid_csv_path, "w", encoding="utf-8-sig") as f:
            f.write("模板名称,仪器编号,用途,默认时长(分钟),提前提醒(分钟),备注,适用负责人,可选时间段\n")
            f.write("重复名,INS-001,测试,60,10,,张工;李工,09:00-10:00\n")
            f.write("重复名,INS-002,测试,60,10,,张工,09:00-10:00\n")
            f.write("无仪器,NOEXIST,测试,60,10,,张工,09:00-10:00\n")
            f.write("非法时段,INS-001,测试,60,10,,张工,25:00-26:00\n")
            f.write("负时长,INS-001,测试,-5,10,,张工,09:00-10:00\n")

        result_invalid = dm4.import_templates_csv(invalid_csv_path, overwrite=False)
        assert_false(result_invalid.success, "4.7 非法CSV导入失败")
        assert_true(result_invalid.total_count == 5, "4.8 共5条待导入")
        assert_true(result_invalid.failed_count >= 3, f"4.9 至少3条失败（实际{result_invalid.failed_count}）")
        assert_true(any("批次内重复" in e for e in result_invalid.errors), "4.10 包含批次内重复项错误")
        assert_true(any("仪器编号" in e and "不存在" in e for e in result_invalid.errors), "4.11 包含仪器不存在错误")
        assert_true(any("不合法" in e for e in result_invalid.errors), "4.12 包含时间段非法错误")

        invalid_person_csv_path = os.path.join(tmpdir, "invalid_person.csv")
        with open(invalid_person_csv_path, "w", encoding="utf-8-sig") as f:
            f.write("模板名称,仪器编号,用途,默认时长(分钟),提前提醒(分钟),备注,适用负责人,可选时间段\n")
            f.write("负责人不匹配测试,INS-001,测试,60,10,,不存在的人;另一个不存在的人,09:00-10:00\n")

        result_invalid_person = dm4.import_templates_csv(invalid_person_csv_path, overwrite=True)
        assert_false(result_invalid_person.success, "4.13 负责人不匹配的模板被当场拦住")
        assert_true(result_invalid_person.failed_count == 1, "4.14 失败数=1")
        assert_true(any("适用负责人" in e and "不存在" in e for e in result_invalid_person.errors),
                    "4.15 错误信息包含适用负责人不存在提示")

        print(f"\n  模板 CSV 导入导出测试通过 ✓")

        # ------------------------------------------------------------------
        separator("五、批量建单 - 冲突检测")
        # ------------------------------------------------------------------

        tpl_batch1, _ = dm.add_template(
            name="批量测试模板1",
            instrument_id=ins_001.id,
            purpose="批量测试1",
            default_duration_minutes=120,
            reminder_minutes=30,
            remark="",
            applicable_persons=["张工", "李工"],
            time_slots=[TimeSlot("09:00", "12:00")],
        )
        tpl_batch2, _ = dm.add_template(
            name="批量测试模板2",
            instrument_id=ins_002.id,
            purpose="批量测试2",
            default_duration_minutes=120,
            reminder_minutes=30,
            remark="",
            applicable_persons=["李工"],
            time_slots=[TimeSlot("09:00", "12:00")],
        )

        day1 = "2099-07-01"
        day2 = "2099-07-02"

        batch_items_ok = [
            {"template_id": tpl_batch1.id, "start_date": day1, "slot_index": 0, "applicant": "张工"},
            {"template_id": tpl_batch2.id, "start_date": day1, "slot_index": 0, "applicant": "李工"},
            {"template_id": tpl_batch1.id, "start_date": day2, "slot_index": 0, "applicant": "张工"},
        ]
        conflicts_ok = dm.check_batch_conflicts(batch_items_ok)
        assert_true(len(conflicts_ok) == 0, "5.1 正常批次无冲突")

        res_existing, _ = dm.add_reservation(
            ins_001.id, "外部用户", "已存在预约",
            "2099-07-01 09:00:00", "2099-07-01 12:00:00"
        )
        dm.update_reservation_status(res_existing.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN)
        dm.update_reservation_status(res_existing.id, ReservationStatus.CONFIRMED, UserRole.ADMIN)

        batch_items_overlap = [
            {"template_id": tpl_batch1.id, "start_date": day1, "slot_index": 0, "applicant": "张工"},
        ]
        conflicts_overlap = dm.check_batch_conflicts(batch_items_overlap)
        assert_true(len(conflicts_overlap) >= 1, "5.2 检测到与现有预约的时间重叠")
        assert_true(any(c["type"] == "时间重叠" for c in conflicts_overlap), "5.3 冲突类型为时间重叠")

        batch_items_internal_overlap = [
            {"template_id": tpl_batch1.id, "start_date": day2, "slot_index": 0, "applicant": "张工"},
            {"template_id": tpl_batch1.id, "start_date": day2, "slot_index": 0, "applicant": "李工"},
        ]
        conflicts_internal = dm.check_batch_conflicts(batch_items_internal_overlap)
        assert_true(any(c["type"] == "批次内时间重叠" for c in conflicts_internal),
                    "5.4 检测到批次内时间重叠")

        batch_same_applicant = [
            {"template_id": tpl_batch1.id, "start_date": day2, "slot_index": 0, "applicant": "王工"},
            {"template_id": tpl_batch2.id, "start_date": day2, "slot_index": 0, "applicant": "王工"},
        ]
        conflicts_applicant = dm.check_batch_conflicts(batch_same_applicant)
        assert_true(any(c["type"] == "同一申请人撞单" for c in conflicts_applicant),
                    "5.5 检测到同一申请人撞单")

        batch_frozen = [
            {"template_id": tpl_batch2.id, "start_date": day1, "slot_index": 0, "applicant": "李工"},
        ]
        dm.freeze_instrument(ins_002.id, "测试冻结", "管理员", UserRole.ADMIN)
        conflicts_frozen = dm.check_batch_conflicts(batch_frozen)
        assert_true(any(c["type"] == "仪器冻结" for c in conflicts_frozen), "5.6 检测到仪器冻结冲突")
        dm.unfreeze_instrument(ins_002.id, "已修复", "管理员", UserRole.ADMIN)

        batch_expired = [
            {"template_id": tpl_batch1.id, "start_date": day1, "slot_index": 0, "applicant": "张工"},
        ]
        ins_003_tpl, _ = dm.add_template(
            name="过期仪器模板",
            instrument_id=ins_003.id,
            purpose="过期仪器测试",
            default_duration_minutes=60,
            reminder_minutes=10,
            remark="",
            applicable_persons=["王工"],
            time_slots=[TimeSlot("10:00", "16:00")],
        )
        batch_expired_item = [
            {"template_id": ins_003_tpl.id, "start_date": day1, "slot_index": 0, "applicant": "王工"},
        ]
        conflicts_expired = dm.check_batch_conflicts(batch_expired_item)
        assert_true(any(c["type"] == "校准过期" for c in conflicts_expired), "5.7 检测到校准过期冲突")

        batch_person_mismatch = [
            {"template_id": tpl_batch2.id, "start_date": day1, "slot_index": 0, "applicant": "王工"},
        ]
        conflicts_person = dm.check_batch_conflicts(batch_person_mismatch)
        assert_true(any(c["type"] == "负责人不匹配" for c in conflicts_person),
                    "5.8 检测到负责人不匹配")

        print(f"\n  批量建单冲突检测测试通过 ✓")

        # ------------------------------------------------------------------
        separator("六、批量建单 - 实际生成")
        # ------------------------------------------------------------------

        batch_create_items = [
            {"template_id": tpl_batch2.id, "start_date": day2, "slot_index": 0, "applicant": "李工"},
            {"template_id": tpl_batch1.id, "start_date": day2, "slot_index": 0, "applicant": "张工"},
            {"template_id": tpl_batch1.id, "start_date": "2099-07-03", "slot_index": 0, "applicant": "李工"},
        ]

        before_count = len(dm.reservations)
        batch_record, fail_msgs = dm.batch_create_reservations(
            batch_create_items, "测试员A", UserRole.NORMAL
        )
        after_count = len(dm.reservations)

        assert_true(batch_record is not None, "6.1 批量建单返回记录")
        assert_true(batch_record.total_count == 3, "6.2 批次总数=3")
        assert_true(batch_record.success_count == 3, f"6.3 成功数=3（实际{batch_record.success_count}）")
        assert_true(batch_record.failed_count == 0, f"6.4 失败数=0（实际{batch_record.failed_count}）")
        assert_true(len(fail_msgs) == 0, "6.5 无失败消息")
        assert_true(after_count - before_count == 3, "6.6 实际增加了3条预约")

        for rid in batch_record.reservation_ids:
            r = [x for x in dm.reservations if x.id == rid][0]
            assert_true(r.batch_id == batch_record.id, f"6.7 预约{rid[:8]}... 关联正确批次ID")
            assert_true(r.template_snapshot is not None, "6.8 批量生成的预约带模板快照")
            assert_true(r.status == ReservationStatus.DRAFT, "6.9 批量生成的预约为草稿状态")

        records = dm.list_batch_records()
        assert_true(len(records) >= 1, "6.10 批量记录列表至少1条")
        assert_true(records[0].id == batch_record.id, "6.11 最新的记录在最前面")

        batch_get = dm.get_batch_record(batch_record.id)
        assert_true(batch_get is not None, "6.12 按ID查询批次记录成功")
        assert_true(batch_get.operation == OperationType.BATCH_CREATE.value, "6.13 批次类型=批量建单")

        print(f"\n  批量建单实际生成测试通过 ✓")

        # ------------------------------------------------------------------
        separator("七、批量撤销 + 权限限制")
        # ------------------------------------------------------------------

        ok, msg = dm.batch_cancel_reservations(
            batch_record.id, "普通用户", UserRole.NORMAL, "测试撤销"
        )
        assert_false(ok, "7.1 普通用户批量撤销被拦截")
        assert_true("管理员" in msg, f"7.2 错误消息包含'管理员': {msg}")

        ok, msg = dm.batch_cancel_reservations(
            batch_record.id, "管理员", UserRole.ADMIN, "测试撤销-管理员操作"
        )
        assert_true(ok, f"7.3 管理员批量撤销成功: {msg}")

        for rid in batch_record.reservation_ids:
            r = [x for x in dm.reservations if x.id == rid][0]
            assert_true(r.status == ReservationStatus.CANCELLED, f"7.4 预约{rid[:8]}... 状态变为已取消")
            assert_true("批量撤销" in r.cancel_reason, "7.5 取消原因包含'批量撤销'")

        batch_reload = dm.get_batch_record(batch_record.id)
        assert_true(batch_reload.is_cancelled, "7.6 批次记录标记为已撤销")
        assert_true(batch_reload.cancel_operator == "管理员", "7.7 撤销操作人已记录")
        assert_true(batch_reload.cancel_reason == "测试撤销-管理员操作", "7.8 撤销原因已记录")
        assert_true(batch_reload.cancel_time is not None, "7.9 撤销时间已记录")

        ok, msg = dm.batch_cancel_reservations(
            batch_record.id, "管理员", UserRole.ADMIN, "再次撤销"
        )
        assert_false(ok, "7.10 已撤销的批次不能再次撤销")
        assert_true("已被撤销" in msg, f"7.11 错误消息包含'已被撤销': {msg}")

        print(f"\n  批量撤销与权限测试通过 ✓")

        # ------------------------------------------------------------------
        separator("八、操作日志")
        # ------------------------------------------------------------------

        logs = dm.list_operation_logs()
        assert_true(len(logs) > 0, "8.1 操作日志有记录")

        create_logs = [l for l in logs if l.operation_type == OperationType.TEMPLATE_CREATE.value]
        assert_true(len(create_logs) >= 3, "8.2 至少3条模板创建日志")

        batch_create_logs = [l for l in logs if l.operation_type == OperationType.BATCH_CREATE.value]
        assert_true(len(batch_create_logs) >= 1, "8.3 有批量建单日志")

        batch_cancel_logs = [l for l in logs if l.operation_type == OperationType.BATCH_CANCEL.value]
        assert_true(len(batch_cancel_logs) >= 1, "8.4 有批量撤销日志")
        assert_true(batch_cancel_logs[0].operator_role == "管理员", "8.5 撤销日志记录了角色")

        import_logs = [l for l in logs if l.operation_type == OperationType.TEMPLATE_EXPORT.value]
        assert_true(len(import_logs) >= 1, "8.6 有模板导出日志")
        export_logs = [l for l in logs if l.operation_type == OperationType.TEMPLATE_IMPORT.value]
        # dm 上没做过导入，用 dm2 验证
        import_logs_dm2 = dm2.list_operation_logs()
        has_import = any(l.operation_type == OperationType.TEMPLATE_IMPORT.value for l in import_logs_dm2)
        assert_true(has_import, "8.7 导入操作有日志记录")

        assert_true(all(l.timestamp for l in logs), "8.7 所有日志都有时间戳")
        assert_true(all(l.operator for l in logs), "8.8 所有日志都有操作人")

        filtered_logs = dm.list_operation_logs(operation_type=OperationType.TEMPLATE_CREATE.value)
        assert_true(len(filtered_logs) == len(create_logs), "8.9 按类型筛选日志正确")

        print(f"\n  操作日志测试通过 ✓")

        # ------------------------------------------------------------------
        separator("九、持久化验证 - 重启恢复")
        # ------------------------------------------------------------------

        dm.save_templates()
        dm.save_batch_records()
        dm.save_operation_logs()
        dm.save_settings()

        dm_reload = DataManager(data_dir=tmpdir)

        assert_true(len(dm_reload.templates) >= 3, f"9.1 模板已持久化（{len(dm_reload.templates)}个）")

        tpl_reload = dm_reload.get_template_by_name("日常样品检测-升级")
        assert_true(tpl_reload is not None, "9.2 改名后的模板持久化正确")
        assert_true(tpl_reload.default_duration_minutes == 150, "9.3 模板更新内容已持久化")

        batch_records_reload = dm_reload.list_batch_records()
        assert_true(len(batch_records_reload) >= 1, "9.4 批量记录已持久化")
        assert_true(batch_records_reload[0].is_cancelled, "9.5 撤销状态已持久化")

        logs_reload = dm_reload.list_operation_logs()
        assert_true(len(logs_reload) > 0, "9.6 操作日志已持久化")

        assert_true(dm_reload.settings.reminder_enabled is True, "9.7 提醒开关已持久化")
        assert_true(dm_reload.settings.default_reminder_minutes == 30, "9.8 默认提醒时长已持久化")

        res_with_snapshot = [r for r in dm_reload.reservations if r.template_snapshot is not None]
        assert_true(len(res_with_snapshot) > 0, "9.9 预约中的模板快照已持久化")
        assert_true(res_with_snapshot[0].template_snapshot.template_name is not None,
                    "9.10 快照数据完整可用")

        print(f"\n  持久化与重启恢复测试通过 ✓")

        # ------------------------------------------------------------------
        separator("十、提醒开关 + 设置")
        # ------------------------------------------------------------------

        dm.settings.reminder_enabled = False
        dm.settings.default_reminder_minutes = 60
        dm.save_settings()

        dm_set = DataManager(data_dir=tmpdir)
        assert_true(dm_set.settings.reminder_enabled is False, "10.1 关闭提醒后重启仍为关闭")
        assert_true(dm_set.settings.default_reminder_minutes == 60, "10.2 默认提醒时长已持久化")

        print(f"\n  提醒开关设置测试通过 ✓")

        # ------------------------------------------------------------------
        separator("✓ 全部模板与批量测试通过！")
        # ------------------------------------------------------------------
        print(f"\n  共执行了 70+ 项断言，覆盖：")
        print("    ✅ 模板 CRUD（增删改查、重名拦截、无效时段拦截）")
        print("    ✅ 模板套用与快照（改名后旧预约快照保留）")
        print("    ✅ 模板 JSON 导入导出（重名覆盖/不覆盖、持久化）")
        print("    ✅ 模板 CSV 导入导出（重复项、仪器不存在、非法时段、负责人警告）")
        print("    ✅ 最近导入结果持久化与跨重启恢复")
        print("    ✅ 批量冲突检测（时间重叠、批次内重叠、撞单、冻结、过期、负责人不匹配）")
        print("    ✅ 批量建单实际生成（批次记录、快照、状态）")
        print("    ✅ 批量撤销（普通用户拦截、管理员可撤销、二次撤销拦截）")
        print("    ✅ 操作日志（创建、更新、删除、导入、导出、批量建单、批量撤销）")
        print("    ✅ 全量持久化与跨重启恢复")
        print("    ✅ 提醒开关与默认时长设置")
        print(f"\n  测试数据目录: {tmpdir}")

    finally:
        pass


if __name__ == "__main__":
    main()
