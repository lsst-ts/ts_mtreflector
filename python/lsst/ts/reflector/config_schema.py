# This file is part of ts_reflector.
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

__all__ = ["CONFIG_SCHEMA"]

import yaml

# $schema: http://json-schema.org/draft-07/schema#
# $id: https://github.com/lsst-ts/
# ts_reflector/python/lsst/ts/reflector/config_schema.py
CONFIG_SCHEMA = yaml.safe_load(
    """
schema: http://json-schema.org/draft-07/schema#
title: Reflector v1
description: Schema for Reflector
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
  sensor_name:
      description: Value for the sensor_name field of the topic.
      type: string
  location:
      description: >-
          Location of sensor.
      type: string
  channel_name:
      description: >-
          LabJack channel name of reflector.
      type: string
required:
  - device_type
  - connection_type
  - identifier
  - sensor_name
  - location
  - channel_name
additionalProperties: false
"""
)
