from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
RDK = (ROOT / "doc/easymesh").is_dir()
HOME = ROOT / ("doc/easymesh" if RDK else "docs")
REFERENCE = ROOT / ("doc/easymesh/reference" if RDK else "reference")
TREES = (HOME,) if RDK else (HOME, REFERENCE)


def prose(content):
    lines = []
    fence = None
    for line in content.splitlines():
        marker = re.match(r"^\s*(\x60{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def targets(content):
    text = prose(content)
    inline = re.findall(r"\]\(<?([^\s)>]+)>?(?:\s+[\"'][^\n]*?[\"'])?\)", text)
    definitions = re.findall(r"^\s*\[[^\]]+\]:\s*<?([^\s>]+)>?", text, re.MULTILINE)
    return inline + definitions


def local_target(document, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return (document.parent / unquote(parsed.path)).resolve()


def documents():
    return sorted({path for tree in TREES for path in tree.rglob("*.md")} | {ROOT / "README.md"})


def anchors(content):
    identifiers = set()
    counts = {}
    for label in re.findall(r"^#{1,6} +(.+?) *#*$", prose(content), re.MULTILINE):
        label = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", label)
        slug = re.sub(r"[^\w\- ]", "", label.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        identifiers.add(slug if count == 0 else f"{slug}-{count}")
    identifiers.update(re.findall(r"(?:id|name)=[\"']([^\"']+)", content))
    return identifiers


class DocumentationTests(unittest.TestCase):
    def test_link_parser_ignores_fenced_examples(self):
        example = "[real](guide.md#start)\n~~~md\n[example](missing.md)\n~~~\n[ref]: other.md\n"
        self.assertEqual(targets(example), ["guide.md#start", "other.md"])
        self.assertIsNone(local_target(HOME / "README.md", "https://example.invalid/guide"))
        self.assertEqual(local_target(HOME / "README.md", "space%20name.md"), HOME / "space name.md")
        self.assertEqual(anchors("# A title\n# A title\n"), {"a-title", "a-title-1"})

    def test_local_links_resolve(self):
        failures = []
        for document in documents():
            for target in targets(document.read_text()):
                destination = local_target(document, target)
                if destination is not None and not destination.exists():
                    failures.append(f"{document.relative_to(ROOT)}: {target}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_local_heading_links_resolve(self):
        failures = []
        for document in documents():
            for target in targets(document.read_text()):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.fragment:
                    continue
                destination = local_target(document, target) or document
                if destination.suffix == ".md" and destination.is_file():
                    if unquote(parsed.fragment) not in anchors(destination.read_text()):
                        failures.append(f"{document.relative_to(ROOT)}: {target}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_packaged_document_inputs(self):
        if RDK:
            builder = (ROOT / "gen/vm/lxd/build.sh").read_text()
            self.assertIn("doc/easymesh/release-notes.md", builder)
            self.assertTrue((HOME / "release-notes.md").is_file())
            return
        packager = (ROOT / "deploy/lxd-vm/package-thin.sh").read_text()
        start = packager.index('DOCS_URL=')
        end = packager.index('cat > "$BUNDLE/release.env"', start)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, "ROOT": str(ROOT), "BUNDLE": directory}
            subprocess.run(["bash", "-c", packager[start:end]], env=environment, check=True)
            rendered = Path(directory, "INTERACTIVE.md").read_text()
            self.assertTrue(rendered.startswith("# Room and topology manual"))
            for target in targets(rendered):
                prefix = f"https://github.com/boardfarmdevs/prplmesh-lab/blob/{revision}/"
                self.assertTrue(target.startswith(prefix), target)
                self.assertTrue((ROOT / target[len(prefix):].split("#")[0]).is_file(), target)
        self.assertIn("README.md RELEASE-NOTES.md INTERACTIVE.md release.env", packager)

    def test_reference_pages_are_indexed(self):
        linked = {
            destination
            for index in REFERENCE.rglob("README.md")
            for target in targets(index.read_text())
            if (destination := local_target(index, target)) is not None
        }
        unindexed = [
            str(path.relative_to(ROOT))
            for path in REFERENCE.rglob("*.md")
            if path != REFERENCE / "README.md" and path not in linked
        ]
        self.assertEqual(sorted(unindexed), [])

    def test_guides_are_reachable_from_home(self):
        active = set(documents())
        visited = set()
        pending = [HOME / "README.md", ROOT / "README.md"]
        while pending:
            document = pending.pop()
            if document in visited:
                continue
            visited.add(document)
            for target in targets(document.read_text()):
                destination = local_target(document, target)
                if destination in active and destination not in visited:
                    pending.append(destination)
        self.assertEqual(sorted(str(path.relative_to(ROOT)) for path in active - visited), [])

    def test_introductory_documents_stay_short(self):
        for document in documents():
            limit = 10000 if REFERENCE in document.parents else 1400
            if document.name == "README.md":
                limit = 650
            with self.subTest(document=str(document.relative_to(ROOT))):
                self.assertLessEqual(len(document.read_text().split()), limit)

    def test_no_raw_results_or_dated_report_dumps(self):
        for tree in TREES:
            for path in tree.rglob("*"):
                if not path.is_file():
                    continue
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertIn(path.suffix.lower(), {".md", ".svg", ".png"})
                    self.assertNotIn("results", path.relative_to(tree).parts)
                    self.assertIsNone(re.search(r"-(?:0[89][0-3][0-9]|20\d{6})(?:-|\.)", path.name))


if __name__ == "__main__":
    unittest.main()
