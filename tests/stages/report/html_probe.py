"""Reads a rendered report.html the way a browser's parser would (stdlib
`html.parser`): its tags, its scripts' contents, and each section's text -
so the tests check structure and escaping, never pixels (5B)."""

from html.parser import HTMLParser


class Page(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[str] = []
        self.sections: dict[str, str] = {}
        self._in_script = False
        self._section: str | None = None
        self._text: list[str] = []
        # The appendix (the report redesign, step 3): text inside a <details>
        # is the analyst's; the rest is the front a shop owner reads.
        self._details = 0
        self._head = False
        self.front: list[str] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        self.tags.append((tag, found))
        if tag == "script":
            self._in_script = True
            self.scripts.append("")
        if tag == "section":
            self._section = found.get("id") or ""
            self.sections[self._section] = ""
        if tag == "details":
            self._details += 1
        if tag == "head":
            self._head = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False
        if tag == "section":
            self._section = None
        if tag == "details":
            self._details -= 1
        if tag == "head":
            self._head = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts[-1] += data
            return
        self._text.append(data)
        if not self._details and not self._head:
            self.front.append(data)
        if self._section is not None:
            self.sections[self._section] += " " + data  # each cell and element is its own run of text

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._text).split())

    @property
    def front_text(self) -> str:
        """Every word outside the appendix and the head."""
        return " ".join(" ".join(self.front).split())

    def section(self, section_id: str) -> str:
        return " ".join(self.sections[section_id].split())

    def ids(self) -> list[str]:
        return [attrs["id"] or "" for _, attrs in self.tags if attrs.get("id")]

    def named(self, tag: str) -> list[dict[str, str | None]]:
        return [attrs for name, attrs in self.tags if name == tag]
