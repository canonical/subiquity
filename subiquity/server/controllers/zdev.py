# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import itertools
import logging
import platform
from collections import OrderedDict
from typing import List, Literal, Optional, TypedDict

import attrs

from subiquity.common.apidef import API
from subiquity.common.types import ZdevInfo
from subiquity.common.types.storage import Bootloader
from subiquity.server.controller import SubiquityController
from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context
from subiquitycore.utils import arun_command, run_command

log = logging.getLogger("subiquity.server.controllers.zdev")

lszdev_cmd = [
    "lszdev",
    "--quiet",
    "--pairs",
    "--columns",
    "id,type,on,exists,pers,auto,failed,names",
]

lszdev_stock = '''id="0.0.1500" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1501" type="dasd-eckd" on="yes" exists="yes" pers="auto" auto="yes" failed="no" names=""
id="0.0.1502" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1503" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1504" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1505" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1506" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1507" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1508" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1509" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.150f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1510" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1511" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1512" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1513" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1514" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1515" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1516" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1517" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1518" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1519" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.151f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1520" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1521" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1522" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1523" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1524" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1525" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1526" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1527" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1528" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1529" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.152f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1530" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1531" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1532" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1533" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1534" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1535" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1536" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1537" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1538" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1539" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.153f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1540" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1541" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1542" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1543" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1544" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1545" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1546" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1547" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1548" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1549" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.154a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.154b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.154c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.154d" type="dasd-eckd" on="yes" exists="yes" pers="yes" auto="no" failed="no" names="dasda"
id="0.0.154e" type="dasd-eckd" on="yes" exists="yes" pers="no" auto="yes" failed="no" names="dasdb"
id="0.0.154f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1550" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1551" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1552" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1553" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1554" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.1555" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e0" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e1" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e2" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e3" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e4" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e5" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e6" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e7" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e8" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15e9" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ea" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15eb" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ec" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ed" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ee" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ef" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f0" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f1" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f2" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f3" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f4" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f5" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f6" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f7" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f8" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15f9" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15fa" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15fb" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15fc" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15fd" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15fe" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.15ff" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2500" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2501" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2502" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2503" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2504" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2505" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2506" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2507" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2508" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2509" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.250f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2510" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2511" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2512" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2513" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2514" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2515" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2516" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2517" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2518" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2519" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.251f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2520" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2521" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2522" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2523" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2524" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2525" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2526" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2527" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2528" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2529" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.252f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2530" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2531" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2532" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2533" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2534" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2535" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2536" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2537" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2538" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2539" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.253f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2540" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2541" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2542" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2543" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2544" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2545" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2546" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2547" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2548" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2549" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254a" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254b" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254c" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254d" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254e" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.254f" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2550" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2551" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2552" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2553" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2554" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.2555" type="dasd-eckd" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e000" type="zfcp-host" on="yes" exists="yes" pers="yes" auto="no" failed="no" names=""
id="0.0.e001" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e002" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e003" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e004" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e005" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e006" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e007" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e008" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e009" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00a" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00b" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00c" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00d" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00e" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e00f" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e100" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e101" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e102" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e103" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e104" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e105" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e106" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e107" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e108" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e109" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10a" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10b" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10c" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10d" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10e" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e10f" type="zfcp-host" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.e000:0x50050763060b16b6:0x4024400400000000" type="zfcp-lun" on="yes" exists="yes" pers="no" auto="no" failed="no" names="sda sg0"
id="0.0.e000:0x50050763060b16b6:0x4024400500000000" type="zfcp-lun" on="yes" exists="yes" pers="no" auto="no" failed="no" names="sdb sg1"
id="0.0.e000:0x50050763061b16b6:0x4024400400000000" type="zfcp-lun" on="yes" exists="yes" pers="no" auto="no" failed="no" names="sdc sg2"
id="0.0.e000:0x50050763061b16b6:0x4024400500000000" type="zfcp-lun" on="yes" exists="yes" pers="no" auto="no" failed="no" names="sdd sg3"
id="0.0.c000:0.0.c001:0.0.c002" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c003:0.0.c004:0.0.c005" type="qeth" on="yes" exists="yes" pers="yes" auto="no" failed="no" names="encc003"
id="0.0.c006:0.0.c007:0.0.c008" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c009:0.0.c00a:0.0.c00b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c00c:0.0.c00d:0.0.c00e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c00f:0.0.c010:0.0.c011" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c012:0.0.c013:0.0.c014" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c015:0.0.c016:0.0.c017" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c018:0.0.c019:0.0.c01a" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c01b:0.0.c01c:0.0.c01d" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c01e:0.0.c01f:0.0.c020" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c021:0.0.c022:0.0.c023" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c024:0.0.c025:0.0.c026" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c027:0.0.c028:0.0.c029" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c02a:0.0.c02b:0.0.c02c" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c02d:0.0.c02e:0.0.c02f" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c030:0.0.c031:0.0.c032" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c033:0.0.c034:0.0.c035" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c036:0.0.c037:0.0.c038" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c039:0.0.c03a:0.0.c03b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c03c:0.0.c03d:0.0.c03e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c03f:0.0.c040:0.0.c041" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c042:0.0.c043:0.0.c044" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c045:0.0.c046:0.0.c047" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c048:0.0.c049:0.0.c04a" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c04b:0.0.c04c:0.0.c04d" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c04e:0.0.c04f:0.0.c050" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c051:0.0.c052:0.0.c053" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c054:0.0.c055:0.0.c056" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c057:0.0.c058:0.0.c059" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c05a:0.0.c05b:0.0.c05c" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c05d:0.0.c05e:0.0.c05f" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c060:0.0.c061:0.0.c062" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c063:0.0.c064:0.0.c065" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c066:0.0.c067:0.0.c068" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c069:0.0.c06a:0.0.c06b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c06c:0.0.c06d:0.0.c06e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c06f:0.0.c070:0.0.c071" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c072:0.0.c073:0.0.c074" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c075:0.0.c076:0.0.c077" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c078:0.0.c079:0.0.c07a" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c07b:0.0.c07c:0.0.c07d" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d000:0.0.d001:0.0.d002" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d003:0.0.d004:0.0.d005" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d006:0.0.d007:0.0.d008" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d009:0.0.d00a:0.0.d00b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d00c:0.0.d00d:0.0.d00e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d00f:0.0.d010:0.0.d011" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d012:0.0.d013:0.0.d014" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d015:0.0.d016:0.0.d017" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d018:0.0.d019:0.0.d01a" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d01b:0.0.d01c:0.0.d01d" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d01e:0.0.d01f:0.0.d020" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d021:0.0.d022:0.0.d023" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d024:0.0.d025:0.0.d026" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d027:0.0.d028:0.0.d029" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d02a:0.0.d02b:0.0.d02c" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d02d:0.0.d02e:0.0.d02f" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d030:0.0.d031:0.0.d032" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d033:0.0.d034:0.0.d035" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d036:0.0.d037:0.0.d038" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d039:0.0.d03a:0.0.d03b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d03c:0.0.d03d:0.0.d03e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d03f:0.0.d040:0.0.d041" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d042:0.0.d043:0.0.d044" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d045:0.0.d046:0.0.d047" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d100:0.0.d101:0.0.d102" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d103:0.0.d104:0.0.d105" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d106:0.0.d107:0.0.d108" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d109:0.0.d10a:0.0.d10b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d10c:0.0.d10d:0.0.d10e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d10f:0.0.d110:0.0.d111" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d112:0.0.d113:0.0.d114" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d115:0.0.d116:0.0.d117" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d118:0.0.d119:0.0.d11a" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d11b:0.0.d11c:0.0.d11d" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d11e:0.0.d11f:0.0.d120" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d121:0.0.d122:0.0.d123" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d124:0.0.d125:0.0.d126" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d127:0.0.d128:0.0.d129" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d12a:0.0.d12b:0.0.d12c" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d12d:0.0.d12e:0.0.d12f" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d130:0.0.d131:0.0.d132" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d133:0.0.d134:0.0.d135" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d136:0.0.d137:0.0.d138" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d139:0.0.d13a:0.0.d13b" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d13c:0.0.d13d:0.0.d13e" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d13f:0.0.d140:0.0.d141" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d142:0.0.d143:0.0.d144" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.d145:0.0.d146:0.0.d147" type="qeth" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a110:0.0.a111" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a112:0.0.a113" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a114:0.0.a115" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a116:0.0.a117" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a118:0.0.a119" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a11a:0.0.a11b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a11c:0.0.a11d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a11e:0.0.a11f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a120:0.0.a121" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a122:0.0.a123" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a124:0.0.a125" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a126:0.0.a127" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a128:0.0.a129" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a12a:0.0.a12b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a12c:0.0.a12d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a12e:0.0.a12f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a130:0.0.a131" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a132:0.0.a133" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a134:0.0.a135" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a136:0.0.a137" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a138:0.0.a139" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a13a:0.0.a13b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a13c:0.0.a13d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a13e:0.0.a13f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a140:0.0.a141" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a142:0.0.a143" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a144:0.0.a145" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a146:0.0.a147" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a148:0.0.a149" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a14a:0.0.a14b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a14c:0.0.a14d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a14e:0.0.a14f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a150:0.0.a151" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a152:0.0.a153" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a154:0.0.a155" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a156:0.0.a157" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a158:0.0.a159" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a15a:0.0.a15b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a15c:0.0.a15d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a15e:0.0.a15f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a160:0.0.a161" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a162:0.0.a163" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a164:0.0.a165" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a166:0.0.a167" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a168:0.0.a169" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a16a:0.0.a16b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a16c:0.0.a16d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a16e:0.0.a16f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a180:0.0.a181" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a182:0.0.a183" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a184:0.0.a185" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a186:0.0.a187" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a188:0.0.a189" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a18a:0.0.a18b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a18c:0.0.a18d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a18e:0.0.a18f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a190:0.0.a191" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a192:0.0.a193" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a194:0.0.a195" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a196:0.0.a197" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a198:0.0.a199" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a19a:0.0.a19b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a19c:0.0.a19d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a19e:0.0.a19f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1a0:0.0.a1a1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1a2:0.0.a1a3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1a4:0.0.a1a5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1a6:0.0.a1a7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1a8:0.0.a1a9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1aa:0.0.a1ab" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ac:0.0.a1ad" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ae:0.0.a1af" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1b0:0.0.a1b1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1b2:0.0.a1b3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1b4:0.0.a1b5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1b6:0.0.a1b7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1b8:0.0.a1b9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ba:0.0.a1bb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1bc:0.0.a1bd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1be:0.0.a1bf" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1c0:0.0.a1c1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1c2:0.0.a1c3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1c4:0.0.a1c5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1c6:0.0.a1c7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1c8:0.0.a1c9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ca:0.0.a1cb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1cc:0.0.a1cd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ce:0.0.a1cf" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1d0:0.0.a1d1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1d2:0.0.a1d3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1d4:0.0.a1d5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1d6:0.0.a1d7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1d8:0.0.a1d9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1da:0.0.a1db" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1dc:0.0.a1dd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1de:0.0.a1df" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1e0:0.0.a1e1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1e2:0.0.a1e3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1e4:0.0.a1e5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1e6:0.0.a1e7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1e8:0.0.a1e9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ea:0.0.a1eb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ec:0.0.a1ed" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1ee:0.0.a1ef" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1f0:0.0.a1f1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1f2:0.0.a1f3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1f4:0.0.a1f5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1f6:0.0.a1f7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1f8:0.0.a1f9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1fa:0.0.a1fb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1fc:0.0.a1fd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.a1fe:0.0.a1ff" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f110:0.0.f111" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f112:0.0.f113" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f114:0.0.f115" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f116:0.0.f117" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f118:0.0.f119" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f11a:0.0.f11b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f11c:0.0.f11d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f11e:0.0.f11f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f120:0.0.f121" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f122:0.0.f123" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f124:0.0.f125" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f126:0.0.f127" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f128:0.0.f129" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f12a:0.0.f12b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f12c:0.0.f12d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f12e:0.0.f12f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f130:0.0.f131" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f132:0.0.f133" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f134:0.0.f135" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f136:0.0.f137" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f138:0.0.f139" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f13a:0.0.f13b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f13c:0.0.f13d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f13e:0.0.f13f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f140:0.0.f141" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f142:0.0.f143" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f144:0.0.f145" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f146:0.0.f147" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f148:0.0.f149" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f14a:0.0.f14b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f14c:0.0.f14d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f14e:0.0.f14f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f150:0.0.f151" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f152:0.0.f153" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f154:0.0.f155" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f156:0.0.f157" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f158:0.0.f159" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f15a:0.0.f15b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f15c:0.0.f15d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f15e:0.0.f15f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f160:0.0.f161" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f162:0.0.f163" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f164:0.0.f165" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f166:0.0.f167" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f168:0.0.f169" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f16a:0.0.f16b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f16c:0.0.f16d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f16e:0.0.f16f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f180:0.0.f181" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f182:0.0.f183" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f184:0.0.f185" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f186:0.0.f187" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f188:0.0.f189" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f18a:0.0.f18b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f18c:0.0.f18d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f18e:0.0.f18f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f190:0.0.f191" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f192:0.0.f193" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f194:0.0.f195" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f196:0.0.f197" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f198:0.0.f199" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f19a:0.0.f19b" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f19c:0.0.f19d" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f19e:0.0.f19f" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1a0:0.0.f1a1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1a2:0.0.f1a3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1a4:0.0.f1a5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1a6:0.0.f1a7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1a8:0.0.f1a9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1aa:0.0.f1ab" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ac:0.0.f1ad" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ae:0.0.f1af" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1b0:0.0.f1b1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1b2:0.0.f1b3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1b4:0.0.f1b5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1b6:0.0.f1b7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1b8:0.0.f1b9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ba:0.0.f1bb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1bc:0.0.f1bd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1be:0.0.f1bf" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1c0:0.0.f1c1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1c2:0.0.f1c3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1c4:0.0.f1c5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1c6:0.0.f1c7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1c8:0.0.f1c9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ca:0.0.f1cb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1cc:0.0.f1cd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ce:0.0.f1cf" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1d0:0.0.f1d1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1d2:0.0.f1d3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1d4:0.0.f1d5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1d6:0.0.f1d7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1d8:0.0.f1d9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1da:0.0.f1db" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1dc:0.0.f1dd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1de:0.0.f1df" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1e0:0.0.f1e1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1e2:0.0.f1e3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1e4:0.0.f1e5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1e6:0.0.f1e7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1e8:0.0.f1e9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ea:0.0.f1eb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ec:0.0.f1ed" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1ee:0.0.f1ef" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1f0:0.0.f1f1" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1f2:0.0.f1f3" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1f4:0.0.f1f5" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1f6:0.0.f1f7" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1f8:0.0.f1f9" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1fa:0.0.f1fb" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1fc:0.0.f1fd" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.f1fe:0.0.f1ff" type="ctc" on="no" exists="yes" pers="no" auto="no" failed="no" names=""
id="0.0.c0fe" type="generic-ccw" on="no" exists="yes" pers="no" auto="no" failed="yes" names=""'''  # noqa: E501


class ZdevAiItem(TypedDict, total=True):
    id: str
    enabled: bool


ZdevAi = list[ZdevAiItem]


@attrs.define(auto_attribs=True)
class ZdevAction:
    id: str
    enable: bool

    @classmethod
    def from_ai_item(cls, item: ZdevAiItem) -> "ZdevAction":
        return cls(id=item["id"], enable=item["enabled"])

    def to_ai_item(self) -> ZdevAiItem:
        return ZdevAiItem(id=self.id, enabled=self.enable)


class ZdevController(SubiquityController):
    endpoint = API.zdev

    autoinstall_key = "zdevs"
    autoinstall_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "enabled": {"type": "boolean"},
            },
        },
    }
    autoinstall_default = []

    def __init__(self, app):
        self.ai_actions: list[ZdevAction] = []
        self.zdev_handling_task: Optional[asyncio.Task] = None

        # Recording of actions that have been performed on the Zdevs. This is
        # only used to produce an autoinstall config at the end.
        self.done_ai_actions: list[ZdevAction] = []

        super().__init__(app)
        if self.opts.dry_run:
            if platform.machine() == "s390x":
                zdevinfos = self.lszdev_sync()
            else:
                devices = lszdev_stock.splitlines()
                devices.sort()
                zdevinfos = [ZdevInfo.from_row(row) for row in devices]
            self.dr_zdevinfos = OrderedDict([(i.id, i) for i in zdevinfos])

    def load_autoinstall_data(self, data: ZdevAi) -> None:
        self.ai_actions = [ZdevAction.from_ai_item(item) for item in data]

    @with_context()
    async def apply_autoinstall_config(self, context) -> None:
        if self.zdev_handling_task is not None:
            await self.zdev_handling_task

    def start(self) -> None:
        if self.ai_actions:
            self.zdev_handling_task = schedule_task(self.handle_zdevs())

    def make_autoinstall(self) -> ZdevAi:
        # Small "optimization" to avoid producing a config that enables or
        # disables a given device multiple times in a row.
        return [x.to_ai_item() for x, _ in itertools.groupby(self.done_ai_actions)]

    async def handle_zdevs(self) -> None:
        if self.opts.dry_run:
            zdevinfos = self.dr_zdevinfos
        else:
            zdevinfos = OrderedDict([(i.id, i) for i in await self.lszdev()])

        for ai_action in self.ai_actions:
            action = "enable" if ai_action.enable else "disable"
            await self.chzdev(action, zdevinfos[ai_action.id])

    def interactive(self):
        if self.app.base_model.filesystem.bootloader != Bootloader.NONE:
            return False
        return super().interactive()

    async def chzdev(
        self, action: Literal["enable", "disable"], zdev: ZdevInfo
    ) -> None:
        if action == "enable":
            on = True
        elif action == "disable":
            on = False
        else:
            raise ValueError("action must be 'enable' or 'disable'")

        self.done_ai_actions.append(ZdevAction(id=zdev.id, enable=on))

        if self.opts.dry_run:
            self.dr_zdevinfos[zdev.id].on = on
            self.dr_zdevinfos[zdev.id].pers = on
        chzdev_cmd = ["chzdev", "--%s" % action, zdev.id]
        await self.app.command_runner.run(chzdev_cmd)

    async def chzdev_POST(self, action: str, zdev: ZdevInfo) -> List[ZdevInfo]:
        await self.chzdev(action, zdev)
        return await self.GET()

    async def GET(self) -> List[ZdevInfo]:
        if self.opts.dry_run:
            return self.dr_zdevinfos.values()
        else:
            return await self.lszdev()

    def _raw_lszdev_sync(self) -> str:
        return run_command(lszdev_cmd, universal_newlines=True).stdout

    async def _raw_lszdev(self) -> str:
        return (await arun_command(lszdev_cmd)).stdout

    def _parse_lszdev(self, output: str) -> list[ZdevInfo]:
        devices = output.splitlines()
        devices.sort()
        return [ZdevInfo.from_row(row) for row in devices]

    def lszdev_sync(self) -> list[ZdevInfo]:
        """Synchronous version of lszdev - which we can drop once we move the
        call to lszdev outside the initializer."""
        return self._parse_lszdev(self._raw_lszdev_sync())

    async def lszdev(self) -> list[ZdevInfo]:
        return self._parse_lszdev(await self._raw_lszdev())
