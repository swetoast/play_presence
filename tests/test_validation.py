from __future__ import annotations

import json
from pathlib import Path

import pytest

from play_presence import validation


def test_integer_file_reads_status_key(tmp_path: Path) -> None:
    path = tmp_path / "status"
    path.write_text("Name:\ttest\nVmRSS:\t1234 kB\n", encoding="ascii")
    assert validation._integer_file(path, "VmRSS") == 1234


def test_collect_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "_require_root", lambda: None)
    properties = {"MainPID": "77", "NRestarts": "2", "FragmentPath": "/etc/systemd/system/test.service"}
    monkeypatch.setattr(validation, "_service_property", lambda name: properties.get(name))
    monkeypatch.setattr(validation, "_sample", lambda pid: {"monotonic_seconds": 1.0, "pid": pid, "cpu_ticks": 1, "rss_kib": 100, "pss_kib": 90, "write_bytes": 0, "rom_fds": []})
    monkeypatch.setattr(validation.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(validation, "_run", lambda command, timeout=15: (0, "enabled" if "is-enabled" in command else "active" if "is-active" in command else "line1\nline2"))
    result = validation.collect(999999, 1)
    assert len(result["samples"]) == validation.MAX_SAMPLES
    assert result["service"]["enabled"] is True
    assert result["service"]["active"] is True
    assert result["service"]["restart_count_before"] == "2"
    assert result["service"]["restart_count_after"] == "2"


def test_collect_rejects_missing_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "_require_root", lambda: None)
    monkeypatch.setattr(validation, "_service_property", lambda name: "0")
    with pytest.raises(validation.ValidationError, match="no running main process"):
        validation.collect(0, 60)


def test_write_result_is_atomic(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    validation.write_result({"secret": None, "value": 1}, output)
    assert json.loads(output.read_text(encoding="utf-8"))["value"] == 1
    assert not output.with_name("result.json.tmp").exists()


def test_invalid_sampling_arguments() -> None:
    with pytest.raises(validation.ValidationError):
        validation.collect(-1, 60)
    with pytest.raises(validation.ValidationError):
        validation.collect(0, 0)


def test_summary_computes_growth_and_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation.os, "sysconf", lambda name: 100)
    samples = [
        {"monotonic_seconds": 10.0, "pid": 77, "cpu_ticks": 100, "rss_kib": 1000, "pss_kib": 900, "write_bytes": 4, "rom_fds": []},
        {"monotonic_seconds": 20.0, "pid": 77, "cpu_ticks": 101, "rss_kib": 1004, "pss_kib": 902, "write_bytes": 4, "rom_fds": []},
    ]
    result = validation._summary(samples)
    assert result["cpu_percent_over_window"] == 0.1
    assert result["rss_growth_kib"] == 4
    assert result["pss_growth_kib"] == 2
    assert result["write_bytes_growth"] == 0
    assert result["rom_file_descriptor_observed"] is False


def test_summary_reports_metric_completeness() -> None:
    samples = [{"monotonic_seconds": 1.0, "pid": 10, "cpu_ticks": 1, "rss_kib": 100, "pss_kib": None, "write_bytes": 0, "rom_fds": []}, {"monotonic_seconds": 2.0, "pid": 10, "cpu_ticks": 2, "rss_kib": 101, "pss_kib": None, "write_bytes": 0, "rom_fds": []}]
    result = validation._summary(samples)
    assert result["valid_sample_counts"] == {"cpu_ticks": 2, "rss_kib": 2, "pss_kib": 0, "write_bytes": 2}
    assert result["final_sample_complete"] is True


def test_summary_marks_missing_process_as_interrupted() -> None:
    samples = [{"monotonic_seconds": 1.0, "pid": 10, "cpu_ticks": 1, "rss_kib": 100, "pss_kib": 90, "write_bytes": 0, "rom_fds": []}, {"monotonic_seconds": 2.0, "pid": None, "cpu_ticks": None, "rss_kib": None, "pss_kib": None, "write_bytes": None, "rom_fds": []}]
    result = validation._summary(samples)
    assert result["interruption_reason"] == "service-unavailable"
    assert result["rss_growth_kib"] is None


def test_runtime_failure_record_is_bounded_and_secret_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "run/last-failure.json"
    monkeypatch.setattr(validation, "RUNTIME_FAILURE", path)
    validation.record_runtime_failure("detector", RuntimeError("secret-value-must-not-appear"))
    payload = path.read_text(encoding="utf-8")
    assert "RuntimeError" in payload
    assert "detector" in payload
    assert "secret-value-must-not-appear" not in payload
    assert path.stat().st_size <= validation.MAX_RUNTIME_FAILURE_BYTES
    result = validation.read_runtime_failure()
    assert result is not None
    assert result["available"] is True
    assert result["phase"] == "detector"
    assert result["exception_type"] == "RuntimeError"


def test_runtime_failure_missing_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "RUNTIME_FAILURE", tmp_path / "missing.json")
    assert validation.read_runtime_failure() is None


def test_runtime_failure_oversized_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "last-failure.json"
    path.write_bytes(b"x" * (validation.MAX_RUNTIME_FAILURE_BYTES + 1))
    monkeypatch.setattr(validation, "RUNTIME_FAILURE", path)
    assert validation.read_runtime_failure() == {"available": False, "error": "oversized"}


def test_assessment_applies_explicit_design_limits() -> None:
    summary = {
        "measurement_continuous": True,
        "sample_count": 2,
        "final_sample_complete": True,
        "cpu_percent_over_window": 0.0,
        "rss_max_kib": 30 * 1024,
        "rss_growth_kib": 0,
        "pss_growth_kib": 0,
        "write_bytes_growth": 0,
        "rom_file_descriptor_observed": False,
    }
    result = validation._assessment(summary, journal_available=True)
    assert result == {
        "continuous_window": True,
        "growth_window_usable": True,
        "cpu_within_negligible_limit": True,
        "cpu_zero_at_reported_precision": True,
        "rss_at_or_below_preferred_limit": True,
        "rss_below_release_ceiling": True,
        "rss_growth_zero": True,
        "pss_growth_zero": True,
        "process_write_growth_zero": True,
        "no_rom_descriptor_observed": True,
        "journal_capture_available": True,
    }


def test_assessment_negligible_cpu_is_the_gate_not_literal_zero() -> None:
    # A small non-zero idle CPU rate (periodic /proc scans) passes the gate
    # while the literal-zero flag reports False for reference.
    summary = {
        "measurement_continuous": True,
        "sample_count": 3,
        "final_sample_complete": True,
        "cpu_percent_over_window": 0.0416,
        "rss_max_kib": 26616,
        "rss_growth_kib": 0,
        "pss_growth_kib": 0,
        "write_bytes_growth": 0,
        "rom_file_descriptor_observed": False,
    }
    result = validation._assessment(summary, journal_available=False)
    assert result["cpu_within_negligible_limit"] is True
    assert result["cpu_zero_at_reported_precision"] is False


def test_assessment_flags_cpu_above_negligible_limit() -> None:
    summary = {
        "measurement_continuous": True,
        "sample_count": 2,
        "final_sample_complete": True,
        "cpu_percent_over_window": 1.5,
        "rss_max_kib": 26616,
        "rss_growth_kib": 0,
        "pss_growth_kib": 0,
        "write_bytes_growth": 0,
        "rom_file_descriptor_observed": False,
    }
    result = validation._assessment(summary, journal_available=True)
    assert result["cpu_within_negligible_limit"] is False


def test_assessment_uses_none_when_measurement_is_unavailable() -> None:
    summary = {
        "measurement_continuous": False,
        "sample_count": 1,
        "final_sample_complete": False,
        "cpu_percent_over_window": None,
        "rss_max_kib": None,
        "rss_growth_kib": None,
        "pss_growth_kib": None,
        "write_bytes_growth": None,
        "rom_file_descriptor_observed": False,
    }
    result = validation._assessment(summary, journal_available=False)
    assert result["growth_window_usable"] is False
    assert result["cpu_within_negligible_limit"] is None
    assert result["cpu_zero_at_reported_precision"] is None
    assert result["rss_below_release_ceiling"] is None
    assert result["rss_growth_zero"] is None
    assert result["journal_capture_available"] is False


def test_assessment_fails_rss_ceiling_at_40_mib() -> None:
    summary = {
        "measurement_continuous": True,
        "sample_count": 2,
        "final_sample_complete": True,
        "cpu_percent_over_window": 0.01,
        "rss_max_kib": 40 * 1024,
        "rss_growth_kib": 1,
        "pss_growth_kib": 1,
        "write_bytes_growth": 1,
        "rom_file_descriptor_observed": True,
    }
    result = validation._assessment(summary, journal_available=True)
    assert result["rss_at_or_below_preferred_limit"] is False
    assert result["rss_below_release_ceiling"] is False
    assert result["no_rom_descriptor_observed"] is False
