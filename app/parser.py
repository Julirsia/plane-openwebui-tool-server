from __future__ import annotations

from bs4 import BeautifulSoup

from app.renderer import SECTION_TITLES, render_section, text_to_html


def parse_ticket_sections(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    parsed: dict[str, str] = {}
    for section in soup.select("section[data-ticket-section]"):
        key = section.get("data-ticket-section", "").strip()
        if not key:
            continue
        title = section.find("h2")
        if title is not None:
            title.extract()
        parsed[key] = section.get_text("\n", strip=True)
    return parsed


def upsert_ticket_sections(html: str, sections: dict[str, str], section_order: list[str] | None = None) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.body is not None:
        container = soup.body
    else:
        container = soup
    existing_nodes = {
        node.get("data-ticket-section", "").strip(): node
        for node in container.select("section[data-ticket-section]")
    }
    order_lookup = {key: idx for idx, key in enumerate(section_order or [])}
    for key, value in sections.items():
        new_node = BeautifulSoup(render_section(key, text_to_html(value)), "html.parser").section
        if key in existing_nodes:
            existing_nodes[key].replace_with(new_node)
            existing_nodes[key] = new_node
            continue
        target = None
        for sibling_key, sibling_node in existing_nodes.items():
            if order_lookup.get(sibling_key, 10_000) > order_lookup.get(key, 10_000):
                target = sibling_node
                break
        if target is not None:
            target.insert_before(new_node)
        else:
            container.append(new_node)
        existing_nodes[key] = new_node
    return "".join(str(node) for node in container.contents)


def parse_note_type(comment_html: str) -> str:
    soup = BeautifulSoup(comment_html or "", "html.parser")
    text = soup.get_text("\n", strip=True)
    first_line = text.splitlines()[0] if text else ""
    if first_line.startswith("[") and "]" in first_line:
        return first_line.split("]", 1)[0].strip("[]").lower()
    return "internal_note"


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text("\n", strip=True)
