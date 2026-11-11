"""List the concepts and tokens of the post engine as a Markdown table (the registry is the one source, see wop/post/tokens.py).

Usage (project root):  python tools/list_post_tokens.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wop.post.concepts import CONCEPTS  # noqa: E402
from wop.post.numbers import FLAG_OPTIONS, VALUE_OPTIONS  # noqa: E402
from wop.post.tokens import TOKENS  # noqa: E402


def main() -> None:
    print("## Concepts\n")
    print("| Section | If no post has it | What it writes |\n|---|---|---|")
    for concept in CONCEPTS.values():
        print(f"| `[{concept.name}]` | {'error when used' if concept.needed else 'writes nothing'} | {concept.description} |")
    print("\n## Tokens\n")
    print("| Token | Works in | Options | What it is | Example |\n|---|---|---|---|---|")
    for token in TOKENS.values():
        where = "every concept" if token.concepts is None else ", ".join(sorted(token.concepts))
        options = sorted(token.options | ({"changed"} if token.changeable else set()))
        print(f"| `<{token.name}>` | {where} | {', '.join(options)} | {token.description} | `{token.example}` |")
    print("\n## Options\n")
    print("| Option | Meaning |\n|---|---|")
    for name, meaning in {**FLAG_OPTIONS, **VALUE_OPTIONS}.items():
        print(f"| `{name}` | {meaning} |")


if __name__ == "__main__":
    main()
