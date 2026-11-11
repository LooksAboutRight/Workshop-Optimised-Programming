"""The postprocessors of the user and their editor."""

from __future__ import annotations

import re
from pathlib import Path

from ...adapters.post_files import save_post_text
from ...adapters.post_library import FALLBACK_POST_ID, load_post_library, user_posts_folder
from ...core.constants import DEFAULT_POSTPROCESSOR_ID
from ...post.post_constants import POST_FILE_SUFFIX
from ...post.post_text import PostText
from ..post_editor_model import NEW_POST_NAME, PostEditorModel
from .helpers import ModelError


class PostsMixin:
    """The postprocessors of the user and their editor. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def post_choices(self) -> tuple[tuple[str, str], ...]:
        """(id, name) of the posts: the ones that come with WOP, then the user's own."""
        names = {post_id: self.post_library.posts[post_id].name for post_id in self.post_library.ids()}
        return tuple(
            (post_id, name if list(names.values()).count(name) == 1 else f"{name} [{post_id}]") for post_id, name in names.items()
        )

    def post_editor_choices(self) -> tuple[tuple[str, str, str], ...]:
        """(id, name, state) of every post file the editor offers; the state is "", "problems" or "unreadable". The machine
        offers only the posts without problems (`post_choices`)."""
        return tuple(self.post_library.editor_entries())

    @property
    def user_folder(self) -> Path | None:
        """The folder of the settings (and of the user's posts); None when the settings are only in memory."""
        return None if self.settings_path is None else self.settings_path.parent

    def reload_posts(self) -> None:
        self.post_library = load_post_library(self.user_folder)

    def posts_folder_path(self) -> Path | None:
        """The folder of the user's posts (made if it is not there yet); None without a settings folder."""
        if self.user_folder is None:
            return None
        folder = user_posts_folder(self.user_folder)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def post_editor(self, post_id: str) -> PostEditorModel:
        """The editor model of a post of the library (a shipped post is read-only)."""
        library = self.post_library
        if post_id in library.unreadable:  # a read-only placeholder: only Delete works
            return PostEditorModel(post_id, "", True, library.posts[FALLBACK_POST_ID], unreadable=library.unreadable[post_id])
        if post_id not in library.posts and post_id not in library.unfinished:
            raise ModelError(f"there is no post called {post_id!r}")
        try:
            text = library.path_of(post_id).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ModelError(f"the post file {post_id!r} cannot be read: {error}") from error
        fallback = None if post_id == FALLBACK_POST_ID else library.posts[FALLBACK_POST_ID]
        return PostEditorModel(post_id, text, library.is_shipped(post_id), fallback)

    def new_post_editor(self) -> PostEditorModel:
        """A new post: a copy of the default post, to be given a name and changed."""
        library = self.post_library
        text = PostText.from_text(library.path_of(FALLBACK_POST_ID).read_text(encoding="utf-8"))
        text.preamble = [
            "# My post. NOTHING in it was run on a machine. Every post can crash a machine:",
            "# check what it writes before you run it.",
        ]
        editor = PostEditorModel("", text.to_text(), False, library.posts[FALLBACK_POST_ID])
        editor.set_meta("name", NEW_POST_NAME)
        editor.set_meta("description", "")
        editor.mark_saved()  # a new post is not "changed" until the user changes it; it has no file until it is saved
        return editor

    def unique_post_id(self, wanted: str) -> str:
        """A file name for a post: lower case letters, digits and _, not taken by any post."""
        base = re.sub(r"[^a-z0-9_]+", "_", wanted.lower()).strip("_") or "post"
        post_id, number = base, 1
        while post_id in self.post_library.posts or post_id in self.post_library.unfinished or post_id in self.post_library.unreadable:
            number += 1
            post_id = f"{base}_{number}"
        return post_id

    def save_post(self, editor: PostEditorModel, as_id: str | None = None) -> str:
        """Write the post as a file of the user (a shipped post only under another id). Returns its id."""
        folder = self.posts_folder_path()
        if folder is None:
            raise ModelError("the settings are not kept in a folder, so there is no place for your own posts")
        if editor.unreadable:
            raise ModelError("this file cannot be read, so there is nothing to save: delete it or fix it outside the program")
        post_id = as_id or editor.post_id
        if not post_id:
            raise ModelError("the post needs a name")
        if self.post_library.is_shipped(post_id):
            raise ModelError(f"{post_id} comes with WOP and cannot be changed: save it under another name")
        try:  # a post with problems is saved too: the editor shows them, and the post is not used until they are fixed
            save_post_text(folder / f"{post_id}{POST_FILE_SUFFIX}", editor.text)
        except OSError as error:
            raise ModelError(f"the post could not be saved: {error}") from error
        editor.mark_saved(post_id)
        self.reload_posts()
        return post_id

    def delete_post(self, post_id: str) -> None:
        if self.post_library.is_shipped(post_id):
            raise ModelError("a post that comes with WOP cannot be deleted")
        library = self.post_library
        if post_id not in library.posts and post_id not in library.unfinished and post_id not in library.unreadable:
            raise ModelError(f"there is no post called {post_id!r}")
        try:
            library.path_of(post_id).unlink()
        except OSError as error:
            raise ModelError(f"the post could not be deleted: {error}") from error
        self.reload_posts()

    def import_post(self, path: Path) -> str:
        """Copy a post file into the user's posts. A file with problems comes in too (the editor shows them). Returns its id."""
        folder = self.posts_folder_path()
        if folder is None:
            raise ModelError("the settings are not kept in a folder, so there is no place for your own posts")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ModelError(f"{path.name} cannot be read as text: {error}") from error
        stem = path.name[: -len(POST_FILE_SUFFIX)] if path.name.endswith(POST_FILE_SUFFIX) else path.stem
        post_id = self.unique_post_id(stem)
        save_post_text(folder / f"{post_id}{POST_FILE_SUFFIX}", text)
        self.reload_posts()
        return post_id

    @property
    def postprocessor_id(self) -> str:
        """The postprocessor of the machine of the project (the default one without a machine)."""
        machine = self.project.machine
        return machine.postprocessor if machine is not None else DEFAULT_POSTPROCESSOR_ID

    def gcode_suffix(self) -> str:
        """The file extension the postprocessor of the machine asks for (.ngc ...)."""
        definition, _not_found = self.post_library.choose(self.postprocessor_id)
        return definition.settings.file_extension

    def post_title(self) -> str:
        """The name of the postprocessor that the next export uses (the one of the machine of the project)."""
        definition, _not_found = self.post_library.choose(self.postprocessor_id)
        return definition.name
