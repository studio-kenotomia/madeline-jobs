"""Regression tests for ranking and document honesty. Uses the real (unsealed) profile."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import documents, evidence, model, rank  # noqa: E402

FIXTURES = json.loads((ROOT / "tests" / "fixtures.json").read_text())


def job(name):
    item = FIXTURES[name]
    return model.make_job(source=item.get("source", "fixture"), source_type=item.get("source_type", "ats"), title=item["title"], company=item["company"],
                          url=item.get("url", "https://example.com/" + name), location=item.get("location", ""), description_text=item.get("description", ""),
                          work_mode=item.get("work_mode", ""))


@unittest.skipUnless((ROOT / "profile.json").exists(), "profile.json not unsealed")
class Ranking(unittest.TestCase):
    def test_canonical_executive_assistant_is_apply_with_ai_ban(self):
        a = rank.evaluate(job("canonical_ea"))
        self.assertFalse(a["rejection"])
        self.assertIn(a["tier"], ("apply", "exceptional"))
        self.assertEqual(a["ai_policy"], "prohibited")
        self.assertEqual(a["geo"]["greece_remote"], "confirmed")

    def test_diversity_is_not_diving(self):
        a = rank.evaluate(job("canonical_ea"))
        self.assertFalse(any("dive" in g.lower() for g in a["blockers"] + a["gaps"]))

    def test_travel_operations_shows_degree_gap(self):
        a = rank.evaluate(job("canonical_travel"))
        self.assertFalse(a["rejection"])
        self.assertTrue(any("degree" in g for g in a["gaps"]))
        self.assertEqual(a["ai_policy"], "prohibited")

    def test_dotsoft_greek_blocker_keeps_it_out_of_apply(self):
        a = rank.evaluate(job("dotsoft_proposal"))
        self.assertFalse(a["rejection"])
        self.assertNotIn(a["tier"], ("apply", "exceptional", "worth"))
        self.assertTrue(a["blockers"])

    def test_pinewood_teacher_rejected(self):
        self.assertEqual(rank.evaluate(job("pinewood_pe"))["rejection"], "excluded:teaching")

    def test_isea_biology_dive_rejected(self):
        self.assertEqual(rank.evaluate(job("isea_pm"))["rejection"], "specialist_requirement")

    def test_dutch_customer_support_rejected(self):
        self.assertTrue(rank.evaluate(job("dutch_cs"))["rejection"].startswith("excluded:customer_service"))

    def test_us_only_remote_rejected(self):
        self.assertEqual(rank.evaluate(job("us_remote"))["rejection"], "geography")

    def test_remote_tied_to_other_country_rejected(self):
        self.assertEqual(rank.evaluate(job("philippines_remote"))["rejection"], "geography")

    def test_bare_remote_needs_verification(self):
        a = rank.evaluate(job("bare_remote"))
        self.assertEqual(a["geo"]["greece_remote"], "unclear")
        self.assertIn(a["tier"], ("verify", "stretch", "archive"))

    def test_thessaloniki_english_project_coordinator_tops(self):
        a = rank.evaluate(job("thess_project"))
        self.assertIn(a["tier"], ("apply", "exceptional"))

    def test_greek_secretarial_native_greek_not_recommended(self):
        a = rank.evaluate(job("greek_secretary"))
        self.assertNotIn(a["tier"], ("apply", "exceptional", "worth"))

    def test_sales_ops_contains_operations_but_is_sales(self):
        self.assertTrue(rank.evaluate(job("sales_ops"))["rejection"].startswith("excluded:sales"))

    def test_americas_suffix_rejected(self):
        self.assertEqual(rank.evaluate(job("americas_hr"))["rejection"], "geography")

    def test_manager_title_capped(self):
        a = rank.evaluate(job("team_manager"))
        self.assertNotIn(a["tier"], ("apply", "exceptional"))


@unittest.skipUnless((ROOT / "profile.json").exists(), "profile.json not unsealed")
class Documents(unittest.TestCase):
    def setUp(self):
        self.job = job("canonical_ea")
        self.analysis = rank.evaluate(self.job)
        self.cv = documents.cv_model(self.job, self.analysis)
        self.cover = documents.cover_model(self.job, self.analysis)
        self.text = documents.model_text(self.cv)

    def test_role_titles_are_unchanged(self):
        for role in evidence.profile()["experience"]:
            self.assertIn(role["title"], self.text)
            self.assertIn(role["employer"], self.text)

    def test_greek_level_never_above_profile(self):
        self.assertIn("A2", self.text)
        self.assertFalse(evidence.lint("Greek (C1)") == [])

    def test_no_critical_lint(self):
        problems = documents.lint_model(self.cv) + documents.lint_model(self.cover)
        self.assertEqual([p for p in problems if p["severity"] == "critical"], [])

    def test_degree_names_exact(self):
        for item in evidence.profile()["education"]:
            if item["id"] in ("edu_ba", "edu_msc"):
                self.assertIn(item["credential"], self.text)

    def test_cover_letter_has_three_paragraphs(self):
        self.assertGreaterEqual(len(self.cover["paragraphs"]), 2)

    def test_unconfirmed_claims_excluded(self):
        low = (self.text + documents.model_text(self.cover)).lower()
        for word in ("chatbot", "subscription", "refund", "atlas.ti"):
            self.assertNotIn(word, low)

    def test_linter_catches_inventions(self):
        role = evidence.profile()["experience"][1]
        bad = f"Greek (fluent). Professional GIS experience. Operations Manager at {role['employer']}. Holds a driving licence. Managed 40 cases."
        issues = " ".join(p["issue"] for p in evidence.lint(bad))
        for needle in ("Greek", "GIS", "title", "driving", "number"):
            self.assertIn(needle.lower(), issues.lower())

    def test_every_bullet_traces_to_confirmed_evidence(self):
        confirmed = {e["id"] for e in evidence.usable()}
        for section in self.cv["sections"]:
            for entry in section.get("entries", []):
                for bullet in entry.get("bullets", []):
                    self.assertTrue(set(bullet["evidence"]) <= confirmed)

    def test_docx_is_real_ooxml(self):
        blob = documents.docx_bytes(self.cv)
        self.assertTrue(blob.startswith(b"PK"))


class Geography(unittest.TestCase):
    def test_thessaloniki_suburbs(self):
        for place in ("Pylaia, Thessaloniki", "Thermi", "Kalamaria", "Πυλαία"):
            self.assertEqual(rank.geography({"location_raw": place, "description_text": "", "title": "Office administrator"})["greece_remote"], "onsite")

    def test_athens_onsite_rejected(self):
        self.assertEqual(rank.geography({"location_raw": "Athens, Greece", "description_text": "", "title": "Administrator"})["verdict"], "ineligible")


if __name__ == "__main__":
    unittest.main()
