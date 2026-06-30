"""Unit tests for the report site builder.

Tests cover the pure nav/template logic and the page generation routing.
No real markdown conversion is tested (that would require the markdown extra).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestBuildSite:
    def _make_site(self, tmp_path: Path) -> dict[str, bool]:
        """Build a site in tmp_path with mocked markdown conversion."""
        import importlib

        import scripts.build_report_site as mod

        importlib.reload(mod)

        def fake_md_to_html(md_path: Path, title: str) -> str:
            return f"<html><body>{title}</body></html>"

        with patch.object(mod, "_md_to_html", side_effect=fake_md_to_html):
            return mod.build_site(site_dir=tmp_path)

    def test_site_dir_is_created(self, tmp_path: Path) -> None:
        site = tmp_path / "output"
        self._make_site(site)
        assert site.exists()

    def test_index_html_generated_when_defects_md_present(self, tmp_path: Path) -> None:
        defects = Path("docs/defects-caught.md")
        if not defects.exists():
            return  # skip if artifact not generated yet
        result = self._make_site(tmp_path)
        assert result.get("index.html") is True
        assert (tmp_path / "index.html").exists()

    def test_calibration_html_generated_when_md_present(self, tmp_path: Path) -> None:
        cal = Path("docs/calibration-report.md")
        if not cal.exists():
            return
        result = self._make_site(tmp_path)
        assert result.get("calibration.html") is True

    def test_cost_html_always_written(self, tmp_path: Path) -> None:
        self._make_site(tmp_path)
        assert (tmp_path / "cost.html").exists()

    def test_allure_placeholder_when_no_report(self, tmp_path: Path) -> None:
        result = self._make_site(tmp_path)
        assert (tmp_path / "allure" / "index.html").exists()
        if not result.get("allure/"):
            content = (tmp_path / "allure" / "index.html").read_text()
            assert "Allure Report" in content

    def test_all_expected_pages_in_result(self, tmp_path: Path) -> None:
        result = self._make_site(tmp_path)
        expected = (
            "index.html",
            "calibration.html",
            "cost.html",
            "vulnerabilities.html",
            "allure/",
        )
        for page in expected:
            assert page in result, f"{page!r} missing from build_site() return value"


class TestNavContent:
    def test_nav_contains_all_links(self) -> None:
        import scripts.build_report_site as mod

        nav = mod._NAV
        expected_hrefs = (
            "index.html",
            "calibration.html",
            "cost.html",
            "vulnerabilities.html",
            "allure/index.html",
        )
        for href in expected_hrefs:
            assert href in nav, f"Nav link {href!r} missing"

    def test_placeholder_html_contains_message(self) -> None:
        import scripts.build_report_site as mod

        html = mod._placeholder_html("Test Title", "Test message here")
        assert "Test Title" in html
        assert "Test message here" in html
        assert "verity eval" in html


class TestVulnerabilitiesPage:
    def _make_site(self, tmp_path: Path) -> dict[str, bool]:
        import importlib
        import scripts.build_report_site as mod

        importlib.reload(mod)

        def fake_md_to_html(md_path: Path, title: str) -> str:
            return f"<html><body>{md_path.name}:{title}</body></html>"

        from unittest.mock import patch
        with patch.object(mod, "_md_to_html", side_effect=fake_md_to_html):
            return mod.build_site(site_dir=tmp_path)

    def test_vulnerabilities_uses_defects_caught_when_present(self, tmp_path: Path) -> None:
        defects_md = Path("docs/defects-caught.md")
        if not defects_md.exists():
            return
        result = self._make_site(tmp_path)
        assert result.get("vulnerabilities.html") is True
        content = (tmp_path / "vulnerabilities.html").read_text()
        assert "defects-caught.md" in content

    def test_vulnerabilities_placeholder_references_defects_report(self, tmp_path: Path) -> None:
        import importlib
        import scripts.build_report_site as mod

        importlib.reload(mod)

        def fake_md_to_html(md_path: Path, title: str) -> str:
            return f"<html><body>{md_path.name}</body></html>"

        from unittest.mock import patch
        # Remove defects-caught.md temporarily by patching Path.exists
        original_exists = Path.exists

        def patched_exists(self: Path) -> bool:
            if self.name == "defects-caught.md":
                return False
            return original_exists(self)

        with patch.object(mod, "_md_to_html", side_effect=fake_md_to_html):
            with patch.object(Path, "exists", patched_exists):
                result = mod.build_site(site_dir=tmp_path)

        assert result.get("vulnerabilities.html") is False
        content = (tmp_path / "vulnerabilities.html").read_text()
        assert "defects-report" in content
