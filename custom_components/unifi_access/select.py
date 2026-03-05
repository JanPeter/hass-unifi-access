"""Platform for select integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiAccessCoordinator
from .door import UnifiAccessDoor
from .hub import UnifiAccessHub

_LOGGER = logging.getLogger(__name__)

NONE_SCHEDULE = "None"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add select entity for passed config entry."""
    hub: UnifiAccessHub = hass.data[DOMAIN][config_entry.entry_id]

    coordinator = hass.data[DOMAIN]["coordinator"]

    entities = []

    if hub.supports_door_lock_rules:
        entities.extend(
            TemporaryLockRuleSelectEntity(coordinator, door_id)
            for door_id in coordinator.data
        )

    if hub.schedules:
        entities.extend(
            UnlockScheduleSelectEntity(coordinator, door_id, hub)
            for door_id in coordinator.data
        )

    async_add_entities(entities)


class TemporaryLockRuleSelectEntity(CoordinatorEntity, SelectEntity):
    """Unifi Access Temporary Lock Rule Select."""

    _attr_translation_key = "door_lock_rules"
    _attr_has_entity_name = True
    should_poll = False

    def __init__(
        self,
        coordinator: UnifiAccessCoordinator,
        door_id: str,
    ) -> None:
        """Initialize Unifi Access Door Lock Rule."""
        super().__init__(coordinator, context="lock_rule")
        self.door: UnifiAccessDoor = self.coordinator.data[door_id]
        self._attr_unique_id = f"door_lock_rule_{door_id}"
        self._attr_options = [
            "",
            "keep_lock",
            "keep_unlock",
            "custom",
            "reset",
            "lock_early",
        ]
        self._update_options()

    @property
    def device_info(self) -> DeviceInfo:
        """Get Unifi Access Door Lock device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.door.id)},
            name=self.door.name,
            model=self.door.hub_type,
            manufacturer="Unifi",
        )

    @property
    def current_option(self) -> str:
        "Get current option."
        return self.door.lock_rule

    def _update_options(self):
        "Update Door Lock Rules."
        self._attr_current_option = self.coordinator.data[self.door.id].lock_rule
        if (
            self._attr_current_option != "schedule"
            and "lock_early" in self._attr_options
        ):
            self._attr_options.remove("lock_early")
        else:
            self._attr_options.append("lock_early")

    async def async_select_option(self, option: str) -> None:
        "Select Door Lock Rule."
        await self.hass.async_add_executor_job(self.door.set_lock_rule, option)

    async def async_added_to_hass(self) -> None:
        """Add Unifi Access Door Rule Lock Select to Home Assistant."""
        await super().async_added_to_hass()
        self.door.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove Unifi Access Rule Lock Select from Home Assistant."""
        await super().async_will_remove_from_hass()
        self.door.remove_callback(self.async_write_ha_state)

    def _handle_coordinator_update(self) -> None:
        """Handle Unifi Access Door Lock updates from coordinator."""
        self._update_options()
        self.async_write_ha_state()


class UnlockScheduleSelectEntity(CoordinatorEntity, SelectEntity):
    """Select entity to pick which schedule controls the unlock duration for a door."""

    _attr_translation_key = "unlock_schedule"
    _attr_has_entity_name = True
    should_poll = False

    def __init__(
        self,
        coordinator: UnifiAccessCoordinator,
        door_id: str,
        hub: UnifiAccessHub,
    ) -> None:
        """Initialize Unlock Schedule Select."""
        super().__init__(coordinator, context="unlock_schedule")
        self.door: UnifiAccessDoor = self.coordinator.data[door_id]
        self._hub = hub
        self._attr_unique_id = f"unlock_schedule_{door_id}"
        self._schedule_map: dict[str, str] = {}
        self._build_options()

    def _build_options(self):
        """Build schedule options from hub schedules."""
        self._schedule_map = {}
        options = [NONE_SCHEDULE]
        for schedule in self._hub.schedules:
            name = schedule.get("name", schedule["id"])
            self._schedule_map[name] = schedule["id"]
            options.append(name)
        self._attr_options = options
        if self.door.schedule_id:
            # Find the name for the current schedule_id
            current_name = next(
                (name for name, sid in self._schedule_map.items()
                 if sid == self.door.schedule_id),
                NONE_SCHEDULE,
            )
            self._attr_current_option = current_name
        else:
            self._attr_current_option = NONE_SCHEDULE

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.door.id)},
            name=self.door.name,
            model=self.door.hub_type,
            manufacturer="Unifi",
        )

    @property
    def current_option(self) -> str:
        """Get current option."""
        if self.door.schedule_id:
            return next(
                (name for name, sid in self._schedule_map.items()
                 if sid == self.door.schedule_id),
                NONE_SCHEDULE,
            )
        return NONE_SCHEDULE

    async def async_select_option(self, option: str) -> None:
        """Select a schedule."""
        if option == NONE_SCHEDULE:
            self.door.schedule_id = None
            _LOGGER.info("Cleared unlock schedule for door %s", self.door.name)
        else:
            schedule_id = self._schedule_map.get(option)
            if schedule_id:
                self.door.schedule_id = schedule_id
                _LOGGER.info(
                    "Set unlock schedule for door %s to %s (%s)",
                    self.door.name, option, schedule_id,
                )

    async def async_added_to_hass(self) -> None:
        """Add to Home Assistant."""
        await super().async_added_to_hass()
        self.door.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove from Home Assistant."""
        await super().async_will_remove_from_hass()
        self.door.remove_callback(self.async_write_ha_state)
