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

__all__ = ["Controller"]
import asyncio
from enum import IntEnum
import functools
import logging
import types
from typing import Any, Callable

# Hide mypy error `Module "labjack" has no attribute "ljm"`.
from labjack import ljm  # type: ignore
from lsst.ts.xml.enums.MTReflector import MTReflectorStatus

# Time limit for communicating with the LabJack (seconds).
COMMUNICATION_TIMEOUT = 5
# Sleep time before trying to reconnect (seconds).
RECONNECT_WAIT = 60

class CIOStates(IntEnum):
    CLOSED = 14
    OPEN = 13

class Controller:
    """Implement MTReflector controller.

    Parameters
    ----------
    config : `types.SimpleNamespace`
        The configuration object.
    log : `logging.Logger`
        The log object.
    simulation_mode : `int`
        Controller in simulation mode?
    Attributes
    ----------
    handle : `None` or `int`
        The labjack ljm handle.
    state : `lsst.ts.xml.MTReflector.MTReflectorStatus`
        The current state of the reflector.
    device_type : `int`
        The labjack device type.
    connection_type : `int`
        The connection type to the labjack.
    identifier : `str`
        The host name of the labjack.
    simulation_mode : `int`
        Controller in simulation mode.
    log : `logging.Logger`
        The log object.
    config : `types.SimpleNamespace`
        The config object.
    fake_value : `None` or `float`
        The fake value used by simulation mode.
    """

    def __init__(
        self,
        config: types.SimpleNamespace,
        log: logging.Logger | None,
        simulation_mode: int,
    ) -> None:
        self.handle: None | int = None
        self.state: MTReflectorStatus = MTReflectorStatus.UNKNOWN
        self.device_type: int = ljm.constants.dtT4
        self.connection_type: int = ljm.constants.ctTCP
        self.identifier: None | str = None
        self.simulation_mode: int = simulation_mode
        if self.simulation_mode == 1:
            self.identifier = ljm.constants.DEMO_MODE
        self.log: logging.Logger = (
            log if log is not None else logging.getLogger(__name__)
        )
        self.config: types.SimpleNamespace = config
        self.fake_value: None | float = None
        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

        self.open_channel_name = 'CIO0'
        self.close_channel_name = 'CIO1'

    async def run(self, func: Callable, **kwargs: Any) -> Any:
        """Run the command.

        Paramters
        ---------
        func : `Callable`
            The function to run.
        kwargs : `Any`
            Any keyword arguments accepted by the function.

        Raises
        ------
        If the function is incorrect.
        If the execution fails.

        Returns
        -------
        `Any`
            Value returned if any.

        """
        partial = functools.partial(func, **kwargs)
        try:
            return await self._loop.run_in_executor(None, partial)
        except Exception:
            self.log.exception("Command failed.")

    @property
    def connected(self) -> bool:
        """Connected to labjack?"""
        return self.handle is not None

    def configure(self) -> None:
        """Configure the controller."""
        if not self.simulation_mode:
            self.identifier = self.config.identifier
        else:
            self.identifier = ljm.constants.DEMO_MODE

    async def connect(self) -> None:
        """Connect to the labjack.

        Raises
        ------
        `RuntimeError`
            When the connect call fails.
        """
        self.configure()
        self.handle = await self.run(
            ljm.open,
            deviceType=self.device_type,
            connectionType=self.connection_type,
            identifier=self.identifier,
        )
        await self.write_channel(name="DIO_INHIBIT", value=0x00000)
        await self.write_channel(name="DIO_ANALOG_ENABLE", value=0x00000)

    async def disconnect(self) -> None:
        """Disconnect from the labjack."""
        try:
            await self.run(ljm.close, handle=self.handle)
        except Exception:
            self.log.exception("Disconnect failed.")
        finally:
            self.handle = None

    async def read_channel(self, name: str) -> float:
        """Read the channel.
        Parameters
        ----------
        name : `str`
            The name of the channel to read.

        Raises
        ------
        RuntimeError
            When the labjack handle is None.
        """
        if self.handle is not None:
            return await self.run(ljm.eReadName, handle=self.handle, name=name)
        else:
            raise RuntimeError("Labjack is not connected.")

    async def write_channel(self, name: str, value: float | int) -> None:
        """Write the channel.

        Parameters
        ----------
        name : `str`
            The name of the channel to write.
        value : `float` or `int`
            The value to write.

        Raises
        ------
        RuntimeError
            When the labjack handle is None.
        """
        if self.handle is not None:
            return await self.run(
                ljm.eWriteName, handle=self.handle, name=name, value=value
            )
        else:
            raise RuntimeError("Labjack is not connected.")

    async def actuate(self, value: float | int) -> None:
        """Actuate the reflector screen.

        Parameters
        ----------
        value : `float` or `int`
            Open/close the reflector.
        """
        begin_cio_state = await self.read_channel("CIO_STATE")
        self.log.info(f"{begin_cio_state=}")
        match value:
            case 1:
                await self.write_channel(name=self.close_channel_name, value=0.0)
                await self.write_channel(name=self.open_channel_name, value=1.0)
            case 0:
                await self.write_channel(name=self.close_channel_name, value=1.0)
                await self.write_channel(name=self.open_channel_name, value=0.0)
        end_cio_state = await self.read_channel("CIO_STATE")
        if self.simulation_mode:
            end_cio_state = CIOStates.OPEN if value == 1 else CIOStates.CLOSED
        self.log.info(f"{end_cio_state=}")
        match end_cio_state:
            case CIOStates.OPEN:
                self.state = MTReflectorStatus.OPEN
            case CIOStates.CLOSED:
                self.state = MTReflectorStatus.CLOSE
            case _:
                raise RuntimeError("Reflector is in unknown state.")
