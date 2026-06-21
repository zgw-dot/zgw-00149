import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
from datetime import datetime, date, timedelta

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, STATUS_FLOW, OperationType, ReservationTemplate,
    ImportResult, BatchRecord, TemplateSnapshot
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

        filepath = filedialog.askopenfilename(
            title="导入模板JSON",
            filetypes=[("JSON 文件", "*.json")],
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
        self._show_import_result(result)
        self._refresh()

    def _import_csv(self):
        if self.dm.settings.current_role != UserRole.ADMIN:
            messagebox.showerror("权限不足", "仅管理员可导入模板", parent=self)
            return

        filepath = filedialog.askopenfilename(
            title="导入模板CSV",
            filetypes=[("CSV 文件", "*.csv")],
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

        if self.conflicts:
            if not messagebox.askyesno(
                "确认创建",
                f"检测到 {len(self.conflicts)} 个冲突，是否仍要创建？\n（有冲突的预约将自动跳过）",
                parent=self
            ):
                return

        record, fails = self.dm.batch_create_reservations(
            self.batch_items,
            operator=self.dm.settings.current_user,
            user_role=self.dm.settings.current_role
        )

        self.result_batch_id = record.id

        if fails:
            msg = f"批量创建完成！\n\n成功：{record.success_count} 个\n失败：{record.failed_count} 个\n\n失败详情：\n" + "\n".join(fails[:10])
            if len(fails) > 10:
                msg += f"\n... 还有 {len(fails) - 10} 条失败记录"
            messagebox.showwarning("部分失败", msg, parent=self)
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
        self.geometry("900x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_records()

    def _build_ui(self):
        padding = {"padx": 8, "pady": 5}

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        filter_frame = ttk.LabelFrame(frm, text="筛选", padding=10)
        filter_frame.pack(fill="x", pady=(0, 10))

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

        columns = ("operation", "operator", "total", "success", "failed",
                   "created_at", "is_cancelled", "cancel_operator", "cancel_time")
        self.record_tree = ttk.Treeview(frm, columns=columns, show="headings", height=15)
        self.record_tree.heading("operation", text="操作类型")
        self.record_tree.heading("operator", text="操作人")
        self.record_tree.heading("total", text="总数")
        self.record_tree.heading("success", text="成功")
        self.record_tree.heading("failed", text="失败")
        self.record_tree.heading("created_at", text="创建时间")
        self.record_tree.heading("is_cancelled", text="状态")
        self.record_tree.heading("cancel_operator", text="撤销人")
        self.record_tree.heading("cancel_time", text="撤销时间")

        self.record_tree.column("operation", width=80, anchor="w")
        self.record_tree.column("operator", width=80, anchor="w")
        self.record_tree.column("total", width=50, anchor="center")
        self.record_tree.column("success", width=50, anchor="center")
        self.record_tree.column("failed", width=50, anchor="center")
        self.record_tree.column("created_at", width=130, anchor="w")
        self.record_tree.column("is_cancelled", width=70, anchor="center")
        self.record_tree.column("cancel_operator", width=80, anchor="w")
        self.record_tree.column("cancel_time", width=130, anchor="w")

        self.record_tree.pack(fill="both", expand=True, pady=(0, 10))
        self.record_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.record_tree.bind("<Double-1>", lambda e: self._show_details())

        scrollbar = ttk.Scrollbar(frm, orient="vertical", command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=scrollbar.set)

        detail_frame = ttk.LabelFrame(frm, text="详情", padding=10)
        detail_frame.pack(fill="x", pady=(0, 10))

        self.detail_text = tk.Text(detail_frame, height=4, width=80)
        self.detail_text.pack(fill="x")
        self.detail_text.configure(state="disabled")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="查看详情", command=self._show_details, width=12).pack(side="left", padx=3)
        self.btn_cancel = ttk.Button(
            btn_frame, text="整批撤销", command=self._cancel_batch, width=12,
            state="disabled"
        )
        self.btn_cancel.pack(side="left", padx=3)

        if self.dm.settings.current_role != UserRole.ADMIN:
            self.btn_cancel.config(text="（需管理员）", state="disabled")

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
            tag = "cancelled" if r.is_cancelled else ""

            self.record_tree.insert(
                "", "end", iid=r.id,
                values=(r.operation, r.operator, r.total_count,
                        r.success_count, r.failed_count, r.created_at,
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
                detail += f"操作人角色: {record.operator_role}\n"
                if record.details:
                    detail += f"详细信息:\n{record.details}"
                if record.cancel_reason:
                    detail += f"\n撤销原因: {record.cancel_reason}"
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

    def _show_details(self):
        selected = self.record_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条记录", parent=self)
            return

        batch_id = selected[0]
        record = self.dm.get_batch_record(batch_id)
        if not record:
            return

        detail = f"批次ID: {record.id}\n"
        detail += f"操作类型: {record.operation}\n"
        detail += f"操作人: {record.operator} ({record.operator_role})\n"
        detail += f"创建时间: {record.created_at}\n"
        detail += f"总数: {record.total_count}, 成功: {record.success_count}, 失败: {record.failed_count}\n"
        detail += f"关联预约ID: {', '.join(record.reservation_ids[:10])}"
        if len(record.reservation_ids) > 10:
            detail += f" 等{len(record.reservation_ids)}个"
        detail += "\n"
        if record.details:
            detail += f"\n详细信息:\n{record.details}\n"
        if record.is_cancelled:
            detail += f"\n已撤销\n撤销人: {record.cancel_operator}\n"
            detail += f"撤销时间: {record.cancel_time}\n撤销原因: {record.cancel_reason}"

        messagebox.showinfo("批次详情", detail, parent=self)

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

        reason = tk.simpledialog.askstring(
            "撤销原因",
            f"确定要撤销该批次的 {len(record.reservation_ids)} 个预约吗？\n请填写撤销原因：",
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
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="导出预约 (CSV)", command=lambda: self._export("csv"))
        file_menu.add_command(label="导出预约 (JSON)", command=lambda: self._export("json"))
        file_menu.add_command(label="导出仪器档案 (CSV)", command=self._export_instruments)
        file_menu.add_separator()
        file_menu.add_command(label="查看校准/冻结记录", command=self._show_calibration_records)
        file_menu.add_command(label="查看操作日志", command=self._show_operation_logs)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        template_menu = tk.Menu(menubar, tearoff=0)
        template_menu.add_command(label="模板管理", command=self._show_template_management)
        template_menu.add_command(label="导入模板 (JSON)", command=self._import_templates_json)
        template_menu.add_command(label="导入模板 (CSV)", command=self._import_templates_csv)
        template_menu.add_command(label="导出模板 (JSON)", command=self._export_templates_json)
        template_menu.add_command(label="导出模板 (CSV)", command=self._export_templates_csv)
        menubar.add_cascade(label="模板", menu=template_menu)

        batch_menu = tk.Menu(menubar, tearoff=0)
        batch_menu.add_command(label="批量创建预约", command=self._show_batch_create)
        batch_menu.add_command(label="批量操作记录", command=self._show_batch_management)
        menubar.add_cascade(label="批量操作", menu=batch_menu)

        role_menu = tk.Menu(menubar, tearoff=0)
        self.role_var = tk.StringVar(value=self.dm.settings.current_role.value)
        role_menu.add_radiobutton(
            label="普通用户", variable=self.role_var, value="普通用户", command=self._on_role_change
        )
        role_menu.add_radiobutton(
            label="管理员", variable=self.role_var, value="管理员", command=self._on_role_change
        )
        menubar.add_cascade(label="角色", menu=role_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        self.reminder_enabled_var = tk.BooleanVar(value=self.dm.settings.reminder_enabled)
        settings_menu.add_checkbutton(
            label="启用提醒", variable=self.reminder_enabled_var, command=self._on_reminder_toggle
        )
        settings_menu.add_command(label="默认提醒时长...", command=self._set_default_reminder)
        menubar.add_cascade(label="设置", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.config(menu=menubar)

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


if __name__ == "__main__":
    main()
