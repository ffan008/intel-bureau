"""存储门面：把各表的读写集中在一个 Store 对象上。"""

from __future__ import annotations

from bureau.core.store.base import StoreBase, jdump, jload
from bureau.core.store.groups import GroupMixin
from bureau.core.store.kb import KbMixin
from bureau.core.store.memory import MemoryMixin
from bureau.core.store.messages import MessageMixin
from bureau.core.store.objects import ObjectMixin
from bureau.core.store.reports import ReportMixin
from bureau.core.store.runs import RunMixin


class Store(GroupMixin, MessageMixin, RunMixin, ReportMixin, ObjectMixin, MemoryMixin, KbMixin, StoreBase):
    pass


__all__ = ["Store", "jdump", "jload"]
