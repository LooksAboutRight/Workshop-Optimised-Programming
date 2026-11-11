import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import tempfile

import zipfile

from build_exe import build_command, clear_old_build, copy_examples, copy_manual, exe_path, make_zip, project_version, sha256_of, zip_files, zip_name  # noqa: E402


class BuildExeTests(unittest.TestCase):
    def test_command_has_the_plugin_packages_and_mode(self):
        command = build_command("WOP", False, False, None, Path("dist"), Path("build"))
        self.assertIn("--onedir", command)
        self.assertIn("--windowed", command)
        self.assertEqual(command[command.index("--collect-submodules") + 1], "wop")
        self.assertEqual(command[command.index("--collect-all") + 1], "ezdxf")
        self.assertTrue(command[-1].endswith("wop_app.py"))

    def test_the_sandbox_stand_ins_stay_out_of_the_exe(self):
        """tools/sandbox_standin stays in the repository (for people who work in a sandbox) but nothing the exe loads may reach it."""
        command = build_command("WOP", False, False, None, Path("dist"), Path("build"))
        self.assertFalse([part for part in command if "sandbox" in str(part) or "standin" in str(part)])
        root = Path(__file__).resolve().parent.parent
        for path in [*(root / "wop").rglob("*.py"), root / "tools" / "wop_app.py"]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sandbox_standin", text, f"{path.name} reaches the sandbox stand-ins")
            self.assertNotIn("fake_pyside6", text, f"{path.name} reaches the sandbox stand-ins")

    def test_the_examples_go_next_to_the_program_and_into_the_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            program = Path(folder) / "WOP"
            program.mkdir()
            copy_examples(program)
            names = {path.relative_to(program).as_posix() for path in zip_files(program)}
            for wanted in ("examples/pawn.wop.json", "examples/reference.wop.json", "examples/example.machine.json", "examples/blocks/grooving.wop.json",
                           "examples/posts/fanuc.post.ini"):
                self.assertIn(wanted, names)
            self.assertFalse([name for name in names if "__pycache__" in name])

    def test_the_manual_pdf_goes_next_to_the_program_when_it_is_built(self):
        with tempfile.TemporaryDirectory() as folder:
            program = Path(folder) / "WOP"
            program.mkdir()
            built = (Path(__file__).resolve().parent.parent / "docs" / "manual" / "build" / "WOP_manual.pdf").is_file()
            self.assertEqual(copy_manual(program), built)  # no manual built: nothing is copied, and the build says so
            self.assertEqual((program / "WOP_manual.pdf").is_file(), built)
            if built:
                self.assertIn("WOP_manual.pdf", {path.name for path in zip_files(program)})

    def test_onefile_console_and_icon(self):
        command = build_command("X", True, True, Path("a.ico"), Path("dist"), Path("build"))
        self.assertIn("--onefile", command)
        self.assertIn("--console", command)
        self.assertEqual(command[command.index("--icon") + 1], "a.ico")

    def test_the_zip_has_the_folder_and_nothing_private(self):
        with tempfile.TemporaryDirectory() as folder:
            built = Path(folder) / "WOP"
            (built / "_internal").mkdir(parents=True)
            (built / "user_data" / "machines").mkdir(parents=True)
            for name in ("WOP.exe", "LICENSE", "wop_selftest.txt", "_internal/a.dll", "user_data/README.txt", "user_data/settings.json", "user_data/machines/mine.json"):
                (built / name).write_text("x", encoding="utf-8")
            files = zip_files(built)
            target = Path(folder) / "WOP-1-windows.zip"
            make_zip(target, built.parent, files)
            with zipfile.ZipFile(target) as archive:
                names = sorted(archive.namelist())
            self.assertEqual(names, ["WOP/LICENSE", "WOP/WOP.exe", "WOP/_internal/a.dll", "WOP/user_data/README.txt"])
            self.assertEqual(len(sha256_of(target)), 64)

    def test_the_zip_is_named_with_the_version_of_the_project(self):
        self.assertRegex(project_version(), r"^\d+\.\d+\.\d+")
        self.assertTrue(zip_name("WOP", "0.1.0").startswith("WOP-0.1.0-"))
        self.assertTrue(zip_name("WOP", "0.1.0").endswith(".zip"))

    def test_exe_location(self):
        self.assertEqual(exe_path("WOP", False, Path("dist")).parent, Path("dist") / "WOP")
        self.assertEqual(exe_path("WOP", True, Path("dist")).parent, Path("dist"))

    def test_old_build_is_removed_but_user_data_is_kept_aside(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root) / "dist" / "WOP"
            (old / "user_data").mkdir(parents=True)
            (old / "user_data" / "settings.json").write_text("{}")
            (old / "_internal").mkdir()
            backup = Path(root) / "work" / "backup"
            backup.parent.mkdir()
            self.assertTrue(clear_old_build(old, backup))
            self.assertFalse(old.exists())
            self.assertTrue((backup / "settings.json").exists())

    def test_nothing_to_remove_is_fine(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(clear_old_build(Path(root) / "none", Path(root) / "b"))


if __name__ == "__main__":
    unittest.main()
