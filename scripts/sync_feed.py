"""Append public Muse episodes without changing already-published identities."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import re
import tempfile
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SOURCE = "https://muse.ai/podcasts/feed/1386220001233313/95178f7a-9eb6-4e22-b8b3-580826012077"
MEDIA = "https://muse.ai/podcasts/media/1386220001233313/95178f7a-9eb6-4e22-b8b3-580826012077/"
OLD_PREMIERE = MEDIA + "ep-18bf980a-be75-421f-95b4-03ed4cc368ec.mp3"
PREMIERE = MEDIA + "ep-8f4b5694-b3d8-427d-ab61-31e897a24fe0.mp3"
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
MAX_BYTES = 5 * 1024 * 1024
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)


def parse_feed(raw: bytes) -> ET.Element:
    if len(raw) > MAX_BYTES or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Feed exceeds the limit or contains a forbidden DTD/entity")
    root = ET.fromstring(raw)
    if root.tag != "rss" or root.findtext("channel/title") != "The Grim Brief":
        raise ValueError("Expected The Grim Brief public RSS feed")
    return root


def canonical_url(url: str) -> str:
    return PREMIERE if url == OLD_PREMIERE else url


def duration(value: str) -> str:
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise ValueError("Invalid episode duration")
    if len(parts) > 1 and any(int(part) >= 60 for part in parts[1:]):
        raise ValueError("Invalid minutes/seconds in duration")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return f"{seconds // 60}:{seconds % 60:02d}"


def normalize_item(source: ET.Element, description: str) -> ET.Element:
    enclosure = source.find("enclosure")
    if enclosure is None:
        raise ValueError("Source episode has no audio enclosure")
    url = canonical_url(enclosure.get("url", ""))
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username or parsed_url.password:
        raise ValueError("Episode audio must have a public HTTPS URL")
    size = "3176677" if url == PREMIERE else enclosure.get("length", "")
    if not size.isdigit() or int(size) <= 0:
        raise ValueError("Episode audio needs a positive byte length")
    media_type = enclosure.get("type", "audio/mpeg")
    if not media_type.startswith("audio/"):
        raise ValueError("Episode enclosure must be audio")
    title = (source.findtext("title") or "").strip()
    published = (source.findtext("pubDate") or "").strip()
    if not title or not published or parsedate_to_datetime(published).tzinfo is None:
        raise ValueError("Episode needs a title and timezone-aware publication date")
    guid = (source.findtext("guid") or url).strip()
    if not guid:
        raise ValueError("Episode identity is empty")
    summary = source.findtext("description") or description
    if not re.search(r"\bAI[- ]generated\b", summary, re.IGNORECASE):
        summary = summary.rstrip() + " AI Generated."
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = summary
    ET.SubElement(item, "pubDate").text = published
    ET.SubElement(item, "enclosure", url=url, length=size, type=media_type)
    ET.SubElement(item, "guid", isPermaLink="false").text = guid
    value = "6:37" if url == PREMIERE else source.findtext(f"{{{ITUNES}}}duration")
    if value:
        ET.SubElement(item, f"{{{ITUNES}}}duration").text = duration(value)
    ET.SubElement(item, f"{{{ITUNES}}}explicit").text = "no"
    ET.SubElement(item, f"{{{ITUNES}}}episodeType").text = "full"
    return item


def merge_feeds(current_raw: bytes, source_raw: bytes) -> tuple[bytes, int]:
    root, source_root = parse_feed(current_raw), parse_feed(source_raw)
    channel = root.find("channel")
    assert channel is not None
    for required in (f"{{{ITUNES}}}author", f"{{{ITUNES}}}owner/{{{ITUNES}}}email", "description"):
        if not channel.findtext(required):
            raise ValueError(f"Public feed is missing {required}")
    image = channel.find(f"{{{ITUNES}}}image")
    if image is None or not image.get("href"):
        raise ValueError("Public feed is missing cover art")
    source_items = source_root.findall("channel/item")
    if not source_items:
        raise ValueError("Source feed is empty; keeping published feed untouched")
    existing_items = channel.findall("item")
    if not existing_items:
        raise ValueError("Expected an existing published episode archive")
    urls, guids = set(), {}
    for item in existing_items:
        enclosure, guid = item.find("enclosure"), item.findtext("guid")
        if enclosure is None or not enclosure.get("url") or not guid:
            raise ValueError("Existing episode identity is incomplete")
        url = canonical_url(enclosure.get("url", ""))
        if url in urls or guid in guids:
            raise ValueError("Existing feed already contains duplicate episodes")
        urls.add(url)
        guids[guid] = url
    new_items = []
    for source in source_items:
        item = normalize_item(source, channel.findtext("description", ""))
        url = item.find("enclosure").get("url")
        guid = item.findtext("guid")
        if guid in guids and guids[guid] != url:
            raise ValueError("Source reused an episode GUID for different audio")
        if url in urls:
            continue  # Preserve the public GUID, title and date already sent to Spotify.
        urls.add(url)
        guids[guid] = url
        new_items.append(item)
    if not new_items:
        return current_raw, 0  # No formatting-only commits or unnecessary deployments.
    # Keep old episodes even when Muse rolls them out of the source feed.
    for item in existing_items:
        channel.remove(item)
    all_items = existing_items + new_items
    all_items.sort(key=lambda item: parsedate_to_datetime(item.findtext("pubDate")), reverse=True)
    for item in all_items:
        channel.append(copy.deepcopy(item))
    ET.indent(root, space="  ")
    output = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
    parse_feed(output)
    return output, len(new_items)


def fetch_source() -> bytes:
    request = Request(SOURCE, headers={"User-Agent": "grim-brief-feed-sync/1.0"})
    with urlopen(request, timeout=60) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Source feed is too large")
    return raw


def write_atomic(path: Path, output: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(output)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=Path("feed.xml"))
    parser.add_argument("--source-file", type=Path, help="Local public source fixture for testing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source_file.read_bytes() if args.source_file else fetch_source()
    output, added = merge_feeds(args.feed.read_bytes(), source)
    if added and not args.dry_run:
        write_atomic(args.feed, output)
    print(f"Validated public source; {added} new episode(s); {len(ET.fromstring(output).findall('channel/item'))} total")


if __name__ == "__main__":
    main()
