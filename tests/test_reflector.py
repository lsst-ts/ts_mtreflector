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

import asyncio
import contextlib
import logging
import pathlib
import types
import unittest
from collections.abc import AsyncGenerator
from typing import TypeAlias

import yaml
from jsonschema.exceptions import ValidationError
from lsst.ts import mtreflector, salobj
from lsst.ts.xml.enums.MTReflector import MTReflectorStatus

logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)

PathT: TypeAlias = str | pathlib.Path

# Standard timeout in seconds
TIMEOUT = 5


class DataClientTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.log = logging.getLogger()
        self.data_dir = pathlib.Path(__file__).parent / "data" / "config"

        config_schema = mtreflector.MTReflectorController.get_config_schema()
        self.validator = salobj.DefaultingValidator(config_schema)

    @contextlib.asynccontextmanager
    async def make_topics(self) -> AsyncGenerator[types.SimpleNamespace, None]:
        salobj.set_random_lsst_dds_partition_prefix()
        async with salobj.make_mock_write_topics(
            name="ESS", attr_names=["mtReflectorController"]
        ) as topics:
            yield topics

    async def test_constructor_good_full(self) -> None:
        """Construct with good_full.yaml and compare values to that file.

        Use the default simulation_mode.
        """
        config = self.get_config("config.yaml")
        mtreflector_client = mtreflector.MTReflectorController(
            config=config,
            log=self.log,
            simulate=True,
        )
        assert mtreflector_client.simulation_mode == 1
        assert isinstance(mtreflector_client.log, logging.Logger)
        topic = config.topics[0]
        assert topic["channel_name"] == "DIO1"

    async def test_state_change(self) -> None:
        config = self.get_config("config.yaml")
        mtreflector_client = mtreflector.MTReflectorController(
            config=config,
            log=self.log,
            simulate=True,
        )

        # status should be unknown on creation
        assert mtreflector_client.labjack_item.status is MTReflectorStatus.UNKNOWN

        # make sure it asserts if we give it invalid state
        with self.assertRaises(ValueError):
            mtreflector_client._set_state("bogus")

        # accept proper values and go by multiple identifiers
        mtreflector_client._set_state(MTReflectorStatus.OPEN)
        assert mtreflector_client.get_state() is MTReflectorStatus.OPEN

        mtreflector_client._set_state(MTReflectorStatus.CLOSE)
        assert mtreflector_client.get_state() is MTReflectorStatus.CLOSE

    async def test_connecting(self) -> None:
        config = self.get_config("config.yaml")
        mtreflector_client = mtreflector.MTReflectorController(
            config=config,
            log=self.log,
            simulate=True,
        )

        # test connection and disconnection
        await mtreflector_client.connect()
        await mtreflector_client.disconnect()

    async def test_mtreflector_actuation(self) -> None:
        config = self.get_config("config.yaml")
        mtreflector_client = mtreflector.MTReflectorController(
            config=config,
            log=self.log,
            simulate=True,
        )

        # status should be unknown on creation
        assert mtreflector_client.labjack_item.status is MTReflectorStatus.UNKNOWN

        # confirm that we cannot switch mtreflector to state that
        # isn't open/close
        for state in MTReflectorStatus:
            if state not in [MTReflectorStatus.OPEN, MTReflectorStatus.CLOSE]:
                with self.assertRaises(TypeError):
                    await asyncio.wait_for(
                        mtreflector_client.actuate_mtreflector(state), timeout=5
                    )

        # accept proper values and go by multiple identifiers
        await asyncio.wait_for(
            mtreflector_client.actuate_mtreflector(MTReflectorStatus.OPEN), timeout=5
        )
        assert mtreflector_client.get_state() is MTReflectorStatus.OPEN

        await mtreflector_client.actuate_mtreflector(MTReflectorStatus.CLOSE)
        assert mtreflector_client.get_state() is MTReflectorStatus.CLOSE

    async def test_bad_configs(self) -> None:
        # test various bad yamls, missing required values
        for i in range(6):
            with self.assertRaises(ValidationError):
                self.get_config(f"bad_config{i}.yaml")

    async def test_labjack_channel_class(self) -> None:
        bad_channels = {"AIN", "AINO1"}

        for chan in bad_channels:
            with self.assertRaises(TypeError):
                mtreflector.LabjackChannel(serial_number="ASDF", channel=chan)

    def get_config(self, filename: PathT) -> types.SimpleNamespace:
        """Get a config dict from tests/data.

        This should always be a good config,
        because validation is done by the ESS CSC,
        not the data client.

        Parameters
        ----------
        filename : `str` or `pathlib.Path`
            Name of config file, including ".yaml" suffix.

        Returns
        -------
        config : types.SimpleNamespace
            The config dict.
        """
        with open(self.data_dir / filename, "r") as f:
            raw_config_dict = yaml.safe_load(f.read())
        config_dict = self.validator.validate(raw_config_dict)
        return types.SimpleNamespace(**config_dict)
