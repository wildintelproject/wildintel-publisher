#!/usr/bin/env python3
"""
Promote CHANGELOG.md's "Upcoming release" bullets for one product (CLI or
Web) to a dated, versioned entry under "Released", and write that entry's
content (without the version heading) to a separate notes file for use as
the GitHub Release body.

Used by .github/workflows/release-cli.yml and release-web.yml on a tag push
— no manual CHANGELOG.md edit is required before tagging.

Unlike a single-product changelog, CLI and Web are released independently
(`vX.Y.Z` tags for CLI, `web-vX.Y.Z` for Web) and "Upcoming release" mixes
bullets for both, so promotion filters by an inline "CLI: "/"Web: " prefix
convention on each bullet:

- A bullet prefixed "CLI: " (or "Web: ") only ever gets promoted (with the
  prefix stripped) when *that* product is the one being released; it's left
  untouched in "Upcoming release" otherwise.
- An unprefixed bullet is treated as shared and is promoted into whichever
  product releases next, then removed from "Upcoming release" — it is not
  duplicated into the other product's release later.

A subsection (### Added / ### Fixed / ### Changed / ...) that ends up with
no items on either side (promoted or remaining) is dropped from that side's
output entirely, rather than left as an empty heading.
"""
from __future__ import annotations

import argparse
import sys

UPCOMING_HEADING = "## Upcoming release"
RELEASED_HEADING = "## Released"
PLACEHOLDER_MARKERS = (
    "**Note:** The information in past release notes",
    "Please refer to the latest release for the most up-to-date information",
)


def find_section(lines: list[str], heading: str) -> tuple[int, int]:
    """Return (start, end) line indices for the section starting at `heading`.

    `start` is the index of the heading line itself; `end` is the index of
    the next top-level ("## ") heading, or len(lines) if there is none.
    """
    start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == heading)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return start, end


def parse_subsections(lines: list[str]) -> list[tuple[str, list[list[str]]]]:
    """Parse a "## Upcoming release" body into ordered (header, items).

    Each item is itself a list of raw lines: the "- ..." line plus any
    indented continuation lines that follow it, up to the next item or
    subsection header.
    """
    subsections: list[tuple[str, list[list[str]]]] = []
    header: str | None = None
    items: list[list[str]] = []
    current: list[str] | None = None

    def flush_item():
        nonlocal current
        if current is not None:
            items.append(current)
            current = None

    def flush_subsection():
        nonlocal header, items
        flush_item()
        if header is not None:
            subsections.append((header, items))
        header = None
        items = []

    for line in lines:
        if line.startswith("### "):
            flush_subsection()
            header = line
        elif line.startswith("- "):
            flush_item()
            current = [line]
        elif line.strip() == "":
            continue
        elif current is not None:
            current.append(line)
    flush_subsection()
    return subsections


def item_owner_and_stripped(item: list[str]) -> tuple[str | None, list[str]]:
    """Return (owning product or None if shared, item with any prefix stripped)."""
    first = item[0]
    content = first[2:]  # after "- "
    for product in ("CLI", "Web"):
        prefix = f"{product}: "
        if content.startswith(prefix):
            return product, [f"- {content[len(prefix):]}"] + item[1:]
    return None, item


def split_for_product(
    subsections: list[tuple[str, list[list[str]]]], product: str
) -> tuple[list[str], list[str]]:
    """Return (promoted_lines, remaining_lines) for `product`."""
    promoted_lines: list[str] = []
    remaining_lines: list[str] = []

    for header, items in subsections:
        promoted_items = []
        remaining_items = []
        for item in items:
            owner, output_item = item_owner_and_stripped(item)
            if owner is None or owner == product:
                promoted_items.append(output_item)
            else:
                remaining_items.append(item)

        if promoted_items:
            if promoted_lines:
                promoted_lines.append("\n")
            promoted_lines.append(header)
            for item in promoted_items:
                promoted_lines.extend(item)
        if remaining_items:
            if remaining_lines:
                remaining_lines.append("\n")
            remaining_lines.append(header)
            for item in remaining_items:
                remaining_lines.extend(item)

    return promoted_lines, remaining_lines


def build_link(repo: str, tag_name: str, prev_tag: str | None) -> str:
    if prev_tag:
        return f"https://github.com/{repo}/compare/{prev_tag}...{tag_name}"
    return f"https://github.com/{repo}/releases/tag/{tag_name}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--product", required=True, choices=["CLI", "Web"])
    parser.add_argument("--version", required=True, help="e.g. 0.2.0")
    parser.add_argument("--tag-name", required=True, help="e.g. v0.2.0 or web-v0.2.0")
    parser.add_argument("--date", required=True, help="ISO date, e.g. 2026-07-21")
    parser.add_argument("--repo", required=True, help="e.g. wildintelproject/wildintel-publisher")
    parser.add_argument("--prev-tag", default="", help="Previous tag for this product line, empty if none")
    parser.add_argument("--notes-out", required=True)
    args = parser.parse_args()

    with open(args.changelog, encoding="utf-8") as f:
        lines = f.readlines()

    up_start, up_end = find_section(lines, UPCOMING_HEADING)
    subsections = parse_subsections(lines[up_start + 1:up_end])

    promoted_lines, remaining_lines = split_for_product(subsections, args.product)

    if not promoted_lines:
        print(
            f"Nothing prefixed '{args.product}:' (or unprefixed/shared) under "
            "'Upcoming release' — aborting promotion.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.notes_out, "w", encoding="utf-8") as f:
        for line in promoted_lines:
            f.write(line if line.endswith("\n") else line + "\n")
        f.write("\n")

    link = build_link(args.repo, args.tag_name, args.prev_tag or None)
    new_heading = f"### [{args.product} v{args.version}]({link}) - {args.date}\n"

    rel_start, _ = find_section(lines, RELEASED_HEADING)
    released_rest = lines[rel_start + 1:]
    released_rest = [
        line for line in released_rest
        if not any(marker in line for marker in PLACEHOLDER_MARKERS)
    ]
    while released_rest and released_rest[0].strip() == "":
        released_rest.pop(0)

    new_upcoming_body = ["\n"]
    if remaining_lines:
        for line in remaining_lines:
            new_upcoming_body.append(line if line.endswith("\n") else line + "\n")
        new_upcoming_body.append("\n")

    new_lines = (
        lines[:up_start]
        + [UPCOMING_HEADING + "\n"]
        + new_upcoming_body
        + lines[rel_start:rel_start + 1]
        + ["\n", new_heading, "\n"]
        + [line if line.endswith("\n") else line + "\n" for line in promoted_lines]
        + ["\n"]
        + released_rest
    )

    with open(args.changelog, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"Promoted 'Upcoming release' ({args.product}) to {new_heading.strip()}")


if __name__ == "__main__":
    main()
