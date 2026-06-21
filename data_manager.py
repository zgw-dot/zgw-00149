import json
import os
import uuid
from datetime import datetime, date
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


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

    def to_dict(self):
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d):
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
        )


@dataclass
class AppSettings:
    export_dir: str = ""
    filter_person: str = ""
    filter_status: str = ""
    ins_filter_person: str = ""
    ins_filter_status: str = ""
    current_user: str = "当前用户"
    current_role: UserRole = UserRole.NORMAL

    def to_dict(self):
        d = asdict(self)
        d["current_role"] = self.current_role.value
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            export_dir=d.get("export_dir", ""),
            filter_person=d.get("filter_person", ""),
            filter_status=d.get("filter_status", ""),
            ins_filter_person=d.get("ins_filter_person", ""),
            ins_filter_status=d.get("ins_filter_status", ""),
            current_user=d.get("current_user", "当前用户"),
            current_role=UserRole(d.get("current_role", UserRole.NORMAL.value)),
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

        self.instruments: List[Instrument] = []
        self.reservations: List[Reservation] = []
        self.settings: AppSettings = AppSettings()
        self.calibration_records: List[dict] = []

        self.load_all()

    def load_all(self):
        self.load_instruments()
        self.load_reservations()
        self.load_settings()
        self.load_calibration_records()
        self._check_calibration_expiry()

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
                        start_time: str, end_time: str) -> Tuple[Optional[Reservation], str]:
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
            import csv
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "预约ID", "仪器编号", "申请人", "用途",
                    "开始时间", "结束时间", "状态", "创建时间", "更新时间", "复核备注", "取消原因"
                ])
                for r in reservations:
                    writer.writerow([
                        r.id, r.instrument_code, r.applicant, r.purpose,
                        r.start_time, r.end_time, r.status.value,
                        r.created_at, r.updated_at,
                        r.review_note or "", r.cancel_reason or ""
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
            import csv
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
        from datetime import timedelta

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
