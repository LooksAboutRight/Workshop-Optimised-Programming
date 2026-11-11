"""Read and write project files on disk."""

from __future__ import annotations

from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..core.program_model.project import Project
from ..core.files.project_io import ProjectError, project_and_preview_from_json, project_to_json

PROJECT_FILE_SUFFIX = ".wop.json"
ENCODING = "utf-8"


def save_project(path: Path, project: Project, preview: list | None = None) -> None:
    """Write the file in one step, so a crash cannot leave half a project behind. `preview`: the loops of the finished part (V9)."""
    write_text_atomically(path, project_to_json(project, preview), ENCODING)


def load_project(path: Path) -> Project:
    return load_project_and_preview(path)[0]


def load_project_and_preview(path: Path) -> tuple[Project, list | None]:
    """The project and the loops of the finished part saved with it (None when there are none)."""
    try:
        text = path.read_text(encoding=ENCODING)
    except (OSError, UnicodeDecodeError) as error:
        raise ProjectError(f"cannot read {path.name}: {error}") from error
    return project_and_preview_from_json(text)
