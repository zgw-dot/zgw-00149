import json
import os
import uuid
import csv
from datetime import datetime, date, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple, Dict, Any


class InstrumentStatus(str, Enum):
    NORMAL = "正常"
    CALIBRATION_EXPIRED = "校准过期"
    MALFUNCTION_FROZEN = "故障冻结"


class ReservationStatus(str, Enum):
    DRAFT = "草稿"
    PENDING_CONFIRM = "待确认"
    CONFIRMED = "已预约"
    IN_USE = "使用中"
    PENDING_REVIEW = "待复核"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class UserRole(str, Enum):
    ADMIN = "管理员"
    NORMAL = "普通用户"


class SandboxItemStatus(str, Enum):
    DIRECT_SUBMIT = "可直接提交"
    NEEDS_CONFIRM = "需人工确认"
    FORBIDDEN = "禁止提交"


class OperationType(str, Enum):
    BATCH_CREATE = "批量建单"
    BATCH_CANCEL = "批量撤销"
    TEMPLATE_IMPORT = "模板导入"
    TEMPLATE_EXPORT = "模板导出"
    TEMPLATE_CREATE = "模板创建"
    TEMPLATE_UPDATE = "模板更新"
    TEMPLATE_DELETE = "模板删除"
    SANDBOX_IMPORT = "沙盘导入"
    SANDBOX_PREVIEW = "沙盘预演"
    SANDBOX_SUBMIT = "沙盘提交"
    SANDBOX_WITHDRAW = "沙盘撤回"
    SANDBOX_EXPORT = "沙盘导出"


STATUS_FLOW = {
    ReservationStatus.DRAFT: [ReservationStatus.PENDING_CONFIRM, ReservationStatus.CANCELLED],
    ReservationStatus.PENDING_CONFIRM: [ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED],
    ReservationStatus.CONFIRMED: [ReservationStatus.IN_USE, ReservationStatus.CANCELLED],
    ReservationStatus.IN_USE: [ReservationStatus.PENDING_REVIEW],
    ReservationStatus.PENDING_REVIEW: [ReservationStatus.COMPLETED, ReservationStatus.CANCELLED],
    ReservationStatus.COMPLETED: [],
    ReservationStatus.CANCELLED: [],
}


@dataclass
class TimeSlot:
    start_time: str
    end_time: str

    def to_dict(self):
        return {"start_time": self.start_time, "end_time": self.end_time}

    @classmethod
    def from_dict(cls, d):
        return cls(start_time=d["start_time"], end_time=d["end_time"])

    def is_valid(self) -> bool:
        try:
            sh, sm = map(int, self.start_time.split(":"))
            eh, em = map(int, self.end_time.split(":"))
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            return 0 <= start_min < end_min <= 24 * 60
        except (ValueError, AttributeError):
            return False


@dataclass
class Instrument:
    id: str
    code: str
    model: str
    person_in_charge: str
    calibration_expiry: str
    available_time_slots: List[TimeSlot] = field(default_factory=list)
    status: InstrumentStatus = InstrumentStatus.NORMAL
    freeze_reason: Optional[str] = None
    freeze_operator: Optional[str] = None
    freeze_time: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["available_time_slots"] = [ts.to_dict() for ts in self.available_time_slots]
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d):
        slots = [TimeSlot.from_dict(ts) for ts in d.get("available_time_slots", [])]
        return cls(
            id=d["id"],
            code=d["code"],
            model=d["model"],
            person_in_charge=d["person_in_charge"],
            calibration_expiry=d["calibration_expiry"],
            available_time_slots=slots,
            status=InstrumentStatus(d["status"]),
            freeze_reason=d.get("freeze_reason"),
            freeze_operator=d.get("freeze_operator"),
            freeze_time=d.get("freeze_time"),
        )

    def is_calibration_expired(self) -> bool:
        try:
            expiry = datetime.strptime(self.calibration_expiry, "%Y-%m-%d").date()
            return date.today() > expiry
        except (ValueError, TypeError):
            return False


@dataclass
class TemplateSnapshot:
    template_id: str
    template_name: str
    instrument_code: str
    instrument_model: str
    purpose: str
    default_duration_minutes: int
    reminder_minutes: int
    remark: str
    applicable_persons: List[str]
    time_slots: List[TimeSlot]
    snapshot_time: str

    def to_dict(self):
        d = asdict(self)
        d["time_slots"] = [ts.to_dict() for ts in self.time_slots]
        return d

    @classmethod
    def from_dict(cls, d):
        slots = [TimeSlot.from_dict(ts) for ts in d.get("time_slots", [])]
        return cls(
            template_id=d["template_id"],
            template_name=d["template_name"],
            instrument_code=d["instrument_code"],
            instrument_model=d["instrument_model"],
            purpose=d["purpose"],
            default_duration_minutes=d["default_duration_minutes"],
            reminder_minutes=d["reminder_minutes"],
            remark=d.get("remark", ""),
            applicable_persons=d.get("applicable_persons", []),
            time_slots=slots,
            snapshot_time=d["snapshot_time"],
        )


@dataclass
class Reservation:
    id: str
    instrument_id: str
    instrument_code: str
    applicant: str
    purpose: str
    start_time: str
    end_time: str
    status: ReservationStatus = ReservationStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    review_note: Optional[str] = None
    cancel_reason: Optional[str] = None
    template_snapshot: Optional[TemplateSnapshot] = None
    batch_id: Optional[str] = None
    reminder_minutes: int = 0

    def to_dict(self):
        d = asdict(self)
        d["status"] = self.status.value
        if self.template_snapshot:
            d["template_snapshot"] = self.template_snapshot.to_dict()
        return d

    @classmethod
    def from_dict(cls, d):
        snap = None
        if d.get("template_snapshot"):
            snap = TemplateSnapshot.from_dict(d["template_snapshot"])
        return cls(
            id=d["id"],
            instrument_id=d["instrument_id"],
            instrument_code=d["instrument_code"],
            applicant=d["applicant"],
            purpose=d["purpose"],
            start_time=d["start_time"],
            end_time=d["end_time"],
            status=ReservationStatus(d["status"]),
            created_at=d.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=d.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            review_note=d.get("review_note"),
            cancel_reason=d.get("cancel_reason"),
            template_snapshot=snap,
            batch_id=d.get("batch_id"),
            reminder_minutes=d.get("reminder_minutes", 0),
        )


@dataclass
class ReservationTemplate:
    id: str
    name: str
    instrument_id: str
    instrument_code: str
    instrument_model: str
    purpose: str
    default_duration_minutes: int
    reminder_minutes: int
    remark: str
    applicable_persons: List[str]
    time_slots: List[TimeSlot]
    created_at: str
    updated_at: str

    def to_dict(self):
        d = asdict(self)
        d["time_slots"] = [ts.to_dict() for ts in self.time_slots]
        return d

    @classmethod
    def from_dict(cls, d):
        slots = [TimeSlot.from_dict(ts) for ts in d.get("time_slots", [])]
        return cls(
            id=d["id"],
            name=d["name"],
            instrument_id=d["instrument_id"],
            instrument_code=d["instrument_code"],
            instrument_model=d.get("instrument_model", ""),
            purpose=d.get("purpose", ""),
            default_duration_minutes=d.get("default_duration_minutes", 60),
            reminder_minutes=d.get("reminder_minutes", 30),
            remark=d.get("remark", ""),
            applicable_persons=d.get("applicable_persons", []),
            time_slots=slots,
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def create_snapshot(self) -> TemplateSnapshot:
        return TemplateSnapshot(
            template_id=self.id,
            template_name=self.name,
            instrument_code=self.instrument_code,
            instrument_model=self.instrument_model,
            purpose=self.purpose,
            default_duration_minutes=self.default_duration_minutes,
            reminder_minutes=self.reminder_minutes,
            remark=self.remark,
            applicable_persons=list(self.applicable_persons),
            time_slots=[TimeSlot(ts.start_time, ts.end_time) for ts in self.time_slots],
            snapshot_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )


@dataclass
class ImportResult:
    success: bool
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    imported_template_ids: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            success=d.get("success", False),
            total_count=d.get("total_count", 0),
            success_count=d.get("success_count", 0),
            failed_count=d.get("failed_count", 0),
            errors=d.get("errors", []),
            warnings=d.get("warnings", []),
            imported_template_ids=d.get("imported_template_ids", []),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class BatchItemResult:
    index: int
    status: str
    template_name: str = ""
    instrument_code: str = ""
    start_time: str = ""
    applicant: str = ""
    reason: str = ""
    reservation_id: str = ""
    template_snapshot: Optional[Dict[str, Any]] = None

    def to_dict(self):
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            index=d.get("index", 0),
            status=d.get("status", ""),
            template_name=d.get("template_name", ""),
            instrument_code=d.get("instrument_code", ""),
            start_time=d.get("start_time", ""),
            applicant=d.get("applicant", ""),
            reason=d.get("reason", ""),
            reservation_id=d.get("reservation_id", ""),
            template_snapshot=d.get("template_snapshot"),
        )


@dataclass
class SandboxDraftItem:
    index: int
    instrument_code: str
    applicant: str
    purpose: str
    start_time: str
    end_time: str
    preview_status: str = ""
    preview_reasons: List[str] = field(default_factory=list)
    reservation_id: str = ""
    template_snapshot: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            index=d.get("index", 0),
            instrument_code=d.get("instrument_code", ""),
            applicant=d.get("applicant", ""),
            purpose=d.get("purpose", ""),
            start_time=d.get("start_time", ""),
            end_time=d.get("end_time", ""),
            preview_status=d.get("preview_status", ""),
            preview_reasons=d.get("preview_reasons", []),
            reservation_id=d.get("reservation_id", ""),
            template_snapshot=d.get("template_snapshot"),
        )


@dataclass
class SandboxDraft:
    id: str
    name: str
    operator: str
    operator_role: str
    items: List[SandboxDraftItem]
    source_file: str
    created_at: str
    updated_at: str
    is_submitted: bool = False
    submitted_at: Optional[str] = None
    submitted_batch_id: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["items"] = [it.to_dict() for it in self.items]
        return d

    @classmethod
    def from_dict(cls, d):
        items = [SandboxDraftItem.from_dict(it) for it in d.get("items", [])]
        return cls(
            id=d["id"],
            name=d["name"],
            operator=d["operator"],
            operator_role=d["operator_role"],
            items=items,
            source_file=d.get("source_file", ""),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            is_submitted=d.get("is_submitted", False),
            submitted_at=d.get("submitted_at"),
            submitted_batch_id=d.get("submitted_batch_id"),
        )


@dataclass
class BatchRecord:
    id: str
    operator: str
    operator_role: str
    operation: str
    total_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    reservation_ids: List[str]
    item_results: List[BatchItemResult]
    details: str
    created_at: str
    is_cancelled: bool = False
    cancel_operator: Optional[str] = None
    cancel_time: Optional[str] = None
    cancel_reason: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["item_results"] = [ir.to_dict() for ir in self.item_results]
        return d

    @classmethod
    def from_dict(cls, d):
        item_results = [BatchItemResult.from_dict(ir) for ir in d.get("item_results", [])]
        return cls(
            id=d["id"],
            operator=d["operator"],
            operator_role=d["operator_role"],
            operation=d["operation"],
            total_count=d["total_count"],
            success_count=d["success_count"],
            failed_count=d.get("failed_count", 0),
            skipped_count=d.get("skipped_count", 0),
            reservation_ids=d.get("reservation_ids", []),
            item_results=item_results,
            details=d.get("details", ""),
            created_at=d["created_at"],
            is_cancelled=d.get("is_cancelled", False),
            cancel_operator=d.get("cancel_operator"),
            cancel_time=d.get("cancel_time"),
            cancel_reason=d.get("cancel_reason"),
        )


@dataclass
class OperationLogEntry:
    id: str
    operation_type: str
    operator: str
    operator_role: str
    description: str
    detail: str
    timestamp: str

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            operation_type=d["operation_type"],
            operator=d.get("operator", ""),
            operator_role=d.get("operator_role", ""),
            description=d.get("description", ""),
            detail=d.get("detail", ""),
            timestamp=d["timestamp"],
        )


@dataclass
class AppSettings:
    export_dir: str = ""
    import_dir: str = ""
    filter_person: str = ""
    filter_status: str = ""
    ins_filter_person: str = ""
    ins_filter_status: str = ""
    current_user: str = "当前用户"
    current_role: UserRole = UserRole.NORMAL
    reminder_enabled: bool = True
    default_reminder_minutes: int = 30
    last_import_result: Optional[ImportResult] = None
    last_template_snapshots: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["current_role"] = self.current_role.value
        if self.last_import_result:
            d["last_import_result"] = self.last_import_result.to_dict()
        return d

    @classmethod
    def from_dict(cls, d):
        last_imp = None
        if d.get("last_import_result"):
            last_imp = ImportResult.from_dict(d["last_import_result"])
        return cls(
            export_dir=d.get("export_dir", ""),
            import_dir=d.get("import_dir", ""),
            filter_person=d.get("filter_person", ""),
            filter_status=d.get("filter_status", ""),
            ins_filter_person=d.get("ins_filter_person", ""),
            ins_filter_status=d.get("ins_filter_status", ""),
            current_user=d.get("current_user", "当前用户"),
            current_role=UserRole(d.get("current_role", UserRole.NORMAL.value)),
            reminder_enabled=d.get("reminder_enabled", True),
            default_reminder_minutes=d.get("default_reminder_minutes", 30),
            last_import_result=last_imp,
            last_template_snapshots=d.get("last_template_snapshots", []),
        )


class DataManager:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.instruments_file = os.path.join(self.data_dir, "instruments.json")
        self.reservations_file = os.path.join(self.data_dir, "reservations.json")
        self.settings_file = os.path.join(self.data_dir, "settings.json")
        self.calibration_records_file = os.path.join(self.data_dir, "calibration_records.json")
        self.templates_file = os.path.join(self.data_dir, "templates.json")
        self.batch_records_file = os.path.join(self.data_dir, "batch_records.json")
        self.operation_logs_file = os.path.join(self.data_dir, "operation_logs.json")
        self.sandbox_drafts_file = os.path.join(self.data_dir, "sandbox_drafts.json")

        self.instruments: List[Instrument] = []
        self.reservations: List[Reservation] = []
        self.settings: AppSettings = AppSettings()
        self.calibration_records: List[dict] = []
        self.templates: List[ReservationTemplate] = []
        self.batch_records: List[BatchRecord] = []
        self.operation_logs: List[OperationLogEntry] = []
        self.sandbox_drafts: List[SandboxDraft] = []

        self.load_all()

    def load_all(self):
        self.load_instruments()
        self.load_reservations()
        self.load_settings()
        self.load_calibration_records()
        self.load_templates()
        self.load_batch_records()
        self.load_operation_logs()
        self.load_sandbox_drafts()
        self._check_calibration_expiry()

    # ===== Instrument & Reservation (existing) =====

    def load_instruments(self):
        if os.path.exists(self.instruments_file):
            with open(self.instruments_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.instruments = [Instrument.from_dict(d) for d in data]
        else:
            self.instruments = []

    def save_instruments(self):
        with open(self.instruments_file, "w", encoding="utf-8") as f:
            json.dump([ins.to_dict() for ins in self.instruments], f, ensure_ascii=False, indent=2)

    def load_reservations(self):
        if os.path.exists(self.reservations_file):
            with open(self.reservations_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.reservations = [Reservation.from_dict(d) for d in data]
        else:
            self.reservations = []

    def save_reservations(self):
        with open(self.reservations_file, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in self.reservations], f, ensure_ascii=False, indent=2)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.settings = AppSettings.from_dict(data)
        else:
            self.settings = AppSettings()

    def save_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings.to_dict(), f, ensure_ascii=False, indent=2)

    def load_calibration_records(self):
        if os.path.exists(self.calibration_records_file):
            with open(self.calibration_records_file, "r", encoding="utf-8") as f:
                self.calibration_records = json.load(f)
        else:
            self.calibration_records = []

    def save_calibration_records(self):
        with open(self.calibration_records_file, "w", encoding="utf-8") as f:
            json.dump(self.calibration_records, f, ensure_ascii=False, indent=2)

    def _check_calibration_expiry(self):
        changed = False
        for ins in self.instruments:
            if ins.status == InstrumentStatus.NORMAL and ins.is_calibration_expired():
                ins.status = InstrumentStatus.CALIBRATION_EXPIRED
                changed = True
            elif ins.status == InstrumentStatus.CALIBRATION_EXPIRED and not ins.is_calibration_expired():
                ins.status = InstrumentStatus.NORMAL
                changed = True
        if changed:
            self.save_instruments()

    def add_instrument(self, code: str, model: str, person_in_charge: str,
                       calibration_expiry: str, available_time_slots: List[TimeSlot]) -> Instrument:
        ins = Instrument(
            id=str(uuid.uuid4()),
            code=code,
            model=model,
            person_in_charge=person_in_charge,
            calibration_expiry=calibration_expiry,
            available_time_slots=available_time_slots,
        )
        if ins.is_calibration_expired():
            ins.status = InstrumentStatus.CALIBRATION_EXPIRED
        self.instruments.append(ins)
        self.save_instruments()
        return ins

    def update_instrument(self, instrument_id: str, **kwargs) -> Optional[Instrument]:
        for ins in self.instruments:
            if ins.id == instrument_id:
                for key, value in kwargs.items():
                    if hasattr(ins, key):
                        setattr(ins, key, value)
                if ins.is_calibration_expired() and ins.status == InstrumentStatus.NORMAL:
                    ins.status = InstrumentStatus.CALIBRATION_EXPIRED
                self.save_instruments()
                return ins
        return None

    def get_instrument(self, instrument_id: str) -> Optional[Instrument]:
        for ins in self.instruments:
            if ins.id == instrument_id:
                return ins
        return None

    def get_instrument_by_code(self, code: str) -> Optional[Instrument]:
        for ins in self.instruments:
            if ins.code == code:
                return ins
        return None

    def get_instruments_by_person(self, person: str) -> List[Instrument]:
        if not person:
            return self.instruments.copy()
        return [ins for ins in self.instruments if ins.person_in_charge == person]

    def get_all_persons(self) -> List[str]:
        persons = set()
        for ins in self.instruments:
            persons.add(ins.person_in_charge)
        return sorted(list(persons))

    def add_reservation(self, instrument_id: str, applicant: str, purpose: str,
                        start_time: str, end_time: str,
                        template_snapshot: TemplateSnapshot = None,
                        batch_id: str = None,
                        reminder_minutes: int = 0) -> Tuple[Optional[Reservation], str]:
        ins = self.get_instrument(instrument_id)
        if not ins:
            return None, "仪器不存在"

        if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
            return None, "仪器处于故障冻结状态，无法预约"
        if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
            return None, "仪器校准已过期，无法预约"

        ok, msg = self._check_time_overlap(instrument_id, start_time, end_time)
        if not ok:
            return None, msg

        res = Reservation(
            id=str(uuid.uuid4()),
            instrument_id=instrument_id,
            instrument_code=ins.code,
            applicant=applicant,
            purpose=purpose,
            start_time=start_time,
            end_time=end_time,
            template_snapshot=template_snapshot,
            batch_id=batch_id,
            reminder_minutes=reminder_minutes,
        )
        self.reservations.append(res)
        self.save_reservations()
        return res, ""

    def _check_time_overlap(self, instrument_id: str, start_time: str, end_time: str,
                            exclude_reservation_id: str = None) -> Tuple[bool, str]:
        try:
            new_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            new_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False, "时间格式错误"

        if new_start >= new_end:
            return False, "开始时间必须早于结束时间"

        active_statuses = [
            ReservationStatus.CONFIRMED,
            ReservationStatus.IN_USE,
            ReservationStatus.PENDING_REVIEW,
        ]

        for r in self.reservations:
            if r.instrument_id != instrument_id:
                continue
            if exclude_reservation_id and r.id == exclude_reservation_id:
                    continue
            if r.status not in active_statuses:
                continue

            try:
                r_start = datetime.strptime(r.start_time, "%Y-%m-%d %H:%M:%S")
                r_end = datetime.strptime(r.end_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if new_start < r_end and new_end > r_start:
                return False, f"预约时间与现有预约重叠（{r.applicant} - {r.start_time} 至 {r.end_time}）"

        return True, ""

    def update_reservation_status(self, reservation_id: str, new_status: ReservationStatus,
                                  user_role: UserRole, note: str = None) -> Tuple[Optional[Reservation], str]:
        res = None
        for r in self.reservations:
            if r.id == reservation_id:
                res = r
                break
        if not res:
            return None, "预约不存在"

        if new_status not in STATUS_FLOW.get(res.status, []):
            return None, f"无法从「{res.status.value}」状态流转到「{new_status.value}」状态"

        if new_status == ReservationStatus.CONFIRMED:
            ins = self.get_instrument(res.instrument_id)
            if not ins:
                return None, "仪器不存在"
            if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
                return None, "仪器处于故障冻结状态，无法确认预约"
            if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
                return None, "仪器校准已过期，无法确认预约"

            ok, msg = self._check_time_overlap(res.instrument_id, res.start_time, res.end_time, res.id)
            if not ok:
                return None, msg

        res.status = new_status
        res.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if note:
            if new_status == ReservationStatus.COMPLETED or new_status == ReservationStatus.PENDING_REVIEW:
                res.review_note = note
            elif new_status == ReservationStatus.CANCELLED:
                res.cancel_reason = note

        self.save_reservations()
        return res, ""

    def update_reservation(self, reservation_id: str, **kwargs) -> Tuple[Optional[Reservation], str]:
        res = None
        for r in self.reservations:
            if r.id == reservation_id:
                res = r
                break
        if not res:
            return None, "预约不存在"

        if res.status not in [ReservationStatus.DRAFT, ReservationStatus.PENDING_CONFIRM]:
            return None, "仅草稿和待确认状态的预约可编辑"

        start_time = kwargs.get("start_time", res.start_time)
        end_time = kwargs.get("end_time", res.end_time)

        if "start_time" in kwargs or "end_time" in kwargs:
            ok, msg = self._check_time_overlap(res.instrument_id, start_time, end_time, res.id)
            if not ok:
                return None, msg

        for key, value in kwargs.items():
            if hasattr(res, key) and key not in ("id", "status", "created_at"):
                setattr(res, key, value)

        res.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_reservations()
        return res, ""

    def get_reservations_by_instrument(self, instrument_id: str) -> List[Reservation]:
        return [r for r in self.reservations if r.instrument_id == instrument_id]

    def get_reservations_filtered(self, person_filter: str = "", status_filter: str = "") -> List[Reservation]:
        results = self.reservations.copy()
        if person_filter:
            ins_ids = {ins.id for ins in self.instruments if ins.person_in_charge == person_filter}
            results = [r for r in results if r.instrument_id in ins_ids]
        if status_filter:
            results = [r for r in results if r.status.value == status_filter]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def freeze_instrument(self, instrument_id: str, reason: str, operator: str,
                          user_role: UserRole) -> Tuple[Optional[Instrument], str]:
        ins = self.get_instrument(instrument_id)
        if not ins:
            return None, "仪器不存在"

        if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
            return None, "仪器已处于故障冻结状态"

        record = {
            "id": str(uuid.uuid4()),
            "instrument_id": instrument_id,
            "instrument_code": ins.code,
            "action": "故障冻结",
            "operator": operator,
            "role": user_role.value,
            "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.calibration_records.append(record)
        self.save_calibration_records()

        ins.status = InstrumentStatus.MALFUNCTION_FROZEN
        ins.freeze_reason = reason
        ins.freeze_operator = operator
        ins.freeze_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_instruments()

        active_statuses = [
            ReservationStatus.CONFIRMED,
            ReservationStatus.IN_USE,
            ReservationStatus.PENDING_REVIEW,
        ]
        for r in self.reservations:
            if r.instrument_id == instrument_id and r.status in active_statuses:
                r.status = ReservationStatus.CANCELLED
                r.cancel_reason = f"仪器故障冻结：{reason}"
                r.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_reservations()

        return ins, ""

    def unfreeze_instrument(self, instrument_id: str, reason: str, operator: str,
                            user_role: UserRole) -> Tuple[Optional[Instrument], str]:
        if user_role != UserRole.ADMIN:
            return None, "仅管理员可解除故障冻结"

        ins = self.get_instrument(instrument_id)
        if not ins:
            return None, "仪器不存在"

        if ins.status != InstrumentStatus.MALFUNCTION_FROZEN:
            return None, "仪器未处于故障冻结状态"

        if ins.is_calibration_expired():
            ins.status = InstrumentStatus.CALIBRATION_EXPIRED
        else:
            ins.status = InstrumentStatus.NORMAL

        record = {
            "id": str(uuid.uuid4()),
            "instrument_id": instrument_id,
            "instrument_code": ins.code,
            "action": "解除冻结",
            "operator": operator,
            "role": user_role.value,
            "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.calibration_records.append(record)
        self.save_calibration_records()

        ins.freeze_reason = None
        ins.freeze_operator = None
        ins.freeze_time = None
        self.save_instruments()

        return ins, ""

    def add_calibration_record(self, instrument_id: str, calibration_date: str,
                               result: str, operator: str) -> dict:
        ins = self.get_instrument(instrument_id)
        record = {
            "id": str(uuid.uuid4()),
            "instrument_id": instrument_id,
            "instrument_code": ins.code if ins else "",
            "calibration_date": calibration_date,
            "result": result,
            "operator": operator,
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.calibration_records.append(record)
        self.save_calibration_records()
        return record

    def export_reservations_csv(self, filepath: str, person_filter: str = "", status_filter: str = "") -> Tuple[bool, str]:
        try:
            reservations = self.get_reservations_filtered(person_filter, status_filter)
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "预约ID", "仪器编号", "申请人", "用途",
                    "开始时间", "结束时间", "状态", "创建时间", "更新时间", "复核备注", "取消原因",
                    "模板名称", "批次ID", "提醒时长(分钟)"
                ])
                for r in reservations:
                    writer.writerow([
                        r.id, r.instrument_code, r.applicant, r.purpose,
                        r.start_time, r.end_time, r.status.value,
                        r.created_at, r.updated_at,
                        r.review_note or "", r.cancel_reason or "",
                        r.template_snapshot.template_name if r.template_snapshot else "",
                        r.batch_id or "",
                        r.reminder_minutes,
                    ])
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_reservations_json(self, filepath: str, person_filter: str = "", status_filter: str = "") -> Tuple[bool, str]:
        try:
            reservations = self.get_reservations_filtered(person_filter, status_filter)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in reservations], f, ensure_ascii=False, indent=2)
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_instruments_csv(self, filepath: str) -> Tuple[bool, str]:
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "仪器ID", "仪器编号", "型号", "负责人",
                    "校准到期日", "状态", "冻结原因", "冻结操作人", "冻结时间"
                ])
                for ins in self.instruments:
                    writer.writerow([
                        ins.id, ins.code, ins.model, ins.person_in_charge,
                        ins.calibration_expiry, ins.status.value,
                        ins.freeze_reason or "", ins.freeze_operator or "", ins.freeze_time or ""
                    ])
            return True, ""
        except Exception as e:
            return False, str(e)

    # ===== Template Management =====

    def load_templates(self):
        if os.path.exists(self.templates_file):
            with open(self.templates_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.templates = [ReservationTemplate.from_dict(d) for d in data]
        else:
            self.templates = []

    def save_templates(self):
        with open(self.templates_file, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in self.templates], f, ensure_ascii=False, indent=2)

    def add_template(self, name: str, instrument_id: str, purpose: str,
                     default_duration_minutes: int, reminder_minutes: int,
                     remark: str, applicable_persons: List[str],
                     time_slots: List[TimeSlot]) -> Tuple[Optional[ReservationTemplate], str]:
        if not name or not name.strip():
            return None, "模板名称不能为空"

        name = name.strip()
        for t in self.templates:
            if t.name == name:
                return None, f"模板名称「{name}」已存在"

        ins = self.get_instrument(instrument_id)
        if not ins:
            return None, "仪器不存在"

        for ts in time_slots:
            if not ts.is_valid():
                return None, f"时间段「{ts.start_time}-{ts.end_time}」不合法"

        if default_duration_minutes <= 0:
            return None, "默认时长必须大于0分钟"

        if reminder_minutes < 0:
            return None, "提前提醒时长不能为负数"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        template = ReservationTemplate(
            id=str(uuid.uuid4()),
            name=name,
            instrument_id=instrument_id,
            instrument_code=ins.code,
            instrument_model=ins.model,
            purpose=purpose,
            default_duration_minutes=default_duration_minutes,
            reminder_minutes=reminder_minutes,
            remark=remark,
            applicable_persons=list(applicable_persons),
            time_slots=[TimeSlot(ts.start_time, ts.end_time) for ts in time_slots],
            created_at=now,
            updated_at=now,
        )
        self.templates.append(template)
        self.save_templates()

        self._add_operation_log(
            operation_type=OperationType.TEMPLATE_CREATE.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"创建模板：{name}",
            detail=f"仪器={ins.code}, 时长={default_duration_minutes}分钟",
        )

        return template, ""

    def update_template(self, template_id: str, **kwargs) -> Tuple[Optional[ReservationTemplate], str]:
        template = None
        for t in self.templates:
            if t.id == template_id:
                template = t
                break
        if not template:
            return None, "模板不存在"

        if "name" in kwargs:
            new_name = kwargs["name"].strip() if kwargs["name"] else ""
            if not new_name:
                return None, "模板名称不能为空"
            for t in self.templates:
                if t.id != template_id and t.name == new_name:
                    return None, f"模板名称「{new_name}」已存在"
            kwargs["name"] = new_name

        if "time_slots" in kwargs:
            for ts in kwargs["time_slots"]:
                if not ts.is_valid():
                    return None, f"时间段「{ts.start_time}-{ts.end_time}」不合法"

        if "default_duration_minutes" in kwargs and kwargs["default_duration_minutes"] <= 0:
            return None, "默认时长必须大于0分钟"

        if "reminder_minutes" in kwargs and kwargs["reminder_minutes"] < 0:
            return None, "提前提醒时长不能为负数"

        if "instrument_id" in kwargs:
            ins = self.get_instrument(kwargs["instrument_id"])
            if not ins:
                return None, "仪器不存在"
            kwargs["instrument_code"] = ins.code
            kwargs["instrument_model"] = ins.model

        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)

        template.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_templates()

        self._add_operation_log(
            operation_type=OperationType.TEMPLATE_UPDATE.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"更新模板：{template.name}",
            detail=f"模板ID={template.id}",
        )

        return template, ""

    def delete_template(self, template_id: str) -> Tuple[bool, str]:
        template = None
        idx = -1
        for i, t in enumerate(self.templates):
            if t.id == template_id:
                template = t
                idx = i
                break
        if not template:
            return False, "模板不存在"

        name = template.name
        del self.templates[idx]
        self.save_templates()

        self._add_operation_log(
            operation_type=OperationType.TEMPLATE_DELETE.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"删除模板：{name}",
            detail=f"模板ID={template_id}",
        )

        return True, ""

    def get_template(self, template_id: str) -> Optional[ReservationTemplate]:
        for t in self.templates:
            if t.id == template_id:
                return t
        return None

    def get_template_by_name(self, name: str) -> Optional[ReservationTemplate]:
        for t in self.templates:
            if t.name == name:
                return t
        return None

    def list_templates(self, instrument_id: str = "", person_filter: str = "") -> List[ReservationTemplate]:
        results = self.templates.copy()
        if instrument_id:
            results = [t for t in results if t.instrument_id == instrument_id]
        if person_filter:
            results = [t for t in results if person_filter in t.applicable_persons or not t.applicable_persons]
        results.sort(key=lambda t: t.updated_at, reverse=True)
        return results

    def get_applicable_templates(self, applicant: str = "") -> List[ReservationTemplate]:
        results = self.templates.copy()
        if applicant:
            results = [t for t in results if not t.applicable_persons or applicant in t.applicable_persons]
        results.sort(key=lambda t: t.updated_at, reverse=True)
        return results

    def save_template_snapshots(self, template_ids: List[str]):
        snapshots = []
        for tid in template_ids:
            tpl = self.get_template(tid)
            if tpl:
                snap = {
                    "template_id": tpl.id,
                    "template_name": tpl.name,
                    "instrument_code": tpl.instrument_code,
                    "instrument_model": tpl.instrument_model,
                    "purpose": tpl.purpose,
                    "default_duration_minutes": tpl.default_duration_minutes,
                    "reminder_minutes": tpl.reminder_minutes,
                    "remark": tpl.remark,
                    "applicable_persons": list(tpl.applicable_persons),
                    "time_slots": [ts.to_dict() for ts in tpl.time_slots],
                    "snapshot_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument_id": tpl.instrument_id,
                    "created_at": tpl.created_at,
                    "updated_at": tpl.updated_at,
                }
                snapshots.append(snap)
        self.settings.last_template_snapshots = snapshots
        self.save_settings()

    def get_last_template_snapshots(self) -> List[Dict[str, Any]]:
        return self.settings.last_template_snapshots or []

    def apply_template(self, template_id: str, start_date: str = None,
                       time_slot_index: int = 0,
                       applicant: str = None) -> Tuple[Optional[Reservation], str]:
        template = self.get_template(template_id)
        if not template:
            return None, "模板不存在"

        ins = self.get_instrument(template.instrument_id)
        if not ins:
            return None, "模板关联的仪器不存在"

        if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
            return None, "仪器处于故障冻结状态，无法套用模板"
        if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
            return None, "仪器校准已过期，无法套用模板"

        if not template.time_slots:
            return None, "模板未设置可选时间段"

        if time_slot_index < 0 or time_slot_index >= len(template.time_slots):
            return None, "时间段索引越界"

        if start_date is None:
            start_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        ts = template.time_slots[time_slot_index]
        start_dt_str = f"{start_date} {ts.start_time}:00"
        try:
            start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None, "开始时间格式错误"

        duration = timedelta(minutes=template.default_duration_minutes)
        end_dt = start_dt + duration
        end_dt_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        app = applicant or self.settings.current_user
        snapshot = template.create_snapshot()

        res, msg = self.add_reservation(
            instrument_id=template.instrument_id,
            applicant=app,
            purpose=template.purpose,
            start_time=start_dt_str,
            end_time=end_dt_str,
            template_snapshot=snapshot,
            reminder_minutes=template.reminder_minutes,
        )
        return res, msg

    # ===== Template Import / Export =====

    def export_templates_csv(self, filepath: str) -> Tuple[bool, str]:
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "模板名称", "仪器编号", "用途", "默认时长(分钟)",
                    "提前提醒(分钟)", "备注", "适用负责人", "可选时间段"
                ])
                for t in self.templates:
                    slots_str = ";".join([f"{ts.start_time}-{ts.end_time}" for ts in t.time_slots])
                    persons_str = ";".join(t.applicable_persons)
                    writer.writerow([
                        t.name, t.instrument_code, t.purpose,
                        t.default_duration_minutes, t.reminder_minutes,
                        t.remark, persons_str, slots_str,
                    ])
            self._add_operation_log(
                operation_type=OperationType.TEMPLATE_EXPORT.value,
                operator=self.settings.current_user,
                operator_role=self.settings.current_role.value,
                description=f"导出模板：{len(self.templates)}个",
                detail=f"文件={filepath}",
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_templates_json(self, filepath: str) -> Tuple[bool, str]:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self.templates], f, ensure_ascii=False, indent=2)
            self._add_operation_log(
                operation_type=OperationType.TEMPLATE_EXPORT.value,
                operator=self.settings.current_user,
                operator_role=self.settings.current_role.value,
                description=f"导出模板：{len(self.templates)}个",
                detail=f"文件={filepath}",
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_batch_records_json(self, filepath: str) -> Tuple[bool, str]:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([b.to_dict() for b in self.batch_records], f, ensure_ascii=False, indent=2)
            self._add_operation_log(
                operation_type=OperationType.BATCH_EXPORT.value
                if hasattr(OperationType, "BATCH_EXPORT")
                else OperationType.TEMPLATE_EXPORT.value,
                operator=self.settings.current_user,
                operator_role=self.settings.current_role.value,
                description=f"导出批次记录：{len(self.batch_records)}个",
                detail=f"文件={filepath}",
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def import_templates_json(self, filepath: str, overwrite: bool = False,
                               user_role: UserRole = None) -> ImportResult:
        result = ImportResult(
            success=False,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        if user_role is not None and user_role != UserRole.ADMIN:
            result.errors.append("仅管理员可导入模板")
            self.settings.last_import_result = result
            self.save_settings()
            return result

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            result.total_count = len(data)
            seen_names = set()

            for idx, item in enumerate(data):
                name = item.get("name", "").strip()
                line_num = idx + 1

                if not name:
                    result.errors.append(f"第{line_num}条：模板名称为空")
                    result.failed_count += 1
                    continue

                if name in seen_names:
                    result.errors.append(f"第{line_num}条：批次内重复模板名「{name}」")
                    result.failed_count += 1
                    continue
                seen_names.add(name)

                instrument_code = item.get("instrument_code", "")
                ins = self.get_instrument_by_code(instrument_code)
                if not ins:
                    result.errors.append(f"第{line_num}条：仪器编号「{instrument_code}」不存在")
                    result.failed_count += 1
                    continue

                purpose = item.get("purpose", "")
                default_duration = int(item.get("default_duration_minutes", 60))
                reminder = int(item.get("reminder_minutes", 30))
                remark = item.get("remark", "")
                applicable_persons = item.get("applicable_persons", [])

                valid_persons = set(self.get_all_persons())
                invalid_persons = [p for p in applicable_persons if p not in valid_persons]
                if invalid_persons:
                    result.errors.append(
                        f"第{line_num}条：适用负责人「{', '.join(invalid_persons)}」不存在"
                    )
                    result.failed_count += 1
                    continue

                time_slots = []
                slots_valid = True
                for ts_dict in item.get("time_slots", []):
                    ts = TimeSlot.from_dict(ts_dict)
                    if not ts.is_valid():
                        result.errors.append(
                            f"第{line_num}条：时间段「{ts.start_time}-{ts.end_time}」不合法"
                        )
                        result.failed_count += 1
                        slots_valid = False
                        break
                    time_slots.append(ts)
                if not slots_valid:
                    continue

                if not time_slots:
                    result.errors.append(f"第{line_num}条：模板「{name}」未设置可选时间段")
                    result.failed_count += 1
                    continue

                existing = self.get_template_by_name(name)
                if existing:
                    if overwrite:
                        upd, msg = self.update_template(
                            existing.id,
                            instrument_id=ins.id,
                            purpose=purpose,
                            default_duration_minutes=default_duration,
                            reminder_minutes=reminder,
                            remark=remark,
                            applicable_persons=applicable_persons,
                            time_slots=time_slots,
                        )
                        if upd:
                            result.success_count += 1
                            result.imported_template_ids.append(upd.id)
                        else:
                            result.errors.append(f"第{line_num}条：更新模板失败 - {msg}")
                            result.failed_count += 1
                    else:
                        result.errors.append(f"第{line_num}条：模板名称「{name}」已存在（使用overwrite=true可覆盖）")
                        result.failed_count += 1
                else:
                    new_tpl, msg = self.add_template(
                        name=name,
                        instrument_id=ins.id,
                        purpose=purpose,
                        default_duration_minutes=default_duration,
                        reminder_minutes=reminder,
                        remark=remark,
                        applicable_persons=applicable_persons,
                        time_slots=time_slots,
                    )
                    if new_tpl:
                        result.success_count += 1
                        result.imported_template_ids.append(new_tpl.id)
                    else:
                        result.errors.append(f"第{line_num}条：创建模板失败 - {msg}")
                        result.failed_count += 1

            result.success = result.failed_count == 0

        except Exception as e:
            result.errors.append(f"导入失败：{str(e)}")

        self.save_template_snapshots(result.imported_template_ids)
        self.settings.last_import_result = result
        self.save_settings()

        self._add_operation_log(
            operation_type=OperationType.TEMPLATE_IMPORT.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"导入模板：成功{result.success_count}个，失败{result.failed_count}个",
            detail=f"文件={filepath}",
        )

        return result

    def import_templates_csv(self, filepath: str, overwrite: bool = False,
                               user_role: UserRole = None) -> ImportResult:
        result = ImportResult(
            success=False,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        if user_role is not None and user_role != UserRole.ADMIN:
            result.errors.append("仅管理员可导入模板")
            self.settings.last_import_result = result
            self.save_settings()
            return result

        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            result.total_count = len(rows)
            seen_names = set()
            template_dicts = []

            for idx, row in enumerate(rows):
                line_num = idx + 2

                name = row.get("模板名称", "").strip()
                if not name:
                    result.errors.append(f"第{line_num}行：模板名称为空")
                    result.failed_count += 1
                    continue

                if name in seen_names:
                    result.errors.append(f"第{line_num}行：批次内重复模板名「{name}」")
                    result.failed_count += 1
                    continue
                seen_names.add(name)

                instrument_code = row.get("仪器编号", "").strip()
                ins = self.get_instrument_by_code(instrument_code)
                if not ins:
                    result.errors.append(f"第{line_num}行：仪器编号「{instrument_code}」不存在")
                    result.failed_count += 1
                    continue

                try:
                    default_duration = int(row.get("默认时长(分钟)", "60"))
                except ValueError:
                    result.errors.append(f"第{line_num}行：默认时长格式错误")
                    result.failed_count += 1
                    continue

                try:
                    reminder = int(row.get("提前提醒(分钟)", "30"))
                except ValueError:
                    result.errors.append(f"第{line_num}行：提前提醒格式错误")
                    result.failed_count += 1
                    continue

                purpose = row.get("用途", "")
                remark = row.get("备注", "")

                persons_str = row.get("适用负责人", "")
                applicable_persons = [p.strip() for p in persons_str.split(";") if p.strip()] if persons_str else []

                valid_persons = set(self.get_all_persons())
                invalid_persons = [p for p in applicable_persons if p not in valid_persons]
                if invalid_persons:
                    result.errors.append(
                        f"第{line_num}行：适用负责人「{', '.join(invalid_persons)}」不存在"
                    )
                    result.failed_count += 1
                    continue

                slots_str = row.get("可选时间段", "")
                time_slots = []
                slots_valid = True
                if slots_str:
                    slot_parts = [s.strip() for s in slots_str.split(";") if s.strip()]
                    for sp in slot_parts:
                        if "-" in sp:
                            st, et = sp.split("-", 1)
                            ts = TimeSlot(st.strip(), et.strip())
                            if not ts.is_valid():
                                result.errors.append(f"第{line_num}行：时间段「{sp}」不合法")
                                result.failed_count += 1
                                slots_valid = False
                                break
                            time_slots.append(ts)
                else:
                    result.errors.append(f"第{line_num}行：模板「{name}」未设置可选时间段")
                    result.failed_count += 1
                    continue

                if not slots_valid:
                    continue

                template_dicts.append({
                    "name": name,
                    "instrument_code": instrument_code,
                    "instrument_id": ins.id,
                    "purpose": purpose,
                    "default_duration_minutes": default_duration,
                    "reminder_minutes": reminder,
                    "remark": remark,
                    "applicable_persons": applicable_persons,
                    "time_slots": time_slots,
                })

            for tpl_dict in template_dicts:
                name = tpl_dict["name"]
                existing = self.get_template_by_name(name)
                if existing:
                    if overwrite:
                        upd, msg = self.update_template(
                            existing.id,
                            instrument_id=tpl_dict["instrument_id"],
                            purpose=tpl_dict["purpose"],
                            default_duration_minutes=tpl_dict["default_duration_minutes"],
                            reminder_minutes=tpl_dict["reminder_minutes"],
                            remark=tpl_dict["remark"],
                            applicable_persons=tpl_dict["applicable_persons"],
                            time_slots=tpl_dict["time_slots"],
                        )
                        if upd:
                            result.success_count += 1
                            result.imported_template_ids.append(upd.id)
                        else:
                            result.errors.append(f"模板「{name}」更新失败：{msg}")
                            result.failed_count += 1
                    else:
                        result.errors.append(f"模板名称「{name}」已存在（使用overwrite=true可覆盖）")
                        result.failed_count += 1
                else:
                    new_tpl, msg = self.add_template(
                        name=name,
                        instrument_id=tpl_dict["instrument_id"],
                        purpose=tpl_dict["purpose"],
                        default_duration_minutes=tpl_dict["default_duration_minutes"],
                        reminder_minutes=tpl_dict["reminder_minutes"],
                        remark=tpl_dict["remark"],
                        applicable_persons=tpl_dict["applicable_persons"],
                        time_slots=tpl_dict["time_slots"],
                    )
                    if new_tpl:
                        result.success_count += 1
                        result.imported_template_ids.append(new_tpl.id)
                    else:
                        result.errors.append(f"模板「{name}」创建失败：{msg}")
                        result.failed_count += 1

            result.success = result.failed_count == 0

        except Exception as e:
            result.errors.append(f"导入失败：{str(e)}")

        self.save_template_snapshots(result.imported_template_ids)
        self.settings.last_import_result = result
        self.save_settings()

        self._add_operation_log(
            operation_type=OperationType.TEMPLATE_IMPORT.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"导入模板：成功{result.success_count}个，失败{result.failed_count}个",
            detail=f"文件={filepath}",
        )

        return result

    # ===== Batch Create / Cancel =====

    def load_batch_records(self):
        if os.path.exists(self.batch_records_file):
            with open(self.batch_records_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.batch_records = [BatchRecord.from_dict(d) for d in data]
        else:
            self.batch_records = []

    def save_batch_records(self):
        with open(self.batch_records_file, "w", encoding="utf-8") as f:
            json.dump([b.to_dict() for b in self.batch_records], f, ensure_ascii=False, indent=2)

    def check_batch_conflicts(self, batch_items: List[dict]) -> List[dict]:
        conflicts = []
        seen_applicant_day = {}

        for i, item in enumerate(batch_items):
            tpl_id = item.get("template_id")
            start_date = item.get("start_date")
            slot_idx = item.get("slot_index", 0)
            applicant = item.get("applicant", self.settings.current_user)

            template = self.get_template(tpl_id)
            if not template:
                conflicts.append({"index": i, "type": "模板不存在", "detail": f"模板ID={tpl_id}"})
                continue

            ins = self.get_instrument(template.instrument_id)
            if not ins:
                conflicts.append({"index": i, "type": "仪器不存在", "detail": f"模板={template.name}"})
                continue

            if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
                conflicts.append({"index": i, "type": "仪器冻结",
                                  "detail": f"仪器{ins.code}处于故障冻结状态，模板={template.name}"})
                continue

            if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
                conflicts.append({"index": i, "type": "校准过期",
                                  "detail": f"仪器{ins.code}校准已过期，模板={template.name}"})
                continue

            if not template.time_slots or slot_idx < 0 or slot_idx >= len(template.time_slots):
                conflicts.append({"index": i, "type": "时间段无效", "detail": f"模板={template.name}, 索引={slot_idx}"})
                continue

            ts = template.time_slots[slot_idx]
            start_dt_str = f"{start_date} {ts.start_time}:00"
            try:
                start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                conflicts.append({"index": i, "type": "日期格式错误",
                                  "detail": f"日期={start_date}, 模板={template.name}"})
                continue

            duration = timedelta(minutes=template.default_duration_minutes)
            end_dt = start_dt + duration
            end_dt_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            ok, msg = self._check_time_overlap(template.instrument_id, start_dt_str, end_dt_str)
            if not ok:
                conflicts.append({"index": i, "type": "时间重叠", "detail": f"模板={template.name}, {msg}"})

            for j in range(i + 1, len(batch_items)):
                other = batch_items[j]
                other_tpl_id = other.get("template_id")
                other_date = other.get("start_date")
                other_slot = other.get("slot_index", 0)
                other_tpl = self.get_template(other_tpl_id)
                if not other_tpl:
                    continue
                if other_tpl.instrument_id != template.instrument_id:
                    continue
                if not other_tpl.time_slots or other_slot < 0 or other_slot >= len(other_tpl.time_slots):
                    continue
                other_ts = other_tpl.time_slots[other_slot]
                other_start_str = f"{other_date} {other_ts.start_time}:00"
                try:
                    other_start = datetime.strptime(other_start_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                other_duration = timedelta(minutes=other_tpl.default_duration_minutes)
                other_end = other_start + other_duration
                if start_dt < other_end and end_dt > other_start:
                    conflicts.append({
                        "index": i,
                        "type": "批次内时间重叠",
                        "detail": f"第{i+1}项与第{j+1}项在仪器{ins.code}上时间重叠"
                    })

            key = (applicant, start_date)
            if key in seen_applicant_day:
                conflicts.append({
                    "index": i,
                    "type": "同一申请人撞单",
                    "detail": f"申请人{applicant}在{start_date}有多个预约"
                })
            else:
                for j in range(i + 1, len(batch_items)):
                    other = batch_items[j]
                    other_applicant = other.get("applicant", self.settings.current_user)
                    other_date = other.get("start_date")
                    if other_applicant == applicant and other_date == start_date:
                        conflicts.append({
                            "index": i,
                            "type": "同一申请人撞单",
                            "detail": f"申请人{applicant}在{start_date}有多个预约"
                        })
                        seen_applicant_day[key] = True
                        break

            if template.applicable_persons and applicant not in template.applicable_persons:
                conflicts.append({
                    "index": i,
                    "type": "负责人不匹配",
                    "detail": f"申请人{applicant}不在模板「{template.name}」的适用负责人列表中"
                })

        return conflicts

    def batch_create_reservations(self, batch_items: List[dict],
                                   operator: str, user_role: UserRole) -> Tuple[Optional[BatchRecord], List[str]]:
        batch_id = str(uuid.uuid4())
        success_ids: List[str] = []
        fail_msgs: List[str] = []
        item_results: List[BatchItemResult] = []

        conflicts = self.check_batch_conflicts(batch_items)
        conflict_map: Dict[int, List[str]] = {}
        for c in conflicts:
            idx = c.get("index", 0)
            ctype = c.get("type", "未知")
            detail = c.get("detail", "")
            if idx not in conflict_map:
                conflict_map[idx] = []
            conflict_map[idx].append(f"{ctype}: {detail}")

        for i, item in enumerate(batch_items):
            tpl_id = item.get("template_id")
            start_date = item.get("start_date")
            slot_idx = item.get("slot_index", 0)
            applicant = item.get("applicant", operator)

            template = self.get_template(tpl_id)
            ins = None
            ins_code = ""
            tpl_name = ""
            start_dt_str = ""
            if template:
                tpl_name = template.name
                ins = self.get_instrument(template.instrument_id)
                if ins:
                    ins_code = ins.code
                if template.time_slots and 0 <= slot_idx < len(template.time_slots):
                    ts = template.time_slots[slot_idx]
                    start_dt_str = f"{start_date} {ts.start_time}:00"

            if i in conflict_map:
                conflict_reasons = conflict_map[i]
                all_reasons = "; ".join(conflict_reasons)
                item_results.append(BatchItemResult(
                    index=i,
                    status="skipped",
                    template_name=tpl_name,
                    instrument_code=ins_code,
                    start_time=start_dt_str,
                    applicant=applicant,
                    reason=all_reasons,
                    reservation_id="",
                    template_snapshot=None,
                ))
                fail_msgs.append(f"第{i+1}项（{tpl_name or '未知模板'}）因冲突被跳过: {all_reasons}")
                continue

            if not template:
                reason = "模板不存在"
                item_results.append(BatchItemResult(
                    index=i, status="failed", reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            if not ins:
                reason = "仪器不存在"
                item_results.append(BatchItemResult(
                    index=i, status="failed", template_name=tpl_name, reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
                reason = f"仪器{ins_code}故障冻结"
                item_results.append(BatchItemResult(
                    index=i, status="failed", template_name=tpl_name,
                    instrument_code=ins_code, reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
                reason = f"仪器{ins_code}校准过期"
                item_results.append(BatchItemResult(
                    index=i, status="failed", template_name=tpl_name,
                    instrument_code=ins_code, reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            if not template.time_slots or slot_idx < 0 or slot_idx >= len(template.time_slots):
                reason = "时间段无效"
                item_results.append(BatchItemResult(
                    index=i, status="failed", template_name=tpl_name,
                    instrument_code=ins_code, reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            ts = template.time_slots[slot_idx]
            start_dt_str = f"{start_date} {ts.start_time}:00"
            try:
                start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                reason = "日期格式错误"
                item_results.append(BatchItemResult(
                    index=i, status="failed", template_name=tpl_name,
                    instrument_code=ins_code, start_time=start_dt_str,
                    reason=reason, applicant=applicant))
                fail_msgs.append(f"第{i+1}项：{reason}")
                continue

            duration = timedelta(minutes=template.default_duration_minutes)
            end_dt = start_dt + duration
            end_dt_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            snapshot = template.create_snapshot()
            snapshot_dict = snapshot.to_dict()

            res, msg = self.add_reservation(
                instrument_id=template.instrument_id,
                applicant=applicant,
                purpose=template.purpose,
                start_time=start_dt_str,
                end_time=end_dt_str,
                template_snapshot=snapshot,
                batch_id=batch_id,
                reminder_minutes=template.reminder_minutes,
            )
            if res:
                success_ids.append(res.id)
                item_results.append(BatchItemResult(
                    index=i, status="success",
                    template_name=tpl_name,
                    instrument_code=ins_code,
                    start_time=start_dt_str,
                    applicant=applicant,
                    reason="",
                    reservation_id=res.id,
                    template_snapshot=snapshot_dict,
                ))
            else:
                item_results.append(BatchItemResult(
                    index=i, status="failed",
                    template_name=tpl_name,
                    instrument_code=ins_code,
                    start_time=start_dt_str,
                    applicant=applicant,
                    reason=msg,
                    reservation_id="",
                    template_snapshot=None,
                ))
                fail_msgs.append(f"第{i+1}项：{msg}")

        success_count = len(success_ids)
        skipped_count = sum(1 for ir in item_results if ir.status == "skipped")
        failed_count = sum(1 for ir in item_results if ir.status == "failed")

        record = BatchRecord(
            id=batch_id,
            operator=operator,
            operator_role=user_role.value,
            operation=OperationType.BATCH_CREATE.value,
            total_count=len(batch_items),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            reservation_ids=success_ids,
            item_results=item_results,
            details="\n".join(fail_msgs) if fail_msgs else "",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.batch_records.insert(0, record)
        self.save_batch_records()

        self._add_operation_log(
            operation_type=OperationType.BATCH_CREATE.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"批量建单：成功{success_count}个，跳过{skipped_count}个，失败{failed_count}个",
            detail=f"批次ID={batch_id}",
        )

        return record, fail_msgs

    def batch_cancel_reservations(self, batch_id: str, operator: str,
                                   user_role: UserRole, reason: str) -> Tuple[bool, str]:
        if user_role != UserRole.ADMIN:
            return False, "仅管理员可执行批量撤销"

        batch = None
        for b in self.batch_records:
            if b.id == batch_id:
                batch = b
                break
        if not batch:
            return False, "批次记录不存在"

        if batch.operation != OperationType.BATCH_CREATE.value:
            return False, "该批次不是建单批次，无法撤销"

        if batch.is_cancelled:
            return False, "该批次已被撤销"

        cancelled_count = 0
        for rid in batch.reservation_ids:
            res = None
            for r in self.reservations:
                if r.id == rid:
                    res = r
                    break
            if not res:
                continue
            if res.status in [ReservationStatus.CANCELLED, ReservationStatus.COMPLETED]:
                continue

            res.status = ReservationStatus.CANCELLED
            res.cancel_reason = f"批量撤销：{reason}"
            res.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cancelled_count += 1

        batch.is_cancelled = True
        batch.cancel_operator = operator
        batch.cancel_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch.cancel_reason = reason
        self.save_batch_records()
        self.save_reservations()

        self._add_operation_log(
            operation_type=OperationType.BATCH_CANCEL.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"批量撤销：批次共{len(batch.reservation_ids)}个，实际撤销{cancelled_count}个",
            detail=f"批次ID={batch_id}, 原因={reason}",
        )

        return True, f"成功撤销 {cancelled_count} 个预约"

    def get_batch_record(self, batch_id: str) -> Optional[BatchRecord]:
        for b in self.batch_records:
            if b.id == batch_id:
                return b
        return None

    def list_batch_records(self, operation: str = "") -> List[BatchRecord]:
        results = self.batch_records.copy()
        if operation:
            results = [b for b in results if b.operation == operation]
        results.sort(key=lambda b: b.created_at, reverse=True)
        return results

    # ===== Operation Logs =====

    def load_operation_logs(self):
        if os.path.exists(self.operation_logs_file):
            with open(self.operation_logs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.operation_logs = [OperationLogEntry.from_dict(d) for d in data]
        else:
            self.operation_logs = []

    def save_operation_logs(self):
        with open(self.operation_logs_file, "w", encoding="utf-8") as f:
            json.dump([l.to_dict() for l in self.operation_logs], f, ensure_ascii=False, indent=2)

    def _add_operation_log(self, operation_type: str, operator: str,
                           operator_role: str, description: str, detail: str = ""):
        entry = OperationLogEntry(
            id=str(uuid.uuid4()),
            operation_type=operation_type,
            operator=operator,
            operator_role=operator_role,
            description=description,
            detail=detail,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.operation_logs.insert(0, entry)
        if len(self.operation_logs) > 500:
            self.operation_logs = self.operation_logs[:500]
        self.save_operation_logs()

    def list_operation_logs(self, operation_type: str = "", limit: int = 100) -> List[OperationLogEntry]:
        results = self.operation_logs.copy()
        if operation_type:
            results = [l for l in results if l.operation_type == operation_type]
        return results[:limit]

    # ===== Sandbox Draft Module =====

    def load_sandbox_drafts(self):
        if os.path.exists(self.sandbox_drafts_file):
            with open(self.sandbox_drafts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.sandbox_drafts = [SandboxDraft.from_dict(d) for d in data]
        else:
            self.sandbox_drafts = []

    def save_sandbox_drafts(self):
        with open(self.sandbox_drafts_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in self.sandbox_drafts], f, ensure_ascii=False, indent=2)

    def _parse_sandbox_csv(self, filepath: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        rows = []
        errors = []
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    line_num = idx + 2
                    instrument_code = row.get("仪器编号", "").strip()
                    applicant = row.get("申请人", "").strip()
                    purpose = row.get("用途", "").strip()
                    start_time = row.get("开始时间", "").strip()
                    end_time = row.get("结束时间", "").strip()
                    if not instrument_code:
                        errors.append(f"第{line_num}行：仪器编号为空")
                        continue
                    if not applicant:
                        errors.append(f"第{line_num}行：申请人为空")
                        continue
                    if not start_time or not end_time:
                        errors.append(f"第{line_num}行：时间为空")
                        continue
                    try:
                        datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                        datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        errors.append(f"第{line_num}行：时间格式错误，需YYYY-MM-DD HH:MM:SS")
                        continue
                    rows.append({
                        "instrument_code": instrument_code,
                        "applicant": applicant,
                        "purpose": purpose,
                        "start_time": start_time,
                        "end_time": end_time,
                    })
        except Exception as e:
            errors.append(f"文件读取失败：{str(e)}")
        return rows, errors

    def _parse_sandbox_json(self, filepath: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        rows = []
        errors = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                errors.append("JSON根元素必须是数组")
                return rows, errors
            for idx, item in enumerate(data):
                line_num = idx + 1
                instrument_code = item.get("instrument_code", "").strip()
                applicant = item.get("applicant", "").strip()
                purpose = item.get("purpose", "").strip()
                start_time = item.get("start_time", "").strip()
                end_time = item.get("end_time", "").strip()
                if not instrument_code:
                    errors.append(f"第{line_num}条：仪器编号为空")
                    continue
                if not applicant:
                    errors.append(f"第{line_num}条：申请人为空")
                    continue
                if not start_time or not end_time:
                    errors.append(f"第{line_num}条：时间为空")
                    continue
                try:
                    datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                    datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    errors.append(f"第{line_num}条：时间格式错误")
                    continue
                rows.append({
                    "instrument_code": instrument_code,
                    "applicant": applicant,
                    "purpose": purpose,
                    "start_time": start_time,
                    "end_time": end_time,
                })
        except Exception as e:
            errors.append(f"文件读取失败：{str(e)}")
        return rows, errors

    def _dedup_sandbox_rows(self, rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        seen = set()
        deduped = []
        dup_count = 0
        for r in rows:
            key = (r["instrument_code"], r["applicant"], r["start_time"], r["end_time"])
            if key in seen:
                dup_count += 1
                continue
            seen.add(key)
            deduped.append(r)
        return deduped, dup_count

    def _compute_item_preview(self, item_dict: Dict[str, Any], existing_times: Dict[str, List[Tuple[str, str]]]) -> Tuple[str, List[str]]:
        reasons = []
        instrument_code = item_dict["instrument_code"]
        applicant = item_dict["applicant"]
        start_time = item_dict["start_time"]
        end_time = item_dict["end_time"]

        ins = self.get_instrument_by_code(instrument_code)
        if not ins:
            return SandboxItemStatus.FORBIDDEN.value, [f"仪器编号「{instrument_code}」不存在"]

        if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
            reasons.append(f"仪器{ins.code}处于故障冻结状态")
        if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
            reasons.append(f"仪器{ins.code}校准已过期")

        try:
            new_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            new_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            if new_start >= new_end:
                reasons.append("开始时间必须早于结束时间")
        except ValueError:
            reasons.append("时间格式错误")
            return SandboxItemStatus.FORBIDDEN.value, reasons

        active_statuses = [
            ReservationStatus.CONFIRMED,
            ReservationStatus.IN_USE,
            ReservationStatus.PENDING_REVIEW,
        ]
        for r in self.reservations:
            if r.instrument_id != ins.id:
                continue
            if r.status not in active_statuses:
                continue
            try:
                r_start = datetime.strptime(r.start_time, "%Y-%m-%d %H:%M:%S")
                r_end = datetime.strptime(r.end_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if new_start < r_end and new_end > r_start:
                reasons.append(f"时间冲突：与{r.applicant}的预约重叠({r.start_time}~{r.end_time})")
                break

        ins_key = ins.id
        if ins_key in existing_times:
            for (es, ee) in existing_times[ins_key]:
                try:
                    es_dt = datetime.strptime(es, "%Y-%m-%d %H:%M:%S")
                    ee_dt = datetime.strptime(ee, "%Y-%m-%d %H:%M:%S")
                    if new_start < ee_dt and new_end > es_dt:
                        reasons.append(f"批次内时间冲突：与同批次其他项重叠")
                        break
                except ValueError:
                    pass

        for r in self.reservations:
            if r.applicant == applicant and r.status in active_statuses:
                try:
                    r_start = datetime.strptime(r.start_time, "%Y-%m-%d %H:%M:%S")
                    r_end = datetime.strptime(r.end_time, "%Y-%m-%d %H:%M:%S")
                    if new_start < r_end and new_end > r_start:
                        reasons.append(f"重复申请：{applicant}在同一时段已有预约")
                        break
                except ValueError:
                    pass

        is_admin = self.settings.current_role == UserRole.ADMIN
        if not is_admin:
            if ins.person_in_charge != applicant:
                reasons.append(f"权限限制：{applicant}不是仪器{ins.code}的负责人")

        if any("故障冻结" in r for r in reasons) or any("校准已过期" in r for r in reasons):
            return SandboxItemStatus.FORBIDDEN.value, reasons
        if any("不存在" in r for r in reasons):
            return SandboxItemStatus.FORBIDDEN.value, reasons
        if any("权限限制" in r for r in reasons):
            return SandboxItemStatus.FORBIDDEN.value, reasons

        if reasons:
            return SandboxItemStatus.NEEDS_CONFIRM.value, reasons

        return SandboxItemStatus.DIRECT_SUBMIT.value, []

    def import_to_sandbox_draft(self, filepath: str, draft_name: str,
                                 operator: str, user_role: UserRole) -> Tuple[Optional[SandboxDraft], List[str]]:
        errors = []
        if user_role != UserRole.ADMIN:
            errors.append("仅管理员可执行沙盘导入")
            return None, errors

        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".csv":
            rows, parse_errors = self._parse_sandbox_csv(filepath)
        elif ext == ".json":
            rows, parse_errors = self._parse_sandbox_json(filepath)
        else:
            errors.append(f"不支持的文件格式：{ext}")
            return None, errors

        errors.extend(parse_errors)
        if not rows:
            errors.append("没有可导入的有效数据行")
            return None, errors

        deduped, dup_count = self._dedup_sandbox_rows(rows)
        if dup_count > 0:
            errors.append(f"去重移除了{dup_count}条重复行")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        items = []
        for i, r in enumerate(deduped):
            items.append(SandboxDraftItem(
                index=i,
                instrument_code=r["instrument_code"],
                applicant=r["applicant"],
                purpose=r["purpose"],
                start_time=r["start_time"],
                end_time=r["end_time"],
            ))

        draft = SandboxDraft(
            id=str(uuid.uuid4()),
            name=draft_name,
            operator=operator,
            operator_role=user_role.value,
            items=items,
            source_file=os.path.basename(filepath),
            created_at=now,
            updated_at=now,
        )
        self.sandbox_drafts.insert(0, draft)
        self.save_sandbox_drafts()

        self._add_operation_log(
            operation_type=OperationType.SANDBOX_IMPORT.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"沙盘导入：草稿「{draft_name}」，{len(items)}条记录",
            detail=f"文件={filepath}，去重{dup_count}条",
        )

        return draft, errors

    def preview_sandbox_draft(self, draft_id: str) -> Optional[SandboxDraft]:
        draft = None
        for d in self.sandbox_drafts:
            if d.id == draft_id:
                draft = d
                break
        if not draft:
            return None

        all_times_map: Dict[str, List[Tuple[str, str]]] = {}
        for item in draft.items:
            ins = self.get_instrument_by_code(item.instrument_code)
            if ins:
                key = ins.id
                if key not in all_times_map:
                    all_times_map[key] = []
                all_times_map[key].append((item.start_time, item.end_time, item.index))

        for item in draft.items:
            other_times: Dict[str, List[Tuple[str, str]]] = {}
            ins = self.get_instrument_by_code(item.instrument_code)
            if ins and ins.id in all_times_map:
                other_list = [(s, e) for s, e, idx in all_times_map[ins.id] if idx != item.index]
                if other_list:
                    other_times[ins.id] = other_list

            saved_role = self.settings.current_role
            status, reasons = self._compute_item_preview({
                "instrument_code": item.instrument_code,
                "applicant": item.applicant,
                "start_time": item.start_time,
                "end_time": item.end_time,
            }, other_times)
            item.preview_status = status
            item.preview_reasons = reasons

        draft.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_sandbox_drafts()

        self._add_operation_log(
            operation_type=OperationType.SANDBOX_PREVIEW.value,
            operator=self.settings.current_user,
            operator_role=self.settings.current_role.value,
            description=f"沙盘预演：草稿「{draft.name}」",
            detail=f"总{len(draft.items)}条",
        )

        return draft

    def confirm_sandbox_draft(self, draft_id: str, operator: str,
                               user_role: UserRole) -> Tuple[Optional[SandboxDraft], List[str], Optional[str]]:
        draft = None
        for d in self.sandbox_drafts:
            if d.id == draft_id:
                draft = d
                break
        if not draft:
            return None, ["草稿不存在"], None

        if draft.is_submitted:
            return None, ["该草稿已提交"], None

        if user_role != UserRole.ADMIN:
            return None, ["仅管理员可确认提交沙盘草稿"], None

        if not any(it.preview_status for it in draft.items):
            draft = self.preview_sandbox_draft(draft_id)
            if not draft:
                return None, ["预演失败"], None

        batch_id = str(uuid.uuid4())
        success_ids = []
        fail_msgs = []
        item_results = []

        for item in draft.items:
            if item.preview_status == SandboxItemStatus.FORBIDDEN.value:
                item_results.append(BatchItemResult(
                    index=item.index, status="skipped",
                    instrument_code=item.instrument_code,
                    start_time=item.start_time, applicant=item.applicant,
                    reason="; ".join(item.preview_reasons),
                ))
                fail_msgs.append(f"第{item.index+1}项禁止提交：{'；'.join(item.preview_reasons)}")
                continue

            ins = self.get_instrument_by_code(item.instrument_code)
            if not ins:
                item_results.append(BatchItemResult(
                    index=item.index, status="failed",
                    instrument_code=item.instrument_code,
                    applicant=item.applicant, reason="仪器不存在",
                ))
                fail_msgs.append(f"第{item.index+1}项：仪器不存在")
                continue

            res, msg = self.add_reservation(
                instrument_id=ins.id,
                applicant=item.applicant,
                purpose=item.purpose,
                start_time=item.start_time,
                end_time=item.end_time,
                batch_id=batch_id,
            )
            if res:
                item.reservation_id = res.id
                success_ids.append(res.id)
                item_results.append(BatchItemResult(
                    index=item.index, status="success",
                    instrument_code=item.instrument_code,
                    start_time=item.start_time, applicant=item.applicant,
                    reservation_id=res.id,
                ))
            else:
                item_results.append(BatchItemResult(
                    index=item.index, status="failed",
                    instrument_code=item.instrument_code,
                    start_time=item.start_time, applicant=item.applicant,
                    reason=msg,
                ))
                fail_msgs.append(f"第{item.index+1}项：{msg}")

        success_count = len(success_ids)
        skipped_count = sum(1 for ir in item_results if ir.status == "skipped")
        failed_count = sum(1 for ir in item_results if ir.status == "failed")

        record = BatchRecord(
            id=batch_id,
            operator=operator,
            operator_role=user_role.value,
            operation=OperationType.SANDBOX_SUBMIT.value,
            total_count=len(draft.items),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            reservation_ids=success_ids,
            item_results=item_results,
            details="\n".join(fail_msgs) if fail_msgs else "",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.batch_records.insert(0, record)
        self.save_batch_records()

        draft.is_submitted = True
        draft.submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draft.submitted_batch_id = batch_id
        draft.updated_at = draft.submitted_at
        self.save_sandbox_drafts()

        self._add_operation_log(
            operation_type=OperationType.SANDBOX_SUBMIT.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"沙盘提交：草稿「{draft.name}」，成功{success_count}，跳过{skipped_count}，失败{failed_count}",
            detail=f"批次ID={batch_id}",
        )

        return draft, fail_msgs, batch_id

    def sandbox_batch_withdraw(self, draft_id: str, operator: str,
                                user_role: UserRole, reason: str) -> Tuple[bool, str]:
        if user_role != UserRole.ADMIN:
            return False, "仅管理员可执行沙盘撤回"

        draft = None
        for d in self.sandbox_drafts:
            if d.id == draft_id:
                draft = d
                break
        if not draft:
            return False, "草稿不存在"

        if not draft.is_submitted or not draft.submitted_batch_id:
            return False, "该草稿尚未提交，无需撤回"

        batch = self.get_batch_record(draft.submitted_batch_id)
        if not batch:
            return False, "关联的批次记录不存在"

        if batch.is_cancelled:
            return False, "该批次已被撤回"

        cancelled_count = 0
        for rid in batch.reservation_ids:
            res = None
            for r in self.reservations:
                if r.id == rid:
                    res = r
                    break
            if not res:
                continue
            if res.status in [ReservationStatus.CANCELLED, ReservationStatus.COMPLETED]:
                continue
            res.status = ReservationStatus.CANCELLED
            res.cancel_reason = f"沙盘撤回：{reason}"
            res.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cancelled_count += 1

        batch.is_cancelled = True
        batch.cancel_operator = operator
        batch.cancel_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch.cancel_reason = reason
        self.save_batch_records()
        self.save_reservations()

        draft.is_submitted = False
        draft.submitted_at = None
        draft.submitted_batch_id = None
        draft.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in draft.items:
            item.reservation_id = ""
        self.save_sandbox_drafts()

        self._add_operation_log(
            operation_type=OperationType.SANDBOX_WITHDRAW.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"沙盘撤回：草稿「{draft.name}」，实际撤销{cancelled_count}个预约",
            detail=f"原因={reason}",
        )

        return True, f"成功撤回 {cancelled_count} 个预约"

    def get_sandbox_draft(self, draft_id: str) -> Optional[SandboxDraft]:
        for d in self.sandbox_drafts:
            if d.id == draft_id:
                return d
        return None

    def list_sandbox_drafts(self) -> List[SandboxDraft]:
        results = self.sandbox_drafts.copy()
        results.sort(key=lambda d: d.created_at, reverse=True)
        return results

    def delete_sandbox_draft(self, draft_id: str) -> Tuple[bool, str]:
        idx = -1
        name = ""
        for i, d in enumerate(self.sandbox_drafts):
            if d.id == draft_id:
                idx = i
                name = d.name
                break
        if idx < 0:
            return False, "草稿不存在"
        if self.sandbox_drafts[idx].is_submitted:
            return False, "已提交的草稿不能删除，请先撤回"
        del self.sandbox_drafts[idx]
        self.save_sandbox_drafts()
        return True, ""

    def export_sandbox_preview(self, draft_id: str, filepath: str) -> Tuple[bool, str]:
        draft = self.get_sandbox_draft(draft_id)
        if not draft:
            return False, "草稿不存在"
        try:
            with open(filepath, "w", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "序号", "仪器编号", "申请人", "用途",
                    "开始时间", "结束时间", "预演状态", "原因"
                ])
                for item in draft.items:
                    reasons_str = "; ".join(item.preview_reasons) if item.preview_reasons else ""
                    writer.writerow([
                        item.index + 1,
                        item.instrument_code,
                        item.applicant,
                        item.purpose,
                        item.start_time,
                        item.end_time,
                        item.preview_status or "未预演",
                        reasons_str,
                    ])
            self._add_operation_log(
                operation_type=OperationType.SANDBOX_EXPORT.value,
                operator=self.settings.current_user,
                operator_role=self.settings.current_role.value,
                description=f"沙盘导出预演结果：草稿「{draft.name}」",
                detail=f"文件={filepath}",
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_sandbox_diff_report(self, draft_id: str, filepath: str) -> Tuple[bool, str]:
        draft = self.get_sandbox_draft(draft_id)
        if not draft:
            return False, "草稿不存在"
        try:
            direct_count = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.DIRECT_SUBMIT.value)
            confirm_count = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.NEEDS_CONFIRM.value)
            forbidden_count = sum(1 for it in draft.items if it.preview_status == SandboxItemStatus.FORBIDDEN.value)
            not_previewed = sum(1 for it in draft.items if not it.preview_status)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"沙盘差异报告 - 草稿「{draft.name}」\n")
                f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"操作人：{draft.operator}({draft.operator_role})\n")
                f.write(f"来源文件：{draft.source_file}\n")
                f.write(f"创建时间：{draft.created_at}\n\n")
                f.write(f"=== 统计概览 ===\n")
                f.write(f"总条目数：{len(draft.items)}\n")
                f.write(f"可直接提交：{direct_count}\n")
                f.write(f"需人工确认：{confirm_count}\n")
                f.write(f"禁止提交：{forbidden_count}\n")
                f.write(f"未预演：{not_previewed}\n\n")
                f.write(f"=== 明细 ===\n")
                for item in draft.items:
                    f.write(f"\n第{item.index+1}条：\n")
                    f.write(f"  仪器：{item.instrument_code}\n")
                    f.write(f"  申请人：{item.applicant}\n")
                    f.write(f"  用途：{item.purpose}\n")
                    f.write(f"  时间：{item.start_time} ~ {item.end_time}\n")
                    f.write(f"  预演状态：{item.preview_status or '未预演'}\n")
                    if item.preview_reasons:
                        for r in item.preview_reasons:
                            f.write(f"    - {r}\n")
                    if item.reservation_id:
                        f.write(f"  已入库预约ID：{item.reservation_id}\n")
                if draft.is_submitted:
                    f.write(f"\n=== 提交记录 ===\n")
                    f.write(f"提交时间：{draft.submitted_at}\n")
                    f.write(f"关联批次ID：{draft.submitted_batch_id}\n")

            self._add_operation_log(
                operation_type=OperationType.SANDBOX_EXPORT.value,
                operator=self.settings.current_user,
                operator_role=self.settings.current_role.value,
                description=f"沙盘导出差异报告：草稿「{draft.name}」",
                detail=f"文件={filepath}",
            )
            return True, ""
        except Exception as e:
            return False, str(e)


    # ===== Sample Data =====

    def init_sample_data(self):
        if self.instruments:
            return

        slots1 = [
            TimeSlot("09:00", "12:00"),
            TimeSlot("14:00", "17:00"),
        ]
        slots2 = [
            TimeSlot("08:00", "11:30"),
            TimeSlot("13:30", "18:00"),
        ]
        slots3 = [
            TimeSlot("10:00", "16:00"),
        ]

        today = date.today()

        self.add_instrument(
            code="INS-001",
            model="高效液相色谱仪 HPLC-2025",
            person_in_charge="张工",
            calibration_expiry=(today + timedelta(days=180)).strftime("%Y-%m-%d"),
            available_time_slots=slots1,
        )

        self.add_instrument(
            code="INS-002",
            model="气相色谱仪 GC-8860",
            person_in_charge="李工",
            calibration_expiry=(today + timedelta(days=30)).strftime("%Y-%m-%d"),
            available_time_slots=slots2,
        )

        self.add_instrument(
            code="INS-003",
            model="紫外可见分光光度计 UV-1800",
            person_in_charge="王工",
            calibration_expiry=(today - timedelta(days=15)).strftime("%Y-%m-%d"),
            available_time_slots=slots3,
        )

        self.add_instrument(
            code="INS-004",
            model="电子分析天平 ME204E",
            person_in_charge="张工",
            calibration_expiry=(today + timedelta(days=90)).strftime("%Y-%m-%d"),
            available_time_slots=[TimeSlot("08:30", "17:30")],
        )

        self.save_settings()