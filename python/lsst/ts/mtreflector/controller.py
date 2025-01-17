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

__all__ = ["LabjackChannel", "MTReflectorController"]
import asyncio
import functools
import logging
import types
from typing import Any

import yaml

# Hide mypy error `Module "labjack" has no attribute "ljm"`.
from labjack import ljm  # type: ignore
from lsst.ts import utils
from lsst.ts.ess.labjack import BaseLabJackDataClient
from lsst.ts.xml.enums.MTReflector import MTReflectorStatus

# Time limit for communicating with the LabJack (seconds).
COMMUNICATION_TIMEOUT = 5
# Sleep time before trying to reconnect (seconds).
RECONNECT_WAIT = 60


class LabjackChannel:
    """Class that represents a single port on the labjack.

    Parameters
    -------
    channel : `str`
        Channel of the labjack, e.g. AIO0, DIO5, etc...
    status : `MTReflectorStatus`, optional
        state of the reflector, default is UNKNOWN

    Raises
    ------
    TypeError
        If channel provided is not valid.
    """

    def __init__(
        self,
        channel: str,
        status: MTReflectorStatus = MTReflectorStatus.UNKNOWN,
    ):
        self.channel = channel
        self.status = status

        # modbus channel dictionary
        self.offset_dict = {
            "AIN": 0,
            "DAC": 1000,
            "DIO": 2000,
            "FIO": 2000,
            "EIO": 2008,
            "CIO": 2016,
            "MIO": 2020,
        }

        # protect against invalid entries
        if self.channel[:3] not in self.offset_dict or not self.channel[3:].isdigit():
            raise TypeError(f"Invalid labjack channel {self.channel}")

    def address(self) -> int:
        """Convert labjack channel name to their respective modbus address.

        Returns
        -------
        addNum : `int`
            Modbus address of the ljm channel.
        """
        addNum = int(self.channel[3:])

        # AIN are 32-bit wide, so their address takes up 2
        # addresses for the LSB/MSB
        if self.channel[:3] == "AIN" or self.channel[:3] == "DAC":
            addNum *= 2
        else:
            # all other DIO is standard 16-bit wide transmission
            addNum += self.offset_dict[self.channel[:3]]
        return addNum

    def check_valid(self, value: Any) -> bool:
        """Wrapper to if value written is valid for labjack channel

        Parameters
        ----------
        value : `Any`
            value to test

        Returns
        -------
        valid : `bool`
            True/False if channel type will accept value
        """
        if isinstance(value, MTReflectorStatus):
            if value == MTReflectorStatus.OPEN or value == MTReflectorStatus.CLOSE:
                return True
        return False

    def value(self, state_to_write: MTReflectorStatus) -> bool:
        """Wrapper to convert OPEN/CLOSE to the actual value to
            write in case of flipped GPIOs

        Parameters
        ----------
        status : `MTReflectorStatus`
            State to set the reflector to.

        Returns
        -------
        state : `bool`
            Proper True/False to send to labjack
        """
        if state_to_write == MTReflectorStatus.OPEN:
            return True
        else:
            return False


class MTReflectorController(BaseLabJackDataClient):
    """Class to handle opening of reflector connected to Labjack Interface

    Parameters
    ----------
    config : `types.SimpleNamespace`
        reflector-specific configuration.
    log : `logging.Logger` or 'None', optional
        Logger.
    simulate : `bool`, optional
        Run in simulation mode?
    """

    def __init__(
        self,
        config: types.SimpleNamespace,
        log: logging.Logger | None = None,
        status: MTReflectorStatus = MTReflectorStatus.UNKNOWN,
        simulate: bool = False,
    ) -> None:
        super().__init__(
            config=config, topics=config.topics, log=log, simulation_mode=simulate
        )

        self.config = config
        self.log = (
            log.getChild(type(self).__name__)
            if log is not None
            else logging.getLogger(type(self).__name__)
        )
        reflector_topic = next(
            topic
            for topic in self.config.topics
            if topic["topic_name"] == "reflector_item"
        )

        self.channel_name = reflector_topic["channel_name"]
        self.labjack_item = LabjackChannel(channel=self.channel_name, status=status)

        self.log.info(f"Opening reflector on channel {self.channel_name}")

        # Set if connected to the labjack and state data seen,
        # cleared otherwise.
        self.status_event = asyncio.Event()
        self.status_task = utils.make_done_future()

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return yaml.safe_load(
            """
schema: http://json-schema.org/draft-07/schema#
title: MTReflector v1
description: Schema for MTReflector
type: object
properties:
  device_type:
    description: LabJack model
    type: string
    default: T7
  connection_type:
    description: Connection type
    type: string
    default: TCP
  identifier:
    description: >-
        LabJack indentifier:
        * A host name or IP address if connection_type = TCP or WIFI
        * A serial number if connection_type = USB
        * For testing in an environment with only one LabJack you may use ANY
    type: string
  topics:
    description: >-
      Array of batches of relevant sensors.
    type: array
    minItems: 1
    items:
      types: object
      minItems: 1
      properties:
        topic_name:
            description: Casual name for the sensor cluster.
            type: string
        sensor_name:
            description: Value for the sensor_name field of the topic.
            type: string
        location:
            description: >-
                Location of sensors. A comma-separated list, with one item per non-null channel_name.
            type: string
        channel_name:
            description: >-
                LabJack channel names, in order of the field array.
            type: string
      required:
        - topic_name
        - sensor_name
        - location
        - channel_name
      additionalProperties: false
required:
  - device_type
  - connection_type
  - identifier
  - topics
additionalProperties: false
"""
        )

    async def run(self) -> None:
        """
        There is no use in constantly reading labjack status, so leave empty.
        common.BaseDataClient requires that we define it:
            TypeError: Can't instantiate abstract class
                        Reflector with abstract method run
        """
        pass

    async def read_data(self) -> None:
        """
        There is no use in constantly reading labjack status, so leave empty.
        common.BaseDataClient requires that we define it:
            TypeError: Can't instantiate abstract class
                        Reflector with abstract method read_data
        """
        pass

    def get_state(
        self,
    ) -> MTReflectorStatus:
        """Get the current MTReflectorStatus.

        Returns
        -------
        state : `MTReflectorStatus`
            State of reflector.
        """
        return self.labjack_item.status

    def _set_state(self, status: MTReflectorStatus) -> None:
        """Set status.

        Parameters
        ----------
        status : `MTReflectorStatus`
            Status to set the reflector to.

        Raises
        ------
        ValueError
            If identifier is not valid
        """
        if status not in [key.value for key in MTReflectorStatus]:
            raise ValueError(f"Status to set reflector to: {status} is not valid")
        self.labjack_item.status = status

    async def actuate_mtreflector(
        self,
        actuate: MTReflectorStatus,
    ) -> None:
        """Run a blocking function in a thread pool executor.

        Only one function will run at a time, because all calls use the same
        thread pool executor, which only has a single thread.

        Parameters
        ----------
        actuate : `MTReflectorStatus`
            open/close to actuate the reflector

        Raises
        ------
        asyncio.CancelledError
            If the blocking call was cancelled before finishing
        Exception
            If the blocking actuate reflector failed
        """
        if self.labjack_item.status == actuate:
            self.log.warning(f"Reflector is already of status: {actuate}")

        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    self._thread_pool,
                    functools.partial(
                        self._blocking_actuate_mtreflector,
                        actuate=actuate,
                    ),
                ),
                timeout=COMMUNICATION_TIMEOUT,
            )
        except asyncio.CancelledError:
            self.log.info(
                "run_in_thread cancelled while running "
                f"blocking function {self._blocking_actuate_mtreflector}."
            )
        except Exception:
            self.log.exception(
                f"Blocking function {self._blocking_actuate_mtreflector} failed."
            )
            raise

    def _blocking_actuate_mtreflector(self, actuate: MTReflectorStatus) -> None:
        """Tell labjack to actuate reflector.

        Parameters
        ----------
        actuate : `MTReflectorStatus`
            open/close to actuate the reflector

        Raises
        ------
        RuntimeError
            If the Labjack cannot connect
            If the Labjack reports back an error
        TypeError
            If actuate includes an item that is not OPEN or CLOSE
        """
        # confirm we have valid reflector values
        if actuate not in [
            MTReflectorStatus.OPEN,
            MTReflectorStatus.CLOSE,
        ]:
            raise TypeError(f"{actuate} is an invalid state to set the reflector to")

        # connect to labjack if we currently are disconnected
        if self.handle is None:
            try:
                self.log.info("Attempting to connect to Labjack...")
                self._blocking_connect()
            except RuntimeError:
                raise RuntimeError("Labjack can't connect")

        self.log.info(f"Switching Reflector to {actuate}")

        # form list of addresses and values to write
        addresses = [self.labjack_item.address()]
        values = [self.labjack_item.value(actuate)]
        try:
            ljm.eWriteAddresses(
                self.handle,
                len(addresses),
                addresses,
                [ljm.constants.UINT16 for _ in range(len(addresses))],
                values,
            )
        except ljm.LJMError as ljm_error:
            # Set up log string
            error_code = ljm_error.errorCode
            error_string = str(ljm_error)
            log_string = str(
                f"Labjack reported error#{error_code} during eWriteAddress"
                f"in actuate_mtreflector, dumping values: "
                f"actuate state: {actuate} "
                f"handle: {self.handle} addresses: {addresses} "
                f"data_type: {ljm.constants.UINT16} values_written: {values} "
                f"ljm_error_string: {error_string}"
            )

            # If error then raise except else its a warning so continue
            if error_code > ljm.errorcodes.WARNINGS_END:
                self.log.exception(log_string)
                raise RuntimeError(f"ljm reported error, see log: {log_string}")
            self.log.warning(log_string)

        # Update state
        self.labjack_item.status = actuate

    def _blocking_connect(self) -> None:
        """
        Connect and then read the specified channels.

        This makes sure that the configured channels can be read.

        Raises
        ------
        RuntimeError
            If each input channel configured at creation of this class,
            does not return a value from the labjack, i.e. configuration
            is not valid.
        """
        self.log.info("Attempting to connect to Labjack...")
        super()._blocking_connect()

        # Configure flexible IO to digital
        # The DIO_INHIBIT hex is what qualifies something as being digital.
        # 0 bit = digital. Read from LSB, ex: FIO0 is bit 0
        self.log.info("Setting all IO as DIO...")
        ljm.eWriteName(self.handle, "DIO_INHIBIT", 0x00000)
        ljm.eWriteName(self.handle, "DIO_ANALOG_ENABLE", 0x00000)

        # Read each input channel, to make sure the configuration is valid.
        input_channel_names = [self.labjack_item.channel]
        num_frames = len(input_channel_names)
        values = ljm.eReadNames(self.handle, num_frames, input_channel_names)
        if len(values) != len(input_channel_names):
            raise RuntimeError(
                f"len(input_channel_names)={input_channel_names} != len(values)={values}"
            )
