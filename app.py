import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, STATUS_FLOW, OperationType, ReservationTemplate,
    ImportResult, BatchRecord, TemplateSnapshot, BatchItemResult,
    SandboxItemStatus, SandboxDraft, SandboxDraftItem,
    STANDARD_COLUMNS, ImportMappingScheme, PrecheckResult, PrecheckIssue,
    ImportValidationRule, ImportValidationScheme, ValidationSnapshot, ValidationBatch,
    BATCH_DISPOSITION_MAPPING, BATCH_DISPOSITION_DRAFT, BATCH_DISPOSITION_REJECT, BATCH_DISPOSITION_PENDING,
    VALIDATION_RULE_DEFAULTS
)


class ReservationDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager, title="新建预约", reservation=None, instrument_id=None):
        super().__init__(parent)
        self.dm = dm
        self.reservation = reservation
        self.result = None
        self.preselected_instrument_id = instrument_id
        self.applied_template_id = None
        self.applied_template = None
        self.reminder_minutes = 0
        self.title(title)
        self.geometry("520x620")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        if reservation:
            self._load_reservation()
        elif instrument_id:
            self._select_instrument_by_id(instrument_id)

    def _build_ui(self):
        padding = {"padx": 10, "pady": 5}

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        if not self.reservation:
            ttk.Label(frm, text="套用模板：").grid(row=0, column=0, sticky="e", **padding)
            self.template_var = tk.StringVar()
            self.template_combo = ttk.Combobox(
                frm, textvariable=self.template_var, state="readonly", width=35
            )
            self._populate_templates()
            self.template_combo.grid(row=0, column=1, **padding)
            self.template_combo.bind("<<ComboboxSelected>>", self._on_template_select)

            ttk.Button(frm, text="一键套用", command=self._apply_template, width=10).grid(
                row=0, column=2, padx=5
            )

            ttk.Separator(frm, orient="horizontal").grid(
                row=1, column=0, columnspan=3, sticky="ew", pady=8
            )
            row_offset = 2
        else:
            row_offset = 0

        ttk.Label(frm, text="仪器：").grid(row=row_offset, column=0, sticky="e", **padding)
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(
            frm, textvariable=self.instrument_var, state="readonly", width=35
        )
        self._populate_instruments()
        self.instrument_combo.grid(row=row_offset, column=1, **padding)
        self.instrument_combo.bind("<<ComboboxSelected>>", self._on_instrument_change)

        ttk.Label(frm, text="申请人：").grid(row=row_offset+1, column=0, sticky="e", **padding)
        self.applicant_var = tk.StringVar(value=self.dm.settings.current_user)
        ttk.Entry(frm, textvariable=self.applicant_var, width=37).grid(row=row_offset+1, column=1, **padding)

        ttk.Label(frm, text="用途：").grid(row=row_offset+2, column=0, sticky="ne", **padding)
        self.purpose_text = tk.Text(frm, width=37, height=3)
        self.purpose_text.grid(row=row_offset+2, column=1, **padding)

        ttk.Label(frm, text="开始时间：").grid(row=row_offset+3, column=0, sticky="e", **padding)
        self.start_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.start_var, width=37).grid(row=row_offset+3, column=1, **padding)
        ttk.Label(frm, text="格式：YYYY-MM-DD HH:MM:SS", foreground="gray").grid(
            row=row_offset+4, column=1, sticky="w", padx=10
        )

        ttk.Label(frm, text="结束时间：").grid(row=row_offset+5, column=0, sticky="e", **padding)
        self.end_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.end_var, width=37).grid(row=row_offset+5, column=1, **padding)
        ttk.Label(frm, text="格式：YYYY-MM-DD HH:MM:SS", foreground="gray").grid(
            row=row_offset+6, column=1, sticky="w", padx=10
        )

        if self.reservation:
            if self.reservation.status in [ReservationStatus.DRAFT, ReservationStatus.PENDING_CONFIRM]:
                ttk.Label(frm, text="当前状态：").grid(row=row_offset+7, column=0, sticky="e", **padding)
                ttk.Label(frm, text=self.reservation.status.value).grid(row=row_offset+7, column=1, sticky="w", **padding)

            if self.reservation.template_snapshot:
                ttk.Label(frm, text="模板快照：").grid(row=row_offset+8, column=0, sticky="ne", **padding)
                snap = self.reservation.template_snapshot
                if isinstance(snap, dict):
                    snap_name = snap.get("template_name", "")
                    snap_time = snap.get("snapshot_time", "")
                else:
                    snap_name = getattr(snap, "template_name", "")
                    snap_time = getattr(snap, "snapshot_time", "")
                snap_text = f"模板：{snap_name}\n快照时间：{snap_time}"
                ttk.Label(frm, text=snap_text, foreground="#1565c0", justify="left").grid(
                    row=row_offset+8, column=1, sticky="w", **padding
                )

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=row_offset+9, column=0, columnspan=3, pady=20)

        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=12).pack(side="left", padx=10)

        if not self.reservation:
            tomorrow = date.today() + timedelta(days=1)
            self.start_var.set(tomorrow.strftime("%Y-%m-%d") + " 09:00:00")
            self.end_var.set(tomorrow.strftime("%Y-%m-%d") + " 11:00:00")

    def _populate_templates(self):
        templates = self.dm.get_applicable_templates(self.dm.settings.current_user)
        self.template_list = templates
        display = ["（不使用模板）"] + [f"{t.name} - {t.instrument_code}" for t in templates]
        self.template_combo["values"] = display
        self.template_combo.current(0)

    def _on_instrument_change(self, _=None):
        if not self.reservation:
            idx = self.instrument_combo.current()
            if idx >= 0:
                normal_instruments = [ins for ins in self.dm.instruments if ins.status == InstrumentStatus.NORMAL]
                if idx < len(normal_instruments):
                    ins = normal_instruments[idx]
                    templates = self.dm.get_applicable_templates(self.dm.settings.current_user)
                    templates = [t for t in templates if t.instrument_id == ins.id]
                    display = ["（不使用模板）"] + [f"{t.name} - {t.instrument_code}" for t in templates]
                    self.template_list = templates
                    self.template_combo["values"] = display
                    self.template_combo.current(0)

    def _select_instrument_by_id(self, instrument_id):
        normal_instruments = [ins for ins in self.dm.instruments if ins.status == InstrumentStatus.NORMAL]
        for i, ins in enumerate(normal_instruments):
            if ins.id == instrument_id:
                self.instrument_combo.current(i)
                self._on_instrument_change()
                break

    def _on_template_select(self, _=None):
        pass

    def _apply_template(self):
        idx = self.template_combo.current()
        if idx <= 0:
            messagebox.showinfo("提示", "请先选择一个模板", parent=self)
            return

        template = self.template_list[idx - 1]
        self.applied_template_id = template.id
        self.applied_template = template
        self.reminder_minutes = template.reminder_minutes

        normal_instruments = [ins for ins in self.dm.instruments if ins.status == InstrumentStatus.NORMAL]
        for i, ins in enumerate(normal_instruments):
            if ins.id == template.instrument_id:
                self.instrument_combo.current(i)
                break

        self.purpose_text.delete("1.0", "end")
        self.purpose_text.insert("1.0", template.purpose)

        messagebox.showinfo(
            "模板已套用",
            f"已套用模板「{template.name}」：\n\n"
            f"仪器：{template.instrument_code}\n"
            f"用途：{template.purpose[:50]}...\n"
            f"默认时长：{template.default_duration_minutes}分钟\n"
            f"提前提醒：{template.reminder_minutes}分钟\n\n"
            f"请确认开始时间，结束时间将自动计算。",
            parent=self
        )

        try:
            start_dt = datetime.strptime(self.start_var.get(), "%Y-%m-%d %H:%M:%S")
            end_dt = start_dt + timedelta(minutes=template.default_duration_minutes)
            self.end_var.set(end_dt.strftime("%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    def _populate_instruments(self):
        normal_instruments = [ins for ins in self.dm.instruments if ins.status == InstrumentStatus.NORMAL]
        instruments = [f"{ins.code} - {ins.model}（{ins.person_in_charge}）" for ins in normal_instruments]
        self.instrument_combo["values"] = instruments
        if instruments:
            if self.reservation:
                for i, ins in enumerate(normal_instruments):
                    if ins.id == self.reservation.instrument_id:
                        self.instrument_combo.current(i)
                        break
            else:
                self.instrument_combo.current(0)

    def _load_reservation(self):
        if self.reservation:
            self.applicant_var.set(self.reservation.applicant)
            self.purpose_text.delete("1.0", "end")
            self.purpose_text.insert("1.0", self.reservation.purpose)
            self.start_var.set(self.reservation.start_time)
            self.end_var.set(self.reservation.end_time)
            self.instrument_combo.config(state="disabled")

    def _on_ok(self):
        idx = self.instrument_combo.current()
        if idx < 0:
            messagebox.showerror("错误", "请选择仪器", parent=self)
            return

        normal_instruments = [ins for ins in self.dm.instruments if ins.status == InstrumentStatus.NORMAL]
        if idx >= len(normal_instruments):
            messagebox.showerror("错误", "请选择有效的仪器", parent=self)
            return

        instrument = normal_instruments[idx]
        applicant = self.applicant_var.get().strip()
        purpose = self.purpose_text.get("1.0", "end").strip()
        start_time = self.start_var.get().strip()
        end_time = self.end_var.get().strip()

        if not applicant:
            messagebox.showerror("错误", "请输入申请人", parent=self)
            return
        if not purpose:
            messagebox.showerror("错误", "请输入用途", parent=self)
            return

        try:
            datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            messagebox.showerror("错误", "时间格式不正确，请使用 YYYY-MM-DD HH:MM:SS 格式", parent=self)
            return

        if self.reservation:
            res, msg = self.dm.update_reservation(
                self.reservation.id,
                applicant=applicant,
                purpose=purpose,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            template_snapshot = None
            if self.applied_template:
                template_snapshot = self.applied_template.create_snapshot()

            res, msg = self.dm.add_reservation(
                instrument.id, applicant, purpose, start_time, end_time,
                template_snapshot=template_snapshot,
                reminder_minutes=self.reminder_minutes,
            )

        if not res:
            messagebox.showerror("预约失败", msg, parent=self)
            return

        self.result = res
        self.destroy()

    def _on_cancel(self):
        self.destroy()


class TemplateDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager, title="新建模板", template=None):
        super().__init__(parent)
        self.dm = dm
        self.template = template
        self.result = None
        self.title(title)
        self.geometry("520x620")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        if template:
            self._load_template()

    def _build_ui(self):
        padding = {"padx": 10, "pady": 5}

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="模板名称：").grid(row=0, column=0, sticky="e", **padding)
        self.name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.name_var, width=37).grid(row=0, column=1, **padding)

        ttk.Label(frm, text="仪器：").grid(row=1, column=0, sticky="e", **padding)
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(
            frm, textvariable=self.instrument_var, state="readonly", width=35
        )
        self._populate_instruments()
        self.instrument_combo.grid(row=1, column=1, **padding)

        ttk.Label(frm, text="用途：").grid(row=2, column=0, sticky="ne", **padding)
        self.purpose_text = tk.Text(frm, width=37, height=3)
        self.purpose_text.grid(row=2, column=1, **padding)

        ttk.Label(frm, text="默认时长(分钟)：").grid(row=3, column=0, sticky="e", **padding)
        self.duration_var = tk.StringVar(value="60")
        ttk.Entry(frm, textvariable=self.duration_var, width=37).grid(row=3, column=1, **padding)

        ttk.Label(frm, text="提前提醒(分钟)：").grid(row=4, column=0, sticky="e", **padding)
        self.reminder_var = tk.StringVar(value="30")
        ttk.Entry(frm, textvariable=self.reminder_var, width=37).grid(row=4, column=1, **padding)

        ttk.Label(frm, text="备注：").grid(row=5, column=0, sticky="ne", **padding)
        self.remark_text = tk.Text(frm, width=37, height=2)
        self.remark_text.grid(row=5, column=1, **padding)

        ttk.Label(frm, text="适用负责人：").grid(row=6, column=0, sticky="ne", **padding)
        ttk.Label(frm, text="多个用分号分隔", foreground="gray").grid(
            row=6, column=1, sticky="w", padx=10
        )
        self.persons_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.persons_var, width=37).grid(row=7, column=1, **padding)

        ttk.Label(frm, text="可选时间段：").grid(row=8, column=0, sticky="ne", **padding)
        ttk.Label(frm, text="格式：HH:MM-HH:MM，多个用分号分隔", foreground="gray").grid(
            row=8, column=1, sticky="w", padx=10
        )
        self.slots_var = tk.StringVar(value="09:00-12:00;14:00-17:00")
        ttk.Entry(frm, textvariable=self.slots_var, width=37).grid(row=9, column=1, **padding)

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=12).pack(side="left", padx=10)

    def _populate_instruments(self):
        instruments = [f"{ins.code} - {ins.model}（{ins.person_in_charge}）" for ins in self.dm.instruments]
        self.instrument_combo["values"] = instruments
        if instruments and not self.template:
            self.instrument_combo.current(0)

    def _load_template(self):
        if self.template:
            self.name_var.set(self.template.name)
            for i, ins in enumerate(self.dm.instruments):
                if ins.id == self.template.instrument_id:
                    self.instrument_combo.current(i)
                    break
            self.purpose_text.delete("1.0", "end")
            self.purpose_text.insert("1.0", self.template.purpose)
            self.duration_var.set(str(self.template.default_duration_minutes))
            self.reminder_var.set(str(self.template.reminder_minutes))
            self.remark_text.delete("1.0", "end")
            self.remark_text.insert("1.0", self.template.remark)
            self.persons_var.set(";".join(self.template.applicable_persons))
            slots_str = ";".join([f"{ts.start_time}-{ts.end_time}" for ts in self.template.time_slots])
            self.slots_var.set(slots_str)
            self.instrument_combo.config(state="disabled")

    def _on_ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "请输入模板名称", parent=self)
            return

        idx = self.instrument_combo.current()
        if idx < 0:
            messagebox.showerror("错误", "请选择仪器", parent=self)
            return
        ins = self.dm.instruments[idx]

        purpose = self.purpose_text.get("1.0", "end").strip()
        if not purpose:
            messagebox.showerror("错误", "请输入用途", parent=self)
            return

        try:
            duration = int(self.duration_var.get())
            if duration <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("错误", "默认时长必须是正整数", parent=self)
            return

        try:
            reminder = int(self.reminder_var.get())
            if reminder < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("错误", "提前提醒必须是非负整数", parent=self)
            return

        remark = self.remark_text.get("1.0", "end").strip()

        persons_str = self.persons_var.get().strip()
        applicable_persons = [p.strip() for p in persons_str.split(";") if p.strip()] if persons_str else []

        slots_str = self.slots_var.get().strip()
        time_slots = []
        if slots_str:
            for slot in slots_str.split(";"):
                slot = slot.strip()
                if not slot:
                    continue
                if "-" not in slot:
                    messagebox.showerror("错误", f"时间段格式错误：{slot}", parent=self)
                    return
                st, et = slot.split("-", 1)
                ts = TimeSlot(st.strip(), et.strip())
                if not ts.is_valid():
                    messagebox.showerror("错误", f"时间段不合法：{slot}", parent=self)
                    return
                time_slots.append(ts)

        if not time_slots:
            messagebox.showerror("错误", "请至少设置一个可选时间段", parent=self)
            return

        if self.template:
            res, msg = self.dm.update_template(
                self.template.id,
                name=name,
                purpose=purpose,
                default_duration_minutes=duration,
                reminder_minutes=reminder,
                remark=remark,
                applicable_persons=applicable_persons,
                time_slots=time_slots,
            )
        else:
            res, msg = self.dm.add_template(
                name=name,
                instrument_id=ins.id,
                purpose=purpose,
                default_duration_minutes=duration,
                reminder_minutes=reminder,
                remark=remark,
                applicable_persons=applicable_persons,
                time_slots=time_slots,
            )

        if not res:
            messagebox.showerror("操作失败", msg, parent=self)
            return

        self.result = res
        self.destroy()

    def _on_cancel(self):
        self.destroy()


class TemplateManagementDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("模板管理")
        self.geometry("900x600")
        self.minsize(800, 500)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=(0, 8))

        self.btn_new = ttk.Button(btn_frame, text="新建模板", command=self._new_template, width=12)
        self.btn_new.pack(side="left", padx=3)

        self.btn_edit = ttk.Button(btn_frame, text="编辑", command=self._edit_template, width=10)
        self.btn_edit.pack(side="left", padx=3)

        self.btn_delete = ttk.Button(btn_frame, text="删除", command=self._delete_template, width=10)
        self.btn_delete.pack(side="left", padx=3)

        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=8)

        self.btn_import_json = ttk.Button(btn_frame, text="导入JSON", command=self._import_json, width=12)
        self.btn_import_json.pack(side="left", padx=3)

        self.btn_import_csv = ttk.Button(btn_frame, text="导入CSV", command=self._import_csv, width=12)
        self.btn_import_csv.pack(side="left", padx=3)

        self.btn_export_json = ttk.Button(btn_frame, text="导出JSON", command=self._export_json, width=12)
        self.btn_export_json.pack(side="left", padx=3)

        self.btn_export_csv = ttk.Button(btn_frame, text="导出CSV", command=self._export_csv, width=12)
        self.btn_export_csv.pack(side="left", padx=3)

        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(btn_frame, text="刷新", command=self._refresh, width=10).pack(side="left", padx=3)

        filter_frame = ttk.LabelFrame(frm, text="筛选", padding=8)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="仪器：").grid(row=0, column=0, padx=(0, 5))
        self.ins_filter_var = tk.StringVar()
        self.ins_combo = ttk.Combobox(
            filter_frame, textvariable=self.ins_filter_var, state="readonly", width=25
        )
        codes = [""] + sorted({ins.code for ins in self.dm.instruments})
        self.ins_combo["values"] = codes
        self.ins_combo.grid(row=0, column=1)
        self.ins_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        ttk.Label(filter_frame, text="适用负责人：").grid(row=0, column=2, padx=(15, 5))
        self.person_filter_var = tk.StringVar()
        self.person_combo = ttk.Combobox(
            filter_frame, textvariable=self.person_filter_var, state="readonly", width=15
        )
        persons = [""] + self.dm.get_all_persons()
        self.person_combo["values"] = persons
        self.person_combo.grid(row=0, column=3)
        self.person_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        ttk.Button(filter_frame, text="清除筛选", command=self._clear_filter, width=10).grid(
            row=0, column=4, padx=(15, 0)
        )

        columns = ("name", "instrument_code", "purpose", "duration", "reminder", "persons", "updated_at")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings")
        self.tree.heading("name", text="模板名称")
        self.tree.heading("instrument_code", text="仪器编号")
        self.tree.heading("purpose", text="用途")
        self.tree.heading("duration", text="默认时长")
        self.tree.heading("reminder", text="提前提醒")
        self.tree.heading("persons", text="适用负责人")
        self.tree.heading("updated_at", text="更新时间")

        self.tree.column("name", width=150, anchor="w")
        self.tree.column("instrument_code", width=90, anchor="w")
        self.tree.column("purpose", width=200, anchor="w")
        self.tree.column("duration", width=80, anchor="center")
        self.tree.column("reminder", width=80, anchor="center")
        self.tree.column("persons", width=120, anchor="w")
        self.tree.column("updated_at", width=150, anchor="w")

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())
        self.tree.bind("<Double-1>", lambda e: self._edit_template())

        bottom_frame = ttk.Frame(frm)
        bottom_frame.pack(fill="x", pady=(10, 0))

        self.status_label = ttk.Label(bottom_frame, text="", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        ttk.Button(bottom_frame, text="关闭", command=self.destroy, width=12).pack(side="right")

        self._update_permissions()
        self._update_buttons()

    def _update_permissions(self):
        is_admin = self.dm.settings.current_role == UserRole.ADMIN
        for btn in [self.btn_import_json, self.btn_import_csv]:
            btn.config(state="normal" if is_admin else "disabled")

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        ins_filter = self.ins_filter_var.get()
        person_filter = self.person_filter_var.get()

        ins_id_filter = ""
        if ins_filter:
            ins = next((i for i in self.dm.instruments if i.code == ins_filter), None)
            if ins:
                ins_id_filter = ins.id

        templates = self.dm.list_templates(ins_id_filter, person_filter)
        for tpl in templates:
            purpose_short = tpl.purpose[:30] + "..." if len(tpl.purpose) > 30 else tpl.purpose
            persons_str = ";".join(tpl.applicable_persons) if tpl.applicable_persons else "全部"
            self.tree.insert(
                "", "end", iid=tpl.id,
                values=(
                    tpl.name, tpl.instrument_code, purpose_short,
                    f"{tpl.default_duration_minutes}分钟",
                    f"{tpl.reminder_minutes}分钟",
                    persons_str, tpl.updated_at,
                )
            )

        self.status_label.config(text=f"共 {len(templates)} 个模板")

    def _clear_filter(self):
        self.ins_filter_var.set("")
        self.person_filter_var.set("")
        self._refresh()

    def _get_selected_template(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.dm.get_template(selection[0])

    def _update_buttons(self):
        has_selection = self._get_selected_template() is not None
        self.btn_edit.config(state="normal" if has_selection else "disabled")
        self.btn_delete.config(state="normal" if has_selection else "disabled")

    def _new_template(self):
        dlg = TemplateDialog(self, self.dm, "新建模板")
        self.wait_window(dlg)
        if dlg.result:
            self._refresh()
            self.status_label.config(text=f"已创建模板：{dlg.result.name}")

    def _edit_template(self):
        tpl = self._get_selected_template()
        if not tpl:
            messagebox.showwarning("提示", "请先选择一个模板", parent=self)
            return

        dlg = TemplateDialog(self, self.dm, "编辑模板", template=tpl)
        self.wait_window(dlg)
        if dlg.result:
            self._refresh()
            self.status_label.config(text=f"已更新模板：{dlg.result.name}")

    def _delete_template(self):
        tpl = self._get_selected_template()
        if not tpl:
            messagebox.showwarning("提示", "请先选择一个模板", parent=self)
            return

        if not messagebox.askyesno("确认", f"确定要删除模板「{tpl.name}」吗？", parent=self):
            return

        success, msg = self.dm.delete_template(tpl.id)
        if success:
            self._refresh()
            self.status_label.config(text=f"已删除模板：{tpl.name}")
        else:
            messagebox.showerror("删除失败", msg, parent=self)

    def _import_json(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入模板", parent=self)
            return

        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入模板JSON",
            initialdir=initial_dir,
            filetypes=[("JSON 文件", "*.json")],
            parent=self,
        )
        if not filepath:
            return

        overwrite = messagebox.askyesno(
            "覆盖确认",
            "如果遇到重名模板，是否覆盖现有模板？\n\n选'是'覆盖，选'否'跳过重名模板",
            parent=self
        )

        result = self.dm.import_templates_json(
            filepath, overwrite=overwrite, user_role=self.dm.settings.current_role
        )
        self.dm.settings.import_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        self._show_import_result(result)
        self._refresh()

    def _import_csv(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入模板", parent=self)
            return

        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入模板CSV",
            initialdir=initial_dir,
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return

        overwrite = messagebox.askyesno(
            "覆盖确认",
            "如果遇到重名模板，是否覆盖现有模板？\n\n选'是'覆盖，选'否'跳过重名模板",
            parent=self
        )

        result = self.dm.import_templates_csv(
            filepath, overwrite=overwrite, user_role=self.dm.settings.current_role
        )
        self.dm.settings.import_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        self._show_import_result(result)
        self._refresh()

    def _show_import_result(self, result: ImportResult):
        msg = f"导入完成！\n\n总计：{result.total_count} 条\n成功：{result.success_count} 条\n失败：{result.failed_count} 条"
        if result.errors:
            msg += "\n\n错误详情：\n" + "\n".join(result.errors[:10])
            if len(result.errors) > 10:
                msg += f"\n...（共{len(result.errors)}条错误）"
        if result.warnings:
            msg += "\n\n警告：\n" + "\n".join(result.warnings[:5])

        if result.success:
            messagebox.showinfo("导入成功", msg, parent=self)
        else:
            messagebox.showwarning("导入完成（有错误）", msg, parent=self)

    def _export_json(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出模板JSON",
            initialdir=initial_dir,
            initialfile=f"模板_{date.today().strftime('%Y%m%d')}.json",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not filepath:
            return

        success, msg = self.dm.export_templates_json(filepath)
        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"模板已导出到：\n{filepath}", parent=self)
            self.status_label.config(text=f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self)

    def _export_csv(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出模板CSV",
            initialdir=initial_dir,
            initialfile=f"模板_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not filepath:
            return

        success, msg = self.dm.export_templates_csv(filepath)
        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"模板已导出到：\n{filepath}", parent=self)
            self.status_label.config(text=f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self)


class BatchCreateDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.batch_items = []
        self.conflicts = []
        self.result_batch_id = None
        self.title("批量创建预约")
        self.geometry("780x640")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._populate_templates()

    def _build_ui(self):
        padding = {"padx": 8, "pady": 5}

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        top_frame = ttk.LabelFrame(frm, text="批量设置", padding=10)
        top_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(top_frame, text="选择模板：").grid(row=0, column=0, sticky="w", **padding)
        self.template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(
            top_frame, textvariable=self.template_var, state="readonly", width=35
        )
        self.template_combo.grid(row=0, column=1, **padding)
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_select)

        ttk.Label(top_frame, text="申请人：").grid(row=0, column=2, sticky="e", **padding)
        self.applicant_var = tk.StringVar(value=self.dm.settings.current_user)
        ttk.Entry(top_frame, textvariable=self.applicant_var, width=15).grid(row=0, column=3, **padding)

        ttk.Label(top_frame, text="开始日期：").grid(row=1, column=0, sticky="w", **padding)
        self.start_date_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.start_date_var, width=15).grid(row=1, column=1, **padding)
        ttk.Label(top_frame, text="格式：YYYY-MM-DD", foreground="gray").grid(
            row=1, column=2, sticky="w", padx=5
        )

        ttk.Label(top_frame, text="结束日期：").grid(row=2, column=0, sticky="w", **padding)
        self.end_date_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.end_date_var, width=15).grid(row=2, column=1, **padding)
        ttk.Label(top_frame, text="格式：YYYY-MM-DD", foreground="gray").grid(
            row=2, column=2, sticky="w", padx=5
        )

        ttk.Label(top_frame, text="时间段：").grid(row=3, column=0, sticky="w", **padding)
        self.slot_var = tk.StringVar()
        self.slot_combo = ttk.Combobox(
            top_frame, textvariable=self.slot_var, state="readonly", width=25
        )
        self.slot_combo.grid(row=3, column=1, **padding)

        ttk.Button(top_frame, text="添加到批次", command=self._add_to_batch, width=12).grid(
            row=3, column=3, **padding
        )

        batch_frame = ttk.LabelFrame(frm, text="批次列表", padding=10)
        batch_frame.pack(fill="both", expand=True, pady=(0, 10))

        list_frame = ttk.Frame(batch_frame)
        list_frame.pack(fill="both", expand=True)

        columns = ("template", "instrument", "date", "slot", "applicant")
        self.batch_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        self.batch_tree.heading("template", text="模板")
        self.batch_tree.heading("instrument", text="仪器")
        self.batch_tree.heading("date", text="日期")
        self.batch_tree.heading("slot", text="时间段")
        self.batch_tree.heading("applicant", text="申请人")

        self.batch_tree.column("template", width=150, anchor="w")
        self.batch_tree.column("instrument", width=100, anchor="w")
        self.batch_tree.column("date", width=100, anchor="w")
        self.batch_tree.column("slot", width=120, anchor="w")
        self.batch_tree.column("applicant", width=80, anchor="w")

        self.batch_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        btn_row = ttk.Frame(batch_frame)
        btn_row.pack(fill="x", pady=(5, 0))
        ttk.Button(btn_row, text="移除选中", command=self._remove_selected, width=10).pack(side="left", padx=3)
        ttk.Button(btn_row, text="清空列表", command=self._clear_batch, width=10).pack(side="left", padx=3)
        ttk.Button(btn_row, text="检查冲突", command=self._check_conflicts, width=12).pack(side="right", padx=3)

        conflict_frame = ttk.LabelFrame(frm, text="冲突检查结果", padding=10)
        conflict_frame.pack(fill="x", pady=(0, 10))

        self.conflict_text = tk.Text(conflict_frame, height=6, width=80)
        self.conflict_text.pack(fill="x")
        self.conflict_text.configure(state="disabled")

        bottom_btn_frame = ttk.Frame(frm)
        bottom_btn_frame.pack(fill="x")

        self.status_label = ttk.Label(bottom_btn_frame, text="", foreground="#1565c0")
        self.status_label.pack(side="left")

        ttk.Button(bottom_btn_frame, text="取消", command=self._on_cancel, width=12).pack(side="right", padx=5)
        ttk.Button(bottom_btn_frame, text="批量创建", command=self._on_create, width=12).pack(side="right", padx=5)

        tomorrow = date.today() + timedelta(days=1)
        self.start_date_var.set(tomorrow.strftime("%Y-%m-%d"))
        self.end_date_var.set(tomorrow.strftime("%Y-%m-%d"))

    def _populate_templates(self):
        templates = self.dm.get_applicable_templates(self.dm.settings.current_user)
        self.template_list = templates
        display = [f"{t.name} - {t.instrument_code}" for t in templates]
        self.template_combo["values"] = display
        if display:
            self.template_combo.current(0)
            self._on_template_select()

    def _on_template_select(self, _=None):
        idx = self.template_combo.current()
        if idx >= 0 and idx < len(self.template_list):
            template = self.template_list[idx]
            slots_display = []
            for i, ts in enumerate(template.time_slots):
                slots_display.append(f"[{i+1}] {ts.start_time}-{ts.end_time}")
            self.slot_combo["values"] = slots_display
            if slots_display:
                self.slot_combo.current(0)
            else:
                self.slot_combo["values"] = ["（无可用时间段）"]
                self.slot_combo.current(0)

    def _add_to_batch(self):
        tpl_idx = self.template_combo.current()
        if tpl_idx < 0 or tpl_idx >= len(self.template_list):
            messagebox.showwarning("提示", "请先选择模板", parent=self)
            return

        template = self.template_list[tpl_idx]
        slot_idx = self.slot_combo.current()
        if not template.time_slots or slot_idx < 0 or slot_idx >= len(template.time_slots):
            messagebox.showwarning("提示", "请选择有效的时间段", parent=self)
            return

        start_date = self.start_date_var.get().strip()
        end_date = self.end_date_var.get().strip()
        applicant = self.applicant_var.get().strip()

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("错误", "日期格式错误，请使用 YYYY-MM-DD 格式", parent=self)
            return

        if end_dt < start_dt:
            messagebox.showerror("错误", "结束日期不能早于开始日期", parent=self)
            return

        if not applicant:
            messagebox.showerror("错误", "请填写申请人", parent=self)
            return

        current = start_dt
        added_count = 0
        while current <= end_dt:
            date_str = current.strftime("%Y-%m-%d")
            ts = template.time_slots[slot_idx]
            item = {
                "template_id": template.id,
                "template_name": template.name,
                "instrument_code": template.instrument_code,
                "start_date": date_str,
                "slot_index": slot_idx,
                "slot_display": f"{ts.start_time}-{ts.end_time}",
                "applicant": applicant,
            }
            self.batch_items.append(item)
            self.batch_tree.insert(
                "", "end",
                values=(template.name, template.instrument_code, date_str,
                        f"{ts.start_time}-{ts.end_time}", applicant)
            )
            added_count += 1
            current += timedelta(days=1)

        self.status_label.config(text=f"已添加 {added_count} 条预约到批次，共 {len(self.batch_items)} 条")
        self.conflicts = []
        self._update_conflict_text()

    def _remove_selected(self):
        selected = self.batch_tree.selection()
        if not selected:
            return
        indices = []
        for iid in selected:
            idx = self.batch_tree.index(iid)
            indices.append(idx)
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.batch_items):
                del self.batch_items[idx]
            self.batch_tree.delete(iid)
        self.status_label.config(text=f"批次剩余 {len(self.batch_items)} 条")
        self.conflicts = []
        self._update_conflict_text()

    def _clear_batch(self):
        if not self.batch_items:
            return
        if not messagebox.askyesno("确认", "确定要清空批次列表吗？", parent=self):
            return
        self.batch_items.clear()
        for item in self.batch_tree.get_children():
            self.batch_tree.delete(item)
        self.status_label.config(text="批次已清空")
        self.conflicts = []
        self._update_conflict_text()

    def _check_conflicts(self):
        if not self.batch_items:
            messagebox.showinfo("提示", "批次列表为空，请先添加预约", parent=self)
            return

        self.conflicts = self.dm.check_batch_conflicts(self.batch_items)
        self._update_conflict_text()

        if self.conflicts:
            messagebox.showwarning(
                "冲突检查",
                f"检测到 {len(self.conflicts)} 个冲突，请查看下方详细信息",
                parent=self
            )
        else:
            messagebox.showinfo("冲突检查", "未检测到冲突，可以安全创建", parent=self)

    def _update_conflict_text(self):
        self.conflict_text.configure(state="normal")
        self.conflict_text.delete("1.0", "end")
        if self.conflicts:
            for c in self.conflicts:
                idx = c.get("index", 0)
                ctype = c.get("type", "未知")
                detail = c.get("detail", "")
                self.conflict_text.insert("end", f"[第{idx+1}条] {ctype}: {detail}\n")
        else:
            if self.batch_items:
                self.conflict_text.insert("end", "未检测到冲突")
            else:
                self.conflict_text.insert("end", "请先添加预约到批次列表")
        self.conflict_text.configure(state="disabled")

    def _on_create(self):
        if not self.batch_items:
            messagebox.showwarning("提示", "批次列表为空，请先添加预约", parent=self)
            return

        if not self.conflicts:
            self.conflicts = self.dm.check_batch_conflicts(self.batch_items)
            self._update_conflict_text()

        conflict_count = len(self.conflicts)
        safe_count = len(self.batch_items) - conflict_count

        if conflict_count > 0:
            if not messagebox.askyesno(
                "确认创建",
                f"检测到 {conflict_count} 个冲突项，这些项将被跳过（不会入库）。\n\n"
                f"将仅创建 {safe_count} 条无冲突的预约。\n\n"
                f"是否继续？",
                parent=self
            ):
                return
        else:
            if not messagebox.askyesno(
                "确认创建",
                f"未检测到冲突，将创建 {safe_count} 条预约。\n\n是否继续？",
                parent=self
            ):
                return

        record, fails = self.dm.batch_create_reservations(
            self.batch_items,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role
        )

        if record is None:
            messagebox.showerror("创建失败", "批量创建返回空记录", parent=self)
            return

        self.result_batch_id = record.id

        skipped = getattr(record, "skipped_count", 0)
        msg = (
            f"批量创建完成！\n\n"
            f"总数：{record.total_count}\n"
            f"成功：{record.success_count} 个（已入库）\n"
            f"跳过：{skipped} 个（冲突拦截，未入库）\n"
            f"失败：{record.failed_count} 个"
        )
        if fails:
            msg += "\n\n详细信息：\n" + "\n".join(fails[:15])
            if len(fails) > 15:
                msg += f"\n... 还有 {len(fails) - 15} 条"

        if record.failed_count > 0 or skipped > 0:
            messagebox.showwarning("部分跳过/失败", msg, parent=self)
        else:
            messagebox.showinfo(
                "创建成功",
                f"成功创建 {record.success_count} 个预约！\n批次ID：{record.id}",
                parent=self
            )

        self.destroy()

    def _on_cancel(self):
        self.result_batch_id = None
        self.destroy()


class BatchManagementDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("批量操作记录")
        self.geometry("1020x700")
        self.minsize(900, 600)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_records()

    def _build_ui(self):
        padding = {"padx": 8, "pady": 5}

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        filter_frame = ttk.LabelFrame(frm, text="筛选", padding=10)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="操作类型：").grid(row=0, column=0, **padding)
        self.operation_var = tk.StringVar()
        self.operation_combo = ttk.Combobox(
            filter_frame, textvariable=self.operation_var, state="readonly", width=15
        )
        self.operation_combo["values"] = ["", "批量建单", "批量撤销"]
        self.operation_combo.grid(row=0, column=1, **padding)
        self.operation_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_records())

        ttk.Button(filter_frame, text="刷新", command=self._refresh_records, width=10).grid(
            row=0, column=2, padx=20
        )

        ttk.Label(filter_frame, text="筛选明细：").grid(row=0, column=3, sticky="e", **padding)
        self.detail_filter_var = tk.StringVar(value="全部")
        self.detail_filter_combo = ttk.Combobox(
            filter_frame, textvariable=self.detail_filter_var,
            values=["全部", "成功", "跳过", "失败"],
            state="readonly", width=10
        )
        self.detail_filter_combo.grid(row=0, column=4, **padding)
        self.detail_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_detail_tree())

        ttk.Label(filter_frame, text="（下方明细表格按此筛选）",
                  foreground="gray").grid(row=0, column=5, sticky="w", padx=5)

        records_frame = ttk.LabelFrame(frm, text="批次记录（点击下方查看明细）", padding=8)
        records_frame.pack(fill="both", expand=False, pady=(0, 8))

        columns = ("operation", "operator", "total", "success", "skipped", "failed",
                   "created_at", "is_cancelled", "cancel_operator", "cancel_time")
        self.record_tree = ttk.Treeview(records_frame, columns=columns, show="headings", height=6)
        self.record_tree.heading("operation", text="操作类型")
        self.record_tree.heading("operator", text="操作人")
        self.record_tree.heading("total", text="总数")
        self.record_tree.heading("success", text="成功")
        self.record_tree.heading("skipped", text="跳过")
        self.record_tree.heading("failed", text="失败")
        self.record_tree.heading("created_at", text="创建时间")
        self.record_tree.heading("is_cancelled", text="状态")
        self.record_tree.heading("cancel_operator", text="撤销人")
        self.record_tree.heading("cancel_time", text="撤销时间")

        self.record_tree.column("operation", width=80, anchor="w")
        self.record_tree.column("operator", width=80, anchor="w")
        self.record_tree.column("total", width=45, anchor="center")
        self.record_tree.column("success", width=45, anchor="center")
        self.record_tree.column("skipped", width=45, anchor="center")
        self.record_tree.column("failed", width=45, anchor="center")
        self.record_tree.column("created_at", width=135, anchor="w")
        self.record_tree.column("is_cancelled", width=60, anchor="center")
        self.record_tree.column("cancel_operator", width=80, anchor="w")
        self.record_tree.column("cancel_time", width=135, anchor="w")

        self.record_tree.pack(fill="x", pady=(0, 2))
        self.record_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.record_tree.bind("<Double-1>", lambda e: self._show_details())

        scrollbar_r = ttk.Scrollbar(records_frame, orient="vertical", command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=scrollbar_r.set)

        detail_nb = ttk.LabelFrame(frm, text="明细 - 逐条结果（成功/跳过/失败）", padding=8)
        detail_nb.pack(fill="both", expand=True, pady=(0, 8))

        detail_columns = ("idx", "status", "template", "instrument", "start_time",
                          "applicant", "reason")
        self.detail_tree = ttk.Treeview(detail_nb, columns=detail_columns, show="headings", height=10)
        self.detail_tree.heading("idx", text="序号")
        self.detail_tree.heading("status", text="状态")
        self.detail_tree.heading("template", text="模板")
        self.detail_tree.heading("instrument", text="仪器")
        self.detail_tree.heading("start_time", text="开始时间")
        self.detail_tree.heading("applicant", text="申请人")
        self.detail_tree.heading("reason", text="原因/快照提示")

        self.detail_tree.column("idx", width=50, anchor="center")
        self.detail_tree.column("status", width=60, anchor="center")
        self.detail_tree.column("template", width=140, anchor="w")
        self.detail_tree.column("instrument", width=90, anchor="w")
        self.detail_tree.column("start_time", width=140, anchor="w")
        self.detail_tree.column("applicant", width=80, anchor="w")
        self.detail_tree.column("reason", width=380, anchor="w")

        self.detail_tree.pack(side="left", fill="both", expand=True, pady=(0, 2))
        self.detail_tree.bind("<<TreeviewSelect>>", self._on_detail_select)
        self.detail_tree.bind("<Double-1>", lambda e: self._show_item_detail())

        vsb_d = ttk.Scrollbar(detail_nb, orient="vertical", command=self.detail_tree.yview)
        self.detail_tree.configure(yscrollcommand=vsb_d.set)
        vsb_d.pack(side="right", fill="y")

        self.detail_tree.tag_configure("success", foreground="#2e7d32")
        self.detail_tree.tag_configure("skipped", foreground="#e65100")
        self.detail_tree.tag_configure("failed", foreground="#c62828")

        info_frame = ttk.LabelFrame(frm, text="详情 / 模板快照 / 操作日志", padding=8)
        info_frame.pack(fill="x", pady=(0, 8))

        self.detail_text = tk.Text(info_frame, height=6, wrap="word")
        self.detail_text.pack(fill="x")
        self.detail_text.configure(state="disabled")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="查看批次详情", command=self._show_details, width=14).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="查看选中条目快照", command=self._show_item_detail, width=18).pack(side="left", padx=3)
        self.btn_cancel = ttk.Button(
            btn_frame, text="整批撤销", command=self._cancel_batch, width=14,
            state="disabled"
        )
        self.btn_cancel.pack(side="left", padx=3)

        if self.dm.settings.current_role != UserRole.ADMIN:
            self.btn_cancel.config(text="（需管理员）", state="disabled")

        ttk.Button(btn_frame, text="导出批次备份(JSON)", command=self._export_batch_backup, width=20).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="关闭", command=self.destroy, width=12).pack(side="right", padx=3)

    def _refresh_records(self):
        operation_filter = self.operation_var.get()
        records = self.dm.list_batch_records(operation_filter)

        for item in self.record_tree.get_children():
            self.record_tree.delete(item)

        for r in records:
            status_text = "已撤销" if r.is_cancelled else "正常"
            cancel_op = r.cancel_operator if r.cancel_operator else ""
            cancel_time = r.cancel_time if r.cancel_time else ""
            skipped = getattr(r, "skipped_count", 0)
            tag = "cancelled" if r.is_cancelled else ""

            self.record_tree.insert(
                "", "end", iid=r.id,
                values=(r.operation, r.operator, r.total_count,
                        r.success_count, skipped, r.failed_count, r.created_at,
                        status_text, cancel_op, cancel_time),
                tags=(tag,)
            )

        self.record_tree.tag_configure("cancelled", foreground="#9e9e9e")
        self._on_select()

    def _on_select(self, _=None):
        selected = self.record_tree.selection()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")

        if selected:
            batch_id = selected[0]
            record = self.dm.get_batch_record(batch_id)
            if record:
                detail = f"批次ID: {record.id}\n"
                detail += f"操作类型: {record.operation}\n"
                detail += f"操作人: {record.operator} ({record.operator_role})\n"
                detail += f"创建时间: {record.created_at}\n"
                skipped = getattr(record, "skipped_count", 0)
                detail += (f"总数: {record.total_count}, "
                           f"成功: {record.success_count}, "
                           f"跳过: {skipped}, "
                           f"失败: {record.failed_count}\n")
                detail += f"关联预约ID: {', '.join(record.reservation_ids[:8])}"
                if len(record.reservation_ids) > 8:
                    detail += f" 等{len(record.reservation_ids)}个"
                detail += "\n"
                if record.details:
                    detail += f"\n详细信息（前300字）:\n{record.details[:300]}"
                    if len(record.details) > 300:
                        detail += "..."
                if record.is_cancelled:
                    detail += f"\n\n【已撤销】\n撤销人: {record.cancel_operator}\n"
                    detail += f"撤销时间: {record.cancel_time}\n撤销原因: {record.cancel_reason}"
                self.detail_text.insert("end", detail)

                can_cancel = (
                    self.dm.settings.current_role == UserRole.ADMIN
                    and record.operation == OperationType.BATCH_CREATE.value
                    and not record.is_cancelled
                )
                self.btn_cancel.config(state="normal" if can_cancel else "disabled")
            else:
                self.btn_cancel.config(state="disabled")
        else:
            self.btn_cancel.config(state="disabled")

        self.detail_text.configure(state="disabled")
        self._refresh_detail_tree()

    def _refresh_detail_tree(self):
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)

        selected = self.record_tree.selection()
        if not selected:
            return

        batch_id = selected[0]
        record = self.dm.get_batch_record(batch_id)
        if not record:
            return

        item_results = getattr(record, "item_results", [])
        if not item_results:
            self.detail_tree.insert(
                "", "end",
                values=("-", "-", "（此批次无逐条明细，可能是旧版本数据）",
                        "-", "-", "-", "请查看上方'详细信息'"),
                tags=("skipped",)
            )
            return

        filter_val = self.detail_filter_var.get()

        for ir in item_results:
            status = ir.status
            if filter_val == "成功" and status != "success":
                continue
            if filter_val == "跳过" and status != "skipped":
                continue
            if filter_val == "失败" and status != "failed":
                continue

            status_display = "成功" if status == "success" else ("跳过" if status == "skipped" else "失败")
            tag = status
            reason_display = ir.reason if ir.reason else (
                "（双击查看模板快照）" if ir.template_snapshot else "")
            self.detail_tree.insert(
                "", "end",
                values=(
                    ir.index + 1,
                    status_display,
                    ir.template_name or "-",
                    ir.instrument_code or "-",
                    ir.start_time or "-",
                    ir.applicant or "-",
                    reason_display,
                ),
                tags=(tag,)
            )

    def _on_detail_select(self, _=None):
        pass

    def _show_item_detail(self):
        selected_detail = self.detail_tree.selection()
        if not selected_detail:
            messagebox.showinfo("提示", "请先在明细表格中选择一条记录", parent=self)
            return

        selected_batch = self.record_tree.selection()
        if not selected_batch:
            return

        record = self.dm.get_batch_record(selected_batch[0])
        if not record:
            return

        item_results = getattr(record, "item_results", [])
        if not item_results:
            messagebox.showinfo("提示", "该批次无逐条明细", parent=self)
            return

        idx_str = self.detail_tree.item(selected_detail[0], "values")[0]
        try:
            display_idx = int(idx_str)
            target_ir = None
            for ir in item_results:
                if ir.index + 1 == display_idx:
                    target_ir = ir
                    break
        except (ValueError, IndexError):
            messagebox.showinfo("提示", "无法定位条目", parent=self)
            return

        if not target_ir:
            messagebox.showinfo("提示", "未找到对应条目", parent=self)
            return

        snap = target_ir.template_snapshot
        msg = f"第{target_ir.index + 1}条 明细\n"
        msg += f"状态: {'成功' if target_ir.status == 'success' else ('跳过' if target_ir.status == 'skipped' else '失败')}\n"
        msg += f"模板: {target_ir.template_name or '-'}\n"
        msg += f"仪器: {target_ir.instrument_code or '-'}\n"
        msg += f"开始时间: {target_ir.start_time or '-'}\n"
        msg += f"申请人: {target_ir.applicant or '-'}\n"
        msg += f"预约ID: {target_ir.reservation_id or '（无）'}\n"
        if target_ir.reason:
            msg += f"\n冲突/失败原因:\n{target_ir.reason}\n"

        if snap:
            msg += f"\n【模板快照】\n"
            snap_name = ""
            snap_time = ""
            snap_purpose = ""
            snap_duration = ""
            snap_reminder = ""
            snap_persons = ""
            if isinstance(snap, dict):
                snap_name = snap.get("template_name", "")
                snap_time = snap.get("snapshot_time", "")
                snap_purpose = snap.get("purpose", "")
                snap_duration = snap.get("default_duration_minutes", "")
                snap_reminder = snap.get("reminder_minutes", "")
                persons = snap.get("applicable_persons", [])
                snap_persons = ";".join(persons) if persons else "全部"
            msg += f"模板名: {snap_name}\n"
            msg += f"快照时间: {snap_time}\n"
            msg += f"用途: {snap_purpose[:80]}{'...' if len(snap_purpose) > 80 else ''}\n"
            msg += f"默认时长: {snap_duration}分钟\n"
            msg += f"提前提醒: {snap_reminder}分钟\n"
            msg += f"适用负责人: {snap_persons}"
        elif target_ir.status == "success":
            msg += "\n（该条成功记录未保存快照）"

        messagebox.showinfo("条目详情 + 模板快照", msg, parent=self)

    def _show_details(self):
        selected = self.record_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条记录", parent=self)
            return

        batch_id = selected[0]
        record = self.dm.get_batch_record(batch_id)
        if not record:
            return

        skipped = getattr(record, "skipped_count", 0)
        detail = f"批次ID: {record.id}\n"
        detail += f"操作类型: {record.operation}\n"
        detail += f"操作人: {record.operator} ({record.operator_role})\n"
        detail += f"创建时间: {record.created_at}\n"
        detail += (f"总数: {record.total_count}\n"
                   f"成功: {record.success_count}（已入库）\n"
                   f"跳过: {skipped}（冲突拦截，未入库）\n"
                   f"失败: {record.failed_count}\n")
        detail += f"关联预约ID: {', '.join(record.reservation_ids[:15])}"
        if len(record.reservation_ids) > 15:
            detail += f" 等{len(record.reservation_ids)}个"
        detail += "\n"
        if record.details:
            detail += f"\n详细信息:\n{record.details}\n"
        if record.is_cancelled:
            detail += f"\n【已撤销】\n撤销人: {record.cancel_operator}\n"
            detail += f"撤销时间: {record.cancel_time}\n撤销原因: {record.cancel_reason}"

        messagebox.showinfo("批次详情", detail, parent=self)

    def _export_batch_backup(self):
        selected = self.record_tree.selection()
        if not selected:
            if not messagebox.askyesno(
                "导出全部",
                "未选中具体批次，是否导出全部批次记录作为备份？",
                parent=self
            ):
                return
            records = self.dm.list_batch_records()
            export_data = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exported_by": self.dm.settings.current_user,
                "role": self.dm.settings.current_role.value,
                "batch_count": len(records),
                "batches": [r.to_dict() for r in records],
            }
            default_name = f"全部批次备份_{date.today().strftime('%Y%m%d')}.json"
        else:
            batch_id = selected[0]
            record = self.dm.get_batch_record(batch_id)
            if not record:
                return
            export_data = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exported_by": self.dm.settings.current_user,
                "role": self.dm.settings.current_role.value,
                "batch_count": 1,
                "batches": [record.to_dict()],
            }
            default_name = f"批次备份_{record.id[:8]}_{date.today().strftime('%Y%m%d')}.json"

        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出批次备份(JSON)",
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            parent=self,
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo(
                "导出成功",
                f"批次备份已导出到：\n{filepath}\n\n包含 {export_data['batch_count']} 个批次记录（含逐条明细与模板快照）",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("导出失败", f"导出过程出错：{str(e)}", parent=self)

    def _cancel_batch(self):
        selected = self.record_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条批量建单记录", parent=self)
            return

        batch_id = selected[0]
        record = self.dm.get_batch_record(batch_id)
        if not record:
            return

        if record.operation != OperationType.BATCH_CREATE.value:
            messagebox.showwarning("提示", "只能撤销批量建单记录", parent=self)
            return

        if record.is_cancelled:
            messagebox.showwarning("提示", "该批次已被撤销", parent=self)
            return

        skipped = getattr(record, "skipped_count", 0)
        reason = tk.simpledialog.askstring(
            "撤销原因",
            f"确定要撤销该批次的 {len(record.reservation_ids)} 个已入库预约吗？\n\n"
            f"（注：跳过的 {skipped} 条从未入库，无需处理）\n\n"
            f"请填写撤销原因：",
            parent=self
        )
        if not reason or not reason.strip():
            messagebox.showwarning("提示", "请填写撤销原因", parent=self)
            return

        success, msg = self.dm.batch_cancel_reservations(
            batch_id,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            reason=reason.strip()
        )

        if success:
            messagebox.showinfo("撤销成功", msg, parent=self)
            self._refresh_records()
        else:
            messagebox.showerror("撤销失败", msg, parent=self)


class OperationLogsDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("操作日志")
        self.geometry("900x560")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_logs()

    def _build_ui(self):
        padding = {"padx": 8, "pady": 5}

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        filter_frame = ttk.LabelFrame(frm, text="筛选", padding=10)
        filter_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(filter_frame, text="操作类型：").grid(row=0, column=0, sticky="e", **padding)
        self.type_var = tk.StringVar(value="全部")
        type_values = ["全部"] + [ot.value for ot in OperationType]
        self.type_combo = ttk.Combobox(
            filter_frame, textvariable=self.type_var, values=type_values,
            state="readonly", width=20
        )
        self.type_combo.grid(row=0, column=1, **padding)
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_logs())

        ttk.Button(filter_frame, text="刷新", command=self._refresh_logs, width=10).grid(
            row=0, column=2, padx=20, pady=5
        )

        ttk.Label(filter_frame, text="显示条数：").grid(row=0, column=3, sticky="e", **padding)
        self.limit_var = tk.StringVar(value="100")
        limit_combo = ttk.Combobox(
            filter_frame, textvariable=self.limit_var,
            values=["50", "100", "200", "500"], state="readonly", width=10
        )
        limit_combo.grid(row=0, column=4, **padding)
        limit_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_logs())

        columns = ("timestamp", "operation_type", "operator", "operator_role", "detail")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings", height=18)
        self.tree.heading("timestamp", text="时间")
        self.tree.heading("operation_type", text="操作类型")
        self.tree.heading("operator", text="操作人")
        self.tree.heading("operator_role", text="角色")
        self.tree.heading("detail", text="详情")

        self.tree.column("timestamp", width=160, anchor="w")
        self.tree.column("operation_type", width=140, anchor="w")
        self.tree.column("operator", width=100, anchor="w")
        self.tree.column("operator_role", width=80, anchor="center")
        self.tree.column("detail", width=380, anchor="w")

        scrollbar = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=(10, 0))

        self.count_label = ttk.Label(btn_frame, text="共 0 条记录")
        self.count_label.pack(side="left")

        ttk.Button(btn_frame, text="关闭", command=self.destroy, width=12).pack(side="right")

    def _refresh_logs(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        op_type = self.type_var.get()
        type_filter = "" if op_type == "全部" else op_type
        limit = int(self.limit_var.get())

        logs = self.dm.list_operation_logs(operation_type=type_filter, limit=limit)
        for log in logs:
            self.tree.insert("", "end", iid=log.id, values=(
                log.timestamp,
                log.operation_type,
                log.operator,
                log.operator_role,
                log.detail[:80] + "..." if len(log.detail) > 80 else log.detail,
            ))

        self.count_label.config(text=f"共 {len(logs)} 条记录")


class StatusChangeDialog(tk.Toplevel):
    def __init__(self, parent, reservation, target_status: ReservationStatus, title="状态变更"):
        super().__init__(parent)
        self.target_status = target_status
        self.reservation = reservation
        self.result_note = None
        self.confirmed = False
        self.title(title)
        self.geometry("420x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(
            frm,
            text=f"将预约状态从「{self.reservation.status.value}」变更为「{self.target_status.value}」",
            font=("Arial", 10, "bold"),
            wraplength=380,
        ).pack(pady=(0, 15))

        self.need_note = self.target_status in [
            ReservationStatus.CANCELLED,
            ReservationStatus.COMPLETED,
            ReservationStatus.PENDING_REVIEW,
        ]

        if self.need_note:
            label_text = "取消原因：" if self.target_status == ReservationStatus.CANCELLED else "备注："
            ttk.Label(frm, text=label_text).pack(anchor="w")
            self.note_text = tk.Text(frm, width=45, height=6)
            self.note_text.pack(pady=5)
        else:
            self.note_text = None

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="确认", command=self._on_ok, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=12).pack(side="left", padx=10)

    def _on_ok(self):
        if self.need_note:
            note = self.note_text.get("1.0", "end").strip()
            if not note:
                messagebox.showerror("错误", "请填写原因/备注", parent=self)
                return
            self.result_note = note
        self.confirmed = True
        self.destroy()

    def _on_cancel(self):
        self.confirmed = False
        self.destroy()


class FreezeDialog(tk.Toplevel):
    def __init__(self, parent, instrument, is_freeze: bool, user_role: UserRole, operator: str):
        super().__init__(parent)
        self.instrument = instrument
        self.is_freeze = is_freeze
        self.user_role = user_role
        self.operator = operator
        self.result_reason = None
        self.title("故障冻结" if is_freeze else "解除冻结")
        self.geometry("420x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        action = "故障冻结" if self.is_freeze else "解除冻结"
        ttk.Label(
            frm,
            text=f"对仪器 {self.instrument.code} 执行「{action}」操作",
            font=("Arial", 10, "bold"),
        ).pack(pady=(0, 10))

        ttk.Label(frm, text=f"操作人：{self.operator}").pack(anchor="w")
        ttk.Label(frm, text=f"角色：{self.user_role.value}").pack(anchor="w", pady=(0, 10))

        ttk.Label(frm, text="原因：").pack(anchor="w")
        self.reason_text = tk.Text(frm, width=45, height=6)
        self.reason_text.pack(pady=5)

        if self.is_freeze:
            ttk.Label(
                frm,
                text="提示：冻结后该仪器的所有活跃预约将被取消。",
                foreground="red",
            ).pack(anchor="w", pady=(5, 0))
        else:
            ttk.Label(
                frm,
                text="提示：仅管理员可解除故障冻结。",
                foreground="gray",
            ).pack(anchor="w", pady=(5, 0))

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="确认", command=self._on_ok, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self.destroy, width=12).pack(side="left", padx=10)

    def _on_ok(self):
        reason = self.reason_text.get("1.0", "end").strip()
        if not reason:
            messagebox.showerror("错误", "请填写原因", parent=self)
            return
        self.result_reason = reason
        self.destroy()


class CalibrationRecordsDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("校准/冻结记录")
        self.geometry("780x500")
        self.minsize(640, 400)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        filter_frame = ttk.LabelFrame(frm, text="筛选", padding=8)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="仪器：").grid(row=0, column=0, padx=(0, 5))
        self.code_filter_var = tk.StringVar()
        self.code_combo = ttk.Combobox(
            filter_frame, textvariable=self.code_filter_var, state="readonly", width=20
        )
        codes = [""] + sorted({r.get("instrument_code", "") for r in self.dm.calibration_records if r.get("instrument_code")})
        self.code_combo["values"] = codes
        self.code_combo.grid(row=0, column=1)
        self.code_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        ttk.Label(filter_frame, text="操作类型：").grid(row=0, column=2, padx=(15, 5))
        self.action_filter_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            filter_frame, textvariable=self.action_filter_var, state="readonly", width=12
        )
        actions = [""] + sorted({r.get("action", "") for r in self.dm.calibration_records if r.get("action")})
        self.action_combo["values"] = actions
        self.action_combo.grid(row=0, column=3)
        self.action_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        ttk.Button(filter_frame, text="清除筛选", command=self._clear_filter, width=10).grid(
            row=0, column=4, padx=(15, 0)
        )

        columns = ("time", "instrument_code", "action", "role", "operator", "reason")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings")
        self.tree.heading("time", text="时间")
        self.tree.heading("instrument_code", text="仪器编号")
        self.tree.heading("action", text="记录类型")
        self.tree.heading("role", text="角色")
        self.tree.heading("operator", text="操作人")
        self.tree.heading("reason", text="原因/内容")

        self.tree.column("time", width=150, anchor="w")
        self.tree.column("instrument_code", width=90, anchor="w")
        self.tree.column("action", width=90, anchor="w")
        self.tree.column("role", width=70, anchor="w")
        self.tree.column("operator", width=90, anchor="w")
        self.tree.column("reason", width=250, anchor="w")

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("freeze", foreground="#c62828")
        self.tree.tag_configure("unfreeze", foreground="#2e7d32")
        self.tree.tag_configure("calibration", foreground="#1565c0")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=(10, 0))

        ttk.Label(btn_frame, text=f"共 {len(self.dm.calibration_records)} 条记录").pack(side="left")
        ttk.Button(btn_frame, text="关闭", command=self.destroy, width=12).pack(side="right")

        self._refresh()

    def _clear_filter(self):
        self.code_filter_var.set("")
        self.action_filter_var.set("")
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        code_filter = self.code_filter_var.get()
        action_filter = self.action_filter_var.get()

        records = sorted(
            self.dm.calibration_records,
            key=lambda r: r.get("time", ""),
            reverse=True,
        )
        for r in records:
            if code_filter and r.get("instrument_code") != code_filter:
                continue
            if action_filter and r.get("action") != action_filter:
                continue

            action = r.get("action", "")
            if "冻结" in action and "解除" not in action:
                tag = "freeze"
            elif "解除" in action:
                tag = "unfreeze"
            else:
                tag = "calibration"

            reason = r.get("reason") or r.get("result") or ""
            if r.get("calibration_date"):
                reason = f"校准日期:{r['calibration_date']} {reason}".strip()

            self.tree.insert(
                "", "end",
                values=(
                    r.get("time", r.get("recorded_at", "")),
                    r.get("instrument_code", ""),
                    action,
                    r.get("role", ""),
                    r.get("operator", ""),
                    reason,
                ),
                tags=(tag,),
            )


class InstrumentDetailDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager, instrument):
        super().__init__(parent)
        self.dm = dm
        self.instrument = instrument
        self.title("仪器详情")
        self.geometry("500x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        info_frame = ttk.LabelFrame(frm, text="基本信息", padding=10)
        info_frame.pack(fill="x", pady=(0, 10))

        rows = [
            ("仪器编号", self.instrument.code),
            ("型号", self.instrument.model),
            ("负责人", self.instrument.person_in_charge),
            ("校准到期日", self.instrument.calibration_expiry),
            ("状态", self.instrument.status.value),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info_frame, text=label + "：").grid(row=i, column=0, sticky="e", padx=5, pady=3)
            ttk.Label(info_frame, text=value, font=("Arial", 10, "bold")).grid(
                row=i, column=1, sticky="w", padx=5, pady=3
            )

        if self.instrument.status == InstrumentStatus.MALFUNCTION_FROZEN:
            freeze_frame = ttk.LabelFrame(frm, text="冻结信息", padding=10)
            freeze_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(freeze_frame, text="冻结原因：").grid(row=0, column=0, sticky="ne", padx=5, pady=3)
            ttk.Label(freeze_frame, text=self.instrument.freeze_reason or "").grid(
                row=0, column=1, sticky="w", padx=5, pady=3
            )
            ttk.Label(freeze_frame, text="操作人：").grid(row=1, column=0, sticky="e", padx=5, pady=3)
            ttk.Label(freeze_frame, text=self.instrument.freeze_operator or "").grid(
                row=1, column=1, sticky="w", padx=5, pady=3
            )
            ttk.Label(freeze_frame, text="冻结时间：").grid(row=2, column=0, sticky="e", padx=5, pady=3)
            ttk.Label(freeze_frame, text=self.instrument.freeze_time or "").grid(
                row=2, column=1, sticky="w", padx=5, pady=3
            )

        slots_frame = ttk.LabelFrame(frm, text="可预约时段", padding=10)
        slots_frame.pack(fill="x", pady=(0, 10))
        slots_text = "\n".join(
            [f"• {ts.start_time} - {ts.end_time}" for ts in self.instrument.available_time_slots]
        ) or "无"
        ttk.Label(slots_frame, text=slots_text, justify="left").pack(anchor="w")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="关闭", command=self.destroy, width=12).pack()


class SandboxDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("预约批量建单沙盘")
        self.geometry("1100x780")
        self.minsize(1000, 700)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._refresh_drafts()

    def _build_ui(self):
        padding = {"padx": 6, "pady": 4}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        top_frame = ttk.Frame(frm)
        top_frame.pack(fill="x", pady=(0, 6))

        ttk.Button(top_frame, text="导入CSV", command=self._import_csv, width=12).pack(side="left", padx=3)
        ttk.Button(top_frame, text="导入JSON", command=self._import_json, width=12).pack(side="left", padx=3)
        ttk.Separator(top_frame, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top_frame, text="删除草稿", command=self._delete_draft, width=10).pack(side="left", padx=3)
        ttk.Button(top_frame, text="刷新", command=self._refresh_drafts, width=8).pack(side="left", padx=3)

        drafts_lf = ttk.LabelFrame(frm, text="草稿列表", padding=6)
        drafts_lf.pack(fill="x", pady=(0, 6))

        draft_cols = ("name", "operator", "items", "source", "submitted", "created_at")
        self.draft_tree = ttk.Treeview(drafts_lf, columns=draft_cols, show="headings", height=5)
        self.draft_tree.heading("name", text="草稿名称")
        self.draft_tree.heading("operator", text="操作人")
        self.draft_tree.heading("items", text="条目数")
        self.draft_tree.heading("source", text="来源文件")
        self.draft_tree.heading("submitted", text="提交状态")
        self.draft_tree.heading("created_at", text="创建时间")
        self.draft_tree.column("name", width=150, anchor="w")
        self.draft_tree.column("operator", width=80, anchor="w")
        self.draft_tree.column("items", width=60, anchor="center")
        self.draft_tree.column("source", width=150, anchor="w")
        self.draft_tree.column("submitted", width=80, anchor="center")
        self.draft_tree.column("created_at", width=140, anchor="w")
        self.draft_tree.pack(fill="x")
        self.draft_tree.bind("<<TreeviewSelect>>", self._on_draft_select)

        action_frame = ttk.Frame(frm)
        action_frame.pack(fill="x", pady=(0, 6))
        ttk.Button(action_frame, text="预演", command=self._preview, width=10).pack(side="left", padx=3)
        ttk.Button(action_frame, text="确认提交", command=self._confirm_submit, width=10).pack(side="left", padx=3)
        ttk.Button(action_frame, text="撤回", command=self._withdraw, width=10).pack(side="left", padx=3)
        ttk.Separator(action_frame, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(action_frame, text="导出预演结果", command=self._export_preview, width=14).pack(side="left", padx=3)
        ttk.Button(action_frame, text="导出差异报告", command=self._export_diff, width=14).pack(side="left", padx=3)

        detail_lf = ttk.LabelFrame(frm, text="草稿明细（预演状态 & 原因）", padding=6)
        detail_lf.pack(fill="both", expand=True, pady=(0, 6))

        detail_cols = ("idx", "instrument", "applicant", "purpose", "start", "end", "status", "reasons")
        self.detail_tree = ttk.Treeview(detail_lf, columns=detail_cols, show="headings", height=12)
        self.detail_tree.heading("idx", text="序号")
        self.detail_tree.heading("instrument", text="仪器编号")
        self.detail_tree.heading("applicant", text="申请人")
        self.detail_tree.heading("purpose", text="用途")
        self.detail_tree.heading("start", text="开始时间")
        self.detail_tree.heading("end", text="结束时间")
        self.detail_tree.heading("status", text="预演状态")
        self.detail_tree.heading("reasons", text="原因")
        self.detail_tree.column("idx", width=45, anchor="center")
        self.detail_tree.column("instrument", width=80, anchor="w")
        self.detail_tree.column("applicant", width=70, anchor="w")
        self.detail_tree.column("purpose", width=120, anchor="w")
        self.detail_tree.column("start", width=130, anchor="w")
        self.detail_tree.column("end", width=130, anchor="w")
        self.detail_tree.column("status", width=80, anchor="center")
        self.detail_tree.column("reasons", width=300, anchor="w")

        self.detail_tree.tag_configure("direct", foreground="#2e7d32")
        self.detail_tree.tag_configure("confirm", foreground="#e65100")
        self.detail_tree.tag_configure("forbidden", foreground="#c62828")
        self.detail_tree.tag_configure("none", foreground="#9e9e9e")

        vsb = ttk.Scrollbar(detail_lf, orient="vertical", command=self.detail_tree.yview)
        self.detail_tree.configure(yscrollcommand=vsb.set)
        self.detail_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.status_label = ttk.Label(frm, text="", anchor="w")
        self.status_label.pack(fill="x")

        ttk.Button(frm, text="关闭", command=self.destroy, width=10).pack(anchor="e", pady=(4, 0))

    def _refresh_drafts(self):
        for item in self.draft_tree.get_children():
            self.draft_tree.delete(item)
        drafts = self.dm.list_sandbox_drafts()
        for d in drafts:
            sub_text = "已提交" if d.is_submitted else "未提交"
            self.draft_tree.insert("", "end", iid=d.id, values=(
                d.name, d.operator, len(d.items),
                d.source_file, sub_text, d.created_at,
            ))
        self._update_permissions()
        self.status_label.config(text=f"共 {len(drafts)} 份草稿")

    def _update_permissions(self):
        is_admin = self.dm.settings.current_role == UserRole.ADMIN

    def _get_selected_draft(self):
        sel = self.draft_tree.selection()
        if not sel:
            return None
        return self.dm.get_sandbox_draft(sel[0])

    def _on_draft_select(self, _=None):
        draft = self._get_selected_draft()
        if not draft:
            return
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)
        for it in draft.items:
            status_display = it.preview_status or "未预演"
            reasons_str = "; ".join(it.preview_reasons) if it.preview_reasons else ""
            tag = "direct" if it.preview_status == SandboxItemStatus.DIRECT_SUBMIT.value else \
                  "confirm" if it.preview_status == SandboxItemStatus.NEEDS_CONFIRM.value else \
                  "forbidden" if it.preview_status == SandboxItemStatus.FORBIDDEN.value else "none"
            self.detail_tree.insert("", "end", values=(
                it.index + 1, it.instrument_code, it.applicant, it.purpose,
                it.start_time, it.end_time, status_display, reasons_str,
            ), tags=(tag,))
        sub_text = "已提交" if draft.is_submitted else "未提交"
        self.status_label.config(
            text=f"草稿「{draft.name}」- {len(draft.items)}条 - {sub_text}"
        )

    def _import_csv(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可执行沙盘导入", parent=self)
            return
        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入预约明细CSV",
            initialdir=initial_dir,
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        self._do_import(filepath)

    def _import_json(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可执行沙盘导入", parent=self)
            return
        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入预约明细JSON",
            initialdir=initial_dir,
            filetypes=[("JSON 文件", "*.json")],
            parent=self,
        )
        if not filepath:
            return
        self._do_import(filepath)

    def _do_import(self, filepath):
        draft_name = os.path.splitext(os.path.basename(filepath))[0]
        draft_name = simpledialog.askstring(
            "草稿名称", "请输入草稿名称：", initialvalue=draft_name, parent=self
        )
        if not draft_name or not draft_name.strip():
            return
        draft, errors = self.dm.import_to_sandbox_draft(
            filepath, draft_name.strip(),
            self.dm.settings.current_user,
            self.dm.settings.current_role,
        )
        if draft:
            msg = f"导入成功！\n\n草稿名称：{draft.name}\n有效条目：{len(draft.items)}条"
            if errors:
                msg += "\n\n提示信息：\n" + "\n".join(errors[:10])
            messagebox.showinfo("沙盘导入", msg, parent=self)
            self._refresh_drafts()
        else:
            messagebox.showerror("沙盘导入失败", "\n".join(errors[:15]), parent=self)

    def _delete_draft(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        if not messagebox.askyesno("确认", f"确定要删除草稿「{draft.name}」吗？", parent=self):
            return
        ok, msg = self.dm.delete_sandbox_draft(draft.id)
        if ok:
            self._refresh_drafts()
        else:
            messagebox.showerror("删除失败", msg, parent=self)

    def _preview(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        draft = self.dm.preview_sandbox_draft(draft.id)
        if not draft:
            messagebox.showerror("预演失败", "草稿不存在", parent=self)
            return
        self._on_draft_select()
        direct = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.DIRECT_SUBMIT.value)
        confirm = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.NEEDS_CONFIRM.value)
        forbidden = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.FORBIDDEN.value)
        messagebox.showinfo(
            "预演完成",
            f"草稿「{draft.name}」预演结果：\n\n"
            f"可直接提交：{direct}条\n需人工确认：{confirm}条\n禁止提交：{forbidden}条",
            parent=self,
        )

    def _confirm_submit(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        if draft.is_submitted:
            messagebox.showwarning("提示", "该草稿已提交", parent=self)
            return
        if not any(it.preview_status for it in draft.items):
            messagebox.showwarning("提示", "请先执行预演", parent=self)
            return
        direct = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.DIRECT_SUBMIT.value)
        confirm = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.NEEDS_CONFIRM.value)
        forbidden = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.FORBIDDEN.value)
        if not messagebox.askyesno(
            "确认提交",
            f"将提交草稿「{draft.name}」：\n\n"
            f"可直接提交：{direct}条（将正式入库）\n"
            f"需人工确认：{confirm}条（将正式入库，请注意风险）\n"
            f"禁止提交：{forbidden}条（将被跳过）\n\n是否继续？",
            parent=self,
        ):
            return
        draft_updated, fail_msgs, batch_id = self.dm.confirm_sandbox_draft(
            draft.id,
            self.dm.settings.current_user,
            self.dm.settings.current_role,
        )
        if not draft_updated:
            messagebox.showerror("提交失败", "\n".join(fail_msgs), parent=self)
            return
        self._refresh_drafts()
        self._on_draft_select()
        msg = f"提交完成！\n\n成功入库：{len([it for it in draft_updated.items if it.reservation_id])}条\n"
        if fail_msgs:
            msg += f"跳过/失败：{len(fail_msgs)}条\n\n" + "\n".join(fail_msgs[:10])
        messagebox.showinfo("沙盘提交", msg, parent=self)

    def _withdraw(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        if not draft.is_submitted:
            messagebox.showwarning("提示", "该草稿尚未提交", parent=self)
            return
        reason = simpledialog.askstring(
            "撤回原因", "请输入撤回原因：", parent=self
        )
        if not reason or not reason.strip():
            messagebox.showwarning("提示", "请填写撤回原因", parent=self)
            return
        ok, msg = self.dm.sandbox_batch_withdraw(
            draft.id,
            self.dm.settings.current_user,
            self.dm.settings.current_role,
            reason.strip(),
        )
        if ok:
            messagebox.showinfo("撤回成功", msg, parent=self)
            self._refresh_drafts()
            self._on_draft_select()
        else:
            messagebox.showerror("撤回失败", msg, parent=self)

    def _export_preview(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出预演结果",
            initialdir=initial_dir,
            initialfile=f"沙盘预演_{draft.name}_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_sandbox_preview(draft.id, filepath)
        if ok:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"预演结果已导出到：\n{filepath}", parent=self)
        else:
            messagebox.showerror("导出失败", msg, parent=self)

    def _export_diff(self):
        draft = self._get_selected_draft()
        if not draft:
            messagebox.showwarning("提示", "请先选择一份草稿", parent=self)
            return
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出差异报告",
            initialdir=initial_dir,
            initialfile=f"沙盘差异_{draft.name}_{date.today().strftime('%Y%m%d')}.txt",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_sandbox_diff_report(draft.id, filepath)
        if ok:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"差异报告已导出到：\n{filepath}", parent=self)
        else:
            messagebox.showerror("导出失败", msg, parent=self)


class App:
    def __init__(self):
        self.dm = DataManager()
        self.dm.init_sample_data()

        self.root = tk.Tk()
        self.root.title("实验室仪器预约校准系统")
        self.root.geometry("1100x680")
        self.root.minsize(900, 600)

        self._setup_styles()
        self._build_menu()
        self._build_ui()
        self._load_settings()
        self._refresh_instruments()
        self._refresh_reservations()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Status.TLabel", padding=5)
        style.configure("Normal.TLabel", foreground="#2e7d32")
        style.configure("Expired.TLabel", foreground="#e65100")
        style.configure("Frozen.TLabel", foreground="#c62828")
        style.configure("Header.TLabel", font=("Arial", 11, "bold"))

    def _build_menu(self):
        self.menubar = tk.Menu(self.root)

        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="导出预约 (CSV)", command=lambda: self._export("csv"))
        file_menu.add_command(label="导出预约 (JSON)", command=lambda: self._export("json"))
        file_menu.add_command(label="导出仪器档案 (CSV)", command=self._export_instruments)
        file_menu.add_separator()
        file_menu.add_command(label="查看校准/冻结记录", command=self._show_calibration_records)
        file_menu.add_command(label="查看操作日志", command=self._show_operation_logs)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        self.menubar.add_cascade(label="文件", menu=file_menu)

        self.template_menu = tk.Menu(self.menubar, tearoff=0)
        self.template_menu.add_command(label="模板管理", command=self._show_template_management)
        self.template_menu.add_command(label="导入模板 (JSON)", command=self._import_templates_json)
        self.template_menu.add_command(label="导入模板 (CSV)", command=self._import_templates_csv)
        self.template_menu.add_separator()
        self.template_menu.add_command(label="查看最近导入结果", command=self._show_last_import_result)
        self.template_menu.add_separator()
        self.template_menu.add_command(label="导出模板 (JSON)", command=self._export_templates_json)
        self.template_menu.add_command(label="导出模板 (CSV)", command=self._export_templates_csv)
        self.menubar.add_cascade(label="模板", menu=self.template_menu)

        self.batch_menu = tk.Menu(self.menubar, tearoff=0)
        self.batch_menu.add_command(label="批量创建预约", command=self._show_batch_create)
        self.batch_menu.add_command(label="批量操作记录", command=self._show_batch_management)
        self.batch_menu.add_separator()
        self.batch_menu.add_command(label="预约沙盘", command=self._show_sandbox)
        self.batch_menu.add_separator()
        self.menu_import_mapping = self.batch_menu.add_command(
            label="预约导入映射中心", command=self._show_import_mapping_center
        )
        self.batch_menu.add_separator()
        self.menu_validation_workbench = self.batch_menu.add_command(
            label="导入体检工作台", command=self._show_validation_workbench
        )
        self.menubar.add_cascade(label="批量操作", menu=self.batch_menu)

        role_menu = tk.Menu(self.menubar, tearoff=0)
        self.role_var = tk.StringVar(value=self.dm.settings.current_role.value)
        role_menu.add_radiobutton(
            label="普通用户", variable=self.role_var, value="普通用户", command=self._on_role_change
        )
        role_menu.add_radiobutton(
            label="管理员", variable=self.role_var, value="管理员", command=self._on_role_change
        )
        self.menubar.add_cascade(label="角色", menu=role_menu)

        settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.reminder_enabled_var = tk.BooleanVar(value=self.dm.settings.reminder_enabled)
        settings_menu.add_checkbutton(
            label="启用提醒", variable=self.reminder_enabled_var, command=self._on_reminder_toggle
        )
        settings_menu.add_command(label="默认提醒时长...", command=self._set_default_reminder)
        self.menubar.add_cascade(label="设置", menu=settings_menu)

        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        self.menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.config(menu=self.menubar)
        self._update_menu_permissions()

    def _build_ui(self):
        main_paned = ttk.PanedWindow(self.root, orient="horizontal")
        main_paned.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(left_frame, weight=1)

        right_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(right_frame, weight=2)

        self._build_instruments_panel(left_frame)
        self._build_reservations_panel(right_frame)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", side="bottom", padx=10, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="就绪", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        role_text = f"当前用户：{self.dm.settings.current_user} | 角色：{self.dm.settings.current_role.value}"
        self.role_status_label = ttk.Label(status_frame, text=role_text, anchor="e")
        self.role_status_label.pack(side="right")

    def _build_instruments_panel(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(header_frame, text="仪器档案", style="Header.TLabel").pack(side="left")

        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side="right")

        ttk.Button(btn_frame, text="详情", command=self._show_instrument_detail, width=6).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="预约", command=self._new_reservation, width=6).pack(side="right", padx=2)

        filter_frame = ttk.LabelFrame(parent, text="筛选", padding=8)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="负责人：").grid(row=0, column=0, padx=(0, 5))
        self.person_filter_var = tk.StringVar()
        self.person_combo = ttk.Combobox(
            filter_frame, textvariable=self.person_filter_var, state="readonly", width=12
        )
        self.person_combo.grid(row=0, column=1)
        self.person_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        ttk.Label(filter_frame, text="状态：").grid(row=0, column=2, padx=(10, 5))
        self.status_filter_var = tk.StringVar()
        self.status_combo = ttk.Combobox(
            filter_frame, textvariable=self.status_filter_var, state="readonly", width=10
        )
        self.status_combo["values"] = ["", "正常", "校准过期", "故障冻结"]
        self.status_combo.grid(row=0, column=3)
        self.status_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        columns = ("code", "model", "person", "status")
        self.instrument_tree = ttk.Treeview(parent, columns=columns, show="headings", height=15)
        self.instrument_tree.heading("code", text="仪器编号")
        self.instrument_tree.heading("model", text="型号")
        self.instrument_tree.heading("person", text="负责人")
        self.instrument_tree.heading("status", text="状态")

        self.instrument_tree.column("code", width=100, anchor="w")
        self.instrument_tree.column("model", width=180, anchor="w")
        self.instrument_tree.column("person", width=80, anchor="w")
        self.instrument_tree.column("status", width=80, anchor="w")

        self.instrument_tree.pack(fill="both", expand=True, pady=(5, 5))
        self.instrument_tree.bind("<<TreeviewSelect>>", lambda e: self._on_instrument_select())
        self.instrument_tree.bind("<Double-1>", lambda e: self._show_instrument_detail())

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.instrument_tree.yview)
        self.instrument_tree.configure(yscrollcommand=scrollbar.set)

        action_frame = ttk.LabelFrame(parent, text="仪器操作", padding=8)
        action_frame.pack(fill="x")

        ttk.Button(action_frame, text="模板管理", command=self._show_template_management).pack(side="left", padx=3)
        ttk.Button(action_frame, text="故障冻结", command=self._freeze_instrument).pack(side="left", padx=3)
        ttk.Button(action_frame, text="解除冻结", command=self._unfreeze_instrument).pack(side="left", padx=3)
        ttk.Button(action_frame, text="校准记录", command=self._show_calibration_records).pack(side="left", padx=3)
        ttk.Button(action_frame, text="刷新", command=self._refresh_instruments).pack(side="right", padx=3)

    def _build_reservations_panel(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(header_frame, text="预约记录", style="Header.TLabel").pack(side="left")

        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side="right")

        ttk.Button(btn_frame, text="模板管理", command=self._show_template_management, width=10).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="批量记录", command=self._show_batch_management, width=10).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="批量创建", command=self._show_batch_create, width=10).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="新建预约", command=self._new_reservation, width=10).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="编辑", command=self._edit_reservation, width=8).pack(side="right", padx=2)

        filter_frame = ttk.LabelFrame(parent, text="筛选", padding=8)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="仪器负责人：").grid(row=0, column=0, padx=(0, 5))
        self.res_person_filter_var = tk.StringVar()
        self.res_person_combo = ttk.Combobox(
            filter_frame, textvariable=self.res_person_filter_var, state="readonly", width=12
        )
        self.res_person_combo.grid(row=0, column=1)
        self.res_person_combo.bind("<<ComboboxSelected>>", lambda e: self._on_res_filter_change())

        ttk.Label(filter_frame, text="预约状态：").grid(row=0, column=2, padx=(10, 5))
        self.res_status_filter_var = tk.StringVar()
        self.res_status_combo = ttk.Combobox(
            filter_frame, textvariable=self.res_status_filter_var, state="readonly", width=10
        )
        statuses = ["", "草稿", "待确认", "已预约", "使用中", "待复核", "已完成", "已取消"]
        self.res_status_combo["values"] = statuses
        self.res_status_combo.grid(row=0, column=3)
        self.res_status_combo.bind("<<ComboboxSelected>>", lambda e: self._on_res_filter_change())

        columns = ("code", "applicant", "purpose", "template", "batch", "start", "end", "status", "created")
        self.reservation_tree = ttk.Treeview(parent, columns=columns, show="headings", height=18)
        self.reservation_tree.heading("code", text="仪器编号")
        self.reservation_tree.heading("applicant", text="申请人")
        self.reservation_tree.heading("purpose", text="用途")
        self.reservation_tree.heading("template", text="模板")
        self.reservation_tree.heading("batch", text="批次")
        self.reservation_tree.heading("start", text="开始时间")
        self.reservation_tree.heading("end", text="结束时间")
        self.reservation_tree.heading("status", text="状态")
        self.reservation_tree.heading("created", text="创建时间")

        self.reservation_tree.column("code", width=80, anchor="w")
        self.reservation_tree.column("applicant", width=70, anchor="w")
        self.reservation_tree.column("purpose", width=100, anchor="w")
        self.reservation_tree.column("template", width=100, anchor="w")
        self.reservation_tree.column("batch", width=60, anchor="w")
        self.reservation_tree.column("start", width=120, anchor="w")
        self.reservation_tree.column("end", width=120, anchor="w")
        self.reservation_tree.column("status", width=70, anchor="w")
        self.reservation_tree.column("created", width=120, anchor="w")

        self.reservation_tree.pack(fill="both", expand=True, pady=(5, 5))
        self.reservation_tree.bind("<<TreeviewSelect>>", lambda e: self._on_reservation_select())

        action_frame = ttk.LabelFrame(parent, text="预约操作", padding=8)
        action_frame.pack(fill="x")

        self.btn_submit = ttk.Button(action_frame, text="提交确认", command=lambda: self._change_status(ReservationStatus.PENDING_CONFIRM))
        self.btn_submit.pack(side="left", padx=3)

        self.btn_confirm = ttk.Button(action_frame, text="确认预约", command=lambda: self._change_status(ReservationStatus.CONFIRMED))
        self.btn_confirm.pack(side="left", padx=3)

        self.btn_use = ttk.Button(action_frame, text="开始使用", command=lambda: self._change_status(ReservationStatus.IN_USE))
        self.btn_use.pack(side="left", padx=3)

        self.btn_review = ttk.Button(action_frame, text="提交复核", command=lambda: self._change_status(ReservationStatus.PENDING_REVIEW))
        self.btn_review.pack(side="left", padx=3)

        self.btn_complete = ttk.Button(action_frame, text="复核完成", command=lambda: self._change_status(ReservationStatus.COMPLETED))
        self.btn_complete.pack(side="left", padx=3)

        self.btn_cancel = ttk.Button(action_frame, text="取消", command=lambda: self._change_status(ReservationStatus.CANCELLED))
        self.btn_cancel.pack(side="left", padx=3)

        ttk.Button(action_frame, text="刷新", command=self._refresh_reservations).pack(side="right", padx=3)

        self._update_action_buttons()

    def _refresh_instruments(self):
        persons = [""] + self.dm.get_all_persons()
        self.person_combo["values"] = persons
        self.res_person_combo["values"] = persons

        person_filter = self.person_filter_var.get()
        status_filter = self.status_filter_var.get()

        for item in self.instrument_tree.get_children():
            self.instrument_tree.delete(item)

        instruments = self.dm.instruments
        if person_filter:
            instruments = [ins for ins in instruments if ins.person_in_charge == person_filter]
        if status_filter:
            instruments = [ins for ins in instruments if ins.status.value == status_filter]

        for ins in instruments:
            tag = "normal" if ins.status == InstrumentStatus.NORMAL else \
                  "expired" if ins.status == InstrumentStatus.CALIBRATION_EXPIRED else "frozen"
            self.instrument_tree.insert(
                "", "end", iid=ins.id,
                values=(ins.code, ins.model, ins.person_in_charge, ins.status.value),
                tags=(tag,)
            )

        self.instrument_tree.tag_configure("normal", foreground="#2e7d32")
        self.instrument_tree.tag_configure("expired", foreground="#e65100")
        self.instrument_tree.tag_configure("frozen", foreground="#c62828")

    def _refresh_reservations(self):
        person_filter = self.res_person_filter_var.get()
        status_filter = self.res_status_filter_var.get()

        for item in self.reservation_tree.get_children():
            self.reservation_tree.delete(item)

        reservations = self.dm.get_reservations_filtered(person_filter, status_filter)

        status_colors = {
            ReservationStatus.DRAFT: "draft",
            ReservationStatus.PENDING_CONFIRM: "pending",
            ReservationStatus.CONFIRMED: "confirmed",
            ReservationStatus.IN_USE: "inuse",
            ReservationStatus.PENDING_REVIEW: "review",
            ReservationStatus.COMPLETED: "completed",
            ReservationStatus.CANCELLED: "cancelled",
        }

        for r in reservations:
            tag = status_colors.get(r.status, "")
            purpose_short = r.purpose[:20] + "..." if len(r.purpose) > 20 else r.purpose

            template_name = ""
            if r.template_snapshot:
                if isinstance(r.template_snapshot, dict):
                    template_name = r.template_snapshot.get("template_name", "")
                else:
                    template_name = getattr(r.template_snapshot, "template_name", "")
            if template_name:
                template_name = template_name[:12] + "..." if len(template_name) > 12 else template_name

            batch_tag = ""
            if r.batch_id:
                batch_tag = "[批量]"

            self.reservation_tree.insert(
                "", "end", iid=r.id,
                values=(r.instrument_code, r.applicant, purpose_short,
                        template_name, batch_tag, r.start_time, r.end_time,
                        r.status.value, r.created_at),
                tags=(tag,)
            )

        self.reservation_tree.tag_configure("draft", foreground="#757575")
        self.reservation_tree.tag_configure("pending", foreground="#f57f17")
        self.reservation_tree.tag_configure("confirmed", foreground="#1565c0")
        self.reservation_tree.tag_configure("inuse", foreground="#2e7d32")
        self.reservation_tree.tag_configure("review", foreground="#6a1b9a")
        self.reservation_tree.tag_configure("completed", foreground="#2e7d32")
        self.reservation_tree.tag_configure("cancelled", foreground="#9e9e9e")

        self._update_action_buttons()

    def _get_selected_instrument(self):
        selection = self.instrument_tree.selection()
        if not selection:
            return None
        return self.dm.get_instrument(selection[0])

    def _get_selected_reservation(self):
        selection = self.reservation_tree.selection()
        if not selection:
            return None
        for r in self.dm.reservations:
            if r.id == selection[0]:
                return r
        return None

    def _on_instrument_select(self):
        pass

    def _on_reservation_select(self):
        self._update_action_buttons()

    def _update_action_buttons(self):
        reservation = self._get_selected_reservation()
        if not reservation:
            for btn in [self.btn_submit, self.btn_confirm, self.btn_use,
                        self.btn_review, self.btn_complete, self.btn_cancel]:
                btn.config(state="disabled")
            return

        current_status = reservation.status
        allowed = STATUS_FLOW.get(current_status, [])

        button_map = {
            ReservationStatus.PENDING_CONFIRM: self.btn_submit,
            ReservationStatus.CONFIRMED: self.btn_confirm,
            ReservationStatus.IN_USE: self.btn_use,
            ReservationStatus.PENDING_REVIEW: self.btn_review,
            ReservationStatus.COMPLETED: self.btn_complete,
            ReservationStatus.CANCELLED: self.btn_cancel,
        }

        for target, btn in button_map.items():
            if target in allowed:
                btn.config(state="normal")
            else:
                btn.config(state="disabled")

    def _on_filter_change(self):
        self.dm.settings.ins_filter_person = self.person_filter_var.get()
        self.dm.settings.ins_filter_status = self.status_filter_var.get()
        self.dm.save_settings()
        self._refresh_instruments()

    def _on_res_filter_change(self):
        self.dm.settings.filter_person = self.res_person_filter_var.get()
        self.dm.settings.filter_status = self.res_status_filter_var.get()
        self.dm.save_settings()
        self._refresh_reservations()

    def _load_settings(self):
        if self.dm.settings.ins_filter_person:
            self.person_filter_var.set(self.dm.settings.ins_filter_person)
        if self.dm.settings.ins_filter_status:
            self.status_filter_var.set(self.dm.settings.ins_filter_status)
        if self.dm.settings.filter_person:
            self.res_person_filter_var.set(self.dm.settings.filter_person)
        if self.dm.settings.filter_status:
            self.res_status_filter_var.set(self.dm.settings.filter_status)
        self.role_var.set(self.dm.settings.current_role.value)

    def _on_role_change(self):
        role_str = self.role_var.get()
        self.dm.settings.current_role = UserRole(role_str)
        self.dm.save_settings()
        self.role_status_label.config(
            text=f"当前用户：{self.dm.settings.current_user} | 角色：{role_str}"
        )
        self._update_action_buttons()
        self._update_menu_permissions()

    def _update_menu_permissions(self):
        is_admin = self.dm.settings.current_role == UserRole.ADMIN
        import_json_idx = 1
        import_csv_idx = 2
        show_last_idx = 4
        try:
            if is_admin:
                self.template_menu.entryconfig(import_json_idx, state="normal")
                self.template_menu.entryconfig(import_csv_idx, state="normal")
                self.template_menu.entryconfig(show_last_idx, state="normal")
            else:
                self.template_menu.entryconfig(import_json_idx, state="disabled")
                self.template_menu.entryconfig(import_csv_idx, state="disabled")
                self.template_menu.entryconfig(show_last_idx, state="disabled")
        except tk.TclError:
            pass
        try:
            mapping_idx = 6
            if is_admin:
                self.batch_menu.entryconfig(mapping_idx, state="normal")
            else:
                self.batch_menu.entryconfig(mapping_idx, state="disabled")
        except tk.TclError:
            pass

    def _show_last_import_result(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可查看导入结果", parent=self.root)
            return

        result = self.dm.settings.last_import_result
        if not result:
            messagebox.showinfo("最近导入结果", "暂无导入记录", parent=self.root)
            return

        msg = f"最近一次导入时间：{result.timestamp}\n\n"
        msg += f"总计：{result.total_count} 条\n"
        msg += f"成功：{result.success_count} 条\n"
        msg += f"失败：{result.failed_count} 条\n"
        msg += f"整体状态：{'全部成功' if result.success else '存在错误'}\n"
        if result.imported_template_ids:
            msg += f"\n导入的模板ID：\n" + "\n".join(
                [f"  - {tid}" for tid in result.imported_template_ids[:10]]
            )
            if len(result.imported_template_ids) > 10:
                msg += f"\n  ... 共 {len(result.imported_template_ids)} 个"
        if result.errors:
            msg += "\n\n错误详情：\n" + "\n".join(
                [f"  × {e}" for e in result.errors[:15]]
            )
            if len(result.errors) > 15:
                msg += f"\n  ... 还有 {len(result.errors) - 15} 条错误"
        if result.warnings:
            msg += "\n\n警告：\n" + "\n".join(
                [f"  ! {w}" for w in result.warnings[:10]]
            )
        messagebox.showinfo("最近一次导入结果", msg, parent=self.root)

    def _new_reservation(self):
        ins = self._get_selected_instrument()
        if not ins:
            messagebox.showwarning("提示", "请先选择一台仪器", parent=self.root)
            return

        if ins.status != InstrumentStatus.NORMAL:
            reason = "校准已过期" if ins.status == InstrumentStatus.CALIBRATION_EXPIRED else "处于故障冻结状态"
            messagebox.showerror("无法预约", f"仪器{reason}，无法预约", parent=self.root)
            return

        dlg = ReservationDialog(self.root, self.dm, "新建预约", instrument_id=ins.id)
        self.root.wait_window(dlg)

        if dlg.result:
            self._set_status(f"预约创建成功：{dlg.result.instrument_code}")
            self._refresh_reservations()

    def _edit_reservation(self):
        res = self._get_selected_reservation()
        if not res:
            messagebox.showwarning("提示", "请选择要编辑的预约", parent=self.root)
            return

        if res.status not in [ReservationStatus.DRAFT, ReservationStatus.PENDING_CONFIRM]:
            messagebox.showwarning("提示", "仅草稿和待确认状态的预约可编辑", parent=self.root)
            return

        dlg = ReservationDialog(self.root, self.dm, "编辑预约", reservation=res)
        self.root.wait_window(dlg)

        if dlg.result:
            self._set_status("预约更新成功")
            self._refresh_reservations()

    def _change_status(self, target_status: ReservationStatus):
        res = self._get_selected_reservation()
        if not res:
            messagebox.showwarning("提示", "请选择预约", parent=self.root)
            return

        dlg = StatusChangeDialog(self.root, res, target_status)
        self.root.wait_window(dlg)

        if not dlg.confirmed:
            return

        updated, msg = self.dm.update_reservation_status(
            res.id, target_status, self.dm.settings.current_role, dlg.result_note
        )
        if not updated:
            messagebox.showerror("操作失败", msg, parent=self.root)
            return

        self._set_status(f"预约状态已变更为「{target_status.value}」")
        self._refresh_reservations()
        self._refresh_instruments()

    def _show_instrument_detail(self):
        ins = self._get_selected_instrument()
        if not ins:
            messagebox.showwarning("提示", "请选择仪器", parent=self.root)
            return
        InstrumentDetailDialog(self.root, self.dm, ins)

    def _show_calibration_records(self):
        CalibrationRecordsDialog(self.root, self.dm)

    def _freeze_instrument(self):
        ins = self._get_selected_instrument()
        if not ins:
            messagebox.showwarning("提示", "请选择仪器", parent=self.root)
            return

        if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
            messagebox.showwarning("提示", "该仪器已处于故障冻结状态", parent=self.root)
            return

        dlg = FreezeDialog(
            self.root, ins, True,
            self.dm.settings.current_role,
            self.dm.settings.current_user
        )
        self.root.wait_window(dlg)

        if dlg.result_reason:
            result, msg = self.dm.freeze_instrument(
                ins.id, dlg.result_reason,
                self.dm.settings.current_user,
                self.dm.settings.current_role
            )
            if not result:
                messagebox.showerror("操作失败", msg, parent=self.root)
                return
            self._set_status(f"仪器 {ins.code} 已故障冻结")
            self._refresh_instruments()
            self._refresh_reservations()

    def _unfreeze_instrument(self):
        ins = self._get_selected_instrument()
        if not ins:
            messagebox.showwarning("提示", "请选择仪器", parent=self.root)
            return

        if ins.status != InstrumentStatus.MALFUNCTION_FROZEN:
            messagebox.showwarning("提示", "该仪器未处于故障冻结状态", parent=self.root)
            return

        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可解除故障冻结", parent=self.root)
            return

        dlg = FreezeDialog(
            self.root, ins, False,
            self.dm.settings.current_role,
            self.dm.settings.current_user
        )
        self.root.wait_window(dlg)

        if dlg.result_reason:
            result, msg = self.dm.unfreeze_instrument(
                ins.id, dlg.result_reason,
                self.dm.settings.current_user,
                self.dm.settings.current_role
            )
            if not result:
                messagebox.showerror("操作失败", msg, parent=self.root)
                return
            self._set_status(f"仪器 {ins.code} 已解除冻结")
            self._refresh_instruments()
            self._refresh_reservations()

    def _export(self, file_type: str):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")

        if file_type == "csv":
            filetypes = [("CSV 文件", "*.csv")]
            default_ext = ".csv"
            default_name = f"预约记录_{date.today().strftime('%Y%m%d')}.csv"
        else:
            filetypes = [("JSON 文件", "*.json")]
            default_ext = ".json"
            default_name = f"预约记录_{date.today().strftime('%Y%m%d')}.json"

        filepath = filedialog.asksaveasfilename(
            title="导出预约记录",
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=default_ext,
            filetypes=filetypes,
        )

        if not filepath:
            return

        person_filter = self.res_person_filter_var.get()
        status_filter = self.res_status_filter_var.get()

        if file_type == "csv":
            success, msg = self.dm.export_reservations_csv(filepath, person_filter, status_filter)
        else:
            success, msg = self.dm.export_reservations_json(filepath, person_filter, status_filter)

        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"预约记录已导出到：\n{filepath}", parent=self.root)
            self._set_status(f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self.root)

    def _export_instruments(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出仪器档案",
            initialdir=initial_dir,
            initialfile=f"仪器档案_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )

        if not filepath:
            return

        success, msg = self.dm.export_instruments_csv(filepath)
        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"仪器档案已导出到：\n{filepath}", parent=self.root)
            self._set_status(f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self.root)

    def _show_template_management(self):
        dlg = TemplateManagementDialog(self.root, self.dm)
        self.root.wait_window(dlg)

    def _import_templates_json(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入模板", parent=self.root)
            return

        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入模板JSON",
            initialdir=initial_dir,
            filetypes=[("JSON 文件", "*.json")],
        )
        if not filepath:
            return

        overwrite = messagebox.askyesno(
            "覆盖确认",
            "是否覆盖已存在的同名模板？\n\n是：覆盖已有模板\n否：跳过同名模板",
            parent=self.root
        )

        result = self.dm.import_templates_json(
            filepath, overwrite=overwrite, user_role=self.dm.settings.current_role
        )

        self.dm.settings.import_dir = os.path.dirname(filepath)
        self.dm.save_settings()

        msg = f"导入完成！\n\n总计：{result.total_count} 条\n成功：{result.success_count} 条\n失败：{result.failed_count} 条"
        if result.errors:
            msg += "\n\n错误信息：\n" + "\n".join(result.errors[:10])
            if len(result.errors) > 10:
                msg += f"\n... 还有 {len(result.errors) - 10} 条错误"
        if result.warnings:
            msg += "\n\n警告：\n" + "\n".join(result.warnings[:5])

        if result.success:
            messagebox.showinfo("导入成功", msg, parent=self.root)
        else:
            messagebox.showerror("导入失败", msg, parent=self.root)

    def _import_templates_csv(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入模板", parent=self.root)
            return

        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入模板CSV",
            initialdir=initial_dir,
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not filepath:
            return

        overwrite = messagebox.askyesno(
            "覆盖确认",
            "是否覆盖已存在的同名模板？\n\n是：覆盖已有模板\n否：跳过同名模板",
            parent=self.root
        )

        result = self.dm.import_templates_csv(
            filepath, overwrite=overwrite, user_role=self.dm.settings.current_role
        )

        self.dm.settings.import_dir = os.path.dirname(filepath)
        self.dm.save_settings()

        msg = f"导入完成！\n\n总计：{result.total_count} 条\n成功：{result.success_count} 条\n失败：{result.failed_count} 条"
        if result.errors:
            msg += "\n\n错误信息：\n" + "\n".join(result.errors[:10])
            if len(result.errors) > 10:
                msg += f"\n... 还有 {len(result.errors) - 10} 条错误"
        if result.warnings:
            msg += "\n\n警告：\n" + "\n".join(result.warnings[:5])

        if result.success:
            messagebox.showinfo("导入成功", msg, parent=self.root)
        else:
            messagebox.showerror("导入失败", msg, parent=self.root)

    def _export_templates_json(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出模板JSON",
            initialdir=initial_dir,
            initialfile=f"模板_{date.today().strftime('%Y%m%d')}.json",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not filepath:
            return

        success, msg = self.dm.export_templates_json(filepath)
        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"模板已导出到：\n{filepath}", parent=self.root)
            self._set_status(f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self.root)

    def _export_templates_csv(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出模板CSV",
            initialdir=initial_dir,
            initialfile=f"模板_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not filepath:
            return

        success, msg = self.dm.export_templates_csv(filepath)
        if success:
            self.dm.settings.export_dir = os.path.dirname(filepath)
            self.dm.save_settings()
            messagebox.showinfo("导出成功", f"模板已导出到：\n{filepath}", parent=self.root)
            self._set_status(f"导出成功：{filepath}")
        else:
            messagebox.showerror("导出失败", msg, parent=self.root)

    def _show_batch_create(self):
        dlg = BatchCreateDialog(self.root, self.dm)
        self.root.wait_window(dlg)
        if dlg.result_batch_id:
            self._set_status(f"批量创建完成，批次ID：{dlg.result_batch_id}")
            self._refresh_reservations()

    def _show_batch_management(self):
        dlg = BatchManagementDialog(self.root, self.dm)
        self.root.wait_window(dlg)
        self._refresh_reservations()

    def _show_sandbox(self):
        dlg = SandboxDialog(self.root, self.dm)
        self.root.wait_window(dlg)
        self._refresh_reservations()

    def _show_import_mapping_center(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可使用预约导入映射中心", parent=self.root)
            return
        dlg = ImportMappingCenterDialog(self.root, self.dm)
        self.root.wait_window(dlg)
        self._refresh_reservations()

    def _show_validation_workbench(self):
        dlg = ImportValidationWorkbenchDialog(self.root, self.dm)
        self.root.wait_window(dlg)
        self._refresh_reservations()

    def _show_operation_logs(self):
        dlg = OperationLogsDialog(self.root, self.dm)
        self.root.wait_window(dlg)

    def _on_reminder_toggle(self):
        self.dm.settings.reminder_enabled = self.reminder_enabled_var.get()
        self.dm.save_settings()
        status = "已启用" if self.dm.settings.reminder_enabled else "已关闭"
        self._set_status(f"提醒功能{status}")

    def _set_default_reminder(self):
        current = self.dm.settings.default_reminder_minutes
        result = simpledialog.askinteger(
            "设置默认提醒时长",
            "请输入默认提前提醒分钟数：",
            initialvalue=current,
            minvalue=0,
            maxvalue=240,
            parent=self.root,
        )
        if result is not None:
            self.dm.settings.default_reminder_minutes = result
            self.dm.save_settings()
            self._set_status(f"默认提醒时长已设为 {result} 分钟")

    def _set_status(self, text: str):
        self.status_label.config(text=text)

    def _show_about(self):
        messagebox.showinfo(
            "关于",
            "实验室仪器预约校准系统 v2.0\n\n"
            "核心功能：\n"
            "• 仪器档案管理\n"
            "• 预约流程管理（草稿→待确认→已预约→使用中→待复核→已完成/已取消）\n"
            "• 校准过期自动检测\n"
            "• 故障冻结与解除\n"
            "• 数据导出（CSV/JSON）\n\n"
            "新增功能（v2.0）：\n"
            "• 排期模板管理（支持7个字段定义）\n"
            "• 新建预约一键套用模板\n"
            "• 模板导入/导出（JSON/CSV）\n"
            "• 批量创建预约\n"
            "• 完整冲突检测（时间重叠、仪器冻结、校准过期、申请人撞单）\n"
            "• 管理员整批撤销\n"
            "• 模板快照（历史可追溯）\n"
            "• 操作日志与权限控制",
            parent=self.root
        )

    def _on_close(self):
        self.dm.save_settings()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = App()
    app.run()


class ImportMappingCenterDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("预约导入映射中心")
        self.geometry("1080x760")
        self.minsize(1000, 700)
        self.transient(parent)
        self.grab_set()

        self.file_path = ""
        self.file_headers: List[str] = []
        self.file_rows: List[Dict[str, Any]] = []
        self.current_scheme: Optional[ImportMappingScheme] = None
        self.column_mapping_vars: Dict[str, tk.StringVar] = {}
        self.precheck_result: Optional[PrecheckResult] = None

        self._build_ui()
        self._refresh_scheme_list()
        self._restore_session()

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab1 = ttk.Frame(nb, padding=10)
        self.tab2 = ttk.Frame(nb, padding=10)
        self.tab3 = ttk.Frame(nb, padding=10)
        nb.add(self.tab1, text="1. 选择文件 & 方案管理")
        nb.add(self.tab2, text="2. 列映射配置")
        nb.add(self.tab3, text="3. 预检 & 导入执行")
        self.nb = nb

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(bottom, text="※ 仅管理员可维护方案，所有操作均记入操作日志",
                  foreground="#666").pack(side="left")
        ttk.Button(bottom, text="关闭", command=self.destroy, width=12).pack(side="right")

    def _build_tab1(self):
        padding = {"padx": 8, "pady": 5}

        file_frame = ttk.LabelFrame(self.tab1, text="步骤1：选择导入文件（CSV / Excel）", padding=10)
        file_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(file_frame, text="文件路径：").grid(row=0, column=0, sticky="e", **padding)
        self.file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_var, width=70).grid(row=0, column=1, **padding)
        ttk.Button(file_frame, text="浏览...", command=self._select_file, width=10).grid(row=0, column=2, **padding)
        ttk.Button(file_frame, text="解析文件", command=self._parse_selected_file, width=10).grid(row=0, column=3, **padding)

        self.file_info_label = ttk.Label(file_frame, text="尚未选择文件", foreground="#888")
        self.file_info_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

        scheme_frame = ttk.LabelFrame(self.tab1, text="步骤2：选择 / 管理映射方案", padding=10)
        scheme_frame.pack(fill="both", expand=True, pady=(0, 10))

        top_row = ttk.Frame(scheme_frame)
        top_row.pack(fill="x", pady=(0, 8))

        ttk.Label(top_row, text="已有方案：").pack(side="left", padx=(0, 8))
        self.scheme_var = tk.StringVar()
        self.scheme_combo = ttk.Combobox(top_row, textvariable=self.scheme_var, state="readonly", width=40)
        self.scheme_combo.pack(side="left", padx=(0, 8))
        self.scheme_combo.bind("<<ComboboxSelected>>", self._on_scheme_select)

        ttk.Button(top_row, text="加载方案", command=self._load_selected_scheme, width=10).pack(side="left", padx=3)
        ttk.Button(top_row, text="自动匹配列", command=self._auto_match_columns, width=12).pack(side="left", padx=3)

        btn_sep = ttk.Frame(top_row)
        btn_sep.pack(side="left", padx=10)

        self.btn_save_scheme = ttk.Button(top_row, text="存为新方案", command=self._save_as_new_scheme, width=12)
        self.btn_save_scheme.pack(side="left", padx=3)
        self.btn_update_scheme = ttk.Button(top_row, text="更新当前方案", command=self._update_current_scheme, width=14)
        self.btn_update_scheme.pack(side="left", padx=3)
        self.btn_revoke_scheme = ttk.Button(top_row, text="撤销当前方案", command=self._revoke_current_scheme, width=14)
        self.btn_revoke_scheme.pack(side="left", padx=3)
        self.btn_delete_scheme = ttk.Button(top_row, text="删除方案", command=self._delete_selected_scheme, width=10)
        self.btn_delete_scheme.pack(side="left", padx=3)

        export_sep = ttk.Frame(scheme_frame)
        export_sep.pack(fill="x", pady=(0, 8))
        ttk.Button(export_sep, text="导出方案备份(JSON)", command=self._export_schemes, width=20).pack(side="left", padx=3)
        ttk.Button(export_sep, text="导入方案(JSON)", command=self._import_schemes, width=16).pack(side="left", padx=3)

        list_frame = ttk.LabelFrame(scheme_frame, text="方案列表（双击加载）", padding=8)
        list_frame.pack(fill="both", expand=True)

        cols = ("name", "created_by", "created_at", "updated_at", "is_revoked", "revoke_reason")
        self.scheme_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8)
        for c, t, w in [
            ("name", "方案名称", 180), ("created_by", "创建人", 90),
            ("created_at", "创建时间", 140), ("updated_at", "更新时间", 140),
            ("is_revoked", "状态", 70), ("revoke_reason", "撤销原因", 180),
        ]:
            self.scheme_tree.heading(c, text=t)
            self.scheme_tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.scheme_tree.yview)
        self.scheme_tree.configure(yscrollcommand=vsb.set)
        self.scheme_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.scheme_tree.bind("<Double-1>", lambda e: self._load_selected_scheme())

        tip = ttk.Label(self.tab1,
                        text="使用流程：选择文件 → 解析表头 → 选择或创建映射方案 → 切到Tab2对列 → 切到Tab3预检 → 全部通过后生成草稿/沙盘",
                        foreground="#1565c0", font=("Arial", 10, "bold"))
        tip.pack(fill="x", pady=(0, 8))

    def _build_tab2(self):
        padding = {"padx": 8, "pady": 5}

        top = ttk.Frame(self.tab2)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="※ 从下拉列表中为每个「标准字段」选择文件中对应的原始列名（必填项标★）",
                  foreground="#666").pack(side="left")

        fmt_frame = ttk.LabelFrame(self.tab2, text="日期 / 时间格式（默认ISO格式，如不一致请修改）", padding=10)
        fmt_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(fmt_frame, text="完整日期时间格式：").grid(row=0, column=0, sticky="e", **padding)
        self.dt_fmt_var = tk.StringVar(value="%Y-%m-%d %H:%M:%S")
        ttk.Entry(fmt_frame, textvariable=self.dt_fmt_var, width=25).grid(row=0, column=1, sticky="w", **padding)
        ttk.Label(fmt_frame, text="例：%Y-%m-%d %H:%M:%S", foreground="gray").grid(row=0, column=2, sticky="w", **padding)

        ttk.Label(fmt_frame, text="仅日期格式：").grid(row=1, column=0, sticky="e", **padding)
        self.d_fmt_var = tk.StringVar(value="%Y-%m-%d")
        ttk.Entry(fmt_frame, textvariable=self.d_fmt_var, width=25).grid(row=1, column=1, sticky="w", **padding)
        ttk.Label(fmt_frame, text="例：%Y-%m-%d", foreground="gray").grid(row=1, column=2, sticky="w", **padding)

        ttk.Label(fmt_frame, text="仅时间格式：").grid(row=2, column=0, sticky="e", **padding)
        self.t_fmt_var = tk.StringVar(value="%H:%M:%S")
        ttk.Entry(fmt_frame, textvariable=self.t_fmt_var, width=25).grid(row=2, column=1, sticky="w", **padding)
        ttk.Label(fmt_frame, text="例：%H:%M:%S", foreground="gray").grid(row=2, column=2, sticky="w", **padding)

        map_frame = ttk.LabelFrame(self.tab2, text="列映射配置", padding=10)
        map_frame.pack(fill="both", expand=True, pady=(0, 10))

        header_cols = ("std_field", "std_desc", "required", "raw_col")
        self.map_tree = ttk.Treeview(map_frame, columns=header_cols, show="headings", height=10)
        self.map_tree.heading("std_field", text="标准字段(Key)")
        self.map_tree.heading("std_desc", text="标准字段(说明)")
        self.map_tree.heading("required", text="必填")
        self.map_tree.heading("raw_col", text="当前对应原始列 → 点击编辑")
        self.map_tree.column("std_field", width=150, anchor="w")
        self.map_tree.column("std_desc", width=150, anchor="w")
        self.map_tree.column("required", width=50, anchor="center")
        self.map_tree.column("raw_col", width=500, anchor="w")
        self.map_tree.pack(fill="both", expand=True)
        self.map_tree.bind("<Double-1>", self._on_map_tree_double_click)

        tip2 = ttk.Label(self.tab2,
                         text="※ 「日期」列可选：如文件中开始/结束时间已经是完整日期时间，可不填日期列\n※ 双击表格最后一行可弹出下拉选择原始列",
                         foreground="#666")
        tip2.pack(fill="x")

    def _build_tab3(self):
        padding = {"padx": 8, "pady": 5}

        action_frame = ttk.LabelFrame(self.tab3, text="预检操作", padding=10)
        action_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(action_frame, text="▶ 运行预检", command=self._run_precheck, width=14).grid(row=0, column=0, **padding)
        ttk.Button(action_frame, text="导出失败行(CSV)", command=self._export_failed_rows, width=16).grid(row=0, column=1, **padding)
        ttk.Label(action_frame, text="→ 只有全部通过预检，才能生成草稿或送入沙盘", foreground="#c62828").grid(row=0, column=2, sticky="w", **padding)

        self.precheck_summary = ttk.Label(action_frame, text="尚未运行预检", foreground="#888", font=("Arial", 10, "bold"))
        self.precheck_summary.grid(row=1, column=0, columnspan=3, sticky="w", padx=8)

        issue_frame = ttk.LabelFrame(self.tab3, text="预检问题明细（逐条列出）", padding=10)
        issue_frame.pack(fill="both", expand=True, pady=(0, 10))

        issue_cols = ("row", "type", "col", "detail")
        self.issue_tree = ttk.Treeview(issue_frame, columns=issue_cols, show="headings", height=10)
        self.issue_tree.heading("row", text="行号")
        self.issue_tree.heading("type", text="问题类型")
        self.issue_tree.heading("col", text="关联列")
        self.issue_tree.heading("detail", text="详细说明")
        self.issue_tree.column("row", width=60, anchor="center")
        self.issue_tree.column("type", width=90, anchor="w")
        self.issue_tree.column("col", width=100, anchor="w")
        self.issue_tree.column("detail", width=700, anchor="w")
        vsb2 = ttk.Scrollbar(issue_frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=vsb2.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

        self.issue_tree.tag_configure("缺列", background="#ffebee")
        self.issue_tree.tag_configure("空值", background="#fff3e0")
        self.issue_tree.tag_configure("时间格式错", background="#fffde7")
        self.issue_tree.tag_configure("时间逻辑错", background="#fce4ec")
        self.issue_tree.tag_configure("仪器不存在", background="#f3e5f5")
        self.issue_tree.tag_configure("重复行", background="#e8f5e9")

        exec_frame = ttk.LabelFrame(self.tab3, text="导入执行（必须预检0失败）", padding=10)
        exec_frame.pack(fill="x")

        ttk.Label(exec_frame, text="目标位置：").grid(row=0, column=0, sticky="e", **padding)
        self.target_var = tk.StringVar(value="草稿")
        ttk.Radiobutton(exec_frame, text="直接生成草稿预约（DRAFT状态）", variable=self.target_var, value="草稿").grid(row=0, column=1, sticky="w", **padding)
        ttk.Radiobutton(exec_frame, text="先送入沙盘（需后续确认提交）", variable=self.target_var, value="沙盘").grid(row=0, column=2, sticky="w", **padding)

        ttk.Label(exec_frame, text="草稿/沙盘名称：").grid(row=1, column=0, sticky="e", **padding)
        self.name_var = tk.StringVar(value=f"导入_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        ttk.Entry(exec_frame, textvariable=self.name_var, width=40).grid(row=1, column=1, columnspan=2, sticky="w", **padding)

        self.btn_execute = ttk.Button(exec_frame, text="▶ 执行导入", command=self._execute_import, width=14, state="disabled")
        self.btn_execute.grid(row=0, column=3, rowspan=2, padx=20)

    # ==================== Tab1 Actions ====================
    def _select_file(self):
        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="选择预约明细文件",
            initialdir=initial_dir,
            filetypes=[("支持的文件", "*.csv *.xlsx *.xls"), ("CSV 文件", "*.csv"), ("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
            parent=self,
        )
        if filepath:
            self.file_var.set(filepath)
            self.file_path = filepath
            self.dm.settings.import_dir = os.path.dirname(filepath)
            self.dm.save_settings()

    def _parse_selected_file(self):
        filepath = self.file_var.get().strip()
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("错误", "请先选择有效的文件", parent=self)
            return
        self.file_path = filepath
        headers, rows, err = self.dm.parse_import_file(filepath)
        if err:
            messagebox.showerror("解析失败", err, parent=self)
            return
        self.file_headers = headers or []
        self.file_rows = rows or []
        info = f"✅ 文件解析成功：{len(self.file_rows)} 条数据，{len(self.file_headers)} 列\n列名：{', '.join(self.file_headers[:10])}"
        if len(self.file_headers) > 10:
            info += f"...（共{len(self.file_headers)}列）"
        self.file_info_label.config(text=info, foreground="#2e7d32")

        self._refresh_map_tree()
        matched = self.dm.auto_match_columns(self.file_headers)
        if matched:
            if messagebox.askyesno("自动匹配", f"检测到文件列名，已自动匹配{len(matched)}个标准字段，是否应用？", parent=self):
                for std_key, raw_col in matched.items():
                    if std_key in self.column_mapping_vars:
                        self.column_mapping_vars[std_key].set(raw_col)
                self._refresh_map_tree_from_vars()

    def _refresh_scheme_list(self):
        schemes = self.dm.list_mapping_schemes(include_revoked=True)
        self._all_schemes = schemes
        active = [s for s in schemes if not s.is_revoked]
        display = [f"{s.name}（{s.updated_at[:16]}）" for s in active]
        self.scheme_combo["values"] = display
        self._active_schemes = active

        for item in self.scheme_tree.get_children():
            self.scheme_tree.delete(item)
        for s in schemes:
            status = "已撤销" if s.is_revoked else "有效"
            self.scheme_tree.insert(
                "", "end", iid=s.id,
                values=(s.name, s.created_by, s.created_at[:19], s.updated_at[:19],
                        status, s.revoke_reason or ""),
                tags=("revoked",) if s.is_revoked else (),
            )
        self.scheme_tree.tag_configure("revoked", foreground="#9e9e9e")

    def _on_scheme_select(self, _=None):
        pass

    def _load_selected_scheme(self):
        idx = self.scheme_combo.current()
        if idx < 0:
            sel = self.scheme_tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先从下拉框或列表中选择方案", parent=self)
                return
            scheme = self.dm.get_mapping_scheme(sel[0])
        else:
            scheme = self._active_schemes[idx] if idx < len(self._active_schemes) else None
        if not scheme:
            messagebox.showerror("错误", "方案不存在", parent=self)
            return
        if scheme.is_revoked:
            messagebox.showwarning("提示", "该方案已被撤销，不能使用", parent=self)
            return
        self.current_scheme = scheme
        self.scheme_combo.current(idx if idx >= 0 else 0)
        self.dt_fmt_var.set(scheme.datetime_format)
        self.d_fmt_var.set(scheme.date_format)
        self.t_fmt_var.set(scheme.time_format)
        for std_key, var in self.column_mapping_vars.items():
            raw_col = scheme.column_mapping.get(std_key, "")
            var.set(raw_col)
        self._refresh_map_tree_from_vars()
        self.dm.set_last_mapping_scheme(scheme.id)

    def _auto_match_columns(self):
        if not self.file_headers:
            messagebox.showwarning("提示", "请先解析文件获得列名", parent=self)
            return
        matched = self.dm.auto_match_columns(self.file_headers)
        if not matched:
            messagebox.showinfo("提示", "未能自动识别任何列，请手动匹配", parent=self)
            return
        for std_key, raw_col in matched.items():
            if std_key in self.column_mapping_vars:
                self.column_mapping_vars[std_key].set(raw_col)
        self._refresh_map_tree_from_vars()
        messagebox.showinfo("自动匹配", f"成功匹配 {len(matched)} 个字段", parent=self)

    def _collect_mapping_from_ui(self) -> Dict[str, str]:
        mapping = {}
        for std_key, var in self.column_mapping_vars.items():
            val = var.get().strip()
            if val:
                mapping[std_key] = val
        return mapping

    def _save_as_new_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可创建方案", parent=self)
            return
        name = simpledialog.askstring("新建映射方案", "请输入方案名称：", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        mapping = self._collect_mapping_from_ui()
        scheme, msg = self.dm.create_mapping_scheme(
            name=name,
            column_mapping=mapping,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            datetime_format=self.dt_fmt_var.get().strip() or "%Y-%m-%d %H:%M:%S",
            date_format=self.d_fmt_var.get().strip() or "%Y-%m-%d",
            time_format=self.t_fmt_var.get().strip() or "%H:%M:%S",
        )
        if not scheme:
            messagebox.showerror("创建失败", msg, parent=self)
            return
        self.current_scheme = scheme
        self._refresh_scheme_list()
        messagebox.showinfo("成功", f"方案「{name}」已创建", parent=self)

    def _update_current_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可更新方案", parent=self)
            return
        if not self.current_scheme:
            messagebox.showwarning("提示", "请先加载一个方案", parent=self)
            return
        mapping = self._collect_mapping_from_ui()
        scheme, msg = self.dm.update_mapping_scheme(
            scheme_id=self.current_scheme.id,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            column_mapping=mapping,
            datetime_format=self.dt_fmt_var.get().strip() or "%Y-%m-%d %H:%M:%S",
            date_format=self.d_fmt_var.get().strip() or "%Y-%m-%d",
            time_format=self.t_fmt_var.get().strip() or "%H:%M:%S",
        )
        if not scheme:
            messagebox.showerror("更新失败", msg, parent=self)
            return
        self.current_scheme = scheme
        self._refresh_scheme_list()
        messagebox.showinfo("成功", f"方案「{scheme.name}」已更新", parent=self)

    def _revoke_current_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可撤销方案", parent=self)
            return
        if not self.current_scheme:
            sel = self.scheme_tree.selection()
            if not sel:
                messagebox.showwarning("提示", "请先选择或加载一个方案", parent=self)
                return
            target_id = sel[0]
        else:
            target_id = self.current_scheme.id
        reason = simpledialog.askstring("撤销方案", "请输入撤销原因：", parent=self)
        if not reason or not reason.strip():
            return
        scheme, msg = self.dm.revoke_mapping_scheme(
            scheme_id=target_id,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            reason=reason.strip(),
        )
        if not scheme:
            messagebox.showerror("撤销失败", msg, parent=self)
            return
        self.current_scheme = None
        self._refresh_scheme_list()
        messagebox.showinfo("成功", f"方案已撤销：{reason.strip()}", parent=self)

    def _delete_selected_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可删除方案", parent=self)
            return
        sel = self.scheme_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请在列表中选择要删除的方案", parent=self)
            return
        sid = sel[0]
        sch = self.dm.get_mapping_scheme(sid)
        if not sch:
            return
        if not messagebox.askyesno("确认删除", f"确定要删除方案「{sch.name}」吗？（不可恢复）", parent=self):
            return
        ok, msg = self.dm.delete_mapping_scheme(sid, self.dm.settings.current_user, self.dm.settings.current_role)
        if not ok:
            messagebox.showerror("删除失败", msg, parent=self)
            return
        self.current_scheme = None
        self._refresh_scheme_list()
        messagebox.showinfo("成功", "方案已删除", parent=self)

    def _export_schemes(self):
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出映射方案备份",
            initialdir=initial_dir,
            initialfile=f"映射方案备份_{date.today().strftime('%Y%m%d')}.json",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_mapping_schemes(filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"方案已导出到：\n{filepath}", parent=self)

    def _import_schemes(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入方案", parent=self)
            return
        initial_dir = self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="导入映射方案",
            initialdir=initial_dir,
            filetypes=[("JSON 文件", "*.json")],
            parent=self,
        )
        if not filepath:
            return
        overwrite = messagebox.askyesno(
            "覆盖确认",
            "遇到同名方案是否覆盖？\n选'是'覆盖，选'否'跳过重名",
            parent=self,
        )
        imported, errors = self.dm.import_mapping_schemes(
            filepath, self.dm.settings.current_user, self.dm.settings.current_role, overwrite=overwrite
        )
        msg = f"导入完成：成功 {imported} 个"
        if errors:
            msg += f"\n\n提示：\n" + "\n".join(errors[:5])
        messagebox.showinfo("导入结果", msg, parent=self)
        self._refresh_scheme_list()

    # ==================== Tab2 Actions ====================
    def _refresh_map_tree(self):
        for item in self.map_tree.get_children():
            self.map_tree.delete(item)
        self.column_mapping_vars.clear()
        required_keys = {"instrument_code", "applicant", "start_time", "end_time", "purpose"}
        for std_key, std_desc in STANDARD_COLUMNS:
            req = "★" if std_key in required_keys else "○"
            var = tk.StringVar()
            self.column_mapping_vars[std_key] = var
            self.map_tree.insert(
                "", "end", iid=std_key,
                values=(std_key, std_desc, req, "（双击右侧选择对应原始列）"),
            )

    def _refresh_map_tree_from_vars(self):
        for std_key, std_desc in STANDARD_COLUMNS:
            var = self.column_mapping_vars.get(std_key)
            if var:
                raw = var.get() or "（双击右侧选择对应原始列）"
                self.map_tree.item(std_key, values=(
                    std_key, std_desc,
                    "★" if std_key in {"instrument_code", "applicant", "start_time", "end_time", "purpose"} else "○",
                    raw,
                ))

    def _on_map_tree_double_click(self, event):
        region = self.map_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col_id = self.map_tree.identify_column(event.x)
        item_id = self.map_tree.identify_row(event.y)
        if not item_id:
            return
        if col_id != "#4":
            return
        if not self.file_headers:
            messagebox.showinfo("提示", "请先在Tab1解析文件，获得列名后再映射", parent=self)
            return
        var = self.column_mapping_vars.get(item_id)
        if not var:
            return

        top = tk.Toplevel(self)
        top.title(f"选择列 - {item_id}")
        top.geometry("380x420")
        top.transient(self)
        top.grab_set()

        ttk.Label(top, text=f"为「{item_id}」选择对应原始列：", padding=10).pack(fill="x")

        listbox = tk.Listbox(top, height=15)
        listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        options = ["（不使用/不映射）"] + list(self.file_headers)
        for o in options:
            listbox.insert("end", o)
        current = var.get()
        if current and current in self.file_headers:
            listbox.selection_set(self.file_headers.index(current) + 1)
        else:
            listbox.selection_set(0)

        def _ok():
            sel = listbox.curselection()
            if sel:
                idx = sel[0]
                if idx == 0:
                    var.set("")
                else:
                    var.set(options[idx])
                self._refresh_map_tree_from_vars()
            top.destroy()

        ttk.Button(top, text="确定", command=_ok, width=10).pack(pady=(0, 10))

    # ==================== Tab3 Actions ====================
    def _run_precheck(self):
        if not self.file_path or not os.path.exists(self.file_path):
            messagebox.showerror("错误", "请先选择并解析文件", parent=self)
            return
        mapping = self._collect_mapping_from_ui()
        required = {"instrument_code", "applicant", "start_time", "end_time", "purpose"}
        missing = [k for k in required if k not in mapping]
        if missing:
            miss_str = ", ".join([dict(STANDARD_COLUMNS)[k] for k in missing])
            messagebox.showerror("映射不完整", f"必填列尚未映射：{miss_str}", parent=self)
            return
        scheme = ImportMappingScheme(
            id="_temp_precheck_",
            name="_临时方案_",
            created_by=self.dm.settings.current_user,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            column_mapping=mapping,
            datetime_format=self.dt_fmt_var.get().strip() or "%Y-%m-%d %H:%M:%S",
            date_format=self.d_fmt_var.get().strip() or "%Y-%m-%d",
            time_format=self.t_fmt_var.get().strip() or "%H:%M:%S",
        )
        result, err = self.dm.run_import_precheck(self.file_path, scheme)
        if err:
            messagebox.showerror("预检失败", err, parent=self)
            return
        self.precheck_result = result
        self._display_precheck_result(result)

    def _display_precheck_result(self, result: PrecheckResult):
        for item in self.issue_tree.get_children():
            self.issue_tree.delete(item)

        for issue in result.issues:
            tag = issue.issue_type
            self.issue_tree.insert(
                "", "end",
                values=(issue.row_number, issue.issue_type, issue.column_name, issue.detail),
                tags=(tag,),
            )

        summary = (f"总计 {result.total_rows} 行 | ✅ 通过 {result.pass_rows} 行 | "
                   f"❌ 失败 {result.fail_rows} 行 | ⚠ 问题 {len(result.issues)} 条 | 来源文件：{result.source_file}")
        if result.fail_rows == 0:
            self.precheck_summary.config(text=summary + " 【可以导入】", foreground="#2e7d32")
            self.btn_execute.config(state="normal")
        else:
            self.precheck_summary.config(text=summary + " 【存在失败，不可导入】", foreground="#c62828")
            self.btn_execute.config(state="disabled")

    def _export_failed_rows(self):
        if not self.precheck_result:
            messagebox.showwarning("提示", "请先运行预检", parent=self)
            return
        if not self.precheck_result.issues:
            messagebox.showinfo("提示", "没有失败的行可导出", parent=self)
            return
        initial_dir = self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出预检失败行",
            initialdir=initial_dir,
            initialfile=f"预检失败行_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_precheck_failed_rows(self.precheck_result, filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"失败行已导出到：\n{filepath}", parent=self)

    def _execute_import(self):
        if not self.precheck_result:
            messagebox.showerror("错误", "请先运行预检", parent=self)
            return
        if self.precheck_result.fail_rows > 0:
            messagebox.showerror("错误", "存在未通过的行，无法执行导入", parent=self)
            return

        target = self.target_var.get()
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "请输入草稿/沙盘名称", parent=self)
            return

        if target == "草稿":
            count, ids, errors = self.dm.execute_import_to_drafts(
                self.precheck_result, self.dm.settings.current_user, self.dm.settings.current_role
            )
            msg = f"导入完成！\n\n成功创建草稿：{count} 条"
            if errors:
                msg += f"\n失败：{len(errors)} 条\n\n详情：\n" + "\n".join(errors[:10])
            if count > 0:
                messagebox.showinfo("导入成功", msg, parent=self)
            else:
                messagebox.showwarning("导入无结果", msg, parent=self)
        else:
            draft, errors = self.dm.execute_import_to_sandbox(
                self.precheck_result, name, self.dm.settings.current_user, self.dm.settings.current_role
            )
            if not draft:
                messagebox.showerror("导入失败", "\n".join(errors) if errors else "未知错误", parent=self)
                return
            messagebox.showinfo(
                "已送入沙盘",
                f"成功创建沙盘草稿「{name}」：{len(draft.items)} 条记录\n\n请在【预约沙盘】中进一步确认和提交",
                parent=self,
            )
        self.destroy()

    # ==================== Session Restore ====================
    def _restore_session(self):
        last_file = self.dm.get_last_mapping_file()
        if last_file and os.path.exists(last_file):
            self.file_var.set(last_file)
            self.file_path = last_file
            self.file_info_label.config(text=f"上次会话恢复：{os.path.basename(last_file)}（请点击'解析文件'）", foreground="#1565c0")

        last_scheme = self.dm.get_last_mapping_scheme()
        if last_scheme:
            self.dt_fmt_var.set(last_scheme.datetime_format)
            self.d_fmt_var.set(last_scheme.date_format)
            self.t_fmt_var.set(last_scheme.time_format)
            for i, s in enumerate(self._active_schemes if hasattr(self, "_active_schemes") else []):
                if s.id == last_scheme.id:
                    self.scheme_combo.current(i)
                    self.current_scheme = last_scheme
                    break

        last_precheck = self.dm.get_last_precheck_result()
        if last_precheck:
            self.precheck_result = last_precheck
            self._display_precheck_result(last_precheck)
            self.nb.select(self.tab2)
            self.nb.select(self.tab3)


class ImportValidationWorkbenchDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager):
        super().__init__(parent)
        self.dm = dm
        self.title("导入体检工作台")
        self.geometry("1180x820")
        self.minsize(1080, 720)
        self.transient(parent)
        self.grab_set()

        self.file_path = ""
        self.file_encoding_var = tk.StringVar(value="auto")
        self.current_mapping_scheme: Optional[ImportMappingScheme] = None
        self.current_validation_scheme: Optional[ImportValidationScheme] = None
        self.current_batch: Optional[ValidationBatch] = None
        self._all_mapping_schemes: List[ImportMappingScheme] = []
        self._active_mapping_schemes: List[ImportMappingScheme] = []
        self._all_validation_schemes: List[ImportValidationScheme] = []
        self._active_validation_schemes: List[ImportValidationScheme] = []
        self._rule_vars: Dict[str, tk.BooleanVar] = {}

        self._build_ui()
        self._refresh_mapping_scheme_list()
        self._refresh_validation_scheme_list()
        self._refresh_batch_list()
        self._restore_session()

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab1 = ttk.Frame(nb, padding=10)
        self.tab2 = ttk.Frame(nb, padding=10)
        self.tab3 = ttk.Frame(nb, padding=10)
        nb.add(self.tab1, text="1. 文件 & 方案")
        nb.add(self.tab2, text="2. 体检执行 & 去向")
        nb.add(self.tab3, text="3. 批次管理 & 快照")
        self.nb = nb

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(bottom, text="※ 管理员可维护体检方案、撤销批次、恢复快照；普通用户仅可见自己的批次",
                  foreground="#666").pack(side="left")
        ttk.Button(bottom, text="关闭", command=self.destroy, width=12).pack(side="right")

    def _build_tab1(self):
        padding = {"padx": 8, "pady": 5}

        file_frame = ttk.LabelFrame(self.tab1, text="步骤1：选择导入文件（支持 UTF-8 / GBK 编码切换）", padding=10)
        file_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(file_frame, text="文件路径：").grid(row=0, column=0, sticky="e", **padding)
        self.file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_var, width=65).grid(row=0, column=1, **padding)
        ttk.Button(file_frame, text="浏览...", command=self._select_file, width=10).grid(row=0, column=2, **padding)

        ttk.Label(file_frame, text="文件编码：").grid(row=1, column=0, sticky="e", **padding)
        self.encoding_combo = ttk.Combobox(
            file_frame, textvariable=self.file_encoding_var,
            values=["auto", "utf-8-sig", "utf-8", "gbk"],
            state="readonly", width=15
        )
        self.encoding_combo.grid(row=1, column=1, sticky="w", **padding)
        ttk.Label(file_frame, text="auto=自动探测（推荐 utf-8-sig → utf-8 → gbk 回退）",
                  foreground="#888").grid(row=1, column=2, sticky="w", **padding)

        self.file_info_label = ttk.Label(file_frame, text="尚未选择文件", foreground="#888")
        self.file_info_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=8)

        mapping_frame = ttk.LabelFrame(self.tab1, text="步骤2：选择列映射方案", padding=10)
        mapping_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(mapping_frame, text="映射方案：").pack(side="left", padx=(0, 8))
        self.mapping_scheme_var = tk.StringVar()
        self.mapping_scheme_combo = ttk.Combobox(
            mapping_frame, textvariable=self.mapping_scheme_var, state="readonly", width=45
        )
        self.mapping_scheme_combo.pack(side="left", padx=(0, 8))
        self.mapping_scheme_combo.bind("<<ComboboxSelected>>", self._on_mapping_scheme_select)

        validation_frame = ttk.LabelFrame(self.tab1, text="步骤3：选择 / 管理体检方案（8 类规则可开关）", padding=10)
        validation_frame.pack(fill="both", expand=True, pady=(0, 10))

        top_row = ttk.Frame(validation_frame)
        top_row.pack(fill="x", pady=(0, 8))

        ttk.Label(top_row, text="体检方案：").pack(side="left", padx=(0, 8))
        self.validation_scheme_var = tk.StringVar()
        self.validation_scheme_combo = ttk.Combobox(
            top_row, textvariable=self.validation_scheme_var, state="readonly", width=40
        )
        self.validation_scheme_combo.pack(side="left", padx=(0, 8))
        self.validation_scheme_combo.bind("<<ComboboxSelected>>", self._on_validation_scheme_select)

        ttk.Button(top_row, text="加载方案", command=self._load_selected_validation_scheme, width=10).pack(side="left", padx=3)
        self.btn_save_vscheme = ttk.Button(top_row, text="存为新方案", command=self._save_as_new_validation_scheme, width=12)
        self.btn_save_vscheme.pack(side="left", padx=3)
        self.btn_update_vscheme = ttk.Button(top_row, text="更新当前方案", command=self._update_current_validation_scheme, width=14)
        self.btn_update_vscheme.pack(side="left", padx=3)
        self.btn_delete_vscheme = ttk.Button(top_row, text="删除方案", command=self._delete_selected_validation_scheme, width=10)
        self.btn_delete_vscheme.pack(side="left", padx=3)

        rules_frame = ttk.LabelFrame(validation_frame, text="体检规则（勾选=启用）", padding=8)
        rules_frame.pack(fill="both", expand=True)

        self.rules_canvas = tk.Canvas(rules_frame, height=180)
        rules_scroll = ttk.Scrollbar(rules_frame, orient="vertical", command=self.rules_canvas.yview)
        self.rules_inner = ttk.Frame(self.rules_canvas)
        self.rules_inner.bind("<Configure>", lambda e: self.rules_canvas.configure(scrollregion=self.rules_canvas.bbox("all")))
        self.rules_canvas.create_window((0, 0), window=self.rules_inner, anchor="nw")
        self.rules_canvas.configure(yscrollcommand=rules_scroll.set)
        self.rules_canvas.pack(side="left", fill="both", expand=True)
        rules_scroll.pack(side="right", fill="y")

        for i, (rule_key, rule_desc, _) in enumerate(VALIDATION_RULE_DEFAULTS):
            var = tk.BooleanVar(value=True)
            self._rule_vars[rule_key] = var
            ttk.Checkbutton(self.rules_inner, text=f"{rule_key}  —  {rule_desc}", variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=10, pady=3
            )

        tip = ttk.Label(self.tab1,
                        text="使用流程：选择文件 → 选择编码 → 选择映射方案 → 选择/配置体检规则 → 切到Tab2运行体检",
                        foreground="#1565c0", font=("Arial", 10, "bold"))
        tip.pack(fill="x", pady=(0, 8))

    def _build_tab2(self):
        padding = {"padx": 8, "pady": 5}

        action_frame = ttk.LabelFrame(self.tab2, text="体检操作", padding=10)
        action_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(action_frame, text="▶ 运行体检", command=self._run_validation, width=14).grid(row=0, column=0, **padding)
        ttk.Button(action_frame, text="导出失败行", command=self._export_failed_rows, width=14).grid(row=0, column=1, **padding)
        ttk.Button(action_frame, text="导出通过行", command=self._export_passed_rows, width=14).grid(row=0, column=2, **padding)
        ttk.Label(action_frame, text="→ 体检完成后选择去向：送去映射中心 / 存草稿 / 退回",
                  foreground="#c62828").grid(row=0, column=3, sticky="w", **padding)

        self.validation_summary = ttk.Label(action_frame, text="尚未运行体检", foreground="#888", font=("Arial", 10, "bold"))
        self.validation_summary.grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

        issue_frame = ttk.LabelFrame(self.tab2, text="体检问题明细（逐条列出，不同类型用颜色区分）", padding=10)
        issue_frame.pack(fill="both", expand=True, pady=(0, 10))

        issue_cols = ("row", "type", "col", "detail")
        self.issue_tree = ttk.Treeview(issue_frame, columns=issue_cols, show="headings", height=12)
        for c, t, w in [
            ("row", "行号", 60), ("type", "问题类型", 110),
            ("col", "关联列", 110), ("detail", "详细说明", 800),
        ]:
            self.issue_tree.heading(c, text=t)
            self.issue_tree.column(c, width=w, anchor="w" if c != "row" else "center")
        vsb2 = ttk.Scrollbar(issue_frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=vsb2.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

        for tag, color in [
            ("缺少必填列", "#ffebee"), ("缺列", "#ffebee"),
            ("空值", "#fff3e0"), ("时间格式错", "#fffde7"),
            ("时间逻辑错", "#fce4ec"), ("重复行", "#e8f5e9"),
            ("仪器撞时段", "#f3e5f5"), ("申请人撞单", "#e3f2fd"),
            ("仪器不存在", "#ffe0b2"),
        ]:
            self.issue_tree.tag_configure(tag, background=color)

        disp_frame = ttk.LabelFrame(self.tab2, text="批次去向（体检完成后选择）", padding=10)
        disp_frame.pack(fill="x")

        self.disposition_var = tk.StringVar(value=BATCH_DISPOSITION_PENDING)
        ttk.Radiobutton(disp_frame, text=f"送去映射中心（后续完成列映射）",
                        variable=self.disposition_var, value=BATCH_DISPOSITION_MAPPING).grid(row=0, column=0, sticky="w", **padding)
        ttk.Radiobutton(disp_frame, text=f"存为草稿（直接生成 DRAFT 预约）",
                        variable=self.disposition_var, value=BATCH_DISPOSITION_DRAFT).grid(row=0, column=1, sticky="w", **padding)
        ttk.Radiobutton(disp_frame, text=f"退回（标记为退回，不做后续处理）",
                        variable=self.disposition_var, value=BATCH_DISPOSITION_REJECT).grid(row=0, column=2, sticky="w", **padding)

        self.btn_apply_disposition = ttk.Button(
            disp_frame, text="▶ 确认去向（仅处理通过项）",
            command=self._apply_disposition, width=24, state="disabled"
        )
        self.btn_apply_disposition.grid(row=0, column=3, padx=30)

    def _build_tab3(self):
        padding = {"padx": 8, "pady": 5}

        filter_frame = ttk.Frame(self.tab3)
        filter_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(filter_frame, text="操作人筛选：").pack(side="left", padx=(0, 5))
        self.operator_filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.operator_filter_var, width=20).pack(side="left", padx=(0, 8))
        ttk.Button(filter_frame, text="查询", command=self._refresh_batch_list, width=8).pack(side="left", padx=3)
        self.include_revoked_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_frame, text="包含已撤销", variable=self.include_revoked_var,
                        command=self._refresh_batch_list).pack(side="left", padx=10)

        batch_frame = ttk.LabelFrame(self.tab3, text="体检批次列表（普通用户仅见自己的批次）", padding=10)
        batch_frame.pack(fill="both", expand=True, pady=(0, 10))

        batch_cols = ("id", "created_at", "operator", "source_file", "encoding",
                      "total", "passed", "failed", "disposition", "is_revoked", "snapshot_id")
        self.batch_tree = ttk.Treeview(batch_frame, columns=batch_cols, show="headings", height=10)
        for c, t, w in [
            ("id", "批次ID", 80), ("created_at", "创建时间", 140), ("operator", "操作人", 80),
            ("source_file", "源文件", 220), ("encoding", "编码", 70),
            ("total", "总行", 50), ("passed", "通过", 50), ("failed", "失败", 50),
            ("disposition", "去向", 100), ("is_revoked", "状态", 60), ("snapshot_id", "快照ID", 80),
        ]:
            self.batch_tree.heading(c, text=t)
            self.batch_tree.column(c, width=w, anchor="w" if c not in ("total", "passed", "failed") else "center")
        vsb3 = ttk.Scrollbar(batch_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=vsb3.set)
        self.batch_tree.pack(side="left", fill="both", expand=True)
        vsb3.pack(side="right", fill="y")
        self.batch_tree.tag_configure("revoked", foreground="#9e9e9e")
        self.batch_tree.bind("<<TreeviewSelect>>", self._on_batch_select)

        action_row = ttk.Frame(self.tab3)
        action_row.pack(fill="x")

        ttk.Button(action_row, text="查看批次详情", command=self._view_batch_detail, width=14).pack(side="left", padx=3)
        ttk.Button(action_row, text="复跑该批次", command=self._rerun_selected_batch, width=14).pack(side="left", padx=3)
        ttk.Button(action_row, text="导出此批次失败行", command=self._export_selected_batch_failed, width=18).pack(side="left", padx=3)
        ttk.Button(action_row, text="导出此批次通过行", command=self._export_selected_batch_passed, width=18).pack(side="left", padx=3)

        sep = ttk.Frame(action_row)
        sep.pack(side="left", padx=15)

        self.btn_restore_snapshot = ttk.Button(
            action_row, text="恢复快照(管理员)", command=self._restore_selected_snapshot, width=18
        )
        self.btn_restore_snapshot.pack(side="left", padx=3)
        self.btn_revoke_batch = ttk.Button(
            action_row, text="撤销批次(管理员)", command=self._revoke_selected_batch, width=18
        )
        self.btn_revoke_batch.pack(side="left", padx=3)

    # ==================== Tab1 Actions ====================
    def _select_file(self):
        initial_dir = getattr(self.dm.settings, "last_import_file_dir", None) or self.dm.settings.import_dir or os.path.expanduser("~")
        filepath = filedialog.askopenfilename(
            title="选择预约明细文件",
            initialdir=initial_dir,
            filetypes=[("支持的文件", "*.csv *.xlsx *.xls"), ("CSV 文件", "*.csv"), ("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
            parent=self,
        )
        if filepath:
            self.file_var.set(filepath)
            self.file_path = filepath
            self.dm.settings.import_dir = os.path.dirname(filepath)
            setattr(self.dm.settings, "last_import_file_dir", os.path.dirname(filepath))
            self.dm.set_last_validation_file(filepath)
            self.dm.save_settings()

    def _refresh_mapping_scheme_list(self):
        schemes = self.dm.list_mapping_schemes(include_revoked=True)
        self._all_mapping_schemes = schemes
        active = [s for s in schemes if not s.is_revoked]
        self._active_mapping_schemes = active
        display = [f"{s.name}（{s.updated_at[:16]}）" for s in active]
        self.mapping_scheme_combo["values"] = display

    def _on_mapping_scheme_select(self, _=None):
        idx = self.mapping_scheme_combo.current()
        if 0 <= idx < len(self._active_mapping_schemes):
            self.current_mapping_scheme = self._active_mapping_schemes[idx]

    def _refresh_validation_scheme_list(self):
        schemes = self.dm.list_validation_schemes(include_revoked=True)
        self._all_validation_schemes = schemes
        active = [s for s in schemes if not s.is_revoked]
        self._active_validation_schemes = active
        display = [f"{s.name}（{s.updated_at[:16]}）" for s in active]
        self.validation_scheme_combo["values"] = display

    def _on_validation_scheme_select(self, _=None):
        pass

    def _load_selected_validation_scheme(self):
        idx = self.validation_scheme_combo.current()
        if idx < 0 or idx >= len(self._active_validation_schemes):
            messagebox.showinfo("提示", "请先从下拉框选择体检方案", parent=self)
            return
        scheme = self._active_validation_schemes[idx]
        self.current_validation_scheme = scheme
        for rule in scheme.rules:
            if rule.rule_key in self._rule_vars:
                self._rule_vars[rule.rule_key].set(rule.enabled)
        self.dm.set_last_validation_scheme(scheme.id)
        messagebox.showinfo("成功", f"已加载体检方案「{scheme.name}」", parent=self)

    def _collect_rules_from_ui(self) -> List[ImportValidationRule]:
        rules = []
        for rule_key, rule_desc, default_params in VALIDATION_RULE_DEFAULTS:
            enabled = self._rule_vars.get(rule_key, tk.BooleanVar(value=True)).get()
            rules.append(ImportValidationRule(
                rule_key=rule_key, description=rule_desc, enabled=enabled, params=dict(default_params)
            ))
        return rules

    def _save_as_new_validation_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可创建体检方案", parent=self)
            return
        name = simpledialog.askstring("新建体检方案", "请输入方案名称：", parent=self)
        if not name or not name.strip():
            return
        rules = self._collect_rules_from_ui()
        scheme, msg = self.dm.create_validation_scheme(
            name=name.strip(), rules=rules,
            operator=self.dm.settings.current_user, user_role=self.dm.settings.current_role,
        )
        if not scheme:
            messagebox.showerror("创建失败", msg, parent=self)
            return
        self.current_validation_scheme = scheme
        self._refresh_validation_scheme_list()
        messagebox.showinfo("成功", f"体检方案「{name.strip()}」已创建", parent=self)

    def _update_current_validation_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可修改体检方案", parent=self)
            return
        if not self.current_validation_scheme:
            messagebox.showwarning("提示", "请先加载一个体检方案", parent=self)
            return
        rules = self._collect_rules_from_ui()
        scheme, msg = self.dm.update_validation_scheme(
            scheme_id=self.current_validation_scheme.id,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            rules=rules,
        )
        if not scheme:
            messagebox.showerror("更新失败", msg, parent=self)
            return
        self.current_validation_scheme = scheme
        self._refresh_validation_scheme_list()
        messagebox.showinfo("成功", f"体检方案「{scheme.name}」已更新", parent=self)

    def _delete_selected_validation_scheme(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可删除体检方案", parent=self)
            return
        idx = self.validation_scheme_combo.current()
        if idx < 0 or idx >= len(self._active_validation_schemes):
            messagebox.showwarning("提示", "请先选择要删除的体检方案", parent=self)
            return
        scheme = self._active_validation_schemes[idx]
        if not messagebox.askyesno("确认删除", f"确定要删除体检方案「{scheme.name}」吗？（不可恢复）", parent=self):
            return
        ok, msg = self.dm.delete_validation_scheme(
            scheme.id, self.dm.settings.current_user, self.dm.settings.current_role
        )
        if not ok:
            messagebox.showerror("删除失败", msg, parent=self)
            return
        self.current_validation_scheme = None
        self._refresh_validation_scheme_list()
        messagebox.showinfo("成功", "方案已删除", parent=self)

    # ==================== Tab2 Actions ====================
    def _run_validation(self):
        filepath = self.file_var.get().strip()
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("错误", "请先选择有效的文件", parent=self)
            return
        self.file_path = filepath

        idx = self.mapping_scheme_combo.current()
        if idx < 0 or idx >= len(self._active_mapping_schemes):
            messagebox.showerror("错误", "请先选择列映射方案", parent=self)
            return
        mapping_scheme = self._active_mapping_schemes[idx]
        self.current_mapping_scheme = mapping_scheme

        encoding = self.file_encoding_var.get()
        setattr(self.dm.settings, "last_file_encoding", encoding)
        self.dm.save_settings()

        temp_rules = self._collect_rules_from_ui()
        temp_vscheme = ImportValidationScheme(
            id="_temp_", name="_临时_", created_by="", created_at="", updated_at="", rules=temp_rules,
        )

        batch, err = self.dm.run_validation_workbench(
            filepath=filepath, mapping_scheme=mapping_scheme,
            validation_scheme=temp_vscheme, file_encoding=encoding,
        )
        if not batch:
            messagebox.showerror("体检失败", err, parent=self)
            return

        self.current_batch = batch
        self._display_validation_result(batch)
        self.btn_apply_disposition.config(state="normal")
        self._refresh_batch_list()

    def _display_validation_result(self, batch: ValidationBatch):
        for item in self.issue_tree.get_children():
            self.issue_tree.delete(item)

        for issue in batch.issues:
            tag = issue.issue_type
            self.issue_tree.insert(
                "", "end",
                values=(issue.row_number, issue.issue_type, issue.column_name, issue.detail),
                tags=(tag,),
            )

        summary = (f"批次 {batch.id} | 总计 {batch.total_rows} 行 | "
                   f"通过 {batch.pass_rows} 行 | 失败 {batch.fail_rows} 行 | "
                   f"问题 {len(batch.issues)} 条 | 编码={batch.file_encoding} | "
                   f"来源：{os.path.basename(batch.source_file)}")
        self.validation_summary.config(text=summary, foreground="#2e7d32" if batch.fail_rows == 0 else "#c62828")

    def _export_failed_rows(self):
        if not self.current_batch:
            messagebox.showwarning("提示", "请先运行体检", parent=self)
            return
        initial_dir = getattr(self.dm.settings, "last_export_dir", None) or self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出体检失败行",
            initialdir=initial_dir,
            initialfile=f"体检失败行_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_validation_failed_rows(self.current_batch, filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        setattr(self.dm.settings, "last_export_dir", os.path.dirname(filepath))
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"失败行已导出到：\n{filepath}", parent=self)

    def _export_passed_rows(self):
        if not self.current_batch:
            messagebox.showwarning("提示", "请先运行体检", parent=self)
            return
        initial_dir = getattr(self.dm.settings, "last_export_dir", None) or self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title="导出体检通过行",
            initialdir=initial_dir,
            initialfile=f"体检通过行_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_validation_passed_rows(self.current_batch, filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        setattr(self.dm.settings, "last_export_dir", os.path.dirname(filepath))
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"通过行已导出到：\n{filepath}", parent=self)

    def _apply_disposition(self):
        if not self.current_batch:
            messagebox.showerror("错误", "请先运行体检", parent=self)
            return
        disposition = self.disposition_var.get()
        if disposition == BATCH_DISPOSITION_PENDING:
            messagebox.showwarning("提示", "请先选择批次去向", parent=self)
            return
        ok, msg = self.dm.set_batch_disposition(
            batch_id=self.current_batch.id, disposition=disposition,
            operator=self.dm.settings.current_user, user_role=self.dm.settings.current_role,
        )
        if not ok:
            messagebox.showerror("操作失败", msg, parent=self)
            return
        self._refresh_batch_list()
        res_info = ""
        updated_batch = self.dm.get_validation_batch(self.current_batch.id)
        if updated_batch and updated_batch.reservation_ids:
            res_info = f"\n已生成预约：{len(updated_batch.reservation_ids)} 条"
        messagebox.showinfo("成功", f"批次去向已设为「{disposition}」{res_info}", parent=self)

    # ==================== Tab3 Actions ====================
    def _refresh_batch_list(self):
        operator_filter = self.operator_filter_var.get().strip()
        include_revoked = self.include_revoked_var.get()
        batches = self.dm.list_validation_batches(
            operator_filter=operator_filter, include_revoked=include_revoked
        )
        for item in self.batch_tree.get_children():
            self.batch_tree.delete(item)
        for b in batches:
            status = "已撤销" if b.is_revoked else "有效"
            self.batch_tree.insert(
                "", "end", iid=b.id,
                values=(b.id[:8], b.created_at[:19], b.operator,
                        os.path.basename(b.source_file), b.file_encoding,
                        b.total_rows, b.pass_rows, b.fail_rows,
                        b.disposition, status, (b.snapshot_id or "")[:8]),
                tags=("revoked",) if b.is_revoked else (),
            )

    def _on_batch_select(self, _=None):
        pass

    def _get_selected_batch(self) -> Optional[ValidationBatch]:
        sel = self.batch_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选择一个批次", parent=self)
            return None
        return self.dm.get_validation_batch(sel[0])

    def _view_batch_detail(self):
        batch = self._get_selected_batch()
        if not batch:
            return
        self.current_batch = batch
        self._display_validation_result(batch)
        self.disposition_var.set(batch.disposition)
        self.btn_apply_disposition.config(state="normal" if not batch.is_revoked else "disabled")
        self.nb.select(self.tab2)

    def _rerun_selected_batch(self):
        batch = self._get_selected_batch()
        if not batch:
            return
        idx = self.mapping_scheme_combo.current()
        if idx < 0 or idx >= len(self._active_mapping_schemes):
            messagebox.showerror("错误", "请先在Tab1选择列映射方案", parent=self)
            return
        mapping_scheme = self._active_mapping_schemes[idx]
        encoding = self.file_encoding_var.get()
        new_batch, err = self.dm.rerun_validation_batch(
            batch_id=batch.id, operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
            mapping_scheme=mapping_scheme, file_encoding=encoding,
        )
        if not new_batch:
            messagebox.showerror("复跑失败", err, parent=self)
            return
        self.current_batch = new_batch
        self._display_validation_result(new_batch)
        self._refresh_batch_list()
        self.nb.select(self.tab2)
        messagebox.showinfo("成功", f"批次复跑完成，新批次ID：{new_batch.id[:8]}", parent=self)

    def _export_selected_batch_failed(self):
        batch = self._get_selected_batch()
        if not batch:
            return
        initial_dir = getattr(self.dm.settings, "last_export_dir", None) or self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title=f"导出批次 {batch.id[:8]} 失败行",
            initialdir=initial_dir,
            initialfile=f"批次{batch.id[:8]}_失败行_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_validation_failed_rows(batch, filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        setattr(self.dm.settings, "last_export_dir", os.path.dirname(filepath))
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"失败行已导出到：\n{filepath}", parent=self)

    def _export_selected_batch_passed(self):
        batch = self._get_selected_batch()
        if not batch:
            return
        initial_dir = getattr(self.dm.settings, "last_export_dir", None) or self.dm.settings.export_dir or os.path.expanduser("~")
        filepath = filedialog.asksaveasfilename(
            title=f"导出批次 {batch.id[:8]} 通过行",
            initialdir=initial_dir,
            initialfile=f"批次{batch.id[:8]}_通过行_{date.today().strftime('%Y%m%d')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            parent=self,
        )
        if not filepath:
            return
        ok, msg = self.dm.export_validation_passed_rows(batch, filepath)
        if not ok:
            messagebox.showerror("导出失败", msg, parent=self)
            return
        setattr(self.dm.settings, "last_export_dir", os.path.dirname(filepath))
        self.dm.settings.export_dir = os.path.dirname(filepath)
        self.dm.save_settings()
        messagebox.showinfo("成功", f"通过行已导出到：\n{filepath}", parent=self)

    def _restore_selected_snapshot(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可恢复快照", parent=self)
            return
        batch = self._get_selected_batch()
        if not batch or not batch.snapshot_id:
            messagebox.showwarning("提示", "所选批次没有关联快照", parent=self)
            return
        if not messagebox.askyesno("确认恢复", f"确定要恢复批次 {batch.id[:8]} 的快照吗？\n这将基于快照重新创建体检批次。", parent=self):
            return
        new_batch, err = self.dm.restore_validation_snapshot(
            snapshot_id=batch.snapshot_id, operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role,
        )
        if not new_batch:
            messagebox.showerror("恢复失败", err, parent=self)
            return
        self.current_batch = new_batch
        self._display_validation_result(new_batch)
        self._refresh_batch_list()
        self.nb.select(self.tab2)
        messagebox.showinfo("成功", f"快照已恢复，新批次ID：{new_batch.id[:8]}", parent=self)

    def _revoke_selected_batch(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可撤销批次", parent=self)
            return
        batch = self._get_selected_batch()
        if not batch:
            return
        if batch.is_revoked:
            messagebox.showwarning("提示", "该批次已被撤销", parent=self)
            return
        reason = simpledialog.askstring("撤销批次", "请输入撤销原因：", parent=self)
        if not reason or not reason.strip():
            return
        ok, msg = self.dm.revoke_validation_batch(
            batch_id=batch.id, operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role, reason=reason.strip(),
        )
        if not ok:
            messagebox.showerror("撤销失败", msg, parent=self)
            return
        self._refresh_batch_list()
        res_count = len(batch.reservation_ids) if hasattr(batch, 'reservation_ids') else 0
        messagebox.showinfo("成功", f"批次已撤销：{reason.strip()}\n已清理预约：{res_count} 条", parent=self)

    # ==================== Session Restore ====================
    def _restore_session(self):
        last_file = getattr(self.dm.settings, "last_validation_file", None)
        if not last_file:
            last_file = self.dm.get_last_validation_file() if hasattr(self.dm, "get_last_validation_file") else None
        if last_file and os.path.exists(last_file):
            self.file_var.set(last_file)
            self.file_path = last_file
            self.file_info_label.config(
                text=f"上次会话恢复：{os.path.basename(last_file)}（编码：{getattr(self.dm.settings, 'last_file_encoding', 'auto')}）",
                foreground="#1565c0"
            )

        last_encoding = getattr(self.dm.settings, "last_file_encoding", "auto")
        if last_encoding:
            self.file_encoding_var.set(last_encoding)

        last_scheme = self.dm.get_last_validation_scheme() if hasattr(self.dm, "get_last_validation_scheme") else None
        if last_scheme:
            for i, s in enumerate(self._active_validation_schemes):
                if s.id == last_scheme.id:
                    self.validation_scheme_combo.current(i)
                    self.current_validation_scheme = last_scheme
                    for rule in last_scheme.rules:
                        if rule.rule_key in self._rule_vars:
                            self._rule_vars[rule.rule_key].set(rule.enabled)
                    break

        last_mapping = self.dm.get_last_mapping_scheme() if hasattr(self.dm, "get_last_mapping_scheme") else None
        if last_mapping:
            for i, s in enumerate(self._active_mapping_schemes):
                if s.id == last_mapping.id:
                    self.mapping_scheme_combo.current(i)
                    self.current_mapping_scheme = last_mapping
                    break


if __name__ == "__main__":
    main()
