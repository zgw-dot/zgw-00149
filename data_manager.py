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


class OperationType(str, Enum):
    BATCH_CREATE = "批量建单"
    BATCH_CANCEL = "批量撤销"
    TEMPLATE_IMPORT = "模板导入"
    TEMPLATE_EXPORT = "模板导出"
    TEMPLATE_CREATE = "模板创建"
    TEMPLATE_UPDATE = "模板更新"
    TEMPLATE_DELETE = "模板删除"


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
class BatchRecord:
    id: str
    operator: str
    operator_role: str
    operation: str
    total_count: int
    success_count: int
    failed_count: int
    reservation_ids: List[str]
    details: str
    created_at: str
    is_cancelled: bool = False
    cancel_operator: Optional[str] = None
    cancel_time: Optional[str] = None
    cancel_reason: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            operator=d["operator"],
            operator_role=d["operator_role"],
            operation=d["operation"],
            total_count=d["total_count"],
            success_count=d["success_count"],
            failed_count=d["failed_count"],
            reservation_ids=d.get("reservation_ids", []),
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

        self.instruments: List[Instrument] = []
        self.reservations: List[Reservation] = []
        self.settings: AppSettings = AppSettings()
        self.calibration_records: List[dict] = []
        self.templates: List[ReservationTemplate] = []
        self.batch_records: List[BatchRecord] = []
        self.operation_logs: List[OperationLogEntry] = []

        self.load_all()

    def load_all(self):
        self.load_instruments()
        self.load_reservations()
        self.load_settings()
        self.load_calibration_records()
        self.load_templates()
        self.load_batch_records()
        self.load_operation_logs()
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
                                   operator: str, user_role: UserRole) -> Tuple[BatchRecord, List[str]]:
        batch_id = str(uuid.uuid4())
        success_ids = []
        fail_msgs = []

        for i, item in enumerate(batch_items):
            tpl_id = item.get("template_id")
            start_date = item.get("start_date")
            slot_idx = item.get("slot_index", 0)
            applicant = item.get("applicant", operator)

            template = self.get_template(tpl_id)
            if not template:
                fail_msgs.append(f"第{i+1}项：模板不存在")
                continue

            ins = self.get_instrument(template.instrument_id)
            if not ins:
                fail_msgs.append(f"第{i+1}项：仪器不存在")
                continue

            if ins.status == InstrumentStatus.MALFUNCTION_FROZEN:
                fail_msgs.append(f"第{i+1}项：仪器{ins.code}故障冻结")
                continue
            if ins.status == InstrumentStatus.CALIBRATION_EXPIRED:
                fail_msgs.append(f"第{i+1}项：仪器{ins.code}校准过期")
                continue

            if not template.time_slots or slot_idx < 0 or slot_idx >= len(template.time_slots):
                fail_msgs.append(f"第{i+1}项：时间段无效")
                continue

            ts = template.time_slots[slot_idx]
            start_dt_str = f"{start_date} {ts.start_time}:00"
            try:
                start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                fail_msgs.append(f"第{i+1}项：日期格式错误")
                continue

            duration = timedelta(minutes=template.default_duration_minutes)
            end_dt = start_dt + duration
            end_dt_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            snapshot = template.create_snapshot()

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
            else:
                fail_msgs.append(f"第{i+1}项：{msg}")

        record = BatchRecord(
            id=batch_id,
            operator=operator,
            operator_role=user_role.value,
            operation=OperationType.BATCH_CREATE.value,
            total_count=len(batch_items),
            success_count=len(success_ids),
            failed_count=len(batch_items) - len(success_ids),
            reservation_ids=success_ids,
            details="\n".join(fail_msgs) if fail_msgs else "",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.batch_records.insert(0, record)
        self.save_batch_records()

        self._add_operation_log(
            operation_type=OperationType.BATCH_CREATE.value,
            operator=operator,
            operator_role=user_role.value,
            description=f"批量建单：成功{len(success_ids)}个，失败{len(batch_items) - len(success_ids)}个",
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