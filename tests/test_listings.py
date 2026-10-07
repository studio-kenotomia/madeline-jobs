"""Listing text, ages and descriptions. These do not need the private profile."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import model, rank, taxonomy  # noqa: E402
from engine.adapters import ats, greek  # noqa: E402

SKYWALKER = """
•
Με φυσική παρουσία
23 Σεπτεμβρίου 2026
Executive Personal Assistant - Δυτική Θεσσαλονίκη
περιοχές
1 }"
class="locations-list">
Ελλάδα
"""

SMART = """{"uuid":"abc","jobTitle":"Administrative & Proposal Assistant","postedDate":"2026-09-21T10:35:50.331Z","jobAdLocation":"Θεσσαλονίκη, Greece","company":{"name":"DOTSOFT SA"},"content":{"sections":{"jobDescription":{"title":"The role","text":"She would prepare proposals and keep the files in order."}}}}"""


class Listings(unittest.TestCase):
    def test_escaped_html_becomes_the_job_text(self):
        raw = "&lt;p&gt;&lt;strong&gt;URL:&lt;/strong&gt; &lt;a href=&quot;https://example.com&quot;&gt;https://example.com&lt;/a&gt;&lt;/p&gt;&lt;div&gt;Keeps the case files current.&lt;/div&gt;"
        text = model.readable(raw)
        self.assertNotIn("<", text)
        self.assertNotIn("https://example.com", text.splitlines()[0] if text else "")
        self.assertIn("case files", text)

    def test_skywalker_card_is_not_a_button_label(self):
        parsed = greek.parse_listing_text(SKYWALKER)
        self.assertEqual(parsed["title"], "Executive Personal Assistant - Δυτική Θεσσαλονίκη")
        self.assertEqual(parsed["date"], "2026-09-23")
        self.assertEqual(parsed["location"], "Thessaloniki, Greece")
        job = {"source": "skywalker", "title": "word.send your cv fast", "description_text": SKYWALKER}
        self.assertTrue(greek.repair_skywalker(job))
        self.assertFalse(job["title"].lower().startswith("word.send"))

    def test_smartrecruiters_blob_is_a_real_job(self):
        job = {"source": "smartrecruiters:dotsoftsa", "title": "https://jobs.smartrecruiters.com/dotsoftsa/1--role", "description_text": SMART, "canonical_url": "https://jobs.smartrecruiters.com/dotsoftsa/1--role", "company": ""}
        self.assertTrue(ats.repair_smartrecruiters(job))
        self.assertEqual(job["title"], "Administrative & Proposal Assistant")
        self.assertEqual(job["date_posted"], "2026-09-21")
        self.assertIn("proposals", job["description_text"])
        self.assertFalse(job["description_text"].startswith("{"))

    def test_hotel_front_office_is_not_an_office_job(self):
        self.assertEqual(taxonomy.family_of("Front Office Manager - Rhodes", "A hotel role.")[1], "hospitality")

    def test_older_than_a_year_is_dropped(self):
        now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.assertTrue(rank.posted_too_old({"date_posted": "2021-06-21"}, now))
        self.assertTrue(rank.posted_too_old({"date_posted": "2025-10-01"}, now))
        self.assertFalse(rank.posted_too_old({"date_posted": "2026-09-21"}, now))
        self.assertFalse(rank.posted_too_old({"date_posted": ""}, now))


if __name__ == "__main__":
    unittest.main()
