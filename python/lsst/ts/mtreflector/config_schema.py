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

__all__ = ["CONFIG_SCHEMA"]

import yaml

# $schema: http://json-schema.org/draft-07/schema#
# $id: https://github.com/lsst-ts/
# ts_mtreflector/python/lsst/ts/mtreflector/config_schema.py
CONFIG_SCHEMA = yaml.safe_load(
    """
schema: http://json-schema.org/draft-07/schema#
title: MTReflector v1
description: Schema for MTReflector
type: object
properties:
  identifier:
    description: >-
        LabJack indentifier:
        * A host name or IP address if connection_type = TCP or WIFI
        * A serial number if connection_type = USB
        * For testing in an environment with only one LabJack you may use ANY
    type: string
required:
  - identifier
additionalProperties: false
"""
)
