import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from datetime import datetime, date, timedelta

from data_manager import (
    DataManager, InstrumentStatus, ReservationStatus, UserRole,
    TimeSlot, STATUS_FLOW
)


class ReservationDialog(tk.Toplevel):
    def __init__(self, parent, dm: DataManager, title="新建预约", reservation=None):
        super().__init__(parent)
        self.dm = dm
        self.reservation = reservation
        self.result = None
        self.title(title)
        self.geometry("480x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        if reservation:
            self._load_reservation()

    def _build_ui(self):
        padding = {"padx": 10, "pady": 5}

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="仪器：").grid(row=0, column=0, sticky="e", **padding)
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(
            frm, textvariable=self.instrument_var, state="readonly", width=35
        )
        self._populate_instruments()
        self.instrument_combo.grid(row=0, column=1, **padding)

        ttk.Label(frm, text="申请人：").grid(row=1, column=0, sticky="e", **padding)
        self.applicant_var = tk.StringVar(value=self.dm.settings.current_user)
        ttk.Entry(frm, textvariable=self.applicant_var, width=37).grid(row=1, column=1, **padding)

        ttk.Label(frm, text="用途：").grid(row=2, column=0, sticky="ne", **padding)
        self.purpose_text = tk.Text(frm, width=37, height=3)
        self.purpose_text.grid(row=2, column=1, **padding)

        ttk.Label(frm, text="开始时间：").grid(row=3, column=0, sticky="e", **padding)
        self.start_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.start_var, width=37).grid(row=3, column=1, **padding)
        ttk.Label(frm, text="格式：YYYY-MM-DD HH:MM:SS", foreground="gray").grid(
            row=4, column=1, sticky="w", padx=10
        )

        ttk.Label(frm, text="结束时间：").grid(row=5, column=0, sticky="e", **padding)
        self.end_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.end_var, width=37).grid(row=5, column=1, **padding)
        ttk.Label(frm, text="格式：YYYY-MM-DD HH:MM:SS", foreground="gray").grid(
            row=6, column=1, sticky="w", padx=10
        )

        if self.reservation and self.reservation.status in [ReservationStatus.DRAFT, ReservationStatus.PENDING_CONFIRM]:
            ttk.Label(frm, text="当前状态：").grid(row=7, column=0, sticky="e", **padding)
            ttk.Label(frm, text=self.reservation.status.value).grid(row=7, column=1, sticky="w", **padding)

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=12).pack(side="left", padx=10)

        if not self.reservation:
            tomorrow = date.today() + timedelta(days=1)
            self.start_var.set(tomorrow.strftime("%Y-%m-%d") + " 09:00:00")
            self.end_var.set(tomorrow.strftime("%Y-%m-%d") + " 11:00:00")

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
            res, msg = self.dm.add_reservation(
                instrument.id, applicant, purpose, start_time, end_time
            )

        if not res:
            messagebox.showerror("预约失败", msg, parent=self)
            return

        self.result = res
        self.destroy()

    def _on_cancel(self):
        self.destroy()


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
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        role_menu = tk.Menu(menubar, tearoff=0)
        self.role_var = tk.StringVar(value=self.dm.settings.current_role.value)
        role_menu.add_radiobutton(
            label="普通用户", variable=self.role_var, value="普通用户", command=self._on_role_change
        )
        role_menu.add_radiobutton(
            label="管理员", variable=self.role_var, value="管理员", command=self._on_role_change
        )
        menubar.add_cascade(label="角色", menu=role_menu)

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

        columns = ("code", "applicant", "purpose", "start", "end", "status", "created")
        self.reservation_tree = ttk.Treeview(parent, columns=columns, show="headings", height=18)
        self.reservation_tree.heading("code", text="仪器编号")
        self.reservation_tree.heading("applicant", text="申请人")
        self.reservation_tree.heading("purpose", text="用途")
        self.reservation_tree.heading("start", text="开始时间")
        self.reservation_tree.heading("end", text="结束时间")
        self.reservation_tree.heading("status", text="状态")
        self.reservation_tree.heading("created", text="创建时间")

        self.reservation_tree.column("code", width=90, anchor="w")
        self.reservation_tree.column("applicant", width=80, anchor="w")
        self.reservation_tree.column("purpose", width=120, anchor="w")
        self.reservation_tree.column("start", width=130, anchor="w")
        self.reservation_tree.column("end", width=130, anchor="w")
        self.reservation_tree.column("status", width=80, anchor="w")
        self.reservation_tree.column("created", width=130, anchor="w")

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
            self.reservation_tree.insert(
                "", "end", iid=r.id,
                values=(r.instrument_code, r.applicant, purpose_short,
                        r.start_time, r.end_time, r.status.value, r.created_at),
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

        dlg = ReservationDialog(self.root, self.dm, "新建预约")
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

    def _set_status(self, text: str):
        self.status_label.config(text=text)

    def _show_about(self):
        messagebox.showinfo(
            "关于",
            "实验室仪器预约校准系统 v1.0\n\n"
            "功能：\n"
            "• 仪器档案管理\n"
            "• 预约流程管理（草稿→待确认→已预约→使用中→待复核→已完成/已取消）\n"
            "• 校准过期自动检测\n"
            "• 故障冻结与解除\n"
            "• 数据导出（CSV/JSON）",
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
