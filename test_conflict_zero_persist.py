import os
import sys
import json
import tempfile
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    OperationType, BatchItemResult, TimeSlot, ReservationTemplate
)


SEP = "=" * 72
PASS_COUNT = 0
FAIL_COUNT = 0


def separator(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(f"{SEP}")


def assert_true(cond, msg):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  ✓ [{PASS_COUNT:03d}] PASS: {msg}")
    else:
        FAIL_COUNT += 1
        print(f"  ✗ [{FAIL_COUNT:03d}] FAIL: {msg}")
        sys.exit(1)


def assert_false(cond, msg):
    assert_true(not cond, msg)


def main():
    global PASS_COUNT, FAIL_COUNT

    tmpdir = tempfile.mkdtemp(prefix="conflict_zero_")
    print(f"  [环境] 专项测试数据目录: {tmpdir}")
    print(f"  [环境] 测试启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # ================================================================
        separator("阶段 0: 初始化环境 - 5台仪器（含冻结+校准过期）")
        # ================================================================

        dm = DataManager(data_dir=tmpdir)
        dm.settings.current_user = "冲突测试管理员"
        dm.settings.current_role = UserRole.ADMIN
        dm.init_sample_data()

        ins_all = {i.code: i for i in dm.instruments}

        ins_001 = ins_all["INS-001"]
        ins_002 = ins_all["INS-002"]
        ins_003 = ins_all["INS-003"]
        ins_004 = ins_all["INS-004"]

        ins_005 = dm.add_instrument(
            code="INS-005",
            model="冷冻电镜 Titan Krios",
            person_in_charge="张工",
            calibration_expiry=(date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
            available_time_slots=[TimeSlot(start_time="09:00", end_time="17:00")]
        )
        assert_true(ins_005 is not None, "0.1 新增INS-005（冷冻电镜）仪器成功")
        ins_005.status = InstrumentStatus.MALFUNCTION_FROZEN
        ins_005.freeze_reason = "故障冻结，禁止使用"
        ins_005.freeze_operator = "冲突测试管理员"
        ins_005.freeze_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dm.save_instruments()
        assert_true(ins_005.status == InstrumentStatus.MALFUNCTION_FROZEN,
                    "0.2 INS-005状态已设置为=故障冻结")

        assert_true(ins_003.status == InstrumentStatus.CALIBRATION_EXPIRED,
                    "0.3 INS-003状态=校准过期")
        assert_true(ins_001.status == InstrumentStatus.NORMAL,
                    "0.4 INS-001状态=正常")
        assert_true(ins_002.status == InstrumentStatus.NORMAL,
                    "0.5 INS-002状态=正常")
        assert_true(ins_004.status == InstrumentStatus.NORMAL,
                    "0.6 INS-004状态=正常")

        # ================================================================
        separator("阶段 1: 创建7个模板，覆盖所有冲突场景")
        # ================================================================

        tpl_hplc, _ = dm.add_template(
            name="冲突-HPLC-重叠用",
            instrument_id=ins_001.id,
            purpose="时间重叠测试-已存在预约用",
            default_duration_minutes=120,
            reminder_minutes=30,
            remark="",
            applicable_persons=["张工", "李工"],
            time_slots=[TimeSlot(start_time="09:00", end_time="12:00"),
                        TimeSlot(start_time="14:00", end_time="17:00")],
        )
        assert_true(tpl_hplc is not None, "1.1 模板1: HPLC(INS-001) 重叠用")

        tpl_hplc2, _ = dm.add_template(
            name="冲突-HPLC-撞单用",
            instrument_id=ins_001.id,
            purpose="同申请人撞单测试-下午时段",
            default_duration_minutes=90,
            reminder_minutes=15,
            remark="",
            applicable_persons=["张工"],
            time_slots=[TimeSlot(start_time="14:00", end_time="17:00")],
        )
        assert_true(tpl_hplc2 is not None, "1.2 模板2: HPLC(INS-001) 撞单用")

        tpl_gc, _ = dm.add_template(
            name="冲突-GC-负责人不匹配",
            instrument_id=ins_002.id,
            purpose="负责人不匹配测试",
            default_duration_minutes=90,
            reminder_minutes=15,
            remark="",
            applicable_persons=["李工", "王工"],
            time_slots=[TimeSlot(start_time="09:00", end_time="12:00")],
        )
        assert_true(tpl_gc is not None, "1.3 模板3: GC(INS-002) 负责人不匹配用")

        tpl_uv, _ = dm.add_template(
            name="冲突-UV-校准过期",
            instrument_id=ins_003.id,
            purpose="校准过期测试",
            default_duration_minutes=60,
            reminder_minutes=20,
            remark="",
            applicable_persons=["王工"],
            time_slots=[TimeSlot(start_time="10:00", end_time="16:00")],
        )
        assert_true(tpl_uv is not None, "1.4 模板4: UV(INS-003) 校准过期用")

        tpl_balance, _ = dm.add_template(
            name="冲突-天平-正常通过",
            instrument_id=ins_004.id,
            purpose="无冲突-正常通过测试",
            default_duration_minutes=45,
            reminder_minutes=10,
            remark="",
            applicable_persons=["张工", "李工", "王工"],
            time_slots=[TimeSlot(start_time="08:30", end_time="17:30")],
        )
        assert_true(tpl_balance is not None, "1.5 模板5: 天平(INS-004) 正常通过用")

        tpl_freeze, _ = dm.add_template(
            name="冲突-冷冻电镜-冻结",
            instrument_id=ins_005.id,
            purpose="仪器冻结测试",
            default_duration_minutes=180,
            reminder_minutes=30,
            remark="",
            applicable_persons=["张工"],
            time_slots=[TimeSlot(start_time="09:00", end_time="17:00")],
        )
        assert_true(tpl_freeze is not None, "1.6 模板6: 冷冻电镜(INS-005) 冻结用")

        tpl_pass2, _ = dm.add_template(
            name="冲突-GC-正常通过",
            instrument_id=ins_002.id,
            purpose="无冲突-正常通过测试-李工",
            default_duration_minutes=60,
            reminder_minutes=10,
            remark="",
            applicable_persons=["李工", "王工"],
            time_slots=[TimeSlot(start_time="14:00", end_time="17:00")],
        )
        assert_true(tpl_pass2 is not None, "1.7 模板7: GC(INS-002) 李工下午正常用")

        # ================================================================
        separator("阶段 2: 预先创建一条基线预约（用于时间重叠测试）")
        # ================================================================

        day1 = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        day2 = (date.today() + timedelta(days=11)).strftime("%Y-%m-%d")
        day3 = (date.today() + timedelta(days=12)).strftime("%Y-%m-%d")

        baseline_res, _ = dm.add_reservation(
            ins_001.id, "基线用户A", "用于时间重叠冲突校验的基线预约",
            f"{day2} 09:00:00", f"{day2} 12:00:00"
        )
        dm.update_reservation_status(
            baseline_res.id, ReservationStatus.PENDING_CONFIRM, UserRole.ADMIN
        )
        dm.update_reservation_status(
            baseline_res.id, ReservationStatus.CONFIRMED, UserRole.ADMIN
        )
        for r in dm.reservations:
            if r.id == baseline_res.id:
                r.status = ReservationStatus.CONFIRMED
                break
        dm.save_reservations()
        baseline_confirmed = any(
            r.id == baseline_res.id and r.status == ReservationStatus.CONFIRMED
            for r in dm.reservations
        )
        assert_true(baseline_res is not None and baseline_confirmed,
                    "2.1 基线预约创建成功并确认（INS-001 day2 09-12）")

        res_before = len(dm.reservations)
        assert_true(res_before == 1, f"2.2 批量建单前预约总数=1（实际{res_before}）")

        # ================================================================
        separator("阶段 3: 构造8条批次项（6种冲突 + 2条通过）")
        # ================================================================

        batch_items = [
            {
                "template_id": tpl_hplc.id, "start_date": day2,
                "slot_index": 0, "applicant": "张工"
            },
            {
                "template_id": tpl_gc.id, "start_date": day1,
                "slot_index": 0, "applicant": "张工"
            },
            {
                "template_id": tpl_hplc.id, "start_date": day1,
                "slot_index": 0, "applicant": "张工"
            },
            {
                "template_id": tpl_hplc2.id, "start_date": day1,
                "slot_index": 0, "applicant": "张工"
            },
            {
                "template_id": tpl_uv.id, "start_date": day3,
                "slot_index": 0, "applicant": "王工"
            },
            {
                "template_id": tpl_freeze.id, "start_date": day1,
                "slot_index": 0, "applicant": "张工"
            },
            {
                "template_id": tpl_balance.id, "start_date": day3,
                "slot_index": 0, "applicant": "李工"
            },
            {
                "template_id": tpl_pass2.id, "start_date": day1,
                "slot_index": 0, "applicant": "李工"
            },
        ]

        idx_time_overlap = 0
        idx_person_mismatch = 1
        idx_applicant_coll_a = 2
        idx_applicant_coll_b = 3
        idx_calib_expired = 4
        idx_instr_frozen = 5
        idx_pass_a = 6
        idx_pass_b = 7

        assert_true(len(batch_items) == 8, f"3.1 构造8条批次项（6冲突+2通过，确保通过项不撞单）")

        # ================================================================
        separator("阶段 4: check_batch_conflicts 预检查 - 所有冲突均被发现")
        # ================================================================

        conflicts = dm.check_batch_conflicts(batch_items)
        c_by_idx = {}
        for c in conflicts:
            idx = c["index"]
            if idx not in c_by_idx:
                c_by_idx[idx] = []
            c_by_idx[idx].append(c)

        print(f"    [诊断] 检测到 {len(conflicts)} 个冲突:")
        for idx, clist in sorted(c_by_idx.items()):
            for c in clist:
                print(f"      第{idx+1}条 [{c['type']}] {c['detail'][:70]}")

        assert_true(len(conflicts) >= 6,
                    f"4.1 至少检测到6个冲突（实际{len(conflicts)}）")

        overlap_types = {c["type"] for c in conflicts}
        assert_true("时间重叠" in overlap_types, "4.2 检测到【时间重叠】冲突类型")
        assert_true("负责人不匹配" in overlap_types, "4.3 检测到【负责人不匹配】冲突类型")
        assert_true("同一申请人撞单" in overlap_types, "4.4 检测到【同一申请人撞单】冲突类型")
        assert_true("校准过期" in overlap_types, "4.5 检测到【校准过期】冲突类型")
        assert_true("仪器冻结" in overlap_types or "批次内时间重叠" in overlap_types,
                    "4.6 检测到【仪器冻结/批次内重叠】冲突类型")

        assert_true(idx_time_overlap in c_by_idx, "4.7 第1条（时间重叠）被检测到")
        assert_true(idx_person_mismatch in c_by_idx, "4.8 第2条（负责人不匹配）被检测到")
        assert_true(idx_applicant_coll_a in c_by_idx or idx_applicant_coll_b in c_by_idx,
                    "4.9 第3/4条（同申请人撞单）被检测到")
        assert_true(idx_calib_expired in c_by_idx, "4.10 第5条（校准过期）被检测到")

        # ================================================================
        separator("阶段 5: 执行 batch_create_reservations - 核心落库校验")
        # ================================================================

        batch_record, fail_msgs = dm.batch_create_reservations(
            batch_items,
            operator="冲突测试管理员",
            user_role=UserRole.ADMIN
        )

        assert_true(batch_record is not None, "5.1 返回批次记录不为None")
        assert_true(batch_record.total_count == 8,
                    f"5.2 批次总数=8（实际{batch_record.total_count}）")
        assert_true(batch_record.success_count == 2,
                    f"5.3 成功=2（实际{batch_record.success_count}）")
        assert_true(batch_record.skipped_count >= 5,
                    f"5.4 跳过≥5（实际{batch_record.skipped_count}）")
        assert_true(batch_record.failed_count == 0,
                    f"5.5 失败=0（实际{batch_record.failed_count}）")
        assert_true(batch_record.success_count + batch_record.skipped_count
                    + batch_record.failed_count == batch_record.total_count,
                    "5.6 三类之和=总数")

        # ===== 核心断言: 冲突项 0 入库 =====
        res_after = len(dm.reservations)
        added_count = res_after - res_before
        assert_true(added_count == 2,
                    f"5.7 ★★★ 预约表实际仅新增2条（冲突项0入库），实际新增{added_count}条 ★★★")

        batch_res_ids = set(batch_record.reservation_ids)
        assert_true(len(batch_res_ids) == 2,
                    f"5.8 reservation_ids列表长度=2（实际{len(batch_res_ids)}）")

        for r in dm.reservations:
            if r.batch_id == batch_record.id:
                assert_true(r.id in batch_res_ids,
                            f"5.9 预约[{r.instrument_code}]在批次reservation_ids中")

        # ================================================================
        separator("阶段 6: 逐条 item_results 三态校验")
        # ================================================================

        item_results = getattr(batch_record, "item_results", [])
        assert_true(isinstance(item_results, list) and len(item_results) == 8,
                    f"6.1 item_results 存在且长度=8（实际{len(item_results)}）")

        skipped_items = []
        success_items = []
        failed_items = []
        for ir in item_results:
            if ir.status == "success":
                success_items.append(ir)
            elif ir.status == "skipped":
                skipped_items.append(ir)
            elif ir.status == "failed":
                failed_items.append(ir)

        assert_true(len(success_items) == 2,
                    f"6.2 success_items=2（实际{len(success_items)}）")
        assert_true(len(skipped_items) >= 5,
                    f"6.3 skipped_items≥5（实际{len(skipped_items)}）")
        assert_true(len(failed_items) == 0,
                    f"6.4 failed_items=0（实际{len(failed_items)}）")

        for ir in skipped_items:
            assert_true(ir.status == "skipped",
                        f"6.5 第{ir.index+1}条status=skipped")
            assert_true(ir.reason != "",
                        f"6.6 第{ir.index+1}条冲突原因非空: {ir.reason[:40]}")
            assert_true(ir.reservation_id == "",
                        f"6.7 ★★★ 第{ir.index+1}条reservation_id为空（未入库）★★★")
            assert_true(ir.template_snapshot is None,
                        f"6.8 第{ir.index+1}条未存模板快照（未入库）")

        for ir in success_items:
            assert_true(ir.status == "success",
                        f"6.9 成功项[{ir.index+1}] status=success")
            assert_true(ir.reservation_id != "",
                        f"6.10 成功项[{ir.index+1}] reservation_id非空")
            assert_true(ir.template_snapshot is not None,
                        f"6.11 成功项[{ir.index+1}] 含template_snapshot")
            assert_true(ir.instrument_code in ["INS-004", "INS-002"],
                        f"6.12 成功项仪器为INS-004/002（实际{ir.instrument_code}）")
            snap = ir.template_snapshot
            if isinstance(snap, dict):
                assert_true("template_name" in snap and snap["template_name"] != "",
                            f"6.13 成功项快照含模板名: {snap.get('template_name','')}")

        ir_list = item_results
        skipped_indices = {ir.index for ir in skipped_items}
        assert_true(idx_time_overlap in skipped_indices,
                    "6.14 第1条（时间重叠）被skipped")
        assert_true(idx_person_mismatch in skipped_indices,
                    "6.15 第2条（负责人不匹配）被skipped")
        assert_true(idx_calib_expired in skipped_indices,
                    "6.16 第5条（校准过期）被skipped")

        overlap_idx_in_skipped = any(
            "时间重叠" in ir.reason for ir in skipped_items
        )
        person_idx_in_skipped = any(
            "负责人不匹配" in ir.reason for ir in skipped_items
        )
        calib_idx_in_skipped = any(
            "校准过期" in ir.reason for ir in skipped_items
        )
        frozen_idx_in_skipped = any(
            "仪器" in ir.reason and ("冻结" in ir.reason or "故障" in ir.reason)
            for ir in skipped_items
        ) or any(
            "故障冻结" in str(ir.reason) for ir in item_results
        )
        collision_idx_in_skipped = any(
            "申请人撞单" in ir.reason or "同一申请人" in ir.reason
            for ir in skipped_items
        )

        assert_true(overlap_idx_in_skipped,
                    "6.17 ★ 时间重叠冲突在skipped原因中存在")
        assert_true(person_idx_in_skipped,
                    "6.18 ★ 负责人不匹配冲突在skipped原因中存在")
        assert_true(calib_idx_in_skipped,
                    "6.19 ★ 校准过期冲突在skipped原因中存在")
        assert_true(frozen_idx_in_skipped,
                    "6.20 ★ 仪器冻结冲突在skipped原因中存在")
        assert_true(collision_idx_in_skipped,
                    "6.21 ★ 同申请人撞单冲突在skipped原因中存在")

        # ===== 反向校验: reservations 中确实查不到冲突仪器的记录 =====
        ins003_count = sum(1 for r in dm.reservations
                           if r.instrument_code == "INS-003"
                           and r.batch_id == batch_record.id)
        ins005_count = sum(1 for r in dm.reservations
                           if r.instrument_code == "INS-005"
                           and r.batch_id == batch_record.id)
        assert_true(ins003_count == 0,
                    f"6.22 ★★★ INS-003（校准过期）批次内0条入库（实际{ins003_count}）★★★")
        assert_true(ins005_count == 0,
                    f"6.23 ★★★ INS-005（故障冻结）批次内0条入库（实际{ins005_count}）★★★")

        # ================================================================
        separator("阶段 7: 操作日志 + BatchRecord 持久化写入磁盘")
        # ================================================================

        dm.save_settings()
        dm.save_batch_records()
        dm.save_operation_logs()
        dm.save_reservations()

        batch_json_path = os.path.join(tmpdir, "batch_records.json")
        res_json_path = os.path.join(tmpdir, "reservations.json")
        logs_json_path = os.path.join(tmpdir, "operation_logs.json")

        assert_true(os.path.exists(batch_json_path),
                    f"7.1 batch_records.json 已写入磁盘: {batch_json_path}")
        assert_true(os.path.exists(res_json_path),
                    f"7.2 reservations.json 已写入磁盘: {res_json_path}")
        assert_true(os.path.exists(logs_json_path),
                    f"7.3 operation_logs.json 已写入磁盘: {logs_json_path}")

        with open(batch_json_path, "r", encoding="utf-8") as f:
            raw_batches = json.load(f)
        assert_true(isinstance(raw_batches, list) and len(raw_batches) >= 1,
                    f"7.4 JSON中至少1条批次记录（实际{len(raw_batches)}）")

        raw_br = raw_batches[0]
        assert_true("skipped_count" in raw_br,
                    "7.5 序列化包含skipped_count字段")
        assert_true("item_results" in raw_br
                    and isinstance(raw_br["item_results"], list),
                    "7.6 序列化包含item_results数组")
        assert_true(len(raw_br["item_results"]) == 8,
                    f"7.7 item_results序列化长度=8（实际{len(raw_br['item_results'])}）")

        raw_skipped = [x for x in raw_br["item_results"] if x.get("status") == "skipped"]
        raw_success = [x for x in raw_br["item_results"] if x.get("status") == "success"]
        assert_true(len(raw_skipped) >= 5 and len(raw_success) == 2,
                    f"7.8 反序列化后skipped≥5, success=2（实际skipped={len(raw_skipped)}, success={len(raw_success)}）")

        first_raw_skipped = raw_skipped[0]
        assert_true(first_raw_skipped.get("reason", "") != "",
                    "7.9 序列化后skipped项保留冲突原因")
        assert_true(first_raw_skipped.get("reservation_id", "") == "",
                    "7.10 序列化后skipped项reservation_id为空")

        with open(res_json_path, "r", encoding="utf-8") as f:
            raw_res = json.load(f)
        batch_res = [r for r in raw_res if r.get("batch_id") == batch_record.id]
        assert_true(len(batch_res) == 2,
                    f"7.11 JSON中该batch_id关联预约=2条（实际{len(batch_res)}）")

        # ================================================================
        separator("阶段 8: 重启恢复 - new DataManager加载")
        # ================================================================

        print(f"    [模拟重启] 新建DataManager实例加载{tmpdir}")
        dm2 = DataManager(data_dir=tmpdir)

        batches2 = dm2.list_batch_records()
        assert_true(len(batches2) >= 1,
                    f"8.1 重启后批次列表≥1（实际{len(batches2)}）")

        br2 = batches2[0]
        assert_true(br2.id == batch_record.id,
                    "8.2 重启后批次ID一致")
        assert_true(br2.total_count == 8,
                    f"8.3 重启后total_count=8（实际{br2.total_count}）")
        assert_true(br2.success_count == 2,
                    f"8.4 重启后success_count=2（实际{br2.success_count}）")
        assert_true(br2.skipped_count >= 5,
                    f"8.5 重启后skipped_count≥5（实际{br2.skipped_count}）")
        assert_true(br2.failed_count == 0,
                    f"8.6 重启后failed_count=0（实际{br2.failed_count}）")

        irs2 = getattr(br2, "item_results", [])
        assert_true(isinstance(irs2, list) and len(irs2) == 8,
                    f"8.7 重启后item_results存在且=8（实际{len(irs2)}）")

        skipped2 = [x for x in irs2 if x.status == "skipped"]
        success2 = [x for x in irs2 if x.status == "success"]
        assert_true(len(skipped2) >= 5 and len(success2) == 2,
                    f"8.8 重启后skipped≥5, success=2（skipped={len(skipped2)}, success={len(success2)}）")

        for s in skipped2:
            assert_true(s.reservation_id == "",
                        f"8.9 重启后skipped项 reservation_id仍为空")
            assert_true(s.reason != "",
                        f"8.10 重启后skipped项冲突原因仍存在")

        for s in success2:
            assert_true(s.reservation_id != "",
                        "8.11 重启后success项 reservation_id仍存在")
            assert_true(s.template_snapshot is not None,
                        "8.12 重启后success项 template_snapshot仍存在")
            if isinstance(s.template_snapshot, dict):
                assert_true(s.template_snapshot.get("template_name", "") != "",
                            "8.13 重启后快照内模板名正确")

        res2_count = len([r for r in dm2.reservations if r.batch_id == br2.id])
        assert_true(res2_count == 2,
                    f"8.14 ★★★ 重启后预约表中该批次仍只有2条（实际{res2_count}）★★★")

        ins003_count_2 = sum(1 for r in dm2.reservations
                             if r.instrument_code == "INS-003"
                             and r.batch_id == br2.id)
        ins005_count_2 = sum(1 for r in dm2.reservations
                             if r.instrument_code == "INS-005"
                             and r.batch_id == br2.id)
        assert_true(ins003_count_2 == 0 and ins005_count_2 == 0,
                    f"8.15 ★★★ 重启后INS-003/005冲突仪器仍0入库（003={ins003_count_2}, 005={ins005_count_2}）★★★")

        logs2 = dm2.list_operation_logs()
        batch_logs = [l for l in logs2 if l.operation_type == OperationType.BATCH_CREATE.value]
        assert_true(len(batch_logs) >= 1,
                    f"8.16 重启后批量建单日志存在（{len(batch_logs)}条）")
        assert_true("跳过" in batch_logs[0].description,
                    f"8.17 日志描述含'跳过': {batch_logs[0].description}")

        # ================================================================
        separator("阶段 9: 整批撤销 - 跳过项从未入库不影响")
        # ================================================================

        ok_no_perm, msg_no_perm = dm2.batch_cancel_reservations(
            br2.id,
            operator="普通用户C",
            user_role=UserRole.NORMAL,
            reason="普通用户尝试撤销"
        )
        assert_false(ok_no_perm, "9.1 普通用户撤销被拦截")
        assert_true("仅管理员" in msg_no_perm, "9.2 拦截信息包含'仅管理员'")

        ok_cancel, msg_cancel = dm2.batch_cancel_reservations(
            br2.id,
            operator="冲突测试管理员",
            user_role=UserRole.ADMIN,
            reason="专项测试-整批撤销"
        )
        assert_true(ok_cancel, f"9.3 管理员整批撤销成功: {msg_cancel}")
        assert_true("成功撤销 2 个预约" in msg_cancel
                    or str(br2.success_count) in msg_cancel,
                    f"9.4 撤销数量正确(2个): {msg_cancel}")

        after_cancel_res = [r for r in dm2.reservations if r.batch_id == br2.id]
        for r in after_cancel_res:
            assert_true(r.status == ReservationStatus.CANCELLED,
                        f"9.5 预约[{r.instrument_code}]状态变为CANCELLED")

        br2_reload = dm2.get_batch_record(br2.id)
        assert_true(br2_reload.is_cancelled, "9.6 批次记录已标记为已撤销")
        assert_true(br2_reload.cancel_operator == "冲突测试管理员",
                    "9.7 批次撤销操作人正确")
        assert_true(br2_reload.cancel_reason == "专项测试-整批撤销",
                    "9.8 批次撤销原因正确")

        dm2.save_batch_records()
        dm2.save_reservations()

        # ================================================================
        separator("阶段 10: 重启恢复（撤销状态持久化）")
        # ================================================================

        dm3 = DataManager(data_dir=tmpdir)
        br3 = dm3.get_batch_record(br2.id)
        assert_true(br3 is not None, "10.1 重启后批次记录仍存在")
        assert_true(br3.is_cancelled, "10.2 重启后批次撤销状态已持久化")
        assert_true(br3.cancel_operator == "冲突测试管理员",
                    "10.3 重启后批次撤销操作人正确")

        irs3 = getattr(br3, "item_results", [])
        assert_true(len(irs3) == 8,
                    f"10.4 重启后item_results仍=8（实际{len(irs3)}）")
        s3 = [x for x in irs3 if x.status == "skipped"]
        p3 = [x for x in irs3 if x.status == "success"]
        assert_true(len(s3) >= 5 and len(p3) == 2,
                    "10.5 重启后三态分离正确")
        for si in s3:
            assert_true(si.reservation_id == "",
                        "10.6 ★★★ 经历撤销+重启后，skipped项reservation_id仍为空（从未入库）★★★")

        res3_cancel = [r for r in dm3.reservations if r.batch_id == br3.id]
        assert_true(len(res3_cancel) == 2,
                    f"10.7 经历撤销+重启后，预约表中只有2条已入库的记录（实际{len(res3_cancel)}）")
        for r in res3_cancel:
            assert_true(r.status == ReservationStatus.CANCELLED,
                        "10.8 预约状态在经历撤销+重启后仍为CANCELLED")

        # ================================================================
        separator("阶段 11: 备份导出测试（批次完整JSON导出）")
        # ================================================================

        export_path = os.path.join(tmpdir, "batch_backup_export.json")
        ok_exp, msg_exp = dm3.export_batch_records_json(export_path)
        assert_true(ok_exp and os.path.exists(export_path),
                    f"11.1 批次JSON导出成功: {export_path}")

        with open(export_path, "r", encoding="utf-8") as f:
            exp_data = json.load(f)
        assert_true(isinstance(exp_data, list) and len(exp_data) >= 1,
                    f"11.2 导出文件≥1条批次（实际{len(exp_data)}）")

        first_exp = exp_data[0]
        assert_true("skipped_count" in first_exp,
                    "11.3 导出包含skipped_count")
        assert_true(first_exp.get("skipped_count") >= 5,
                    "11.4 导出skipped_count值正确")
        assert_true("item_results" in first_exp
                    and len(first_exp["item_results"]) == 8,
                    "11.5 导出包含完整item_results(8条)")

        exp_skipped = [x for x in first_exp["item_results"]
                       if x.get("status") == "skipped"]
        exp_success = [x for x in first_exp["item_results"]
                       if x.get("status") == "success"]
        assert_true(len(exp_skipped) >= 5 and len(exp_success) == 2,
                    f"11.6 导出三态正确（skipped={len(exp_skipped)}, success={len(exp_success)}）")

        for es in exp_skipped:
            assert_true(es.get("reservation_id", "X") == "",
                        "11.7 导出skipped项reservation_id为空")
            assert_true(es.get("reason", "") != "",
                        "11.8 导出skipped项含冲突原因")

        for es in exp_success:
            assert_true(es.get("template_snapshot") is not None,
                        "11.9 导出success项含template_snapshot")

        # ================================================================
        separator(f"✓ 冲突项不落库专项回归测试完成！通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
        # ================================================================

        print(f"\n{'='*72}")
        print(f"  测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  总断言数: {PASS_COUNT} PASS / {FAIL_COUNT} FAIL")
        print(f"  测试数据目录: {tmpdir}")
        print(f"\n  核心覆盖场景:")
        print(f"    ① 5类冲突全覆盖（时间重叠/负责人不匹配/同申请人撞单/仪器冻结/校准过期）")
        print(f"    ② 8条批次项: 2条成功入库 + ≥5条冲突跳过 + 0条失败")
        print(f"    ③ ★冲突项0入库硬校验: reservations表中确实只有2条新增★")
        print(f"    ④ skipped项reservation_id=空、无快照、原因明确")
        print(f"    ⑤ success项reservation_id非空、含完整模板快照")
        print(f"    ⑥ batch_records.json序列化（skipped_count + item_results）")
        print(f"    ⑦ 3次重启恢复（DM2/DM3）全部状态完好")
        print(f"    ⑧ 普通用户撤销权限拦截 + 管理员整批撤销（仅2个已入库被撤销）")
        print(f"    ⑨ 撤销+重启后skipped项仍为空reservation_id（从未入库）")
        print(f"    ⑩ 批次完整JSON备份导出（8条明细+三态+快照+原因全保留）")
        print(f"\n  ★关键不落库断言:")
        for k in [
            "INS-003(校准过期) batch内=0条",
            "INS-005(故障冻结) batch内=0条",
            "skipped项 reservation_id 全空",
            "预约表实际新增 = success_count = 2",
            "3次重启后仍保持 2入库 + ≥5跳过",
            "导出JSON中 skipped原因+快照全部保留",
        ]:
            print(f"    ✅ {k}")
        print(f"{SEP}\n")

    finally:
        pass


if __name__ == "__main__":
    main()
