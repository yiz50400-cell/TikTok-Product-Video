"""Employee-facing workspace support without business-domain dependencies."""

from .config import EmployeeConfigError, load_employee_config
from .models import EmployeeConfig, StoreBinding

__all__ = [
    "EmployeeConfig",
    "EmployeeConfigError",
    "StoreBinding",
    "load_employee_config",
]
