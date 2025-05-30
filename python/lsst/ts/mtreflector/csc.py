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

from lsst.ts import salobj
from lsst.ts.xml.enums.MTReflector import MTReflectorStatus

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .controller import COMMUNICATION_TIMEOUT, Controller


class MTReflectorCsc(salobj.ConfigurableCsc):
    """Implement MTReflector CSC.

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
    simulation_mode : `int`, optional
        Simulation mode; one of:

        * 0 for normal operation
        * 1 for simulation

    Attributes
    ----------
    controller : `Controller`
        The controller representing the labjack controller
        which is controlling the reflector.
    should_be_connected : `bool`
        Should the controller be connected?
    config : `None` or `types.SimpleNamespace`
        Config object.
    """

    version = __version__
    valid_simulation_modes = (0, 1)

    def __init__(
        self,
        config_dir: None | str = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        override: str = "",
        simulation_mode: int = False,
    ) -> None:
        self.controller: None | Controller = None
        self.should_be_connected: bool = False

        self.config: None | types.SimpleNamespace = None

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
        """Get configuration package name."""
        return "ts_config_mtcalsys"

    @property
    def connected(self) -> bool:
        """Is the LabJack connected?"""
        return self.controller is not None and self.controller.connected

    async def configure(self, config: types.SimpleNamespace) -> None:
        """Configure the CSC.

        Parameters
        ----------
        config : `types.SimpleNameSpace`
            The config object.
        """
        self.config = config

    async def handle_summary_state(self) -> None:
        """Create connection to labjack when transitioning
        to disabled state and destroy connection when transitioning
        to standby state.

        Raises
        ------
        ValueError
            If config is None.
            If reflector Controller should be connected but isn't.
        """
        if self.disabled_or_enabled:
            if self.should_be_connected and not self.connected:
                await self.fault(
                    code=MTReflectorStatus.CONNECTION_ERROR.value,
                    report="reflector controller should be connected but isn't.",
                )
                return
            if not self.connected:

                if self.config is None:
                    msg = (
                        "Tried to create MTReflectorController without a configuration. "
                        "This is most likely a bug with the control sequence causing "
                        "the configuration step to be skipped. Try sending the CSC back "
                        "to STANDBY or OFFLINE and restarting it. You should report this issue."
                    )
                    await self.fault(code=1, report=msg)
                    return
                self.controller = Controller(
                    config=self.config,
                    log=self.log,
                    simulation_mode=self.simulation_mode,
                )
                try:
                    await self.connect()
                except Exception:
                    await self.fault(code=2, report="Failed to connect.")
                    return
        else:
            if self.controller is None:
                await self.evt_reflectorStatus.set_write(reflectorStatus=MTReflectorStatus.UNKNOWN)
            await self.disconnect()

    async def connect(self) -> None:
        """Connect to the LabJack and get status.

        This method initiates the MTReflectorController as well.

        Raises
        ------
        RuntimeError
            If there is no MTReflectorController object.
        asyncio.TimeoutError
            If it takes longer than self.config.reflector.connect_timeout.
        """
        if self.controller is None:
            raise RuntimeError("Reflector controller is None.")

        async with asyncio.timeout(COMMUNICATION_TIMEOUT):
            await self.controller.connect()
        self.should_be_connected = True
        await self.evt_reflectorStatus.set_write(reflectorStatus=MTReflectorStatus.CONNECTED)

    async def disconnect(self) -> None:
        """Disconnect from the labjack and reset the controller object.

        Raises
        ------
        Exception
            If disconnect failed.
        """
        try:
            if self.controller is None:
                return
            await self.controller.disconnect()
        except Exception as e:
            self.log.warning(f"Failed to disconnect reflector; continuing: {e!r}")
        finally:
            self.controller = None
            self.should_be_connected = False
            await self.evt_reflectorStatus.set_write(reflectorStatus=MTReflectorStatus.DISCONNECTED)

    async def close_tasks(self) -> None:
        """Close the CSC gracefully.

        Disconnects the labjack, deletes MTReflectorController object
        and closes tasks.

        """
        await self.disconnect()
        await super().close_tasks()

    async def do_open(self, data: types.SimpleNamespace) -> None:
        """Open reflector.

        Parameters
        ----------
        data : `lsst.ts.salobj.BaseMsgType`
            Unused.
        """
        self.assert_enabled()
        if self.controller is None:
            raise salobj.ExpectedError("Labjack not connected")
        try:
            await self.controller.actuate(value=1.0)
        except Exception:
            await self.fault(code=3, report="Open failed.")
            return

        await self.evt_reflectorStatus.set_write(
            reflectorStatus=self.controller.state,
        )

    async def do_close(self, data: types.SimpleNamespace) -> None:
        """Close reflector.

        Parameters
        ----------
        data : `lsst.ts.salobj.BaseMsgType`
            Unused.
        """
        self.assert_enabled()
        if self.controller is None:
            raise salobj.ExpectedError("Labjack not connected")

        try:
            await self.controller.actuate(value=0.0)
        except Exception:
            await self.fault(code=4, report="Close failed.")
            return

        await self.evt_reflectorStatus.set_write(
            reflectorStatus=self.controller.state,
        )


def run_mtreflector() -> None:
    """Run the MTReflector CSC."""
    asyncio.run(MTReflectorCsc.amain(index=None))
