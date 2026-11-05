from __future__ import annotations

import ctypes
import gc
import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from fastparquet import ParquetFile


def _windows_working_set_bytes() -> tuple[int, int]:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def _working_set_bytes() -> int:
    if os.name == "nt":
        return _windows_working_set_bytes()[0]
    try:
        with Path("/proc/self/statm").open(encoding="ascii") as handle:
            resident_pages = int(handle.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        import resource

        maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(maximum * (1 if os.uname().sysname == "Darwin" else 1024))


def _peak_working_set_bytes() -> int:
    if os.name == "nt":
        return _windows_working_set_bytes()[1]
    try:
        import resource

        maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(maximum * (1 if os.uname().sysname == "Darwin" else 1024))
    except (OSError, ValueError, AttributeError, ImportError):
        return _working_set_bytes()


def process_working_set_bytes(process_id: int) -> int:
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        handle = kernel32.OpenProcess(0x0400 | 0x0010, 0, process_id)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(counters.PeakWorkingSetSize)
        finally:
            kernel32.CloseHandle(handle)

    try:
        with Path(f"/proc/{process_id}/statm").open(encoding="ascii") as handle:
            resident_pages = int(handle.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return 0


class ReportingStep:
    """Measure and log the files and resource use for one reporting step."""

    def __init__(
        self,
        logger: logging.Logger,
        name: str,
        files: Iterable[Path],
        columns: Optional[Iterable[str]] = None,
    ) -> None:
        self.logger = logger
        self.name = name
        self.files = [Path(path) for path in files]
        self.columns = list(columns or [])
        self.rows = 0
        self.row_groups = 0
        self.source_columns = 0
        self.metadata_recorded = False
        self.bytes_read = 0
        self.seconds = 0.0
        self.peak_rss_bytes = 0
        self._stop = threading.Event()
        self._sampler: Optional[threading.Thread] = None

    def __enter__(self) -> "ReportingStep":
        self._sample_rss()
        self._sampler = threading.Thread(
            target=self._sample_until_stopped,
            name=f"report-rss-{self.name}",
            daemon=True,
        )
        self._sampler.start()
        self._started = time.perf_counter()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.seconds = time.perf_counter() - self._started
        self._stop.set()
        if self._sampler is not None:
            self._sampler.join(timeout=1.0)
        self._sample_rss()
        names = []
        for path in self.files:
            names.append(str(path))
            try:
                self.bytes_read += path.stat().st_size
            except OSError:
                continue
            if path.suffix.lower() != ".parquet" or self.metadata_recorded:
                continue
            try:
                try:
                    import pyarrow as pyarrow
                    import pyarrow.parquet as pyarrow_parquet
                except ImportError:
                    pyarrow = None
                    parquet = ParquetFile(path)
                    row_groups = len(parquet.row_groups)
                    source_columns = len(parquet.columns)
                else:
                    parquet = pyarrow_parquet.ParquetFile(path)
                    row_groups = parquet.metadata.num_row_groups
                    source_columns = len(parquet.schema.names)
                self.row_groups += row_groups
                self.source_columns = max(self.source_columns, source_columns)
                if pyarrow is not None:
                    del parquet
                    gc.collect()
                    pyarrow.default_memory_pool().release_unused()
            except (OSError, ValueError, ImportError):
                self.logger.exception(
                    "Could not read reporting metadata for %s", path
                )
        self._sample_rss()
        columns = self.columns
        if not columns and self.source_columns:
            columns = [f"<{self.source_columns} source columns>"]
        self.logger.info(
            "Reporting step=%s files=%s rows=%d row_groups=%d columns=%d "
            "source_columns=%d bytes=%d seconds=%.3f peak_rss_mb=%.1f",
            self.name,
            ",".join(names) or "-",
            self.rows,
            self.row_groups,
            len(columns),
            self.source_columns,
            self.bytes_read,
            self.seconds,
            self.peak_rss_bytes / (1024 * 1024),
        )

    def record_parquet_metadata(
        self, row_groups: int, source_columns: int
    ) -> None:
        self.row_groups += row_groups
        self.source_columns = max(self.source_columns, source_columns)
        self.metadata_recorded = True

    def _sample_rss(self) -> None:
        try:
            self.peak_rss_bytes = max(self.peak_rss_bytes, _working_set_bytes())
        except (OSError, AttributeError, ImportError):
            self.logger.exception("Could not sample RSS for reporting step %s", self.name)

    def _sample_until_stopped(self) -> None:
        while not self._stop.wait(0.1):
            self._sample_rss()
