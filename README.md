# LeapSpan

LeapSpan computes UTC–TAI conversions and elapsed time from an independently reconciled leap-second schedule. It preserves the inserted `23:59:60Z` label and gives it its own TAI second.

[Contract source](contracts/leap_span.py) · [Direct tests](tests/direct/test_leap_span.py)

| UTC label | TAI seconds since 1970-01-01 00:00:00 TAI |
| --- | ---: |
| 2016-12-31T23:59:59Z | 1483228835 |
| 2016-12-31T23:59:60Z | 1483228836 |
| 2017-01-01T00:00:00Z | 1483228837 |

The first and last UTC labels in the table are **two elapsed seconds** apart.

## Agreement and history

The leader and every validator independently fetch IANA's leap-second file and the U.S. Naval Observatory's TAI−UTC table. The contract parses each format separately and requires them to agree on the complete transition sequence from 1972 onward. Validators require exact equality of that sequence and the IANA expiration. Dates are bounded by the published coverage. [IANA data](https://data.iana.org/time-zones/data/leap-seconds.list) · [USNO data](https://maia.usno.navy.mil/ser7/tai-utc.dat) · [UTC leap-second example](https://www.rfc-editor.org/rfc/rfc7164.html#section-4)

Anyone can synchronize the public timetable. A later sync can extend its expiration or append transitions beyond the previous horizon. An update that changes a covered UTC label or a historical transition reverts.

| Contract method | Result |
| --- | --- |
| `sync()` | Fetch and reconcile both tables, persist permitted coverage, and return the schedule digest. |
| `get_table()` | Return the effective UTC midnights, TAI offsets, exclusive UTC expiry, and source URLs. |
| `utc_to_tai(stamp)` | Convert a UTC label, including an announced positive leap second, to an integer TAI second. |
| `tai_to_utc(seconds)` | Reverse the conversion at one-second precision. |
| `elapsed(start, end)` | Return the signed elapsed SI seconds between two UTC labels. |

## Verify locally

```sh
python -m pip install -r requirements-dev.txt
genvm-lint download --version v0.2.16
genvm-lint check contracts/leap_span.py
python -m pytest tests/direct -q
```

Tests exercise all 27 historical positive leap seconds in the captured schedule, a synthetic negative leap, source disagreement, and attempts to revise published coverage.
