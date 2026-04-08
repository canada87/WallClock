from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import List

from ..database import get_db
from ..models import Setting, ServoPosition, Holiday, TimerAlarm

router = APIRouter()


# ── DB helpers ────────────────────────────────────────────────────────

def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def _set(db: Session, key: str, value) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))
    db.commit()


def _bump_config_version(db: Session) -> int:
    cv = int(_get(db, "config_version", "1")) + 1
    _set(db, "config_version", cv)
    return cv


# ── Settings ──────────────────────────────────────────────────────────

class SettingsIn(BaseModel):
    timezone_offset: int
    daylight_saving: int
    weekday_start:   int
    weekday_end:     int
    weekend_start:   int
    weekend_end:     int
    mid_offset:      int
    time_delay:      int
    time_delay2:     int
    active:          bool
    fetch_interval:  int = 30


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {
        "timezone_offset": int(_get(db, "timezone_offset", "1")),
        "daylight_saving":  int(_get(db, "daylight_saving",  "1")),
        "weekday_start":    int(_get(db, "weekday_start",    "8")),
        "weekday_end":      int(_get(db, "weekday_end",      "21")),
        "weekend_start":    int(_get(db, "weekend_start",    "11")),
        "weekend_end":      int(_get(db, "weekend_end",      "23")),
        "mid_offset":       int(_get(db, "mid_offset",       "150")),
        "time_delay":       int(_get(db, "time_delay",       "100")),
        "time_delay2":      int(_get(db, "time_delay2",      "20")),
        "active":           _get(db, "active", "1") == "1",
        "fetch_interval":   int(_get(db, "fetch_interval",   "30")),
    }


@router.put("/settings")
def save_settings(data: SettingsIn, db: Session = Depends(get_db)):
    for k, v in data.model_dump().items():
        _set(db, k, "1" if v is True else "0" if v is False else v)
    _bump_config_version(db)
    return {"ok": True}


# ── Servo config ──────────────────────────────────────────────────────

class ServoConfigIn(BaseModel):
    h_on:  List[int]
    h_off: List[int]
    m_on:  List[int]
    m_off: List[int]


class SingleServoIn(BaseModel):
    pos_on:  int
    pos_off: int


@router.get("/servo-config")
def get_servo_config(db: Session = Depends(get_db)):
    def _arr(board: str, which: str):
        rows = (db.query(ServoPosition)
                  .filter(ServoPosition.board == board)
                  .order_by(ServoPosition.channel)
                  .all())
        return [r.pos_on if which == "on" else r.pos_off for r in rows]

    return {
        "h_on":  _arr("H", "on"),
        "h_off": _arr("H", "off"),
        "m_on":  _arr("M", "on"),
        "m_off": _arr("M", "off"),
    }


@router.put("/servo-config")
def save_servo_config(data: ServoConfigIn, db: Session = Depends(get_db)):
    for ch in range(14):
        for board, on_arr, off_arr in [("H", data.h_on, data.h_off),
                                        ("M", data.m_on, data.m_off)]:
            row = (db.query(ServoPosition)
                     .filter(ServoPosition.board == board,
                             ServoPosition.channel == ch)
                     .first())
            if row:
                row.pos_on  = on_arr[ch]
                row.pos_off = off_arr[ch]
    cv = _bump_config_version(db)
    db.commit()
    return {"ok": True, "config_version": cv}


@router.put("/servo/{board}/{channel}")
def save_single_servo(board: str, channel: int, data: SingleServoIn,
                      db: Session = Depends(get_db)):
    if board not in ("H", "M") or not (0 <= channel <= 13):
        raise HTTPException(400, "Invalid board or channel")
    row = (db.query(ServoPosition)
             .filter(ServoPosition.board == board,
                     ServoPosition.channel == channel)
             .first())
    if not row:
        raise HTTPException(404, "Servo not found")
    row.pos_on  = data.pos_on
    row.pos_off = data.pos_off
    cv = _bump_config_version(db)
    db.commit()
    return {"ok": True, "config_version": cv}


# ── Holidays ──────────────────────────────────────────────────────────

class HolidayIn(BaseModel):
    date:        date
    description: str = ""


@router.get("/holidays")
def list_holidays(db: Session = Depends(get_db)):
    rows = db.query(Holiday).order_by(Holiday.date).all()
    return [{"id": r.id, "date": r.date.isoformat(),
             "description": r.description} for r in rows]


@router.post("/holidays")
def add_holiday(data: HolidayIn, db: Session = Depends(get_db)):
    if db.query(Holiday).filter(Holiday.date == data.date).first():
        raise HTTPException(400, "Data già presente")
    h = Holiday(date=data.date, description=data.description)
    db.add(h)
    db.commit()
    return {"id": h.id, "date": h.date.isoformat(), "description": h.description}


@router.delete("/holidays/{hid}")
def delete_holiday(hid: int, db: Session = Depends(get_db)):
    h = db.query(Holiday).filter(Holiday.id == hid).first()
    if not h:
        raise HTTPException(404, "Not found")
    db.delete(h)
    db.commit()
    return {"ok": True}


# ── Timer / Alarm ─────────────────────────────────────────────────────

class TimerIn(BaseModel):
    minutes: int


class AlarmIn(BaseModel):
    time: str  # "HH:MM"


@router.get("/timer-alarm")
def get_timer_alarm(db: Session = Depends(get_db)):
    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if not ta:
        return {"mode": "clock", "timer_end": None,
                "alarm_time": None, "ringing": False, "remaining_seconds": None}
    remaining = None
    if ta.mode == "timer" and ta.timer_end:
        secs = (ta.timer_end - datetime.utcnow()).total_seconds()
        remaining = max(0, int(secs))
    return {
        "mode":              ta.mode,
        "timer_end":         ta.timer_end.isoformat() if ta.timer_end else None,
        "alarm_time":        ta.alarm_time,
        "ringing":           ta.ringing,
        "remaining_seconds": remaining,
    }


@router.post("/timer")
def set_timer(data: TimerIn, db: Session = Depends(get_db)):
    end = datetime.utcnow() + timedelta(minutes=data.minutes)
    ta  = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if ta:
        ta.mode = "timer"; ta.timer_end = end
        ta.alarm_time = None; ta.ringing = False
    else:
        db.add(TimerAlarm(id=1, mode="timer", timer_end=end, ringing=False))
    db.commit()
    return {"ok": True}


@router.post("/alarm")
def set_alarm(data: AlarmIn, db: Session = Depends(get_db)):
    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if ta:
        ta.mode = "alarm"; ta.alarm_time = data.time
        ta.timer_end = None; ta.ringing = False
    else:
        db.add(TimerAlarm(id=1, mode="alarm", alarm_time=data.time, ringing=False))
    db.commit()
    return {"ok": True}


@router.delete("/timer-alarm")
def cancel_timer_alarm(db: Session = Depends(get_db)):
    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if ta:
        ta.mode = "clock"; ta.timer_end = None
        ta.alarm_time = None; ta.ringing = False
        db.commit()
    return {"ok": True}


@router.get("/clock-status")
def get_clock_status(db: Session = Depends(get_db)):
    """Stato corrente del clock per la UI — NON consuma il flag force_update."""
    from datetime import timedelta
    tz  = int(_get(db, "timezone_offset", "1"))
    dst = int(_get(db, "daylight_saving",  "1"))
    local = datetime.utcnow() + timedelta(hours=tz + dst)
    config_version = int(_get(db, "config_version", "1"))
    system_active  = _get(db, "active", "1") == "1"
    force_pending  = _get(db, "force_update", "0") == "1"
    last_esp_ping  = _get(db, "last_esp_ping", "")

    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if ta and ta.ringing:
        return {"active": True, "hour": 88, "minute": 88,
                "mode": "alarm_ringing", "config_version": config_version,
                "force_update_pending": force_pending, "last_esp_ping": last_esp_ping}
    if ta and ta.mode == "timer" and ta.timer_end:
        secs = (ta.timer_end - datetime.utcnow()).total_seconds()
        if secs > 0:
            h = int(secs // 3600); m = int((secs % 3600) // 60)
            return {"active": True, "hour": min(h, 99), "minute": m,
                    "mode": "timer", "config_version": config_version,
                    "force_update_pending": force_pending, "last_esp_ping": last_esp_ping}

    if not system_active:
        return {"active": False, "hour": local.hour, "minute": local.minute,
                "mode": "clock", "config_version": config_version,
                "force_update_pending": force_pending, "last_esp_ping": last_esp_ping}

    is_weekend = local.weekday() >= 5
    start = int(_get(db, "weekend_start" if is_weekend else "weekday_start",
                     "11" if is_weekend else "8"))
    end   = int(_get(db, "weekend_end"   if is_weekend else "weekday_end",
                     "23" if is_weekend else "21"))
    holiday = db.query(Holiday).filter(Holiday.date == local.date()).first()
    if holiday or not (start <= local.hour < end):
        return {"active": False, "hour": local.hour, "minute": local.minute,
                "mode": "clock", "config_version": config_version,
                "force_update_pending": force_pending, "last_esp_ping": last_esp_ping}

    return {"active": True, "hour": local.hour, "minute": local.minute,
            "mode": "clock", "config_version": config_version,
            "force_update_pending": force_pending, "last_esp_ping": last_esp_ping}


@router.post("/force-update")
def force_update(db: Session = Depends(get_db)):
    """Setta un flag: al prossimo poll dell'ESP32 l'ora viene aggiornata
    anche se fuori dall'orario configurato."""
    _set(db, "force_update", "1")
    return {"ok": True}


@router.post("/dismiss")
def dismiss_alarm(db: Session = Depends(get_db)):
    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()
    if ta:
        ta.ringing = False; ta.mode = "clock"
        ta.timer_end = None
        db.commit()
    return {"ok": True}
