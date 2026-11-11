"""Write examples/example.machine.json (or the file given as the first argument): a machine definition to edit (the values are placeholders)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wop.adapters.machine_files import MACHINE_FILE_SUFFIX, save_machine  # noqa: E402
from wop.core.lathe.machine import AxisLimits, MachineDef  # noqa: E402

EXAMPLE_FOLDER = "examples"
EXAMPLE_NAME = "example"
X_LIMITS = (-5, 80)
Z_LIMITS = (-250, 10)
RPM_LIMITS = (50, 3000)
POWER_KW = 2.2


def main(argv: list[str]) -> None:
    machine = MachineDef(
        name="Example lathe (edit the values)",
        axes=(AxisLimits("X", *X_LIMITS), AxisLimits("Z", *Z_LIMITS)),
        min_rpm=RPM_LIMITS[0], max_rpm=RPM_LIMITS[1], spindle_power_kw=POWER_KW,
    )
    path = Path(argv[1]) if len(argv) > 1 else Path(EXAMPLE_FOLDER) / f"{EXAMPLE_NAME}{MACHINE_FILE_SUFFIX}"
    path.parent.mkdir(exist_ok=True)
    save_machine(path, machine)
    print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
