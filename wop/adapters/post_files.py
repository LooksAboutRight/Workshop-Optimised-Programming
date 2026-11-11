"""Read and write post files (`name.post.ini`)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..post.post_constants import POST_FILE_SUFFIX
from ..post.post_definition import PostDefinition, PostFileError, parse_post
from ..post.post_text import PostText, entries

ENCODING = "utf-8"
NEWLINE = chr(10)


def post_id_of(path: Path) -> str:
    """The id of a post is the file name without `.post.ini`."""
    return path.name[: -len(POST_FILE_SUFFIX)] if path.name.endswith(POST_FILE_SUFFIX) else path.stem


def load_post_file(path: Path, fallback: PostDefinition | None = None) -> PostDefinition:
    try:
        text = path.read_text(encoding=ENCODING)
    except (OSError, UnicodeDecodeError) as error:
        raise PostFileError(f"cannot read {path.name}: {error}") from error
    try:
        return parse_post(text, post_id_of(path), fallback)
    except PostFileError as error:
        raise PostFileError(f"{path.name}, {error}") from error


def save_post_text(path: Path, text: str) -> None:
    """Write the text of a post file as it is. A post with problems is saved too (an unfinished post): the editor shows the
    problems and a post with problems is not used; `load_post_folder` and `scan_post_folder` find them again."""
    write_text_atomically(path, text if text.endswith(NEWLINE) else text + NEWLINE, ENCODING)


@dataclass(frozen=True)
class UnfinishedPost:
    """A post file that reads as text but has problems: the editor opens it, nothing else uses it."""

    post_id: str
    name: str  # from the file when it has one, else the id
    problem: str


@dataclass(frozen=True)
class PostFolder:
    posts: dict[str, PostDefinition]  # the posts that can be used
    unfinished: dict[str, UnfinishedPost]  # readable text with problems
    unreadable: dict[str, str]  # post id -> why the file cannot be read as text at all


def scan_post_folder(folder: Path, fallback: PostDefinition | None = None) -> PostFolder:
    """Every post file of a folder sorted into: usable, with problems, unreadable (one bad file does not stop the others)."""
    posts: dict[str, PostDefinition] = {}
    unfinished: dict[str, UnfinishedPost] = {}
    unreadable: dict[str, str] = {}
    for path in sorted(folder.glob(f"*{POST_FILE_SUFFIX}")) if folder.is_dir() else []:
        post_id = post_id_of(path)
        try:
            text = path.read_text(encoding=ENCODING)
        except (OSError, UnicodeDecodeError) as error:
            unreadable[post_id] = f"cannot read {path.name}: {error}"
            continue
        try:
            posts[post_id] = parse_post(text, post_id, fallback)
        except PostFileError as error:
            name = next((value for _n, key, value in entries(PostText.from_text(text).body("post")) if key == "name"), "") or post_id
            unfinished[post_id] = UnfinishedPost(post_id, name, f"{path.name}, {error}")
    return PostFolder(posts, unfinished, unreadable)


def load_post_folder(folder: Path, fallback: PostDefinition | None = None) -> tuple[dict[str, PostDefinition], list[str]]:
    """Every post file of a folder by id, and one text per file that could not be used (one bad file does not stop the others)."""
    found = scan_post_folder(folder, fallback)
    problems = [post.problem for post in found.unfinished.values()] + list(found.unreadable.values())
    return found.posts, problems
