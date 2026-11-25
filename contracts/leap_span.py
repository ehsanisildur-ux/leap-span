# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from datetime import date, timedelta
import hashlib
import json
import re

from genlayer import *


IANA = "https://data.iana.org/time-zones/data/leap-seconds.list"
USNO = "https://maia.usno.navy.mil/ser7/tai-utc.dat"
NTP_EPOCH_DELTA = 2_208_988_800
EPOCH = date(1970, 1, 1)
DAY = 86_400
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
STAMP = r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_iana(text):
    rows = []
    expires = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#@"):
            match = re.fullmatch(r"#@\s+([0-9]{10})", line)
            if not match or expires is not None:
                raise ValueError("Invalid IANA expiry")
            expires = int(match[1]) - NTP_EPOCH_DELTA
        elif line and not line.startswith("#"):
            match = re.fullmatch(r"([0-9]{10})\s+([0-9]{1,2})(?:\s*#.*)?", line)
            if not match:
                raise ValueError("Invalid IANA transition")
            rows.append([int(match[1]) - NTP_EPOCH_DELTA, int(match[2])])
    if expires is None:
        raise ValueError("Missing IANA expiry")
    return rows, expires


def parse_usno(text):
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not re.match(r"[0-9]{4}\s+", line):
            raise ValueError("Invalid USNO row")
        if int(line[:4]) < 1972:
            continue
        match = re.fullmatch(
            r"([0-9]{4})\s+([A-Z]{3})\s+([0-9]{1,2})\s+=JD\s+([0-9]+)\.5\s+"
            r"TAI-UTC=\s+([0-9]{1,2})(?:\.0+)?\s+S\s+\+\s+"
            r"\(MJD\s+-\s+[0-9]+(?:\.[0-9]*)?\)\s+X\s+0(?:\.0+)?\s+S",
            line,
        )
        if not match:
            raise ValueError("Invalid post-1971 USNO row")
        day = date(int(match[1]), MONTHS.index(match[2]) + 1, int(match[3]))
        days = (day - EPOCH).days
        if int(match[4]) != 2_440_587 + days:
            raise ValueError("USNO calendar and Julian day disagree")
        rows.append([days * DAY, int(match[5])])
    return rows


def normalize(iana, usno):
    rows, expires = parse_iana(iana)
    if not 1 <= len(rows) <= 128 or rows[0] != [63_072_000, 10] or rows != parse_usno(usno):
        raise ValueError("Sources disagree on transitions")
    if not rows[-1][0] < expires <= 253_402_214_400 or expires % DAY:
        raise ValueError("Expiry outside supported coverage")
    for (before, old), (after, new) in zip(rows, rows[1:]):
        day = EPOCH + timedelta(days=after // DAY)
        if after <= before or after % DAY or day.day != 1 or abs(new - old) != 1:
            raise ValueError("Invalid leap transition")
    return {"expires_utc": expires, "transitions": rows, "sources": [IANA, USNO]}


def read_source(url):
    response = gl.nondet.web.get(url)
    if response.status != 200 or not 1 <= len(response.body) <= 16_384:
        raise ValueError("Invalid time-table response")
    return response.body.decode("utf-8")


def acquire():
    def observe():
        try:
            return canonical(normalize(read_source(IANA), read_source(USNO)))
        except Exception:
            raise gl.vm.UserError("Leap-second sources unavailable or inconsistent")

    def validate(leader):
        if not isinstance(leader, gl.vm.Return):
            return False
        try:
            return observe() == leader.calldata
        except Exception:
            return False

    return gl.vm.run_nondet_unsafe(observe, validate)


def tai_for_utc(stamp, table):
    match = re.fullmatch(STAMP, stamp)
    if not match:
        raise ValueError("Expected YYYY-MM-DDTHH:MM:SSZ")
    year, month, day, hour, minute, second = map(int, match.groups())
    midnight = (date(year, month, day) - EPOCH).days * DAY
    if hour > 23 or minute > 59 or second > 60 or (second == 60 and (hour, minute) != (23, 59)):
        raise ValueError("Invalid UTC time")
    rows = table["transitions"]
    utc = midnight + hour * 3600 + minute * 60 + min(second, 59)
    if not rows[0][0] <= utc < table["expires_utc"]:
        raise ValueError("UTC outside published coverage")
    current = next(offset for start, offset in reversed(rows) if start <= utc)
    next_offset = next((offset for start, offset in rows if start == utc + 1), current)
    if second == 60:
        if next_offset != current + 1:
            raise ValueError("No positive leap second at this UTC label")
        return utc + current + 1
    if next_offset == current - 1:
        raise ValueError("UTC label removed by negative leap second")
    return utc + current


def utc_for_tai(tai, table):
    rows = table["transitions"]
    if not rows[0][0] + rows[0][1] <= tai < table["expires_utc"] + rows[-1][1]:
        raise ValueError("TAI outside published coverage")
    for index in range(len(rows) - 1, -1, -1):
        start, offset = rows[index]
        if tai >= start + offset:
            utc = tai - offset
            day, seconds = divmod(utc, DAY)
            hour, seconds = divmod(seconds, 3600)
            minute, second = divmod(seconds, 60)
            return (EPOCH + timedelta(days=day)).isoformat() + f"T{hour:02d}:{minute:02d}:{second:02d}Z"
        if index and offset == rows[index - 1][1] + 1 and tai == start + offset - 1:
            return (EPOCH + timedelta(days=start // DAY - 1)).isoformat() + "T23:59:60Z"
    raise ValueError("TAI outside published coverage")


class LeapSpan(gl.Contract):
    table: str

    def __init__(self):
        self.table = ""

    @gl.public.write
    def sync(self) -> str:
        candidate = acquire()
        if self.table and candidate != self.table:
            previous, updated = json.loads(self.table), json.loads(candidate)
            old, new = previous["transitions"], updated["transitions"]
            if new[:len(old)] != old or updated["expires_utc"] < previous["expires_utc"]:
                raise gl.vm.UserError("Schedule would rewrite published coverage")
            if len(new) > len(old) and new[len(old)][0] <= previous["expires_utc"]:
                raise gl.vm.UserError("New leap overlaps published coverage")
        if self.table != candidate:
            self.table = candidate
        return hashlib.sha256(candidate.encode("utf-8")).hexdigest()

    @gl.public.view
    def get_table(self) -> dict | None:
        return json.loads(self.table) if self.table else None

    def require_table(self):
        if not self.table:
            raise gl.vm.UserError("No leap-second table")
        return json.loads(self.table)

    @gl.public.view
    def utc_to_tai(self, stamp: str) -> u64:
        try:
            return u64(tai_for_utc(stamp, self.require_table()))
        except ValueError as error:
            raise gl.vm.UserError(str(error))

    @gl.public.view
    def tai_to_utc(self, seconds: u64) -> str:
        try:
            return utc_for_tai(int(seconds), self.require_table())
        except ValueError as error:
            raise gl.vm.UserError(str(error))

    @gl.public.view
    def elapsed(self, start: str, end: str) -> i64:
        try:
            table = self.require_table()
            return i64(tai_for_utc(end, table) - tai_for_utc(start, table))
        except ValueError as error:
            raise gl.vm.UserError(str(error))
