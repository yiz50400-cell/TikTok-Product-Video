from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoreBinding:
    store_alias: str
    ziniao_store_id: str
    tiktok_shop_id: str
    advertiser_id: str
    authorization_profile_id: str
    timezone: str

    @property
    def exact_scope(self) -> tuple[str, str, str]:
        return (
            self.authorization_profile_id,
            self.advertiser_id,
            self.tiktok_shop_id,
        )


@dataclass(frozen=True, slots=True)
class EmployeeConfig:
    employee_id: str
    display_name: str
    stores: tuple[StoreBinding, ...]
