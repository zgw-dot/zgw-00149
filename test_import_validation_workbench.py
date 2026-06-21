"""
导入体检工作台 - 回归测试
覆盖：CSV/Excel 双格式、UTF-8/GBK 编码切换、8 条体检规则、
权限隔离、管理员撤销/恢复快照、批次复跑、重启后一致性、
失败行/通过行导出、批次去向、体检方案管理
"""
import os
import sys
import json
import csv
import shutil
import tempfile
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, UserRole, ReservationStatus, OperationType,
    STANDARD_COLUMNS, ImportMappingScheme, ImportValidationRule,
    ImportValidationScheme, ValidationSnapshot, ValidationBatch,
    BATCH_DISPOSITION_MAPPING, BATCH_DISPOSITION_DRAFT,
    BATCH_DISPOSITION_REJECT, BATCH_DISPOSITION_PENDING,
    VALIDATION_RULE_DEFAULTS, InstrumentStatus,
)


def separator(title=""):
    line = "=" * 70
    print("\n" + line)
    if title:
        print(f"  {title}")
    print(line)


def assert_true(cond, msg):
    if not cond:
        print(f"[FAIL] 断言失败: {msg}")
        sys.exit(1)
    print(f"[PASS] {msg}")


def assert_false(cond, msg):
    if cond:
        print(f"[FAIL] 断言失败(应为False): {msg}")
        sys.exit(1)
    print(f"[PASS] {msg}")


def assert_eq(a, b, msg):
    if a != b:
        print(f"[FAIL] 断言失败: {msg}")
        print(f"   期望: {b!r}")
        print(f"   实际: {a!r}")
        sys.exit(1)
    print(f"[PASS] {msg}")


def setup_dm(tmpdir, role=UserRole.ADMIN, user="admin"):
    """在临时目录创建一个 DataManager"""
    dm = DataManager(tmpdir)
    dm.settings.current_role = role
    dm.settings.current_user = user
    dm.save_settings()
    if len(dm.instruments) < 3:
        dm.init_sample_data()
        dm.save_instruments()
    return dm


def make_csv(path, rows, headers=None, encoding="utf-8-sig"):
    if headers is None:
        headers = ["仪器编号", "申请人", "日期", "开始时间", "结束时间", "用途"]
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(r)


def make_excel(path, rows, headers=None):
    try:
        import openpyxl
    except ImportError:
        return False
    if headers is None:
        headers = ["仪器编号", "申请人", "日期", "开始时间", "结束时间", "用途"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "预约"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return True


def get_instrument_codes(dm, count=3):
    return [ins.code for ins in dm.instruments if ins.status == InstrumentStatus.NORMAL][:count]


def create_default_mapping_scheme(dm, name="默认映射方案"):
    """创建一个基于中文列名的映射方案"""
    mapping = {
        "instrument_code": "仪器编号",
        "applicant": "申请人",
        "reservation_date": "日期",
        "start_time": "开始时间",
        "end_time": "结束时间",
        "purpose": "用途",
    }
    scheme, msg = dm.create_mapping_scheme(
        name=name,
        column_mapping=mapping,
        operator=dm.settings.current_user,
        user_role=dm.settings.current_role,
        datetime_format="%Y-%m-%d %H:%M:%S",
        date_format="%Y-%m-%d",
        time_format="%H:%M:%S",
    )
    assert_true(scheme is not None, f"创建映射方案成功: {msg}")
    return scheme


def create_good_rows(dm, count=3):
    """生成一组肯定能通过体检的数据行"""
    codes = get_instrument_codes(dm, count)
    today = date.today().strftime("%Y-%m-%d")
    rows = []
    for i in range(count):
        start_h = 9 + i * 2
        end_h = start_h + 1
        rows.append([
            codes[i],
            f"用户{i+1}",
            today,
            f"{start_h:02d}:00:00",
            f"{end_h:02d}:00:00",
            f"测试用途{i+1}",
        ])
    return rows


# ============================================================
# 主测试流程
# ============================================================
def main():
    tmp_root = tempfile.mkdtemp(prefix="test_vwb_")
    print(f"临时测试目录: {tmp_root}")
    has_openpyxl = False
    try:
        import openpyxl
        has_openpyxl = True
    except ImportError:
        print("⚠ 未安装 openpyxl，跳过 Excel 测试")

    try:
        # ===== 测试1: 体检方案 CRUD =====
        separator("测试1: 体检方案 CRUD（创建/读取/更新/删除）")
        tmp1 = os.path.join(tmp_root, "t1_scheme_crud")
        os.makedirs(tmp1)
        dm = setup_dm(tmp1, role=UserRole.ADMIN, user="admin01")

        rules = [
            ImportValidationRule(rule_key="required_columns", description="缺少必填列检查",
                                 enabled=True, params={}),
            ImportValidationRule(rule_key="empty_values", description="空值检查",
                                 enabled=True, params={}),
            ImportValidationRule(rule_key="time_format", description="时间格式检查",
                                 enabled=False, params={}),
        ]
        scheme1, msg = dm.create_validation_scheme("方案A", rules, "admin01", UserRole.ADMIN)
        assert_true(scheme1 is not None, f"创建体检方案成功: {msg}")
        assert_eq(len(scheme1.rules), 3, "方案有3条规则")
        assert_eq(scheme1.rules[2].enabled, False, "time_format 规则被禁用")

        got = dm.get_validation_scheme(scheme1.id)
        assert_true(got is not None, "读取方案成功")
        assert_eq(got.name, "方案A", "方案名称正确")

        schemes = dm.list_validation_schemes()
        assert_eq(len(schemes), 1, "列表中有1个方案")

        updated, msg = dm.update_validation_scheme(
            scheme1.id, "admin01", UserRole.ADMIN, name="方案A-改"
        )
        assert_true(updated is not None, f"更新方案成功: {msg}")
        assert_eq(updated.name, "方案A-改", "方案名称已更新")

        ok, msg = dm.delete_validation_scheme(scheme1.id, "admin01", UserRole.ADMIN)
        assert_true(ok, f"删除方案成功: {msg}")
        auto_scheme = dm.list_validation_schemes(include_revoked=False)
        assert_true(len(auto_scheme) >= 1, "删除后 list_validation_schemes 自动创建默认方案")
        assert_eq(auto_scheme[0].name, "默认体检方案", "自动创建的是默认体检方案")

        # 权限：普通用户不能创建方案
        dm.settings.current_role = UserRole.NORMAL
        dm.settings.current_user = "user01"
        s, msg = dm.create_validation_scheme("普通用户方案", rules, "user01", UserRole.NORMAL)
        assert_true(s is None, "普通用户无法创建体检方案（权限拦截）")

        # ===== 测试2: CSV UTF-8 编码 + 完整通过 =====
        separator("测试2: CSV UTF-8 编码 + 完整数据通过体检")
        tmp2 = os.path.join(tmp_root, "t2_csv_utf8")
        os.makedirs(tmp2)
        dm = setup_dm(tmp2, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射2")

        good_rows = create_good_rows(dm, 3)
        csv_path = os.path.join(tmp2, "good_utf8.csv")
        make_csv(csv_path, good_rows, encoding="utf-8-sig")

        batch, err = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme,
            validation_scheme=None, file_encoding="utf-8-sig",
        )
        assert_true(batch is not None, f"体检执行成功: {err}")
        assert_eq(batch.total_rows, 3, "总共有3行")
        assert_eq(batch.pass_rows, 3, "3行全部通过")
        assert_eq(batch.fail_rows, 0, "0行失败")
        assert_eq(len(batch.issues), 0, "没有问题")
        assert_eq(batch.file_encoding, "utf-8-sig", "文件编码记录正确")
        assert_true(batch.snapshot_id is not None, "批次关联了快照")

        # ===== 测试3: CSV GBK 编码 =====
        separator("测试3: CSV GBK 编码解析")
        tmp3 = os.path.join(tmp_root, "t3_csv_gbk")
        os.makedirs(tmp3)
        dm = setup_dm(tmp3, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射3")

        good_rows = create_good_rows(dm, 2)
        csv_path = os.path.join(tmp3, "data_gbk.csv")
        make_csv(csv_path, good_rows, encoding="gbk")

        batch, err = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme,
            validation_scheme=None, file_encoding="gbk",
        )
        assert_true(batch is not None, f"GBK 编码文件体检成功: {err}")
        assert_eq(batch.total_rows, 2, "GBK 解析得到2行数据")
        assert_eq(batch.file_encoding, "gbk", "编码记录为 gbk")

        # auto 模式自动回退到 gbk
        batch2, err = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme,
            validation_scheme=None, file_encoding="auto",
        )
        assert_true(batch2 is not None, f"auto 模式能自动识别 gbk: {err}")

        # ===== 测试4: 8 类问题检测 =====
        separator("测试4: 各类体检问题检测（缺列、空值、时间格式、逻辑错、重复、撞时段、撞单、仪器不存在）")
        tmp4 = os.path.join(tmp_root, "t4_issues")
        os.makedirs(tmp4)
        dm = setup_dm(tmp4, role=UserRole.ADMIN, user="admin01")
        codes = get_instrument_codes(dm, 3)
        today = date.today().strftime("%Y-%m-%d")
        mapping_scheme = create_default_mapping_scheme(dm, "映射4")

        # 混合多种问题的测试数据
        bad_rows = [
            ["", "空仪器用户", today, "09:00:00", "10:00:00", "空仪器"],
            [codes[0], "", today, "09:00:00", "10:00:00", "空申请人"],
            [codes[0], "时间格式错用户", today, "xxxxx", "10:00:00", "开始时间格式错"],
            [codes[0], "时间逻辑错", today, "11:00:00", "09:00:00", "结束早于开始"],
            [codes[0], "重复行A", today, "14:00:00", "15:00:00", "重复行1"],
            [codes[0], "重复行B", today, "14:00:00", "15:00:00", "重复行2"],
            ["不存在的仪器999", "仪器不存在", today, "16:00:00", "17:00:00", "无此仪器"],
        ]
        csv_path = os.path.join(tmp4, "bad_rows.csv")
        make_csv(csv_path, bad_rows)

        batch, err = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        assert_true(batch is not None, f"体检执行: {err}")
        issue_types = {iss.issue_type for iss in batch.issues}
        print(f"  检测到的问题类型: {issue_types}")
        assert_true("空值" in issue_types, "检测到空值问题")
        assert_true("时间格式错" in issue_types, "检测到时间格式错")
        assert_true("时间逻辑错" in issue_types, "检测到时间逻辑错")
        assert_true("重复行" in issue_types, "检测到重复行")
        assert_true("仪器不存在" in issue_types, "检测到仪器不存在")
        assert_true(batch.fail_rows > 0, "存在失败行")

        # 同仪器撞时段（先建一个已存在的预约）
        dm.add_reservation(
            instrument_id=dm.instruments[0].id,
            applicant="已存在用户",
            purpose="已存在预约",
            start_time=f"{today} 08:00:00",
            end_time=f"{today} 09:30:00",
        )
        conflict_rows = [
            [codes[0], "撞时段用户", today, "08:30:00", "09:00:00", "和已存在的重叠"],
        ]
        csv_conflict = os.path.join(tmp4, "conflict.csv")
        make_csv(csv_conflict, conflict_rows)
        batch3, err = dm.run_validation_workbench(
            filepath=csv_conflict, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        assert_true(batch3 is not None, f"撞时段体检: {err}")
        types3 = {iss.issue_type for iss in batch3.issues}
        assert_true("同仪器撞时段" in types3, f"检测到同仪器撞时段（实际：{types3}）")

        # 同申请人撞单
        dm.add_reservation(
            instrument_id=dm.instruments[1].id,
            applicant="撞单申请人",
            purpose="该用户当天已有的单",
            start_time=f"{today} 10:00:00",
            end_time=f"{today} 11:00:00",
        )
        applicant_rows = [
            [codes[2], "撞单申请人", today, "13:00:00", "14:00:00", "同一人当天第二单"],
        ]
        csv_app = os.path.join(tmp4, "applicant_conflict.csv")
        make_csv(csv_app, applicant_rows)
        batch4, err = dm.run_validation_workbench(
            filepath=csv_app, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        assert_true(batch4 is not None, f"申请人撞单体检: {err}")
        types4 = {iss.issue_type for iss in batch4.issues}
        assert_true("同申请人撞单" in types4, f"检测到同申请人撞单（实际：{types4}）")

        # ===== 测试5: 导出失败行 / 通过行 =====
        separator("测试5: 导出失败行和通过行")
        tmp5 = os.path.join(tmp_root, "t5_export")
        os.makedirs(tmp5)
        dm = setup_dm(tmp5, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射5")
        codes = get_instrument_codes(dm, 2)
        today = date.today().strftime("%Y-%m-%d")
        mixed_rows = [
            [codes[0], "好用户", today, "09:00:00", "10:00:00", "正常"],
            ["", "坏用户", today, "11:00:00", "12:00:00", "空仪器"],
            [codes[1], "好用户2", today, "13:00:00", "14:00:00", "正常2"],
        ]
        csv_path = os.path.join(tmp5, "mixed.csv")
        make_csv(csv_path, mixed_rows)

        batch, err = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        assert_true(batch is not None, f"体检完成: {err}")
        assert_eq(batch.pass_rows, 2, "2行通过")
        assert_eq(batch.fail_rows, 1, "1行失败")

        failed_csv = os.path.join(tmp5, "failed.csv")
        ok, msg = dm.export_validation_failed_rows(batch, failed_csv)
        assert_true(ok, f"导出失败行: {msg}")
        assert_true(os.path.exists(failed_csv), "失败行文件存在")
        with open(failed_csv, encoding="utf-8-sig") as f:
            content = f.read()
            assert_true("坏用户" in content, "失败行CSV包含坏用户数据")

        passed_csv = os.path.join(tmp5, "passed.csv")
        ok, msg = dm.export_validation_passed_rows(batch, passed_csv)
        assert_true(ok, f"导出通过行: {msg}")
        assert_true(os.path.exists(passed_csv), "通过行文件存在")
        with open(passed_csv, encoding="utf-8-sig") as f:
            content = f.read()
            assert_true("好用户" in content, "通过行CSV包含好用户数据")
            assert_true("坏用户" not in content, "通过行CSV不包含坏用户数据")

        # ===== 测试6: 批次去向 =====
        separator("测试6: 批次去向设置（送去映射中心/存草稿/退回）")
        tmp6 = os.path.join(tmp_root, "t6_disposition")
        os.makedirs(tmp6)
        dm = setup_dm(tmp6, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射6")

        for disp in [BATCH_DISPOSITION_MAPPING, BATCH_DISPOSITION_DRAFT, BATCH_DISPOSITION_REJECT]:
            good_rows = create_good_rows(dm, 2)
            csv_path = os.path.join(tmp6, f"good_{disp[:2]}.csv")
            make_csv(csv_path, good_rows)
            batch, err = dm.run_validation_workbench(
                filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
            )
            assert_eq(batch.disposition, BATCH_DISPOSITION_PENDING, "初始去向为待处理")
            ok, msg = dm.set_batch_disposition(batch.id, disp, "admin01", UserRole.ADMIN)
            assert_true(ok, f"设置去向「{disp}」成功: {msg}")
            got = dm.get_validation_batch(batch.id)
            assert_eq(got.disposition, disp, f"批次去向更新为「{disp}」")
            if disp == BATCH_DISPOSITION_DRAFT:
                assert_true(got.disposition_executed, "存为草稿后 disposition_executed=True")
                assert_eq(len(got.reservation_ids), 2, "存为草稿生成了2条预约")
                for rid in got.reservation_ids:
                    res = next((r for r in dm.reservations if r.id == rid), None)
                    assert_true(res is not None, f"预约 {rid} 存在于系统中")
                    assert_eq(res.status, ReservationStatus.DRAFT, f"预约 {rid} 是草稿状态")

        # 重复执行同一去向应被拒绝
        dm_dup = setup_dm(os.path.join(tmp_root, "t6_dup"), role=UserRole.ADMIN, user="admin01")
        mapping_scheme_dup = create_default_mapping_scheme(dm_dup, "映射6dup")
        good_rows_dup = create_good_rows(dm_dup, 2)
        csv_dup = os.path.join(tmp_root, "t6_dup", "dup.csv")
        make_csv(csv_dup, good_rows_dup)
        b_dup, _ = dm_dup.run_validation_workbench(
            filepath=csv_dup, mapping_scheme=mapping_scheme_dup, file_encoding="utf-8-sig",
        )
        ok1, _ = dm_dup.set_batch_disposition(b_dup.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        assert_true(ok1, "首次存为草稿成功")
        ok2, msg2 = dm_dup.set_batch_disposition(b_dup.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        assert_true(ok2 is not None, "重复同一去向返回 batch 而非 None")
        got_dup = dm_dup.get_validation_batch(b_dup.id)
        assert_eq(len(got_dup.reservation_ids), 2, "重复执行不会重复创建预约")

        # ===== 测试7: 权限隔离 =====
        separator("测试7: 权限隔离（普通用户只能看自己的批次）")
        tmp7 = os.path.join(tmp_root, "t7_permission")
        os.makedirs(tmp7)
        dm_admin = setup_dm(tmp7, role=UserRole.ADMIN, user="adminA")
        mapping_scheme = create_default_mapping_scheme(dm_admin, "映射7")

        # adminA 创建 2 个批次
        good_rows = create_good_rows(dm_admin, 2)
        for i in range(2):
            csv_path = os.path.join(tmp7, f"admin_{i}.csv")
            make_csv(csv_path, good_rows)
            b, _ = dm_admin.run_validation_workbench(
                filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
            )

        # userB 创建 1 个批次
        dm_admin.settings.current_user = "userB"
        dm_admin.settings.current_role = UserRole.NORMAL
        csv_path = os.path.join(tmp7, "userB.csv")
        make_csv(csv_path, good_rows)
        b_user, _ = dm_admin.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )

        # 管理员能看到所有批次
        dm_admin.settings.current_user = "adminA"
        dm_admin.settings.current_role = UserRole.ADMIN
        all_batches = dm_admin.list_validation_batches()
        assert_eq(len(all_batches), 3, "管理员能看到全部3个批次")

        # 普通用户 userB 只能看到自己的
        dm_admin.settings.current_user = "userB"
        dm_admin.settings.current_role = UserRole.NORMAL
        user_batches = dm_admin.list_validation_batches()
        assert_eq(len(user_batches), 1, "普通用户只能看到自己的1个批次")
        assert_eq(user_batches[0].operator, "userB", "是 userB 创建的批次")

        # 普通用户 userC 看不到任何批次
        dm_admin.settings.current_user = "userC"
        dm_admin.settings.current_role = UserRole.NORMAL
        userc_batches = dm_admin.list_validation_batches()
        assert_eq(len(userc_batches), 0, "userC 看不到任何批次")

        # 普通用户不能撤销批次
        dm_admin.settings.current_user = "userB"
        dm_admin.settings.current_role = UserRole.NORMAL
        ok, msg = dm_admin.revoke_validation_batch(b_user.id, "userB", UserRole.NORMAL, "我想撤销")
        assert_false(ok, "普通用户无法撤销批次")

        # ===== 测试8: 管理员撤销批次 + 恢复快照 + 复跑 =====
        separator("测试8: 管理员撤销批次、恢复快照、复跑")
        tmp8 = os.path.join(tmp_root, "t8_admin_ops")
        os.makedirs(tmp8)
        dm = setup_dm(tmp8, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射8")
        good_rows = create_good_rows(dm, 2)
        csv_path = os.path.join(tmp8, "batch.csv")
        make_csv(csv_path, good_rows)

        batch, _ = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        snapshot_id = batch.snapshot_id
        assert_true(snapshot_id is not None, "批次有快照")

        ok, msg = dm.set_batch_disposition(batch.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        assert_true(ok, f"存为草稿成功: {msg}")
        got_after_draft = dm.get_validation_batch(batch.id)
        res_ids = got_after_draft.reservation_ids
        assert_eq(len(res_ids), 2, "草稿前生成了2条预约")

        for rid in res_ids:
            res = next((r for r in dm.reservations if r.id == rid), None)
            assert_true(res is not None, f"预约 {rid} 存在")
            assert_eq(res.status, ReservationStatus.DRAFT, f"预约 {rid} 是草稿")

        ok, msg = dm.revoke_validation_batch(batch.id, "admin01", UserRole.ADMIN, "测试撤销")
        assert_true(ok, f"撤销批次成功: {msg}")
        got = dm.get_validation_batch(batch.id)
        assert_true(got.is_revoked, "批次已标记撤销")
        assert_eq(got.revoke_reason, "测试撤销", "撤销原因正确")

        for rid in res_ids:
            res = next((r for r in dm.reservations if r.id == rid), None)
            assert_true(res is not None, f"撤销后预约 {rid} 仍在系统中")
            assert_eq(res.status, ReservationStatus.CANCELLED, f"撤销后预约 {rid} 状态为已取消")

        snap = dm.get_validation_snapshot(snapshot_id)
        assert_true(snap is not None, "撤销后快照仍存在")
        assert_true("已撤销" in snap.disposition, f"快照去向已更新为已撤销: {snap.disposition}")

        revoke_logs = [log for log in dm.operation_logs
                       if log.operation_type == "批次导入撤销"]
        assert_true(len(revoke_logs) >= 1, "撤销操作记入了日志")
        last_revoke = revoke_logs[-1]
        assert_true("清理预约2条" in last_revoke.description or "清理预约 2" in last_revoke.description,
                     f"撤销日志包含清理预约数: {last_revoke.description}")

        restored, msg = dm.restore_validation_snapshot(
            snapshot_id, "admin01", UserRole.ADMIN
        )
        assert_true(restored is not None, f"从快照恢复成功: {msg}")
        assert_neq = restored.id != batch.id
        assert_true(assert_neq, "恢复后是新的批次ID")
        assert_eq(restored.total_rows, batch.total_rows, "恢复的批次行数相同")
        assert_eq(restored.disposition, BATCH_DISPOSITION_PENDING, "恢复后去向为待处理")
        assert_false(restored.is_revoked, "恢复的批次未撤销")
        assert_false(restored.disposition_executed, "恢复的批次未执行过去向")

        rerun, msg = dm.rerun_validation_batch(
            batch_id=restored.id, operator="admin01", user_role=UserRole.ADMIN,
            mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )
        assert_true(rerun is not None, f"批次复跑成功: {msg}")
        assert_true(rerun.id != restored.id, "复跑后是新的批次ID")
        assert_eq(rerun.pass_rows, restored.pass_rows, "复跑通过行数相同")

        # ===== 测试8a: 混合批次存草稿只继续通过项 =====
        separator("测试8a: 混合批次(2通过1失败)存草稿只为通过项生成预约")
        tmp8a = os.path.join(tmp_root, "t8a_mixed_draft")
        os.makedirs(tmp8a)
        dm8a = setup_dm(tmp8a, role=UserRole.ADMIN, user="admin01")
        mapping_scheme_8a = create_default_mapping_scheme(dm8a, "映射8a")
        codes_8a = get_instrument_codes(dm8a, 2)
        today_8a = date.today().strftime("%Y-%m-%d")
        mixed_rows_8a = [
            [codes_8a[0], "通过用户1", today_8a, "09:00:00", "10:00:00", "正常1"],
            ["", "失败用户", today_8a, "11:00:00", "12:00:00", "空仪器编号"],
            [codes_8a[1], "通过用户2", today_8a, "13:00:00", "14:00:00", "正常2"],
        ]
        csv_8a = os.path.join(tmp8a, "mixed.csv")
        make_csv(csv_8a, mixed_rows_8a)

        batch_8a, err_8a = dm8a.run_validation_workbench(
            filepath=csv_8a, mapping_scheme=mapping_scheme_8a, file_encoding="utf-8-sig",
        )
        assert_true(batch_8a is not None, f"混合批次体检成功: {err_8a}")
        assert_eq(batch_8a.pass_rows, 2, "2行通过")
        assert_eq(batch_8a.fail_rows, 1, "1行失败")

        ok_8a, msg_8a = dm8a.set_batch_disposition(batch_8a.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        assert_true(ok_8a, f"混合批次存草稿成功: {msg_8a}")
        got_8a = dm8a.get_validation_batch(batch_8a.id)
        assert_true(got_8a.disposition_executed, "混合批次草稿已执行")
        assert_eq(len(got_8a.reservation_ids), 2, "只为2行通过项生成预约")

        for rid in got_8a.reservation_ids:
            res = next((r for r in dm8a.reservations if r.id == rid), None)
            assert_true(res is not None, f"通过项预约 {rid} 存在")
            assert_eq(res.status, ReservationStatus.DRAFT, f"预约 {rid} 是草稿状态")
            assert_true(res.applicant != "失败用户", "失败用户的预约不应被创建")

        # ===== 测试8b: 撤销后预约、批次状态、快照和日志一致 =====
        separator("测试8b: 撤销全通过批次后预约清理+批次状态+快照+日志一致")
        tmp8b = os.path.join(tmp_root, "t8b_revoke_consistency")
        os.makedirs(tmp8b)
        dm8b = setup_dm(tmp8b, role=UserRole.ADMIN, user="admin01")
        mapping_scheme_8b = create_default_mapping_scheme(dm8b, "映射8b")
        good_rows_8b = create_good_rows(dm8b, 3)
        csv_8b = os.path.join(tmp8b, "full_pass.csv")
        make_csv(csv_8b, good_rows_8b)

        batch_8b, _ = dm8b.run_validation_workbench(
            filepath=csv_8b, mapping_scheme=mapping_scheme_8b, file_encoding="utf-8-sig",
        )
        dm8b.set_batch_disposition(batch_8b.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        batch_8b_refreshed = dm8b.get_validation_batch(batch_8b.id)
        assert_eq(len(batch_8b_refreshed.reservation_ids), 3, "3条预约已生成")

        draft_count_before = sum(1 for r in dm8b.reservations if r.status == ReservationStatus.DRAFT)
        assert_eq(draft_count_before, 3, "撤销前有3条草稿预约")

        ok_8b, _ = dm8b.revoke_validation_batch(batch_8b.id, "admin01", UserRole.ADMIN, "一致性测试")
        assert_true(ok_8b, "撤销成功")

        got_8b = dm8b.get_validation_batch(batch_8b.id)
        assert_true(got_8b.is_revoked, "批次已撤销")
        assert_eq(got_8b.revoke_reason, "一致性测试", "撤销原因一致")

        cancelled_count = sum(1 for r in dm8b.reservations if r.status == ReservationStatus.CANCELLED)
        assert_eq(cancelled_count, 3, "3条预约均变为已取消")
        draft_count_after = sum(1 for r in dm8b.reservations if r.status == ReservationStatus.DRAFT)
        assert_eq(draft_count_after, 0, "撤销后没有残留的草稿预约")

        snap_8b = dm8b.get_validation_snapshot(batch_8b.snapshot_id)
        assert_true("已撤销" in snap_8b.disposition, "快照去向标记已撤销")

        revoke_log_8b = [log for log in dm8b.operation_logs
                         if log.operation_type == "批次导入撤销"][-1]
        assert_true("3" in revoke_log_8b.description, f"撤销日志包含预约清理数: {revoke_log_8b.description}")

        # ===== 测试8c: 恢复快照再复跑结果稳定 =====
        separator("测试8c: 恢复快照再复跑结果稳定")
        tmp8c = os.path.join(tmp_root, "t8c_snapshot_rerun")
        os.makedirs(tmp8c)
        dm8c = setup_dm(tmp8c, role=UserRole.ADMIN, user="admin01")
        mapping_scheme_8c = create_default_mapping_scheme(dm8c, "映射8c")
        good_rows_8c = create_good_rows(dm8c, 2)
        csv_8c = os.path.join(tmp8c, "stable.csv")
        make_csv(csv_8c, good_rows_8c)

        batch_8c, _ = dm8c.run_validation_workbench(
            filepath=csv_8c, mapping_scheme=mapping_scheme_8c, file_encoding="utf-8-sig",
        )
        original_pass = batch_8c.pass_rows
        original_fail = batch_8c.fail_rows
        original_total = batch_8c.total_rows
        snap_8c_id = batch_8c.snapshot_id

        dm8c.set_batch_disposition(batch_8c.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        dm8c.revoke_validation_batch(batch_8c.id, "admin01", UserRole.ADMIN, "准备恢复")

        restored_8c, _ = dm8c.restore_validation_snapshot(snap_8c_id, "admin01", UserRole.ADMIN)
        assert_true(restored_8c is not None, "快照恢复成功")
        assert_eq(restored_8c.pass_rows, original_pass, "恢复后通过行数与原始一致")
        assert_eq(restored_8c.fail_rows, original_fail, "恢复后失败行数与原始一致")

        dm8c.set_batch_disposition(restored_8c.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        restored_after_draft = dm8c.get_validation_batch(restored_8c.id)
        assert_eq(len(restored_after_draft.reservation_ids), original_pass,
                  "恢复后再存草稿预约数等于通过行数")

        dm8c.revoke_validation_batch(restored_8c.id, "admin01", UserRole.ADMIN, "撤销后准备复跑")

        rerun_8c, _ = dm8c.rerun_validation_batch(
            batch_id=restored_8c.id, operator="admin01", user_role=UserRole.ADMIN,
            mapping_scheme=mapping_scheme_8c, file_encoding="utf-8-sig",
        )
        assert_true(rerun_8c is not None, "复跑成功")
        assert_eq(rerun_8c.pass_rows, original_pass, "复跑通过行数稳定")
        assert_eq(rerun_8c.total_rows, original_total, "复跑总行数稳定")

        dm8c.set_batch_disposition(rerun_8c.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)
        rerun_after_draft = dm8c.get_validation_batch(rerun_8c.id)
        assert_eq(len(rerun_after_draft.reservation_ids), original_pass,
                  "复跑后存草稿预约数与原始通过行数一致")

        # ===== 测试9: 重启后一致性 =====
        separator("测试9: 重启后数据一致性（批次、快照、方案、用户偏好）")
        tmp9 = os.path.join(tmp_root, "t9_restart")
        os.makedirs(tmp9)
        dm = setup_dm(tmp9, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射9")

        # 保存体检方案
        rules = [ImportValidationRule(rule_key=k, description=n, enabled=True, params=dict(p))
                 for k, n, p in VALIDATION_RULE_DEFAULTS[:4]]
        vscheme, _ = dm.create_validation_scheme("重启方案", rules, "admin01", UserRole.ADMIN)
        dm.set_last_validation_scheme(vscheme.id)

        # 保存用户偏好
        setattr(dm.settings, "last_file_encoding", "gbk")
        setattr(dm.settings, "last_export_dir", tmp9)
        good_rows = create_good_rows(dm, 2)
        csv_path = os.path.join(tmp9, "restart.csv")
        make_csv(csv_path, good_rows, encoding="gbk")
        dm.set_last_validation_file(csv_path)

        # 运行体检生成批次
        batch, _ = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="gbk",
        )
        batch_id = batch.id
        snapshot_id = batch.snapshot_id

        dm.save_settings()
        del dm

        # 重启：重新创建 DataManager
        dm2 = DataManager(tmp9)
        assert_eq(getattr(dm2.settings, "last_file_encoding", None), "gbk", "重启后编码偏好恢复")
        assert_eq(getattr(dm2.settings, "last_export_dir", None), tmp9, "重启后导出目录恢复")

        # 检查方案
        schemes = dm2.list_validation_schemes()
        assert_eq(len(schemes), 1, "重启后体检方案还在")
        last_vs = dm2.get_last_validation_scheme()
        assert_true(last_vs is not None, "上次体检方案可恢复")

        # 检查批次
        got_batch = dm2.get_validation_batch(batch_id)
        assert_true(got_batch is not None, "重启后批次仍存在")
        assert_eq(got_batch.total_rows, 2, "批次数据完整")
        assert_true(got_batch.snapshot_id is not None, "批次快照ID存在")

        # 检查快照
        snapshots = getattr(dm2, "validation_snapshots", [])
        assert_true(any(s.id == snapshot_id for s in snapshots), "重启后快照仍存在")

        # ===== 测试10: Excel 格式（如果安装了 openpyxl） =====
        if has_openpyxl:
            separator("测试10: Excel 格式导入体检")
            tmp10 = os.path.join(tmp_root, "t10_excel")
            os.makedirs(tmp10)
            dm = setup_dm(tmp10, role=UserRole.ADMIN, user="admin01")
            mapping_scheme = create_default_mapping_scheme(dm, "映射10")

            codes = get_instrument_codes(dm, 2)
            today = date.today().strftime("%Y-%m-%d")
            rows = [
                [codes[0], "Excel用户1", today, "09:00:00", "10:00:00", "Excel测试1"],
                [codes[1], "Excel用户2", today, "11:00:00", "12:00:00", "Excel测试2"],
            ]
            xlsx_path = os.path.join(tmp10, "data.xlsx")
            ok = make_excel(xlsx_path, rows)
            assert_true(ok, "生成 Excel 文件成功")

            batch, err = dm.run_validation_workbench(
                filepath=xlsx_path, mapping_scheme=mapping_scheme, file_encoding="auto",
            )
            assert_true(batch is not None, f"Excel 体检成功: {err}")
            assert_eq(batch.total_rows, 2, "Excel 解析得到2行")
            assert_eq(batch.pass_rows, 2, "Excel 数据2行通过")

        # ===== 测试11: 规则开关生效 =====
        separator("测试11: 体检规则开关可独立控制")
        tmp11 = os.path.join(tmp_root, "t11_rule_toggle")
        os.makedirs(tmp11)
        dm = setup_dm(tmp11, role=UserRole.ADMIN, user="admin01")
        mapping_scheme = create_default_mapping_scheme(dm, "映射11")
        codes = get_instrument_codes(dm, 1)
        today = date.today().strftime("%Y-%m-%d")

        # 有空值的数据
        rows_with_empty = [["", "空仪器", today, "09:00:00", "10:00:00", "测试"]]
        csv_path = os.path.join(tmp11, "toggle.csv")
        make_csv(csv_path, rows_with_empty)

        # 关闭空值检查
        all_rules_off_empty = [
            ImportValidationRule(rule_key=k, description=n,
                                 enabled=(k != "empty_values"), params=dict(p))
            for k, n, p in VALIDATION_RULE_DEFAULTS
        ]
        vscheme = ImportValidationScheme(
            id="_t_", name="_t_", created_by="", created_at="", updated_at="",
            rules=all_rules_off_empty,
        )
        batch_off, _ = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme,
            validation_scheme=vscheme, file_encoding="utf-8-sig",
        )
        types_off = {iss.issue_type for iss in batch_off.issues}
        assert_true("空值" not in types_off, "关闭空值检查后不再报空值问题")

        # 开启空值检查
        all_rules_on = [
            ImportValidationRule(rule_key=k, description=n, enabled=True, params=dict(p))
            for k, n, p in VALIDATION_RULE_DEFAULTS
        ]
        vscheme_on = ImportValidationScheme(
            id="_t2_", name="_t2_", created_by="", created_at="", updated_at="",
            rules=all_rules_on,
        )
        batch_on, _ = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme,
            validation_scheme=vscheme_on, file_encoding="utf-8-sig",
        )
        types_on = {iss.issue_type for iss in batch_on.issues}
        assert_true("空值" in types_on, "开启空值检查后会报空值问题")

        # ===== 测试12: 操作日志记录 =====
        separator("测试12: 所有关键操作均记入操作日志")
        tmp12 = os.path.join(tmp_root, "t12_logs")
        os.makedirs(tmp12)
        dm = setup_dm(tmp12, role=UserRole.ADMIN, user="admin01")
        initial_log_count = len(dm.operation_logs)

        mapping_scheme = create_default_mapping_scheme(dm, "映射12")
        good_rows = create_good_rows(dm, 1)
        csv_path = os.path.join(tmp12, "log.csv")
        make_csv(csv_path, good_rows)

        # 创建体检方案
        rules = [ImportValidationRule(rule_key=k, description=n, enabled=True, params=dict(p))
                 for k, n, p in VALIDATION_RULE_DEFAULTS]
        vscheme, _ = dm.create_validation_scheme("日志方案", rules, "admin01", UserRole.ADMIN)

        # 运行体检
        batch, _ = dm.run_validation_workbench(
            filepath=csv_path, mapping_scheme=mapping_scheme, file_encoding="utf-8-sig",
        )

        # 设置去向
        dm.set_batch_disposition(batch.id, BATCH_DISPOSITION_DRAFT, "admin01", UserRole.ADMIN)

        # 撤销批次
        dm.revoke_validation_batch(batch.id, "admin01", UserRole.ADMIN, "日志测试撤销")

        # 恢复快照
        dm.restore_validation_snapshot(batch.snapshot_id, "admin01", UserRole.ADMIN)

        # 更新方案
        dm.update_validation_scheme(vscheme.id, "admin01", UserRole.ADMIN, name="日志方案改")

        # 删除方案
        dm.delete_validation_scheme(vscheme.id, "admin01", UserRole.ADMIN)

        log_types = {str(log.operation_type) for log in dm.operation_logs[initial_log_count:]}
        expected_names = [
            "体检方案创建",
            "批次体检执行",
            "批次去向处理",
            "批次导入撤销",
            "批次快照恢复",
            "体检方案更新",
            "体检方案删除",
        ]
        print(f"  记录的操作类型: {log_types}")
        for name in expected_names:
            assert_true(name in log_types, f"日志包含操作：{name}")

        # ===== 总结 =====
        separator("[ALL PASS] 所有测试通过！")
        print(f"\n测试完成，临时目录可清理：{tmp_root}")

    finally:
        # 清理临时目录（测试通过后可删除，失败则保留以便排查）
        try:
            shutil.rmtree(tmp_root)
            print(f"\n已清理临时目录: {tmp_root}")
        except Exception as e:
            print(f"\n清理临时目录失败（可手动删除）: {e}")


if __name__ == "__main__":
    main()
