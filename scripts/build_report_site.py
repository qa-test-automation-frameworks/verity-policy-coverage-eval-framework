"""Assemble the static report site in site/.

Converts committed Markdown artifacts to HTML pages and links them via a
shared nav header. If Allure HTML is already built at reports/allure-report/
it is copied to site/allure/. No API key required.

Pages produced:
  site/index.html          - defects-caught landing (the money screenshot)
  site/calibration.html    - judge calibration report
  site/cost.html           - token + cost summary (when present)
  site/vulnerabilities.html - adversarial vulnerability summary
  site/allure/             - Allure HTML report copy (when present)
"""

from __future__ import annotations

import shutil
from pathlib import Path

_SITE = Path("site")

_NAV = """
<nav style="font-family:sans-serif;background:#1a1a2e;padding:0.75rem 1.5rem;
            display:flex;gap:1.5rem;align-items:center;margin-bottom:1.5rem;">
  <strong style="color:#e2e8f0;font-size:1.1rem;">verity eval reports</strong>
  <a href="index.html" style="color:#90cdf4;text-decoration:none;">Defects Caught</a>
  <a href="calibration.html" style="color:#90cdf4;text-decoration:none;">Calibration</a>
  <a href="cost.html" style="color:#90cdf4;text-decoration:none;">Cost</a>
  <a href="vulnerabilities.html" style="color:#90cdf4;text-decoration:none;">Vulnerabilities</a>
  <a href="allure/index.html" style="color:#90cdf4;text-decoration:none;">Allure</a>
</nav>
"""

_CSS = """
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto;
         padding: 0 1rem 2rem; color: #1a202c; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; text-align: left; }
  th { background: #f7fafc; font-weight: 600; }
  tr:nth-child(even) { background: #f7fafc; }
  code { background: #edf2f7; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }
  pre code { background: none; padding: 0; }
  pre { background: #2d3748; color: #e2e8f0; padding: 1rem; border-radius: 6px;
        overflow-x: auto; }
  h1, h2, h3 { margin-top: 1.5rem; }
  hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }
</style>
"""


def _md_to_html(md_path: Path, title: str) -> str:
    """Convert a Markdown file to a full HTML page."""
    try:
        import markdown  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "The 'markdown' package is required: uv sync --extra report"
        ) from exc

    body = markdown.markdown(
        md_path.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc"],
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | verity eval</title>
  {_CSS}
</head>
<body>
{_NAV}
{body}
</body>
</html>
"""


def _placeholder_html(title: str, message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title} | verity eval</title>
  {_CSS}
</head>
<body>
{_NAV}
<h1>{title}</h1>
<p><em>{message}</em></p>
</body>
</html>
"""


def build_site(site_dir: Path = _SITE) -> dict[str, bool]:
    """Build the site and return a dict of page -> was_generated."""
    site_dir.mkdir(parents=True, exist_ok=True)
    generated: dict[str, bool] = {}

    # index.html — defects-caught
    defects_md = Path("docs/defects-caught.md")
    if defects_md.exists():
        (site_dir / "index.html").write_text(
            _md_to_html(defects_md, "Defects Caught"),
            encoding="utf-8",
        )
        generated["index.html"] = True
    else:
        (site_dir / "index.html").write_text(
            _placeholder_html(
                "Defects Caught",
                "Run `make defects-report` to generate docs/defects-caught.md",
            ),
            encoding="utf-8",
        )
        generated["index.html"] = False

    # calibration.html
    cal_md = Path("docs/calibration-report.md")
    if cal_md.exists():
        (site_dir / "calibration.html").write_text(
            _md_to_html(cal_md, "Judge Calibration"),
            encoding="utf-8",
        )
        generated["calibration.html"] = True
    else:
        (site_dir / "calibration.html").write_text(
            _placeholder_html("Judge Calibration", "docs/calibration-report.md not found"),
            encoding="utf-8",
        )
        generated["calibration.html"] = False

    # cost.html
    cost_md = Path("reports/cost-summary.md")
    if cost_md.exists():
        (site_dir / "cost.html").write_text(
            _md_to_html(cost_md, "Token & Cost Summary"),
            encoding="utf-8",
        )
        generated["cost.html"] = True
    else:
        (site_dir / "cost.html").write_text(
            _placeholder_html(
                "Token & Cost Summary",
                "Run any eval suite to produce reports/cost-summary.md",
            ),
            encoding="utf-8",
        )
        generated["cost.html"] = False

    # vulnerabilities.html
    vuln_md = Path("docs/seeded-defects.md")
    if vuln_md.exists():
        (site_dir / "vulnerabilities.html").write_text(
            _md_to_html(vuln_md, "Adversarial Vulnerability Summary"),
            encoding="utf-8",
        )
        generated["vulnerabilities.html"] = True
    else:
        (site_dir / "vulnerabilities.html").write_text(
            _placeholder_html(
                "Adversarial Vulnerability Summary",
                "docs/seeded-defects.md not found",
            ),
            encoding="utf-8",
        )
        generated["vulnerabilities.html"] = False

    # allure/  - copy if already built
    allure_src = Path("reports/allure-report")
    allure_dst = site_dir / "allure"
    if allure_src.exists() and allure_src.is_dir():
        if allure_dst.exists():
            shutil.rmtree(allure_dst)
        shutil.copytree(allure_src, allure_dst)
        generated["allure/"] = True
    else:
        allure_dst.mkdir(exist_ok=True)
        (allure_dst / "index.html").write_text(
            _placeholder_html(
                "Allure Report",
                "Run `make report-allure` to build the Allure report",
            ),
            encoding="utf-8",
        )
        generated["allure/"] = False

    return generated


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build static report site in site/")
    parser.add_argument("--site-dir", default="site", help="Output directory (default: site/)")
    args = parser.parse_args()

    site_dir = Path(args.site_dir)
    generated = build_site(site_dir)

    print(f"Site built at {site_dir}/")
    for page, ok in generated.items():
        mark = "ok" if ok else "placeholder"
        print(f"  {mark:<12}  {site_dir}/{page}")


if __name__ == "__main__":
    main()
