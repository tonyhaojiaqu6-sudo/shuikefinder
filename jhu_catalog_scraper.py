"""
JHU Course Catalog Scraper
Fetches course catalog data from https://e-catalogue.jhu.edu

HOW TO USE:
1. Install dependencies (one-time):
       pip3 install requests beautifulsoup4
2. Edit CATALOG_URL below to point at the department you want.
   Examples:
       Chemistry:  https://e-catalogue.jhu.edu/course-descriptions/chemistry/
       Biology:    https://e-catalogue.jhu.edu/course-descriptions/biology/
       Math:       https://e-catalogue.jhu.edu/course-descriptions/mathematics/
       CS:         https://e-catalogue.jhu.edu/course-descriptions/computer-science/
3. Set DEPARTMENT to match (e.g. "as.030" for Chemistry).
4. Run:
       python3 jhu_catalog_scraper.py
5. Output saved to: <school>/<department>/catalog.csv

OUTPUT COLUMNS:
    code              course code (e.g. "AS.030.101")
    title             course title
    credits           credit count (e.g. "3")
    description       course description (cleaned up, single paragraph)
    fa_tags           comma-separated FA tags (e.g. "FA1, FA2")
    distribution      distribution areas (e.g. "Natural Sciences")
    prereq_codes      course codes mentioned in prereq block (e.g. "AS.030.101, AS.030.102")
    prereq_text       full raw prerequisite text
    restrictions      raw text of restrictions, term offerings, cross-listings, etc.
    raw_description   the COMPLETE unmodified text block for the course
                      (kept for AI processing later)
"""

import requests
from bs4 import BeautifulSoup
import csv
import os
import re

# ─── CONFIG ───────────────────────────────────────────────────────────────────

CATALOG_URL = "https://e-catalogue.jhu.edu/course-descriptions/film_and_media_studies/"

SCHOOL = "jhu"
DEPARTMENT = "as.061"   # change to match the catalog url

OUTPUT_DIR = os.path.join(SCHOOL, DEPARTMENT)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "catalog.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

# ─── PARSING HELPERS ──────────────────────────────────────────────────────────

# Match course codes like AS.030.101, EN.601.220, EN.540.307, etc.
COURSE_CODE_RE = re.compile(r"\b[A-Z]{2}\.\d{3}\.\d{3}\b")

# Match the course header line: "AS.030.101.  General Chemistry I.  3 Credits."
HEADER_RE = re.compile(
    r"^([A-Z]{2}\.\d{3}\.\d{3})\.\s+"   # course code
    r"(.+?)\.\s+"                        # title (non-greedy)
    r"(\d+(?:\.\d+)?)\s+Credits?\.?",    # credits
    re.MULTILINE
)

# Match FA tags like "(FA1)", "(FA2)" inside text
FA_TAG_RE = re.compile(r"\(FA\d+\)")


def fetch_catalog_page(url):
    """Fetch the catalog page and return its HTML."""
    print(f"Fetching {url} ...")
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    print(f"  ✓ Got {len(response.text):,} chars\n")
    return response.text


def extract_course_blocks(html):
    """
    Find each course block in the catalog.

    JHU's catalog uses <div class="courseblock"> for each course (this is the
    standard CourseLeaf/Acalog structure). Each block contains a title line
    and a description.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try a few selectors — JHU may use different markup conventions
    blocks = soup.select("div.courseblock")
    if not blocks:
        # Fallback: some catalog pages wrap each course in <p> tags
        blocks = soup.select("p.courseblocktitle")
        # If we found titles via fallback, build pairs of (title, description)
        if blocks:
            return _pair_title_desc_blocks(soup)

    return blocks


def _pair_title_desc_blocks(soup):
    """Fallback: pair each .courseblocktitle <p> with following description."""
    pairs = []
    for title_tag in soup.select("p.courseblocktitle"):
        # The description usually follows in a sibling .courseblockdesc
        desc_tag = title_tag.find_next_sibling(class_="courseblockdesc")
        # Wrap them in a synthetic container
        wrapper = soup.new_tag("div")
        wrapper.append(title_tag)
        if desc_tag:
            wrapper.append(desc_tag)
        pairs.append(wrapper)
    return pairs


def parse_course_block(block):
    """Pull structured fields out of one course block."""
    # Get the entire block as text, normalized
    raw_text = block.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)

    # Parse the header line for code, title, credits
    header_match = HEADER_RE.search(raw_text)
    if not header_match:
        return None

    code = header_match.group(1)
    title = header_match.group(2).strip()
    credits = header_match.group(3)

    # Everything after the header
    after_header = raw_text[header_match.end():].strip()

    # Split into labeled sections we care about
    description = _extract_description(after_header)
    distribution = _extract_section(after_header, "Distribution Area:")
    fa_tags = _extract_fa_tags(after_header)
    prereq_text = _extract_section(after_header, "Prerequisite\\(s\\):")
    prereq_codes = _extract_true_prereq_codes(prereq_text) if prereq_text else ""
    restrictions = _extract_restrictions(after_header)

    return {
        "code": code,
        "title": title,
        "credits": credits,
        "description": description,
        "fa_tags": fa_tags,
        "distribution": distribution,
        "prereq_codes": prereq_codes,
        "prereq_text": prereq_text,
        "restrictions": restrictions,
        "raw_description": raw_text,
    }


def _extract_description(text):
    """The description is the first paragraph, before any labeled section."""
    # Cut at the first labeled section we recognize
    cut_points = [
        text.find("Distribution Area:"),
        text.find("AS Foundational Abilities:"),
        text.find("EN Foundational Abilities:"),
        text.find("Prerequisite(s):"),
        text.find("Recommended Course Background:"),
        text.find("Cross-listed"),
        text.find("Writing Intensive"),
    ]
    cut_points = [p for p in cut_points if p >= 0]
    if cut_points:
        text = text[:min(cut_points)]
    return text.strip()


def _extract_section(text, label_regex):
    """Extract content following a labeled section header."""
    pattern = re.compile(
        re.escape(label_regex.replace("\\", ""))
        if "\\" not in label_regex else label_regex,
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return ""
    after = text[m.end():].strip()
    # Stop at the next known label or 2 blank lines
    stop_patterns = [
        r"\n\s*Distribution Area:",
        r"\n\s*AS Foundational Abilities:",
        r"\n\s*EN Foundational Abilities:",
        r"\n\s*Prerequisite\(s\):",
        r"\n\s*Recommended Course Background:",
        r"\n\s*Writing Intensive",
        r"\n\s*Cross-listed",
        r"\n\n",
    ]
    end = len(after)
    for pat in stop_patterns:
        m2 = re.search(pat, after)
        if m2 and m2.start() < end:
            end = m2.start()
    return after[:end].strip()


def _extract_fa_tags(text):
    """Pull all (FA#) tags from both AS and EN Foundational Abilities sections."""
    # Find AS / EN Foundational Abilities sections
    fa_sections = []
    for label in ["AS Foundational Abilities:", "EN Foundational Abilities:"]:
        idx = text.find(label)
        if idx >= 0:
            # Take a chunk after the label and stop at next big section
            chunk = text[idx:idx + 500]
            fa_sections.append(chunk)

    tags = set()
    for section in fa_sections:
        for m in FA_TAG_RE.finditer(section):
            # Strip parentheses for cleaner output
            tags.add(m.group().strip("()"))

    return ", ".join(sorted(tags))


def _extract_course_codes(text):
    """Pull all course codes (AS.030.101, EN.601.220, etc.) from text."""
    if not text:
        return ""
    codes = COURSE_CODE_RE.findall(text)
    # Dedupe while preserving order
    seen = set()
    unique = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return ", ".join(unique)


# Keywords that signal a sentence is a restriction (anti-prereq), not a prereq
_RESTRICTION_KEYWORDS_RE = re.compile(
    r"may not enroll|restriction|must not|cannot enroll|"
    r"not (?:be )?eligible|excluded|not (?:have )?taken|"
    r"already (?:have )?completed|students who have completed",
    re.IGNORECASE
)
_SENTINEL = "\x00"


def _extract_true_prereq_codes(prereq_text):
    """
    Extract course codes that are genuine prerequisites — i.e. codes that appear
    in the prereq block but NOT inside restriction-type sentences.

    Example:
        "AS.020.303 AND AS.020.306; Cell Biology restriction: students who have
         completed EN.540.307 may not enroll."
        → prereq_codes = "AS.020.303, AS.020.306"  (EN.540.307 excluded)
    """
    if not prereq_text:
        return ""

    # Protect course codes from sentence-splitting
    protected = COURSE_CODE_RE.sub(
        lambda m: m.group().replace(".", _SENTINEL), prereq_text
    )

    # Find all codes that appear in restriction-type sentences
    restriction_codes = set()
    for sentence in re.split(r"(?<=[.;|])\s*", protected):
        restored = sentence.replace(_SENTINEL, ".")
        if _RESTRICTION_KEYWORDS_RE.search(restored):
            for code in COURSE_CODE_RE.findall(restored):
                restriction_codes.add(code)

    # Extract all codes from the full prereq block, excluding restriction ones
    all_codes = COURSE_CODE_RE.findall(prereq_text)
    seen = set()
    true_prereqs = []
    for c in all_codes:
        if c not in seen and c not in restriction_codes:
            seen.add(c)
            true_prereqs.append(c)

    return ", ".join(true_prereqs)


def _extract_restrictions(text):
    """
    Capture restriction-like statements:
      - 'restriction' clauses ('students who have ... may not enroll')
      - term offerings ('offered in fall terms only')
      - year/level limits ('Sophomores, Juniors, and Seniors Only')
      - cross-listings
      - 'Writing Intensive' label
    Returns concatenated raw text — we keep this loose since correctness > tidiness.

    Note: the sentence regex uses a "not preceded by a course code letter or
    digit" rule for periods, so course codes like AS.020.303 don't break sentences.
    """
    # Pre-process: protect course codes from sentence-splitting by temporarily
    # replacing their periods with a sentinel
    SENTINEL = "\x00"
    protected = COURSE_CODE_RE.sub(
        lambda m: m.group(0).replace(".", SENTINEL), text
    )

    parts = []
    patterns = [
        r"[^.]*\brestriction[s]?\b[^.]*\.",
        r"[^.]*\boffered in [^.]*terms only\b[^.]*\.",
        r"[^.]*\b(?:Sophomores?|Juniors?|Seniors?|Freshmen|Graduate Students?)\s*[^.]*\bOnly\b[^.]*\.",
        r"[^.]*\bCross-listed[^.]*\.",
        r"[^.]*\bmay not enroll\b[^.]*\.",
        r"[^.]*\bPerm\.\s*Req[^.]*\.",
        r"\bWriting Intensive\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, protected, flags=re.IGNORECASE):
            # Restore protected periods
            s = m.group().replace(SENTINEL, ".").strip()
            if s and s not in parts:
                parts.append(s)
    return " | ".join(parts)


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

def save_to_csv(records, filename):
    if not records:
        print("⚠️  No records to save.")
        return
    fieldnames = [
        "code", "title", "credits", "description",
        "fa_tags", "distribution",
        "prereq_codes", "prereq_text",
        "restrictions", "raw_description",
    ]
    out_dir = os.path.dirname(filename)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"\n✅ Saved {len(records)} courses to {filename}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    html = fetch_catalog_page(CATALOG_URL)
    blocks = extract_course_blocks(html)
    print(f"Found {len(blocks)} course blocks in HTML\n")

    if not blocks:
        # Save the raw HTML for debugging
        with open("debug_catalog.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("⚠️  No course blocks detected. Saved raw HTML to debug_catalog.html")
        print("   Open it in a browser, find a course block, and tell me what")
        print("   HTML tags/classes wrap each course.")
        return

    records = []
    for i, block in enumerate(blocks, 1):
        record = parse_course_block(block)
        if record:
            records.append(record)
        else:
            print(f"  [{i}] ⚠️  Couldn't parse this block (no header match)")

    print(f"Successfully parsed {len(records)} courses\n")

    save_to_csv(records, OUTPUT_FILE)

    # Preview first 3
    print("\nPreview (first 3 courses):")
    print("-" * 100)
    for r in records[:3]:
        print(f"📘 {r['code']}  {r['title']}  ({r['credits']} cr)")
        if r["fa_tags"]:
            print(f"   FA Tags: {r['fa_tags']}")
        if r["distribution"]:
            print(f"   Distribution: {r['distribution']}")
        if r["prereq_codes"]:
            print(f"   Prereq codes: {r['prereq_codes']}")
        if r["restrictions"]:
            print(f"   Restrictions: {r['restrictions'][:120]}"
                  + ("..." if len(r["restrictions"]) > 120 else ""))
        print()


if __name__ == "__main__":
    main()
