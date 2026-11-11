"""The posts the program knows: the shipped ones (read-only, `wop/post/posts/`) and the user's own (`posts/` in the user folder).

Shipped posts win: a user file with the id of a shipped post is not used and says so. "Edit" on a shipped post is a copy
under another name in the user folder. Every post that lacks a section takes it from the default post (`generic`, part of the
program, not offered in the lists). Only LinuxCNC is shipped; other controllers are reference files in `examples/posts` to import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.constants import DEFAULT_POSTPROCESSOR_ID
from ..post.post_constants import POST_FILE_SUFFIX
from ..post.post_definition import PostDefinition
from .post_files import PostFolder, UnfinishedPost, load_post_file, scan_post_folder

SHIPPED_FOLDER = Path(__file__).resolve().parent.parent / "post" / "posts"
USER_SUBFOLDER = "posts"
FALLBACK_POST_ID = "generic"  # the post that supplies the sections another post lacks


def user_posts_folder(user_folder: Path) -> Path:
    return user_folder / USER_SUBFOLDER


@dataclass(frozen=True)
class PostLibrary:
    posts: dict[str, PostDefinition]
    shipped: frozenset[str]
    problems: tuple[str, ...] = ()  # one text per file that could not be used
    user_folder: Path | None = None  # the user folder the posts were read from (None: only the shipped posts)
    unfinished: dict[str, UnfinishedPost] = field(default_factory=dict)  # files that read as text but have problems: only the editor uses them
    unreadable: dict[str, str] = field(default_factory=dict)  # files that cannot be read as text at all: id -> why

    def is_shipped(self, post_id: str) -> bool:
        return post_id in self.shipped

    def path_of(self, post_id: str) -> Path:
        """The file of a post (shipped or the user's)."""
        if post_id in self.shipped or self.user_folder is None:
            return SHIPPED_FOLDER / f"{post_id}{POST_FILE_SUFFIX}"
        return user_posts_folder(self.user_folder) / f"{post_id}{POST_FILE_SUFFIX}"

    def ids(self) -> list[str]:
        """The posts the user can choose: the shipped ones first (the default post is part of the program and not offered), then the user's own."""
        return sorted((post_id for post_id in self.posts if post_id != FALLBACK_POST_ID), key=lambda post_id: (post_id not in self.shipped, post_id))

    def editor_entries(self) -> list[tuple[str, str, str]]:
        """(id, name, state) of every post file the editor offers: the usable ones, then the ones with problems, then the
        unreadable ones. The state is "", "problems" or "unreadable"."""
        entries = [(post_id, self.posts[post_id].name, "") for post_id in self.ids()]
        entries += [(post_id, post.name, "problems") for post_id, post in sorted(self.unfinished.items())]
        entries += [(post_id, post_id, "unreadable") for post_id in sorted(self.unreadable)]
        return entries

    def choose(self, post_id: str) -> tuple[PostDefinition, str]:
        """The post with this id; when it cannot be used (not there, with problems, unreadable) the default post and a message."""
        if post_id in self.posts:
            return self.posts[post_id], ""
        for fallback in (DEFAULT_POSTPROCESSOR_ID, FALLBACK_POST_ID):
            if fallback in self.posts:
                name = self.posts[fallback].name
                if post_id in self.unfinished:
                    return self.posts[fallback], f"the post {post_id!r} has problems and is not used ({self.unfinished[post_id].problem}): {name} is used instead"
                if post_id in self.unreadable:
                    return self.posts[fallback], f"the post file {post_id!r} cannot be read and is not used: {name} is used instead"
                return self.posts[fallback], f"the post {post_id!r} was not found: {name} is used instead"
        raise KeyError(post_id)


def load_post_library(user_folder: Path | None = None) -> PostLibrary:
    """Read the shipped posts and, when a user folder is given, the posts in its `posts` folder."""
    problems: list[str] = []
    generic_path = SHIPPED_FOLDER / f"{FALLBACK_POST_ID}.post.ini"
    fallback = load_post_file(generic_path)  # the default post is part of the program: if it does not read, that is a bug
    found = scan_post_folder(SHIPPED_FOLDER, fallback)
    shipped = found.posts
    shipped[FALLBACK_POST_ID] = fallback
    problems += [post.problem for post in found.unfinished.values()] + list(found.unreadable.values())
    posts = dict(shipped)
    unfinished: dict[str, UnfinishedPost] = {}
    unreadable: dict[str, str] = {}
    if user_folder is not None:
        own: PostFolder = scan_post_folder(user_posts_folder(user_folder), fallback)
        for post_id in (*own.posts, *own.unfinished, *own.unreadable):
            if post_id in shipped:
                problems.append(f"{post_id}.post.ini in the user folder is not used: a shipped post has this name; save it under another name")
        posts.update({post_id: definition for post_id, definition in own.posts.items() if post_id not in shipped})
        unfinished = {post_id: post for post_id, post in own.unfinished.items() if post_id not in shipped}
        unreadable = {post_id: reason for post_id, reason in own.unreadable.items() if post_id not in shipped}
        problems += [post.problem for post in unfinished.values()] + list(unreadable.values())
    return PostLibrary(posts, frozenset(shipped), tuple(problems), user_folder, unfinished, unreadable)
