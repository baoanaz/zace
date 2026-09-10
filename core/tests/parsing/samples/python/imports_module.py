"""TASK-002 语料：import 形态（裸名/别名/from-import/相对/星号）。"""

# ruff: noqa

import os
import os.path as osp
import xml.etree.ElementTree as ET

from . import sibling
from ..parent import thing
from ..parent.pkg import other as renamed
from star_pkg import *
