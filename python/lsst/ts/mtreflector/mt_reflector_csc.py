# This file is part of ts_mtreflector.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["MTReflectorCsc", "run_mtreflector"]

import asyncio
import types
from typing import Any

from lsst.ts import salobj
from lsst.ts.xml.enums.MTReflector import MTReflectorStatus

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .mt_reflector import COMMUNICATION_TIMEOUT, MTReflectorController


class MTReflectorCsc(salobj.ConfigurableCsc):
    """MTReflector controller

    Parameters
    ----------
    config_dir : `None` or `str`, optional
        Directory of configuration files, or None for the standard
        configuration directory (obtained from `_get_default_config_dir`).
        This is provided for unit testing.
    initial_state : `State` or `int`, optional
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `State.STANDBY`, the default.
    override : `str`, optional
        Configuration override file to apply if ``initial_state`` is
        `State.DISABLED` or `State.ENABLED`.
    simulation_mode : `bool`, optional
        Simulation mode; one of:

        * False for normal operation
        * True for simulation

    Attributes
    ----------
    mtreflector_controller : `MTReflectorController`
        The controller representing the labjack controller
        which is controlling the reflector.
    """

    version = __version__
    valid_simulation_modes = (0, 1)

    def __init__(
        self,
        config_dir: None | str = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        override: str = "",
        simulation_mode: bool = False,
    ) -> None:
        self.reflector_controller = None
        self.should_be_connected = False

        self.config = None

        super().__init__(
            name="MTReflector",
            index=None,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_mtcalsys"

    @property
    def controller_connected(self) -> bool:
        """Return True if the LabJack is connected"""
        return (
            self.reflector_controller is not None
            and self.reflector_controller.connected
        )

    async def configure(self, config: Any) -> None:
        """Configure the CSC"""
        self.config = config

    async def handle_summary_state(self) -> None:
        """Override of the handle_summary_state function to
        create reflector controller object when enabled

        Raises
        ------
        ValueError
            If config is None
            If reflector Controller should be connected but isn't
        """
        self.log.info(f"handle_summary_state {salobj.State(self.summary_state).name}")
        if self.disabled_or_enabled and self.reflector_controller is None:
            if self.should_be_connected:
                await self.fault(
                    code=MTReflectorStatus.CONNECTION_ERROR.value,
                    report="reflector controller should be connected but isn't.",
                )
                raise RuntimeError("Reflector Controller should be connected but isn't")
            elif self.config is None:
                raise RuntimeError(
                    "Tried to create MTReflectorController without a configuration. "
                    "This is most likely a bug with the control sequence causing "
                    "the configuration step to be skipped. Try sending the CSC back "
                    "to STANDBY or OFFLINE and restarting it. You should report this issue."
                )
            self.reflector_controller = MTReflectorController(
                config=self.config,
                log=self.log,
                simulate=self.simulation_mode,
            )
        if self.disabled_or_enabled:
            await self.connect_mtreflector()
        else:
            await self.disconnect_mtreflector()

    async def connect_mtreflector(self) -> None:
        """Connect to the LabJack and get status.
        This method initiates the MTReflectorController as well

        Raises
        ------
        RuntimeError
            If there is no MTReflectorController object
        asyncio.TimeoutError
            If it takes longer than self.config.reflector.connect_timeout
        """
        # if self.controller_connected:
        #     await self.disconnect_mtreflector()
        if self.reflector_controller is None:
            raise RuntimeError(
                "CSC Tried to use reflector controller without a valid object"
            )

        async with asyncio.timeout(COMMUNICATION_TIMEOUT):
            await self.reflector_controller.connect()
        self.should_be_connected = True

    async def disconnect_mtreflector(self) -> None:
        """Disconnect to the LabJack & delete the MTReflectorController object

        Raises
        ------
        Exception
            If disconnect failed
        """
        try:
            if self.reflector_controller is None:
                return
            await self.reflector_controller.disconnect()
        except Exception as e:
            self.log.warning(f"Failed to disconnect reflector; continuing: {e!r}")

        # Delete the reflector controller because the config may change.
        self.reflector_controller = None
        self.should_be_connected = False

    async def close_tasks(self) -> None:
        """Close the CSC gracefully.

        Disconnects the labjack, deletes MTReflectorController object
        Then closes tasks.

        """
        await self.disconnect_mtreflector()
        await super().close_tasks()

    async def do_open(self, data: types.SimpleNamespace) -> None:
        """Switch open reflector.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Unused
        """
        self.assert_enabled()
        if self.reflector_controller is None:
            raise salobj.ExpectedError("Labjack not connected")
        await self.reflector_controller.actuate_mtreflector(
            actuate=MTReflectorStatus.OPEN
        )

        await self.evt_reflectorStatus.set_write(
            reflectorStatus=self.reflector_controller.labjack_item.status,
        )

    async def do_close(self, data: types.SimpleNamespace) -> None:
        """Switch close reflector.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Unused
        """
        self.assert_enabled()
        if self.reflector_controller is None:
            raise salobj.ExpectedError("Labjack not connected")

        await self.reflector_controller.actuate_mtreflector(
            actuate=MTReflectorStatus.CLOSE
        )

        await self.evt_reflectorStatus.set_write(
            reflectorStatus=self.reflector_controller.labjack_item.status,
        )


def run_mtreflector() -> None:
    """Run the MTReflector CSC."""
    asyncio.run(MTReflectorCsc.amain(index=None))