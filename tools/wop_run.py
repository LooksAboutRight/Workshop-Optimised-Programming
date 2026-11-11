"""Run a project file: check it, draw it and write the G-code (requirements B9, V1, O1).

Usage (project root):
    python tools/wop_run.py examples/reference.wop.json
    python tools/wop_run.py examples/reference.wop.json --block 3
    python tools/wop_run.py file.wop.json --out my_folder --accept-all

--block N runs only block N (1 = the first block); the material left by the
blocks before it is taken into account. --accept-all accepts every suggested
remedy of the postprocessor (fixed RPM instead of constant surface speed and so on).
Writes <name>.ngc, <name>.svg into the output folder and prints what it found.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wop.adapters.machine_files import load_machine  # noqa: E402
from wop.core.constants import DEFAULT_POSTPROCESSOR_ID  # noqa: E402
from wop.core.lathe.machine import MachineError  # noqa: E402
from wop.core.lathe.machine_check import check_against_machine  # noqa: E402
from wop.core.material import MaterialLibrary  # noqa: E402
from wop.core.lathe.power import estimate_power  # noqa: E402
from wop.adapters.project_files import load_project  # noqa: E402
from wop.core.program_model.program import plan_program  # noqa: E402
from wop.core.files.project_io import ProjectError, program_problems  # noqa: E402
from wop.core.verify import verify_plan  # noqa: E402
from wop.adapters.post_library import load_post_library  # noqa: E402
from wop.core.files.user_folder import user_folder  # noqa: E402
from wop.post.base import PostSettings  # noqa: E402
from wop.post.context import make_context  # noqa: E402
from wop.post.engine import TemplatePost  # noqa: E402
from wop.post.generate import generate_gcode  # noqa: E402
from wop.ui.svg_preview import render_svg  # noqa: E402
from datetime import datetime  # noqa: E402

DEFAULT_OUTPUT_FOLDER = "wop_output"
FILE_SUFFIX = ".wop.json"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check a WOP project and write G-code and a picture.")
    parser.add_argument("project", type=Path)
    parser.add_argument("--block", type=int, help="run only this block (1 = first)")
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_OUTPUT_FOLDER))
    parser.add_argument("--machine", type=Path, help="machine definition file: checks sizes, RPM and power")
    parser.add_argument("--accept-all", action="store_true", help="accept every suggested remedy")
    args = parser.parse_args(argv[1:])

    try:
        project = load_project(args.project)
    except ProjectError as error:
        print(f"cannot open the project: {error}")
        return 1
    program = project.program
    for problem in program_problems(program):
        print(f"problem: {problem}")

    only = None if args.block is None else args.block - 1
    plan = plan_program(program, only_block=only)
    findings = verify_plan(program, plan)
    for message in plan.messages:
        print(f"note: {message}")
    if args.machine is not None:
        try:
            machine = load_machine(args.machine)
        except MachineError as error:
            print(f"cannot use the machine file: {error}")
            return 1
        for text in check_against_machine(program, plan, machine):
            print(f"MACHINE: {text}")
        material = MaterialLibrary().find(program.raw_part.material)
        power = estimate_power(program, plan, machine, material)
        for text in power.messages:
            print(f"POWER ({power.label}): {text}")
        for entry in power.blocks:
            print(f"power estimate block {entry.block_index + 1}: {entry.required_kw:.2f} kW")
    for finding in findings:
        print(f"COLLISION: {finding.message} (remedy: {finding.remedy})")

    library = load_post_library(user_folder())
    definition, not_found = library.choose(project.machine.postprocessor if project.machine else DEFAULT_POSTPROCESSOR_ID)
    for problem in (*library.problems, *([not_found] if not_found else [])):
        print(f"post: {problem}")
    post = TemplatePost(definition)
    machine = project.machine
    settings = PostSettings(project.settings.x_mode)
    context = make_context(program, plan, project.settings.title, machine.name if machine else "", datetime.now(),
                           machine=machine, work_offset=project.settings.work_offset)
    first = generate_gcode(plan, post, settings, context=context)
    accepted = {issue.key for issue in first.issues if issue.key is not None}
    result = generate_gcode(plan, post, settings, accepted, context=context) if args.accept_all else first
    for issue in result.issues:
        state = "accepted" if issue.key in (accepted if args.accept_all else set()) else "open"
        print(f"issue ({state}): {issue.message} - {issue.remedy_text or 'no safe remedy'}")
    if not result.complete:
        print("the program is INCOMPLETE: blocks with open issues were left out")

    name = args.project.name.removesuffix(FILE_SUFFIX).removesuffix(".json")
    suffix = "" if only is None else f"_block{args.block}"
    args.out.mkdir(parents=True, exist_ok=True)
    gcode_path = args.out / f"{name}{suffix}{definition.settings.file_extension}"
    svg_path = args.out / f"{name}{suffix}.svg"
    gcode_path.write_text(result.text, encoding="utf-8", newline="\n")
    svg_path.write_text(render_svg(plan, findings=findings), encoding="utf-8")
    print(f"written {gcode_path} and {svg_path}")
    print(f"{len(plan.operations)} operations, {len(findings)} collision findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
