import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_feed as sync


BASE = (Path(__file__).resolve().parents[1] / "feed.xml").read_bytes()


def source_feed(*items):
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "The Grim Brief"
    for item in items:
        channel.append(copy.deepcopy(item))
    return ET.tostring(root)


def new_episode():
    item = ET.Element("item")
    ET.SubElement(item, "title").text = 'AI & tech: "The next episode"'
    ET.SubElement(item, "description").text = "News & analysis <with receipts>."
    ET.SubElement(item, "pubDate").text = "Mon, 19 Oct 2026 12:44:00 +0000"
    ET.SubElement(item, "enclosure", url=sync.MEDIA + 'test-next.mp3?a=1&b=2', length="12345", type="audio/mpeg")
    ET.SubElement(item, "guid").text = "test-next-episode"
    ET.SubElement(item, f"{{{sync.ITUNES}}}duration").text = "401"
    return item


class SyncFeedTests(unittest.TestCase):
    def test_existing_premiere_and_corrected_alias_do_not_duplicate_or_change_guid(self):
        current = ET.fromstring(BASE)
        premiere = next(item for item in current.findall("channel/item")
                        if item.find("enclosure").get("url") == sync.PREMIERE)
        original = copy.deepcopy(premiere)
        original.find("enclosure").set("url", sync.OLD_PREMIERE)
        original.find("enclosure").set("length", "2155621")
        original.find("guid").text = "ep-18bf980a-be75-421f-95b4-03ed4cc368ec"
        corrected = copy.deepcopy(premiere)
        corrected.find("guid").text = "ep-8f4b5694-b3d8-427d-ab61-31e897a24fe0"
        output, added = sync.merge_feeds(BASE, source_feed(original, corrected))
        self.assertEqual(added, 0)
        self.assertEqual(output, BASE)

    def test_new_episode_keeps_archive_metadata_and_xml_characters(self):
        before = ET.fromstring(BASE)
        output, added = sync.merge_feeds(BASE, source_feed(new_episode()))
        after = ET.fromstring(output)
        self.assertEqual(added, 1)
        self.assertEqual(len(after.findall("channel/item")), len(before.findall("channel/item")) + 1)
        after_by_guid = {item.findtext("guid"): item for item in after.findall("channel/item")}
        for old in before.findall("channel/item"):
            self.assertEqual(ET.tostring(old).strip(), ET.tostring(after_by_guid[old.findtext("guid")]).strip())
        for tag in ("description", f"{{{sync.ITUNES}}}author", f"{{{sync.ITUNES}}}owner/{{{sync.ITUNES}}}email"):
            self.assertEqual(before.findtext("channel/" + tag), after.findtext("channel/" + tag))
        item = after_by_guid["test-next-episode"]
        self.assertEqual(item.findtext("title"), new_episode().findtext("title"))
        self.assertEqual(item.find("enclosure").get("url"), new_episode().find("enclosure").get("url"))
        self.assertEqual(item.findtext(f"{{{sync.ITUNES}}}duration"), "6:41")
        self.assertIn("AI Generated.", item.findtext("description"))

    def test_repeated_sync_is_byte_identical(self):
        source = source_feed(new_episode())
        first, _ = sync.merge_feeds(BASE, source)
        second, added = sync.merge_feeds(first, source)
        self.assertEqual(added, 0)
        self.assertEqual(first, second)

    def test_empty_malformed_and_wrong_show_are_rejected(self):
        for source in (source_feed(), b"<html>broken", source_feed(new_episode()).replace(b"The Grim Brief", b"Private Briefing")):
            with self.subTest(source=source[:40]), self.assertRaises((ValueError, ET.ParseError)):
                sync.merge_feeds(BASE, source)

    def test_invalid_audio_date_or_size_are_rejected(self):
        bad_url = new_episode()
        bad_url.find("enclosure").set("url", "http://example.org/private.mp3")
        bad_size = new_episode()
        bad_size.find("enclosure").set("length", "0")
        bad_date = new_episode()
        bad_date.find("pubDate").text = "not-a-date"
        bad_type = new_episode()
        bad_type.find("enclosure").set("type", "text/html")
        missing_audio = new_episode()
        missing_audio.remove(missing_audio.find("enclosure"))
        for item in (bad_url, bad_size, bad_date, bad_type, missing_audio):
            with self.subTest(item=ET.tostring(item)), self.assertRaises(ValueError):
                sync.merge_feeds(BASE, source_feed(item))

    def test_reused_guid_for_different_audio_is_rejected(self):
        item = new_episode()
        item.find("guid").text = ET.fromstring(BASE).findtext("channel/item/guid")
        with self.assertRaisesRegex(ValueError, "reused an episode GUID"):
            sync.merge_feeds(BASE, source_feed(item))

    def test_source_failure_leaves_published_file_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feed.xml"
            source = Path(folder) / "source.xml"
            path.write_bytes(BASE)
            source.write_bytes(source_feed())
            with patch.object(sys, "argv", ["sync_feed.py", "--feed", str(path), "--source-file", str(source)]):
                with self.assertRaises(ValueError):
                    sync.main()
            self.assertEqual(path.read_bytes(), BASE)

    def test_atomic_write_publishes_valid_output(self):
        output, _ = sync.merge_feeds(BASE, source_feed(new_episode()))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feed.xml"
            path.write_bytes(BASE)
            sync.write_atomic(path, output)
            self.assertEqual(path.read_bytes(), output)
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
