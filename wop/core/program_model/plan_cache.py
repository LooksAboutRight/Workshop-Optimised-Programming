"""What the planning of a program worked out before, for the next plan of nearly the same program (`plan_program(cache=...)`).

A block gives the same result for the same inputs: the block itself, its tool (with its holding), the raw part, the safety values,
the contours, the workholding and the material before it. The material is compared as the same object (a region is never changed in
place, and the material after a block taken from here is the same object as the last time): when block 2 is changed, block 2 and
every block after it are planned again, the blocks before it are taken from here. The bar and the placed jaws are kept the same way,
so that the first block finds the same material object.

`plan_program` and `verify_plan` read and fill it (the check of a block is kept like its plan); the window keeps one for the whole session (`AppModel`).
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass

from ..blocks.base import BlockResult
from ..constants import BLOCK_CACHE_MATERIALS, BLOCK_CACHE_SIZE
from ..geometry.region import Region


@dataclass(frozen=True)
class CachedBlock:
    """What one block made from one material: its result and the material after it (with what it cut off)."""

    residual_before: Region
    result: BlockResult
    residual_after: Region
    cut_off: Region


class PlanCache:
    def __init__(self, size: int = BLOCK_CACHE_SIZE) -> None:
        self._size = size
        self._blocks: OrderedDict[tuple, list[CachedBlock]] = OrderedDict()  # inputs without the material -> results, newest last
        self._stock: tuple | None = None  # (raw part, bar)
        self._jaws: tuple | None = None  # ((raw part, workholding), (jaws, problem))
        self._looks: OrderedDict[tuple, tuple] = OrderedDict()  # (look, inputs...) -> (material, result, what the look found)
        self.hits = 0  # blocks taken from here (for the tests and the profile)
        self.recalled: Counter[str] = Counter()  # looks at blocks taken from here, by look ("check")

    def stock(self, raw_part, make) -> Region:
        """The bar of this raw part: the same object as the last time when the raw part is the same."""
        if self._stock is None or self._stock[0] != raw_part:
            self._stock = (raw_part, make(raw_part))
        return self._stock[1]

    def jaws(self, raw_part, workholding, make) -> tuple:
        """The placed jaws and the workholding problem, the same objects as the last time for the same raw part and workholding."""
        key = (raw_part, workholding)
        if self._jaws is None or self._jaws[0] != key:
            self._jaws = (key, make(raw_part, workholding))
        return self._jaws[1]

    def get(self, inputs: tuple, residual: Region) -> CachedBlock | None:
        for entry in self._blocks.get(inputs, ()):
            if entry.residual_before is residual:
                self._blocks.move_to_end(inputs)
                self.hits += 1
                return entry
        return None

    def put(self, inputs: tuple, entry: CachedBlock) -> None:
        entries = self._blocks.setdefault(inputs, [])
        entries.insert(0, entry)
        del entries[BLOCK_CACHE_MATERIALS:]
        self._blocks.move_to_end(inputs)
        while len(self._blocks) > self._size:
            self._blocks.popitem(last=False)

    def recall(self, inputs: tuple, block_plan) -> object | None:
        """What a look at this block found the last time (the check `verify._check_block`): `inputs`
        names the look and holds what it depends on besides the block plan; the material and the result must be the same objects
        (they come from the plan cache, so the same objects mean the same block)."""
        known = self._looks.get(inputs)
        if known is None or known[0] is not block_plan.residual_before or known[1] is not block_plan.result:
            return None
        self._looks.move_to_end(inputs)
        self.recalled[inputs[0]] += 1
        return known[2]

    def remember(self, inputs: tuple, block_plan, found: object) -> None:
        self._looks[inputs] = (block_plan.residual_before, block_plan.result, found)
        self._looks.move_to_end(inputs)
        while len(self._looks) > self._size:
            self._looks.popitem(last=False)

    def clear(self) -> None:
        self._blocks.clear()
        self._looks.clear()
        self._stock = self._jaws = None
