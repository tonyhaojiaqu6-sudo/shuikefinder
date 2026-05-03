"""
JHU Course Catalog Scraper (Bulk Mode)
Scrapes all AS (Arts & Sciences) and EN (Engineering) departments from
https://e-catalogue.jhu.edu/course-descriptions/

HOW TO USE:
1. Install dependencies (one-time):
       pip3 install requests beautifulsoup4
2. (Optional) Edit ONLY_DEPARTMENTS below to scrape just one or a few.
   Default: scrape all AS + EN.
3. Run:
       python3 jhu_catalog_scraper.py
4. Output: <school>/<department>/catalog.csv for each department
   e.g. jhu/as.020/catalog.csv, jhu/en.601/catalog.csv

OUTPUT COLUMNS:
    code              course code (e.g. "AS.030.101")
    title             course title
    credits           credit count
    description       FULL course description including any inline prereq/coreq
                      sentences (e.g. "Recommended Course Background: ...")
    fa_tags           comma-separated FA tags (e.g. "FA1, FA2")
    distribution      distribution areas
    prereq_codes      course codes mentioned in the formal Prerequisite(s): block
    prereq_text       full raw prerequisite block text
    restrictions      raw restriction/term/cross-list text
    raw_description   complete unmodified text block (for AI processing later)

NOTES:
- Only courses with AS.* or EN.* prefixes are saved. Cross-listed courses with
  other prefixes (ME.*, BU.*, etc.) found in these pages are skipped.
- Run time: ~1–2 minutes for all departments (with polite delays).
"""

import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import time

# ─── DEPARTMENT REGISTRY ──────────────────────────────────────────────────────

CATALOG_BASE = "https://e-catalogue.jhu.edu/course-descriptions"

DEPT_PAGES = [
    # ─── ARTS & SCIENCES ───
    ("as-first-year-seminars",                     ["as.001"]),
    ("as-university-writing-program",              ["as.004"]),
    ("history_of_art",                             ["as.010"]),
    ("biology",                                    ["as.020"]),
    ("chemistry",                                  ["as.030"]),
    ("classics",                                   ["as.040"]),
    ("cognitive_science",                          ["as.050"]),
    ("english",                                    ["as.060"]),
    ("film_and_media_studies",                     ["as.061"]),
    ("anthropology",                               ["as.070"]),
    ("neuroscience",                               ["as.080"]),
    ("history",                                    ["as.100"]),
    ("mathematics",                                ["as.110"]),
    ("near_eastern_studies",                       ["as.130", "as.131", "as.132", "as.133", "as.134"]),
    ("archaeology",                                ["as.136"]),
    ("history_of_science__medicine__and_technology", ["as.140"]),
    ("medicine__science_and_the_humanities",       ["as.145"]),
    ("philosophy",                                 ["as.150"]),
    ("physics___astronomy",                        ["as.171", "as.172", "as.173"]),
    ("economics",                                  ["as.180"]),
    ("political_science",                          ["as.190", "as.191"]),
    ("international_studies",                      ["as.192"]),
    ("islamic_studies",                            ["as.194"]),
    ("agora-institute",                            ["as.196"]),
    ("economy-society",                            ["as.197"]),
    ("psychological___brain_sciences",             ["as.200"]),
    ("modern_languages___literatures",             ["as.210", "as.211", "as.212", "as.213", "as.214", "as.215", "as.216", "as.217"]),
    ("writing_seminars",                           ["as.220"]),
    ("theatre_arts___studies",                     ["as.225"]),
    ("sociology",                                  ["as.230"]),
    ("biophysics",                                 ["as.250"]),
    ("earth___planetary_sciences",                 ["as.270", "as.271"]),
    ("public_health_studies",                      ["as.280"]),
    ("behavioral_biology",                         ["as.290"]),
    ("comparative_thought_and_literature",         ["as.300"]),
    ("critical-study-racism",                      ["as.305"]),
    ("east_asian_studies",                         ["as.310"]),
    ("interdepartmental",                          ["as.360"]),
    ("latin-american-caribbean-latinx-studies",    ["as.361"]),
    ("center_for_africana_studies",                ["as.362"]),
    ("study_of_women__gender____sexuality",        ["as.363"]),
    ("center_for_language_education",              ["as.370", "as.373", "as.375", "as.377", "as.378", "as.379", "as.380", "as.381"]),
    ("art",                                        ["as.371"]),
    ("military_science",                           ["as.374"]),
    ("music",                                      ["as.376"]),
    ("program_in_museums_and_society",             ["as.389"]),

    # ─── ENGINEERING ───
    ("general_engineering",                        ["en.500"]),
    ("EN-first-year-seminars",                     ["en.501"]),
    ("materials_science___engineering",            ["en.510"]),
    ("materials_science_and_engineering",          ["en.515"]),
    ("electrical___computer_engineering",          ["en.520"]),
    ("electrical_and_computer_engineering",        ["en.525"]),
    ("mechanical_engineering",                     ["en.530"]),
    ("ep_mechanical_engineering",                  ["en.535"]),
    ("chemical___biomolecular_engineering",        ["en.540"]),
    ("chemical_and_biomolecular_engineering",      ["en.545"]),
    ("applied_mathematics___statistics",           ["en.553"]),
    ("financial_mathematics",                      ["en.555"]),
    ("civil_engineering",                          ["en.560"]),
    ("ep_civil_engineering",                       ["en.565"]),
    ("environmental_health_and_engineering",       ["en.570"]),
    ("environmental_engineering_and_science",      ["en.575"]),
    ("biomedical_engineering",                     ["en.580"]),
    ("applied_biomedical_engineering",             ["en.585"]),
    ("engineering_management",                     ["en.595"]),
    ("computer_science_601",                       ["en.601"]),
    ("computer_science",                           ["en.605"]),
    ("applied_physics",                            ["en.615"]),
    ("robotics",                                   ["en.620"]),
    ("applied_and_computational_mathematics",      ["en.625"]),
    ("information_systems_engineering",            ["en.635"]),
    ("systems_engineering",                        ["en.645"]),
    ("information_security_institute",             ["en.650"]),
    ("healthcare_systems_engineering",             ["en.655"]),
    ("center_for_leadership_education",            ["en.660", "en.661", "en.662", "en.663"]),
    ("robotics-autonomous-systems",                ["en.665"]),
    ("institute_for_nanobio_technology",           ["en.670"]),
    ("space_systems_engineering",                  ["en.675"]),
    ("data_science",                               ["en.685"]),
    ("cybersecurity",                              ["en.695"]),
    ("doctor_of_engineering",                      ["en.700"]),
    ("artificial_intelligence",                    ["en.705"]),
]

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SCHOOL = "jhu"

# Optional: if non-empty, scrape ONLY these dept codes (e.g. ["as.020"]).
# Leave empty list to scrape all AS + EN.
ONLY_DEPARTMENTS = []

# Polite delay between page fetches
DELAY_SECONDS = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

# ─── PARSING HELPERS ──────────────────────────────────────────────────────────

COURSE_CODE_RE = re.compile(r"\b[A-Z]{2}\.\d{3}\.\d{3}\b")
HEADER_RE = re.compile(
    r"^([A-Z]{2}\.\d{3}\.\d{3})\.\s+"
    r"(.+?)\.\s+"
    r"(\d+(?:\.\d+)?)\s+Credits?\.?",
    re.MULTILINE
)
FA_TAG_RE = re.compile(r"\(FA\d+\)")


def fetch_catalog_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_course_blocks(html):
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.courseblock")
    if not blocks:
        blocks = soup.select("p.courseblocktitle")
        if blocks:
            return _pair_title_desc_blocks(soup)
    return blocks


def _pair_title_desc_blocks(soup):
    pairs = []
    for title_tag in soup.select("p.courseblocktitle"):
        desc_tag = title_tag.find_next_sibling(class_="courseblockdesc")
        wrapper = soup.new_tag("div")
        wrapper.append(title_tag)
        if desc_tag:
            wrapper.append(desc_tag)
        pairs.append(wrapper)
    return pairs


def parse_course_block(block):
    raw_text = block.get_text(separator="\n", strip=True)
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)

    header_match = HEADER_RE.search(raw_text)
    if not header_match:
        return None

    code = header_match.group(1)
    title = header_match.group(2).strip()
    credits = header_match.group(3)
    after_header = raw_text[header_match.end():].strip()

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
    """
    The description should include the actual prose AND any prereq/coreq/
    recommended background statements (since users want to see them).

    We only cut at fields that are clearly metadata after the prose — i.e.
    Distribution Area and Foundational Abilities labels. Everything else
    (Prerequisite(s), Recommended Course Background, Cross-listed, Writing
    Intensive, etc.) is kept inline.

    Also: JHU's catalog renders course codes as separate HTML links, which
    BeautifulSoup's get_text(separator="\\n") turns into "\\nAS.171.101\\n"
    fragments. Collapse those so the codes flow naturally inside sentences.
    """
    cut_points = [
        text.find("Distribution Area:"),
        text.find("AS Foundational Abilities:"),
        text.find("EN Foundational Abilities:"),
    ]
    cut_points = [p for p in cut_points if p >= 0]
    if cut_points:
        text = text[:min(cut_points)]

    # Course codes are surrounded by \n in the raw text. Replace those line
    # breaks with a single space so codes sit naturally in sentences like
    # "C- or better in AS.171.101 or AS.171.103."
    text = re.sub(
        r"\s*\n\s*([A-Z]{2}\.\d{3}\.\d{3})\s*\n\s*",
        r" \1 ",
        text
    )
    # Collapse any remaining multi-line breaks
    text = re.sub(r"\n+", " ", text)
    # Squash multiple spaces
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def _extract_section(text, label_regex):
    pattern = re.compile(
        re.escape(label_regex.replace("\\", ""))
        if "\\" not in label_regex else label_regex,
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return ""
    after = text[m.end():].strip()
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
    fa_sections = []
    for label in ["AS Foundational Abilities:", "EN Foundational Abilities:"]:
        idx = text.find(label)
        if idx >= 0:
            chunk = text[idx:idx + 500]
            fa_sections.append(chunk)
    tags = set()
    for section in fa_sections:
        for m in FA_TAG_RE.finditer(section):
            tags.add(m.group().strip("()"))
    return ", ".join(sorted(tags))


def _extract_course_codes(text):
    if not text:
        return ""
    codes = COURSE_CODE_RE.findall(text)
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
    """Extract only codes that aren't in restriction sentences."""
    if not prereq_text:
        return ""
    protected = COURSE_CODE_RE.sub(
        lambda m: m.group().replace(".", _SENTINEL), prereq_text
    )
    restriction_codes = set()
    for sentence in re.split(r"(?<=[.;|])\s*", protected):
        restored = sentence.replace(_SENTINEL, ".")
        if _RESTRICTION_KEYWORDS_RE.search(restored):
            for code in COURSE_CODE_RE.findall(restored):
                restriction_codes.add(code)
    all_codes = COURSE_CODE_RE.findall(prereq_text)
    seen = set()
    true_prereqs = []
    for c in all_codes:
        if c not in seen and c not in restriction_codes:
            seen.add(c)
            true_prereqs.append(c)
    return ", ".join(true_prereqs)


def _extract_restrictions(text):
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
            s = m.group().replace(SENTINEL, ".").strip()
            if s and s not in parts:
                parts.append(s)
    return " | ".join(parts)


# ─── ROUTING ──────────────────────────────────────────────────────────────────

def code_to_dept_folder(code):
    """Convert 'AS.020.303' to 'as.020'. Returns None if not AS or EN."""
    parts = code.split(".")
    if len(parts) < 3:
        return None
    school = parts[0].upper()
    if school not in ("AS", "EN"):
        return None
    return f"{parts[0].lower()}.{parts[1]}"


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "code", "title", "credits", "description",
    "fa_tags", "distribution",
    "prereq_codes", "prereq_text",
    "restrictions", "raw_description",
]


def write_to_csv(records, filename):
    out_dir = os.path.dirname(filename)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if ONLY_DEPARTMENTS:
        wanted = set(d.lower() for d in ONLY_DEPARTMENTS)
        pages = [(slug, depts) for slug, depts in DEPT_PAGES
                 if any(d in wanted for d in depts)]
        print(f"Filtering to {len(pages)} pages covering: {sorted(wanted)}\n")
    else:
        pages = DEPT_PAGES
        print(f"Scraping all {len(pages)} AS + EN catalog pages\n")

    records_by_dept = {}
    skipped_codes = set()
    failed_pages = []

    for i, (slug, dept_codes) in enumerate(pages, 1):
        url = f"{CATALOG_BASE}/{slug}/"
        print(f"[{i}/{len(pages)}] {slug}")
        try:
            html = fetch_catalog_page(url)
        except requests.RequestException as e:
            print(f"  ⚠️  Fetch failed: {e}")
            failed_pages.append(slug)
            time.sleep(DELAY_SECONDS)
            continue

        blocks = extract_course_blocks(html)
        if not blocks:
            print(f"  ⚠️  No course blocks found")
            failed_pages.append(slug)
            time.sleep(DELAY_SECONDS)
            continue

        page_count = 0
        page_skipped = 0
        for block in blocks:
            record = parse_course_block(block)
            if not record:
                continue
            folder = code_to_dept_folder(record["code"])
            if folder is None:
                skipped_codes.add(record["code"])
                page_skipped += 1
                continue
            records_by_dept.setdefault(folder, []).append(record)
            page_count += 1

        print(f"  ✓ Parsed {page_count} courses"
              + (f" (skipped {page_skipped} non-AS/EN)" if page_skipped else ""))
        time.sleep(DELAY_SECONDS)

    print(f"\n{'─' * 60}")
    print(f"Writing CSVs for {len(records_by_dept)} departments...")
    for folder, records in sorted(records_by_dept.items()):
        seen = set()
        unique = []
        for r in records:
            if r["code"] not in seen:
                seen.add(r["code"])
                unique.append(r)
        out_path = os.path.join(SCHOOL, folder, "catalog.csv")
        write_to_csv(unique, out_path)
        print(f"  ✓ {out_path}  ({len(unique)} courses)")

    print(f"\n{'─' * 60}")
    print(f"✅ Done. {len(records_by_dept)} departments saved under {SCHOOL}/")
    if skipped_codes:
        print(f"\n   Skipped {len(skipped_codes)} non-AS/EN cross-listings "
              f"(e.g. {', '.join(sorted(skipped_codes)[:5])}...)")
    if failed_pages:
        print(f"\n   ⚠️  Failed to scrape {len(failed_pages)} pages:")
        for p in failed_pages:
            print(f"      - {p}")


if __name__ == "__main__":
    main()
