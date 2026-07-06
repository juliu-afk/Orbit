"""向后兼容 shim——offpeak_scheduler 已拆分为 offpeak/ 包。

保留此文件使旧 import 路径继续工作。
"""

from orbit.scheduler.offpeak import DeferredQueue, OffPeakScheduler, PeakWindowManager

# 模块级函数 re-export
from orbit.scheduler.offpeak.scheduler import estimate_window_capacity

__all__ = ["PeakWindowManager", "DeferredQueue", "OffPeakScheduler", "estimate_window_capacity"]
