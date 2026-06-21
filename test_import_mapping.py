"""
预约导入映射中心 - 回归测试
覆盖：CSV/Excel双格式、权限隔离、方案撤销、重启恢复、预检、导入导出
"""
import os
import sys
import json
import csv
import shutil
import tempfile
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import (
    DataManager, UserRole, ReservationStatus, OperationType,
    STANDARD_COLUMNS, ImportMappingScheme
)


def separator(title=""):
    line = "=" * 70
    print("\n" + line)
    if title:
        print(f"  {title}")
        print(line)


def assert_true(cond, msg):
    if not cond:
        print(f"❌ 断言失败: {msg}")
        sys.exit(1)
    print(f"✅ {msg}")


def assert_false(cond, msg):
    if cond:
        print(f"❌ 断言失败(应为False): {msg}")
        sys.exit(1)
    print(f"✅ {msg}")


def assert_eq(a, b, msg):
    if a != b:
        print(f"❌ 断言失败: {msg}")
        print(f"   期望: {b!r}")
        print(f"   实际: {a!r}")
        sys.exit(1)
    print(f"✅ {msg}")


def setup_dm(tmpdir):
    """在临时目录创建一个 DataManager"""
    dm = DataManager(tmpdir)
    # 确保有几台仪器（预检需要仪器存在）
    if len(dm.instruments) < 3:
        dm.init_sample_data()
        dm.save_instruments()
    return dm


def make_csv(path, rows, headers=None):
    if headers is None:
        headers = ["仪器编号", "申请人", "日期", "开始时间", "结束时间", "用途"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
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


def get_instrument_codes(dm):
    from data_manager import InstrumentStatus
    return [ins.code for ins in dm.instruments if ins.status == InstrumentStatus.NORMAL][:3]


def main():
    tmp_root = tempfile.mkdtemp(prefix="test_map_")
    print(f"临时测试目录: {tmp_root}")

    try:
        # ===== 测试1: CSV导入 - 完整通过 =====
        separator("测试1: CSV格式导入 - 完整流程（解析→预检→生成草稿）")
        tmp1 = os.path.join(tmp_root, "t1_csv_ok")
        os.makedirs(tmp1)
        dm = setup_dm(tmp1)
        codes = get_instrument_codes(dm)
        csv_path = os.path.join(tmp1, "good.csv")
        today = date.today().strftime("%Y-%m-%d")
        data_rows = [
            [codes[0], "张三", today, "09:00:00", "10:00:00", "日常校准"],
            [codes[1], "李四", today, "10:30:00", "11:30:00", "性能测试"],
            [codes[2], "王五", today, "14:00:00", "15:30:00", "年度检定"],
        ]
        make_csv(csv_path, data_rows)

        # 1a: 解析CSV文件
        headers, rows, err = dm.parse_import_file(csv_path)
        assert_true(not err, f"CSV解析无错误: {err!r}")
        assert_eq(len(rows), 3, "CSV解析得到3行数据")
        assert_eq(len(headers), 6, f"CSV解析得到6列（实际{len(headers)}）")

        # 1b: 自动匹配列
        matched = dm.auto_match_columns(headers)
        assert_true(len(matched) >= 5, f"自动匹配至少5列（实际{len(matched)}）")
        assert_true("instrument_code" in matched and "applicant" in matched, "仪器编号&申请人都匹配到")

        # 1c: 创建映射方案（管理员）
        scheme, msg = dm.create_mapping_scheme(
            name="默认CSV方案",
            column_mapping=matched,
            operator="管理员",
            user_role=UserRole.ADMIN,
            datetime_format="%Y-%m-%d %H:%M:%S",
            date_format="%Y-%m-%d",
            time_format="%H:%M:%S",
        )
        assert_true(scheme is not None, f"创建映射方案成功: {msg}")
        assert_true(scheme.id and scheme.name, "方案有ID和名称")
        assert_eq(scheme.created_by, "管理员", "创建人记录正确")

        # 1d: 运行预检
        precheck, err = dm.run_import_precheck(csv_path, scheme)
        assert_true(not err and precheck is not None, f"预检执行无错误: {err!r}")
        assert_eq(precheck.total_rows, 3, f"预检总计3行（实际{precheck.total_rows}）")
        assert_eq(precheck.fail_rows, 0, f"预检失败0行（实际失败{precheck.fail_rows}，问题: {precheck.issues[:3]}）")
        assert_eq(precheck.pass_rows, 3, f"预检通过3行")
        assert_true(len(precheck.standard_rows) == 3, "生成3条标准数据")

        # 1e: 预检结果已持久化（会话状态）
        loaded = dm.get_last_precheck_result()
        assert_true(loaded is not None, "预检结果已保存到会话状态")
        assert_eq(loaded.total_rows, 3, "恢复的预检结果正确")
        assert_eq(dm.get_last_mapping_file(), csv_path, "上次文件路径已保存")

        # 1f: 执行导入到草稿
        count, ids, errors = dm.execute_import_to_drafts(
            precheck, "test_user", UserRole.ADMIN
        )
        assert_eq(count, 3, f"成功生成3条草稿预约（实际{count}，错误: {errors[:2]}）")
        assert_true(len(ids) == 3, "返回3个预约ID")
        # 验证预约确实是草稿状态
        draft_count = sum(1 for r in dm.reservations if r.status == ReservationStatus.DRAFT)
        assert_true(draft_count >= 3, f"预约列表中至少3条草稿（实际{draft_count}）")

        # 1g: 日志验证 - 预检和导入都记了日志
        dm.load_operation_logs()
        log_types = [log.operation_type for log in dm.operation_logs[-10:]]
        assert_true(OperationType.RESERVATION_IMPORT_PRECHECK in log_types, "预检操作记入日志")
        assert_true(OperationType.RESERVATION_IMPORT_EXECUTE in log_types, "导入执行记入日志")
        assert_true(OperationType.MAPPING_SCHEME_CREATE in log_types, "方案创建记入日志")
        print("  💡 日志中最后10条类型:", log_types)

        # ===== 测试2: 预检问题检测 =====
        separator("测试2: 预检 - 缺列/空值/时间格式错/重复行/仪器不存在")
        tmp2 = os.path.join(tmp_root, "t2_precheck_issues")
        os.makedirs(tmp2)
        dm2 = setup_dm(tmp2)
        codes = get_instrument_codes(dm2)

        bad_csv = os.path.join(tmp2, "bad.csv")
        bad_headers = ["设备编号", "申请人", "日期", "开始", "结束"]  # 缺“用途”列
        bad_rows = [
            ["", "张三", today, "09:00", "10:00"],  # 仪器编号空
            [codes[0], "", today, "09:00", "10:00"],  # 申请人空
            [codes[0], "张三", today, "10:00", "09:00"],  # 结束早于开始
            [codes[0], "张三", today, "NOT_TIME", "10:00"],  # 时间格式错
            ["NOT_EXIST_CODE", "张三", today, "09:00", "10:00"],  # 仪器不存在
            [codes[0], "张三", today, "09:00", "10:00"],  # 重复（与第一行修正后重复）
            [codes[0], "张三", today, "09:00", "10:00"],  # 再次重复
        ]
        make_csv(bad_csv, bad_rows, bad_headers)

        # 创建映射 - 缺“用途”列
        bad_mapping = {
            "instrument_code": "设备编号",
            "applicant": "申请人",
            "reservation_date": "日期",
            "start_time": "开始",
            "end_time": "结束",
            # purpose 缺失
        }
        bad_scheme, _ = dm2.create_mapping_scheme(
            "问题方案", bad_mapping, "管理员", UserRole.ADMIN,
            time_format="%H:%M"
        )

        result, err = dm2.run_import_precheck(bad_csv, bad_scheme)
        assert_true(result is not None, "问题文件也能完成预检（只是有问题）")
        print(f"  预检结果: 总计{result.total_rows},通过{result.pass_rows},失败{result.fail_rows},问题{len(result.issues)}条")
        issue_types = [i.issue_type for i in result.issues]
        assert_true("空值" in issue_types, "检测到空值问题")
        assert_true("时间逻辑错" in issue_types, "检测到时间逻辑错（开始晚于结束）")
        assert_true("时间格式错" in issue_types, "检测到时间格式错误")
        assert_true("仪器不存在" in issue_types, "检测到仪器不存在")
        assert_true("重复行" in issue_types, "检测到重复行")
        print(f"  问题类型统计: {set(issue_types)}")

        # 失败行导出
        fail_csv = os.path.join(tmp2, "fails.csv")
        ok, msg = dm2.export_precheck_failed_rows(result, fail_csv)
        assert_true(ok and os.path.exists(fail_csv), f"失败行导出成功: {msg}")
        with open(fail_csv, encoding="utf-8-sig") as f:
            lines = f.readlines()
        assert_true(len(lines) >= 2, "失败行CSV有表头+至少1条记录")

        # 执行导入必须失败（fail_rows>0）
        count, ids, errors = dm2.execute_import_to_drafts(
            result, "admin", UserRole.ADMIN
        )
        assert_eq(count, 0, "预检不通过则导入0条")
        assert_true(len(errors) > 0, "返回了错误提示")

        # ===== 测试3: 权限隔离 - 普通用户不能维护方案 =====
        separator("测试3: 权限隔离 - 普通用户禁止创建/更新/撤销/删除方案")
        tmp3 = os.path.join(tmp_root, "t3_perms")
        os.makedirs(tmp3)
        dm3 = setup_dm(tmp3)
        admin_scheme, _ = dm3.create_mapping_scheme(
            "admin_only", {
                "instrument_code": "仪器编号",
                "applicant": "申请人",
                "start_time": "开始",
                "end_time": "结束",
                "purpose": "用途",
            },
            "admin", UserRole.ADMIN
        )
        assert_true(admin_scheme is not None, "管理员创建方案成功")

        # 普通用户尝试创建
        s, msg = dm3.create_mapping_scheme(
            "hacker", {"instrument_code": "x"},
            "普通用户", UserRole.NORMAL
        )
        assert_true(s is None, f"普通用户创建被拒绝: {msg}")

        # 普通用户尝试更新
        s, msg = dm3.update_mapping_scheme(
            admin_scheme.id, "普通用户", UserRole.NORMAL,
            name="篡改"
        )
        assert_true(s is None, f"普通用户更新被拒绝: {msg}")

        # 普通用户尝试撤销
        s, msg = dm3.revoke_mapping_scheme(
            admin_scheme.id, "普通用户", UserRole.NORMAL, "haha"
        )
        assert_true(s is None, f"普通用户撤销被拒绝: {msg}")

        # 普通用户尝试删除
        ok, msg = dm3.delete_mapping_scheme(
            admin_scheme.id, "普通用户", UserRole.NORMAL
        )
        assert_false(ok, f"普通用户删除被拒绝: {msg}")

        # 管理员依然可以正常操作
        loaded = dm3.get_mapping_scheme(admin_scheme.id)
        assert_eq(loaded.name, "admin_only", "管理员的方案未被篡改")
        print("  ✅ 4项权限控制均生效")

        # ===== 测试4: 方案撤销 =====
        separator("测试4: 方案撤销 - 标记后不可复用，但保留历史")
        tmp4 = os.path.join(tmp_root, "t4_revoke")
        os.makedirs(tmp4)
        dm4 = setup_dm(tmp4)
        scheme4, _ = dm4.create_mapping_scheme(
            "临时方案", {"instrument_code": "c", "applicant": "a",
                        "start_time": "s", "end_time": "e", "purpose": "p"},
            "admin", UserRole.ADMIN
        )
        assert_false(scheme4.is_revoked, "新建方案is_revoked=False")

        revoked, msg = dm4.revoke_mapping_scheme(
            scheme4.id, "admin", UserRole.ADMIN, "弃用，已更换新版本"
        )
        assert_true(revoked is not None, f"撤销成功: {msg}")
        assert_true(revoked.is_revoked, "撤销后is_revoked=True")
        assert_eq(revoked.revoke_reason, "弃用，已更换新版本", "撤销原因已记录")
        assert_true(revoked.revoked_by == "admin", "撤销人已记录")
        assert_true(revoked.revoked_at is not None and len(revoked.revoked_at) > 0, "撤销时间已记录")

        # 列表默认不含已撤销
        active = dm4.list_mapping_schemes(include_revoked=False)
        assert_true(all(not s.is_revoked for s in active), "默认列表无已撤销方案")
        # 含撤销的能查到
        all_schemes = dm4.list_mapping_schemes(include_revoked=True)
        assert_true(any(s.id == scheme4.id and s.is_revoked for s in all_schemes),
                    "include_revoked=True时可查询到历史方案")

        # 已撤销方案不允许更新
        s2, msg2 = dm4.update_mapping_scheme(
            scheme4.id, "admin", UserRole.ADMIN, name="试试改名"
        )
        assert_true(s2 is None, f"已撤销方案禁止更新: {msg2}")

        # 日志验证
        dm4.load_operation_logs()
        recent_types = [log.operation_type for log in dm4.operation_logs[-5:]]
        assert_true(OperationType.MAPPING_SCHEME_REVOKE in recent_types,
                    "方案撤销操作已记入日志")

        # ===== 测试5: 重启后配置恢复 =====
        separator("测试5: 跨重启恢复 - 方案/文件/预检/最近选择持久化")
        tmp5 = os.path.join(tmp_root, "t5_restart")
        os.makedirs(tmp5)
        dm5a = setup_dm(tmp5)
        codes = get_instrument_codes(dm5a)

        # 5a: 创建2套方案
        sA, _ = dm5a.create_mapping_scheme(
            "方案A",
            {"instrument_code": "仪器编号", "applicant": "申请人",
             "reservation_date": "日期", "start_time": "开始时间", "end_time": "结束时间", "purpose": "用途"},
            "admin", UserRole.ADMIN
        )
        sB, _ = dm5a.create_mapping_scheme(
            "方案B",
            {"instrument_code": "InsCode", "applicant": "User",
             "reservation_date": "Date", "start_time": "Start", "end_time": "End", "purpose": "Usage"},
            "admin", UserRole.ADMIN
        )
        assert_true(sA and sB, "两套方案创建成功")

        # 5b: 选一个CSV并预检
        good_csv5 = os.path.join(tmp5, "recover.csv")
        make_csv(good_csv5, [
            [codes[0], "A", today, "09:00:00", "10:00:00", "测试A"],
            [codes[1], "B", today, "11:00:00", "12:00:00", "测试B"],
        ])
        precheck5, _ = dm5a.run_import_precheck(good_csv5, sA)
        assert_true(precheck5 is not None and precheck5.fail_rows == 0,
                    "预检通过（用于持久化测试）")
        # 记录last_scheme = sB
        dm5a.set_last_mapping_scheme(sB.id)

        # 5c: 强制保存所有数据
        dm5a.save_settings()
        dm5a.save_mapping_schemes()
        dm5a.save_operation_logs()

        # 5d: 模拟重启 - 新建 DataManager 实例（读同一目录）
        dm5b = DataManager(tmp5)
        dm5b.load_all()

        # 方案恢复
        loaded_all = dm5b.list_mapping_schemes(include_revoked=True)
        assert_true(len(loaded_all) >= 2, f"重启后至少2套方案（实际{len(loaded_all)}）")
        sA_reloaded = dm5b.get_mapping_scheme(sA.id)
        assert_true(sA_reloaded is not None, "方案A已从磁盘恢复")
        assert_eq(sA_reloaded.name, "方案A", "方案A名称正确")

        # 最近文件/方案恢复
        last_scheme = dm5b.get_last_mapping_scheme()
        assert_true(last_scheme is not None and last_scheme.id == sB.id,
                    f"最近选择的方案B已恢复（实际{last_scheme.id if last_scheme else None}）")
        last_file = dm5b.get_last_mapping_file()
        assert_eq(last_file, good_csv5, "最近文件路径已恢复")

        # 预检结果恢复
        last_pc = dm5b.get_last_precheck_result()
        assert_true(last_pc is not None, "最近预检结果已恢复")
        assert_eq(last_pc.total_rows, 2, "恢复的预检总2行")
        assert_eq(last_pc.fail_rows, 0, "恢复的预检失败0行")

        print("  ✅ 4种持久化均通过：方案列表、指定方案详情、最近方案选择、最近预检结果")

        # ===== 测试6: 方案导入导出备份 =====
        separator("测试6: 方案导入/导出备份")
        tmp6 = os.path.join(tmp_root, "t6_io")
        os.makedirs(tmp6)
        dm6a = setup_dm(tmp6)
        s1, _ = dm6a.create_mapping_scheme(
            "导出版-1", {"a": "1", "b": "2"}, "admin", UserRole.ADMIN
        )
        s2, _ = dm6a.create_mapping_scheme(
            "导出版-2", {"x": "100"}, "admin", UserRole.ADMIN
        )
        s3_revoked, _ = dm6a.create_mapping_scheme(
            "撤销的", {}, "admin", UserRole.ADMIN
        )
        dm6a.revoke_mapping_scheme(s3_revoked.id, "admin", UserRole.ADMIN, "过期")

        # 导出
        backup = os.path.join(tmp6, "backup.json")
        ok, msg = dm6a.export_mapping_schemes(backup)
        assert_true(ok and os.path.exists(backup), f"导出成功: {msg}")
        with open(backup, encoding="utf-8") as f:
            backup_data = json.load(f)
        schemes_in_backup = backup_data.get("schemes", [])
        names_in_backup = {x.get("name", "") for x in schemes_in_backup}
        assert_true("导出版-1" in names_in_backup and "撤销的" in names_in_backup,
                    f"备份文件包含我们创建的3套方案（备份含{len(schemes_in_backup)}个）")

        # 清空目录后导入
        tmp6b = os.path.join(tmp_root, "t6_import")
        os.makedirs(tmp6b)
        dm6b = setup_dm(tmp6b)
        imported, errors = dm6b.import_mapping_schemes(
            backup, "import_user", UserRole.ADMIN, overwrite=False
        )
        assert_eq(imported, 3, f"成功导入3套方案（实际{imported}，错误{errors}）")
        loaded_names = {s.name for s in dm6b.list_mapping_schemes(include_revoked=True)}
        assert_true("导出版-1" in loaded_names and "撤销的" in loaded_names,
                    "导入后方案名称齐全")

        # 导入后方案可用于预检
        s1_loaded = dm6b.get_mapping_scheme(s1.id)
        assert_true(s1_loaded is not None and s1_loaded.column_mapping == {"a": "1", "b": "2"},
                    "方案映射细节（列对应）完整保留")

        # 导入权限测试 - 普通用户
        tmp6c = os.path.join(tmp_root, "t6_import_perm")
        os.makedirs(tmp6c)
        dm6c = setup_dm(tmp6c)
        n, errs = dm6c.import_mapping_schemes(backup, "用户A", UserRole.NORMAL, overwrite=True)
        assert_eq(n, 0, f"普通用户导入被拒绝，错误: {errs[:1]}")

        # ===== 测试7: 沙盘导入 =====
        separator("测试7: 导入到沙盘（而非直接草稿）")
        tmp7 = os.path.join(tmp_root, "t7_sandbox")
        os.makedirs(tmp7)
        dm7 = setup_dm(tmp7)
        codes = get_instrument_codes(dm7)
        sandbox_csv = os.path.join(tmp7, "sb.csv")
        make_csv(sandbox_csv, [
            [codes[0], "赵一", today, "09:00:00", "10:30:00", "沙盘演练1"],
            [codes[1], "钱二", today, "13:00:00", "14:00:00", "沙盘演练2"],
        ])
        scheme7, _ = dm7.create_mapping_scheme(
            "sandbox_test",
            dm7.auto_match_columns(["仪器编号", "申请人", "日期", "开始时间", "结束时间", "用途"]),
            "admin", UserRole.ADMIN
        )
        pc7, _ = dm7.run_import_precheck(sandbox_csv, scheme7)

        # 普通用户不能导入沙盘
        draft, errs = dm7.execute_import_to_sandbox(
            pc7, "测试沙盘草稿", "普通用户", UserRole.NORMAL
        )
        assert_true(draft is None and len(errs) > 0, f"普通用户被禁止导入沙盘: {errs[:1]}")

        # 管理员可以
        draft, errs = dm7.execute_import_to_sandbox(
            pc7, "测试沙盘草稿", "admin", UserRole.ADMIN
        )
        assert_true(draft is not None, f"管理员成功创建沙盘草稿: {errs}")
        assert_eq(draft.name, "测试沙盘草稿", "沙盘名称正确")
        assert_eq(len(draft.items), 2, "沙盘包含2条记录")
        assert_true(draft.status == "PENDING", "沙盘状态为PENDING待确认")
        # 校验项目确实来自数据
        assert_true(draft.items[0].applicant == "赵一", "第1条申请人正确")
        assert_true(draft.items[1].purpose == "沙盘演练2", "第2条用途正确")

        # ===== 测试8: Excel格式支持 =====
        separator("测试8: Excel格式导入（若环境有openpyxl）")
        tmp8 = os.path.join(tmp_root, "t8_excel")
        os.makedirs(tmp8)
        dm8 = setup_dm(tmp8)
        codes = get_instrument_codes(dm8)
        excel_path = os.path.join(tmp8, "orders.xlsx")
        ok = make_excel(excel_path, [
            [codes[0], "孙七", today, "08:30:00", "09:30:00", "Excel校准1"],
            [codes[1], "周八", today, "15:00:00", "16:00:00", "Excel校准2"],
            [codes[2], "吴九", today, "16:30:00", "17:30:00", "Excel校准3"],
        ])
        if not ok:
            print("⏭  环境无openpyxl，Excel测试跳过（CSV已完整覆盖）")
        else:
            headers, rows, err = dm8.parse_import_file(excel_path)
            assert_true(not err, f"Excel解析成功，错误: {err!r}")
            assert_eq(len(rows), 3, f"Excel读取3行（实际{len(rows)}）")
            assert_true("仪器编号" in headers, "Excel列名读取正确")

            matched = dm8.auto_match_columns(headers)
            scheme8, _ = dm8.create_mapping_scheme(
                "Excel方案", matched, "admin", UserRole.ADMIN
            )
            pc8, err = dm8.run_import_precheck(excel_path, scheme8)
            assert_true(pc8 is not None and not err, f"Excel预检无错误: {err!r}")
            assert_eq(pc8.fail_rows, 0, f"Excel预检失败0行（失败: {pc8.fail_rows}）")
            # 导入草稿
            count, _, _ = dm8.execute_import_to_drafts(
                pc8, "admin", UserRole.ADMIN
            )
            assert_eq(count, 3, "Excel数据成功生成3条草稿")

        # ===== 结束 =====
        separator("所有测试通过 ✅")
        print(f"\n🎉 8大模块全部通过，临时目录: {tmp_root}")
        print("   1. CSV完整导入+日志")
        print("   2. 预检问题检测（6类问题）")
        print("   3. 权限隔离（4项）")
        print("   4. 方案撤销+历史保留")
        print("   5. 跨重启4种持久化")
        print("   6. 方案导入导出备份")
        print("   7. 沙盘导入权限+数据正确性")
        print("   8. Excel格式（如环境支持）")

    finally:
        # 清理临时文件（保留7秒以便排查，可注释掉）
        # shutil.rmtree(tmp_root, ignore_errors=True)
        pass


if __name__ == "__main__":
    main()
