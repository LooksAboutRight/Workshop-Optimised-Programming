"""The four documents in docs/ stay in step with the project: what they name exists."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted((ROOT / "docs").glob("wop_0*.md"))
PATH_PATTERN = re.compile(r"`((?:wop|tests|tools|examples|docs)/[A-Za-z0-9_./*<>-]+)`")


def named_paths(text: str) -> set[str]:
    return {m.group(1).rstrip(".,;:") for m in PATH_PATTERN.finditer(text)}


class DocPathTests(unittest.TestCase):
    def test_there_are_four_documents(self):
        self.assertEqual([p.name[:6] for p in DOCS], ["wop_01", "wop_02", "wop_03", "wop_04"])

    def test_every_file_a_document_names_exists(self):
        missing = []
        for doc in DOCS:
            for name in sorted(named_paths(doc.read_text(encoding="utf-8"))):
                if "<" in name or "*" in name:  # a pattern such as examples/blocks/<type>.wop.json
                    folder = name.split("<")[0].split("*")[0].rsplit("/", 1)[0]
                    found = (ROOT / folder).is_dir()
                else:
                    found = (ROOT / name).exists()
                if not found:
                    missing.append(f"{doc.name}: {name}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
