from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

import pytest


CONTRACT = "contracts/leap_span.py"
IANA = "https://data.iana.org/time-zones/data/leap-seconds.list"
USNO = "https://maia.usno.navy.mil/ser7/tai-utc.dat"
IANA_DATA = Path("fixtures/iana-leap-seconds.list").read_bytes()
USNO_DATA = Path("fixtures/usno-tai-utc.dat").read_bytes()
EPOCH = date(1970, 1, 1)
BASE = [("1972-01-01", 10)]
BEFORE = "2016-12-31T23:59:59Z"
LEAP = "2016-12-31T23:59:60Z"
AFTER = "2017-01-01T00:00:00Z"


@pytest.fixture
def contract(direct_deploy):
    return direct_deploy(CONTRACT, sdk_version="v0.2.16")


def provide(vm, iana=IANA_DATA, usno=USNO_DATA):
    for url, body in [(IANA, iana), (USNO, usno)]:
        vm.mock_web(re.escape(url), {"status": 200, "body": body})


def provide_schedule(vm, schedule, horizon):
    expires = (date.fromisoformat(horizon) - EPOCH).days * 86400 + 2208988800
    iana = [f"#@ {expires}"]
    usno = []
    months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    for stamp, offset in schedule:
        day = date.fromisoformat(stamp)
        days = (day - EPOCH).days
        iana.append(f"{days * 86400 + 2208988800} {offset}")
        usno.append(f"{day.year} {months[day.month - 1]} {day.day} =JD {2440587 + days}.5 "
                    f"TAI-UTC= {offset}.0 S + (MJD - {40587 + days}.) X 0.0 S")
    vm.clear_mocks()
    provide(vm, "\n".join(iana).encode(), "\n".join(usno).encode())


def test_live_fixture_round_trips_every_inserted_second(direct_vm, contract, direct_bob):
    assert contract.get_table() is None
    provide(direct_vm)
    with direct_vm.prank(direct_bob):
        first = contract.sync()
    assert direct_vm.run_validator() is True
    table = contract.get_table()
    expected = hashlib.sha256(json.dumps(table, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    assert first == expected
    assert contract.sync() == first
    assert len(table["transitions"]) == 28
    for (transition, offset) in table["transitions"][1:]:
        day = datetime(1970, 1, 1) + timedelta(seconds=transition)
        previous_date = (day - timedelta(days=1)).date().isoformat()
        after = day.isoformat() + "Z"
        before = previous_date + "T23:59:59Z"
        leap = previous_date + "T23:59:60Z"
        assert [int(contract.utc_to_tai(label)) for label in (before, leap, after)] == [
            transition + offset - 2, transition + offset - 1, transition + offset,
        ]
        assert contract.tai_to_utc(transition + offset - 1) == leap
        assert contract.elapsed(before, after) == 2
    assert [int(contract.utc_to_tai(stamp)) for stamp in (BEFORE, LEAP, AFTER)] == [
        1483228835, 1483228836, 1483228837,
    ]
    assert contract.elapsed(AFTER, BEFORE) == -2


def test_disagreeing_institutions_and_changed_validator_payload(direct_vm, contract):
    provide(direct_vm)
    contract.sync()
    original = contract.get_table()
    direct_vm.clear_mocks()
    provide(direct_vm, usno=USNO_DATA.replace(b"37.0", b"38.0"))
    assert direct_vm.run_validator() is False
    with direct_vm.expect_revert("Leap-second sources unavailable or inconsistent"):
        contract.sync()
    assert contract.get_table() == original


def test_sources_can_extend_but_cannot_rewrite_coverage(direct_vm, contract):
    provide_schedule(direct_vm, BASE, "1972-06-01")
    first = contract.sync()
    extended = BASE + [("1972-07-01", 11)]
    provide_schedule(direct_vm, extended, "1972-08-01")
    assert contract.sync() != first
    newest = contract.get_table()
    provide_schedule(direct_vm, BASE, "1972-09-01")
    with direct_vm.expect_revert("Schedule would rewrite published coverage"):
        contract.sync()
    provide_schedule(direct_vm, extended, "1972-07-02")
    with direct_vm.expect_revert("Schedule would rewrite published coverage"):
        contract.sync()
    assert contract.get_table() == newest


def test_transition_at_horizon_would_change_old_last_day(direct_vm, contract):
    provide_schedule(direct_vm, BASE, "1972-07-01")
    contract.sync()
    provide_schedule(direct_vm, BASE + [("1972-07-01", 9)], "1972-08-01")
    with direct_vm.expect_revert("New leap overlaps published coverage"):
        contract.sync()


def test_negative_leap_removes_utc_label_without_tai_gap(direct_vm, contract):
    provide_schedule(direct_vm, BASE + [("1972-07-01", 9)], "1972-08-01")
    contract.sync()
    before, after = "1972-06-30T23:59:58Z", "1972-07-01T00:00:00Z"
    assert contract.elapsed(before, after) == 1
    assert contract.tai_to_utc(contract.utc_to_tai(before)) == before
    assert contract.tai_to_utc(contract.utc_to_tai(after)) == after
    with direct_vm.expect_revert("UTC label removed by negative leap second"):
        contract.utc_to_tai("1972-06-30T23:59:59Z")


def test_unknown_invalid_and_outside_labels(direct_vm, contract):
    with direct_vm.expect_revert("No leap-second table"):
        contract.utc_to_tai(BEFORE)
    provide_schedule(direct_vm, BASE, "1972-07-01")
    contract.sync()
    with direct_vm.expect_revert("No positive leap second at this UTC label"):
        contract.utc_to_tai("1972-06-30T23:59:60Z")
    with direct_vm.expect_revert("UTC outside published coverage"):
        contract.utc_to_tai("1972-07-01T00:00:00Z")
    with direct_vm.expect_revert("TAI outside published coverage"):
        contract.tai_to_utc((date(1972, 7, 1) - EPOCH).days * 86400 + 10)
