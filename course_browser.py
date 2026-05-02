"""
水课finder — JHU 课程评估浏览器

使用方法：
1. 安装依赖（仅需一次）：
       pip3 install streamlit pandas
2. 文件结构应该是这样：
       shuikefinder/
       ├── course_browser.py
       ├── jhu_eval_scraper.py
       ├── jhu_catalog_scraper.py
       ├── cookie.txt
       ├── manual_overrides.csv      （app 自动生成/更新）
       └── jhu/
           └── as.020/
               ├── evals.csv         （评估爬虫生成）
               └── catalog.csv       （目录爬虫生成，可选）
3. 运行：
       cd Desktop/shuikefinder
       streamlit run course_browser.py
4. 浏览器会自动打开。要停止应用，在 Terminal 中按 Ctrl+C。

管理员模式：在侧边栏底部输入密码 6629 进入。
管理员可以为任何课程手动设置三个标签（工作量、老师、简单到无聊），
覆盖会保存到 manual_overrides.csv。
"""

import streamlit as st
import pandas as pd
import os
import re
import glob
import hashlib
from datetime import datetime, date

# ─── 配置 ─────────────────────────────────────────────────────────────────────

EVALS_PATTERN = os.path.join("*", "*", "evals.csv")
CATALOG_PATTERN = os.path.join("*", "*", "catalog.csv")
OVERRIDES_FILE = "manual_overrides.csv"
DAILY_FILTER_FILE = "daily_filter.csv"
ADMIN_PASSWORD = "6629"

# 院系代码 → 中文/英文名映射（管理员维护）
# 用于侧边栏「数据来源」展示，让代码更易读。
# 没有匹配的代码会显示为 "(name not set)"。
DEPT_NAMES = {
    # ─── ARTS & SCIENCES ───
    "as.001": "First Year Seminars",
    "as.004": "University Writing Program",
    "as.010": "History of Art",
    "as.020": "Biology",
    "as.030": "Chemistry",
    "as.040": "Classics",
    "as.050": "Cognitive Science",
    "as.060": "English",
    "as.061": "Film and Media Studies",
    "as.070": "Anthropology",
    "as.080": "Neuroscience",
    "as.100": "History",
    "as.110": "Mathematics",
    "as.130": "Near Eastern Studies",
    "as.131": "Near Eastern Studies",
    "as.132": "Near Eastern Studies",
    "as.133": "Near Eastern Studies",
    "as.134": "Near Eastern Studies",
    "as.136": "Archaeology",
    "as.140": "History of Science, Medicine, and Technology",
    "as.145": "Medicine, Science and the Humanities",
    "as.150": "Philosophy",
    "as.171": "Physics & Astronomy",
    "as.172": "Physics & Astronomy",
    "as.173": "Physics & Astronomy",
    "as.180": "Economics",
    "as.190": "Political Science",
    "as.191": "Political Science",
    "as.192": "International Studies",
    "as.194": "Islamic Studies",
    "as.196": "Agora Institute",
    "as.197": "Economy and Society",
    "as.200": "Psychological & Brain Sciences",
    "as.210": "Modern Languages & Literatures",
    "as.211": "Modern Languages & Literatures",
    "as.212": "Modern Languages & Literatures",
    "as.213": "Modern Languages & Literatures",
    "as.214": "Modern Languages & Literatures",
    "as.215": "Modern Languages & Literatures",
    "as.216": "Modern Languages & Literatures",
    "as.217": "Modern Languages & Literatures",
    "as.220": "Writing Seminars",
    "as.225": "Theatre Arts & Studies",
    "as.230": "Sociology",
    "as.250": "Biophysics",
    "as.270": "Earth & Planetary Sciences",
    "as.271": "Earth & Planetary Sciences",
    "as.280": "Public Health Studies",
    "as.290": "Behavioral Biology",
    "as.300": "Comparative Thought and Literature",
    "as.305": "Critical Study of Racism, Immigration, & Colonialism",
    "as.310": "East Asian Studies",
    "as.360": "Interdepartmental",
    "as.361": "Latin American, Caribbean, and Latinx Studies",
    "as.362": "Center for Africana Studies",
    "as.363": "Study of Women, Gender, & Sexuality",
    "as.370": "Center for Language Education",
    "as.371": "Art",
    "as.373": "Center for Language Education",
    "as.374": "Military Science",
    "as.375": "Center for Language Education",
    "as.376": "Music",
    "as.377": "Center for Language Education",
    "as.378": "Center for Language Education",
    "as.379": "Center for Language Education",
    "as.380": "Center for Language Education",
    "as.381": "Center for Language Education",
    "as.389": "Program in Museums and Society",
    # ─── ENGINEERING ───
    "en.500": "General Engineering",
    "en.501": "First Year Seminars (EN)",
    "en.510": "Materials Science & Engineering",
    "en.515": "Materials Science and Engineering",
    "en.520": "Electrical & Computer Engineering",
    "en.525": "Electrical and Computer Engineering",
    "en.530": "Mechanical Engineering",
    "en.535": "Mechanical Engineering",
    "en.540": "Chemical & Biomolecular Engineering",
    "en.545": "Chemical and Biomolecular Engineering",
    "en.553": "Applied Mathematics & Statistics",
    "en.555": "Financial Mathematics",
    "en.560": "Civil and Systems Engineering",
    "en.565": "Civil Engineering",
    "en.570": "Environmental Health and Engineering",
    "en.575": "Environmental Engineering and Science",
    "en.580": "Biomedical Engineering",
    "en.585": "Applied Biomedical Engineering",
    "en.595": "Engineering Management",
    "en.601": "Computer Science",
    "en.605": "Computer Science",
    "en.615": "Applied Physics",
    "en.620": "Robotics",
    "en.625": "Applied and Computational Mathematics",
    "en.635": "Information Systems Engineering",
    "en.645": "Systems Engineering",
    "en.650": "Information Security Institute",
    "en.655": "Healthcare Systems Engineering",
    "en.660": "Center for Leadership Education",
    "en.661": "Center for Leadership Education",
    "en.662": "Center for Leadership Education",
    "en.663": "Center for Leadership Education",
    "en.665": "Robotics and Autonomous Systems",
    "en.670": "Institute for NanoBio Technology",
    "en.675": "Space Systems Engineering",
    "en.685": "Data Science",
    "en.695": "Cybersecurity",
    "en.700": "Doctor of Engineering",
    "en.705": "Artificial Intelligence",
}

# 课程级别桶
LEVEL_BUCKETS = ["100s", "200s", "300s", "400s", "500s", "600s", "700s+"]

# 工作量阈值
WL_T1, WL_T2, WL_T3, WL_T4 = 2.4, 2.8, 3.2, 3.6

# 老师评分阈值
TE_HIGH, TE_LOW = 4.4, 3.8

# 智力挑战阈值
IC_BORING = 3.7


# ─── 标签定义 ─────────────────────────────────────────────────────────────────

# 工作量标签（按顺序：从最水到最难）
WORKLOAD_TAGS = [
    ("🟢", "水的不能再水了", "green"),
    ("🔵", "水课",           "blue"),
    ("🟣", "正常课",         "violet"),
    ("🟡", "有点难了",       "orange"),
    ("🔴", "你想疯吗",       "red"),
]

# 老师标签
TEACHING_TAGS = [
    ("🙇", "我想给老师磕一个", "green"),
    ("😐", "老师还行吧",      "blue"),
    ("😤", "老师比较矫情",    "red"),
]

# 简单到无聊标签
BORING_TAG = ("💤", "简单到无聊", "gray")

# 管理员选项
ADMIN_NONE = "（无标签）"


def workload_label_to_tag(label):
    for tag in WORKLOAD_TAGS:
        if tag[1] == label:
            return tag
    return None


def teaching_label_to_tag(label):
    for tag in TEACHING_TAGS:
        if tag[1] == label:
            return tag
    return None


# ─── 数据加载 ─────────────────────────────────────────────────────────────────

@st.cache_data
def load_evals():
    """从所有 学校/院系/evals.csv 加载评估数据。"""
    files = sorted(glob.glob(EVALS_PATTERN))
    if not files:
        return pd.DataFrame(), []

    dfs = []
    for fp in files:
        try:
            d = pd.read_csv(fp)
            parts = fp.split(os.sep)
            d["school"] = parts[-3] if len(parts) >= 3 else "unknown"
            d["dept_path"] = parts[-2] if len(parts) >= 2 else "unknown"
            dfs.append(d)
        except Exception as e:
            st.warning(f"无法加载 {fp}: {e}")

    df = pd.concat(dfs, ignore_index=True)
    for col in ["workload_avg", "teaching_avg", "intellectual_avg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["base_code"] = df["course_code"].str.extract(
        r"^([A-Z]{2}\.\d{3}\.\d{3})", expand=False
    )
    return df, files


@st.cache_data
def load_catalog():
    files = sorted(glob.glob(CATALOG_PATTERN))
    if not files:
        return pd.DataFrame()
    dfs = []
    for fp in files:
        try:
            dfs.append(pd.read_csv(fp))
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def load_overrides():
    """
    加载手动覆盖 CSV。无缓存以便管理员保存后立即看到变化。

    支持的列：
        course_code      课程代码（必需）
        recommendation   take / avoid / 空（普通备注用横幅显示）
        note             备注文字
        workload_tag     管理员设置的工作量标签（如"水课"）
        teaching_tag     管理员设置的老师标签
        boring_tag       是否强制显示"简单到无聊"标签（true/false）
        last_updated     时间戳
    """
    cols = ["course_code", "recommendation", "note",
            "workload_tag", "teaching_tag", "boring_tag",
            "last_updated"]
    if not os.path.exists(OVERRIDES_FILE):
        return pd.DataFrame({c: pd.Series(dtype="string") for c in cols})
    # 强制所有列读为字符串，避免 pandas 把空列推断成 float
    df = pd.read_csv(OVERRIDES_FILE, dtype="string", keep_default_na=False)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].astype("string").fillna("")


def load_daily_filter():
    """
    加载每日好课的过滤设置。无缓存。

    存储为长格式 CSV：
        kind          "department" 或 "level"
        value         dept code（如 "as.020"）或 level bucket（如 "100s"）
        enabled       "true" / "false"

    没文件 = 默认所有项都启用（无过滤，等同于当前行为）。
    返回: (allowed_dept_codes_set, allowed_level_buckets_set, file_exists_bool)
    """
    if not os.path.exists(DAILY_FILTER_FILE):
        return None, None, False
    try:
        df = pd.read_csv(DAILY_FILTER_FILE, dtype="string", keep_default_na=False)
    except Exception:
        return None, None, False

    allowed_depts = set()
    allowed_levels = set()
    for _, row in df.iterrows():
        kind = str(row.get("kind", "")).strip().lower()
        value = str(row.get("value", "")).strip()
        enabled = str(row.get("enabled", "")).strip().lower() in ("true", "1", "yes")
        if not enabled:
            continue
        if kind == "department":
            allowed_depts.add(value.lower())
        elif kind == "level":
            allowed_levels.add(value)
    return allowed_depts, allowed_levels, True


def save_daily_filter(allowed_depts, allowed_levels, all_depts, all_levels):
    """
    保存每日好课过滤设置。
    传入：当前选中的 dept 集合、level 集合，以及全部可选项（用于记录禁用状态）。
    """
    rows = []
    for d in sorted(all_depts):
        rows.append({"kind": "department", "value": d,
                     "enabled": "true" if d in allowed_depts else "false"})
    for lvl in all_levels:
        rows.append({"kind": "level", "value": lvl,
                     "enabled": "true" if lvl in allowed_levels else "false"})
    df = pd.DataFrame(rows)
    df.to_csv(DAILY_FILTER_FILE, index=False)


def _read_known_depts(filename):
    """读取过滤文件里所有出现过的 dept code（无论启用与否）。"""
    if not os.path.exists(filename):
        return set()
    try:
        df = pd.read_csv(filename, dtype="string", keep_default_na=False)
    except Exception:
        return set()
    return {str(v).lower() for k, v in zip(df.get("kind", []), df.get("value", []))
            if str(k).strip().lower() == "department"}


def _read_known_levels(filename):
    """读取过滤文件里所有出现过的 level（无论启用与否）。"""
    if not os.path.exists(filename):
        return set()
    try:
        df = pd.read_csv(filename, dtype="string", keep_default_na=False)
    except Exception:
        return set()
    return {str(v) for k, v in zip(df.get("kind", []), df.get("value", []))
            if str(k).strip().lower() == "level"}


def get_dept_display_name(dept_code):
    """返回 'as.020 — Biology' 格式；没匹配的显示 '(name not set)'。"""
    name = DEPT_NAMES.get(dept_code.lower(), "(name not set)")
    return f"{dept_code} — {name}"


def code_to_level_bucket(course_code):
    """
    从课程代码（如 'AS.020.303.01.SP25'）提取课号最后一段（实际是中间段，
    例如 020.303 中的 303），按百位分桶。
    返回 '100s' / '200s' / ... / '700s+'，无法解析返回 None。
    """
    if not course_code:
        return None
    m = re.match(r"^[A-Z]{2}\.\d{3}\.(\d{3})", course_code)
    if not m:
        return None
    num = int(m.group(1))
    if num < 100:
        return None  # 罕见，如 AS.020.001
    if num >= 700:
        return "700s+"
    return f"{(num // 100) * 100}s"


def code_to_dept_code(course_code):
    """从 'AS.020.303.01.SP25' 提取 'as.020'。"""
    if not course_code:
        return None
    m = re.match(r"^([A-Z]{2}\.\d{3})", course_code)
    if not m:
        return None
    return m.group(1).lower()


def save_overrides(df):
    """保存覆盖文件。"""
    df.to_csv(OVERRIDES_FILE, index=False)


def upsert_override(course_code, **fields):
    """
    更新或插入一行覆盖。
    传入要修改的字段（如 workload_tag="水课"）。
    """
    df = load_overrides()
    fields["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if course_code in df["course_code"].values:
        for k, v in fields.items():
            df.loc[df["course_code"] == course_code, k] = v
    else:
        new_row = {"course_code": course_code,
                   "recommendation": "", "note": "",
                   "workload_tag": "", "teaching_tag": "", "boring_tag": ""}
        new_row.update(fields)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    save_overrides(df)


def delete_override_tags(course_code):
    """删除某课程的标签覆盖（保留 recommendation/note）。"""
    df = load_overrides()
    if course_code in df["course_code"].values:
        for col in ["workload_tag", "teaching_tag", "boring_tag"]:
            df.loc[df["course_code"] == course_code, col] = ""
        df.loc[df["course_code"] == course_code, "last_updated"] = (
            datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        save_overrides(df)


# ─── 业务逻辑：标签计算 ───────────────────────────────────────────────────────

def workload_tag_from_score(score):
    if score is None or pd.isna(score):
        return None
    if score < WL_T1: return WORKLOAD_TAGS[0]
    if score < WL_T2: return WORKLOAD_TAGS[1]
    if score < WL_T3: return WORKLOAD_TAGS[2]
    if score < WL_T4: return WORKLOAD_TAGS[3]
    return WORKLOAD_TAGS[4]


def teaching_tag_from_score(score):
    if score is None or pd.isna(score):
        return None
    if score > TE_HIGH: return TEACHING_TAGS[0]
    if score < TE_LOW:  return TEACHING_TAGS[2]
    return TEACHING_TAGS[1]


def boring_tag_from_scores(workload, intellectual):
    if workload is None or intellectual is None:
        return None
    if pd.isna(workload) or pd.isna(intellectual):
        return None
    if workload < WL_T2 and intellectual < IC_BORING:
        return BORING_TAG
    return None


def get_unique_courses(df):
    courses = (
        df.dropna(subset=["base_code"])
          .groupby("base_code")
          .agg({"course_title": "first"})
          .reset_index()
          .sort_values("base_code")
    )
    return list(zip(courses["base_code"], courses["course_title"]))


def get_course_rows(df, base_code):
    rows = df[df["base_code"] == base_code].copy()
    rows = rows.sort_values(["term", "instructor"])
    return rows


def aggregate_for_instructor(rows, instructor=None):
    if instructor and instructor != "全部教师（综合）":
        rows = rows[rows["instructor"] == instructor]
    if rows.empty:
        return {"workload": None, "teaching": None, "intellectual": None}
    return {
        "workload":     rows["workload_avg"].mean()     if "workload_avg" in rows else None,
        "teaching":     rows["teaching_avg"].mean()     if "teaching_avg" in rows else None,
        "intellectual": rows["intellectual_avg"].mean() if "intellectual_avg" in rows else None,
    }


def get_effective_tags(base_code, agg, overrides_df):
    """
    返回应该显示的三个标签（工作量、老师、简单到无聊），
    优先使用管理员覆盖，然后才是计算值。
    返回 dict: { "workload": tag_or_None, "teaching": tag_or_None,
                 "boring": tag_or_None, "is_overridden": bool }
    """
    override = None
    if not overrides_df.empty:
        match = overrides_df[overrides_df["course_code"] == base_code]
        if not match.empty:
            override = match.iloc[0]

    is_overridden = False
    wl_tag = workload_tag_from_score(agg["workload"])
    te_tag = teaching_tag_from_score(agg["teaching"])
    br_tag = boring_tag_from_scores(agg["workload"], agg["intellectual"])

    if override is not None:
        wl_label = str(override.get("workload_tag", "") or "").strip()
        te_label = str(override.get("teaching_tag", "") or "").strip()
        br_flag  = str(override.get("boring_tag", "") or "").strip().lower()

        if wl_label:
            wl_tag = workload_label_to_tag(wl_label)
            is_overridden = True
        if te_label:
            te_tag = teaching_label_to_tag(te_label)
            is_overridden = True
        if br_flag in ("true", "1", "yes"):
            br_tag = BORING_TAG
            is_overridden = True
        elif br_flag in ("false", "0", "no"):
            br_tag = None
            is_overridden = True

    return {
        "workload": wl_tag, "teaching": te_tag, "boring": br_tag,
        "is_overridden": is_overridden,
    }


# ─── 每日好课 ─────────────────────────────────────────────────────────────────

# 合格的工作量标签（按从最水到正常的顺序）—— 必须是水课或更水
ELIGIBLE_WORKLOAD_LABELS = {"水的不能再水了", "水课"}

# 合格的老师标签 —— 必须是还行或更好（不能是矫情）
ELIGIBLE_TEACHING_LABELS = {"我想给老师磕一个", "老师还行吧"}


def get_eligible_courses(courses, evals_df, overrides_df,
                         allowed_depts=None, allowed_levels=None):
    """
    返回所有满足"水课 + 老师还行" 条件的课程列表。
    每个元素是 (base_code, title, effective_tags_dict)。

    allowed_depts: 如果提供，只保留这些 dept code 的课程
    allowed_levels: 如果提供，只保留这些级别的课程（'100s', '200s', ...）
    None 表示不过滤该维度。
    """
    eligible = []
    for code, title in courses:
        # 应用每日过滤
        if allowed_depts is not None:
            dept = code_to_dept_code(code)
            if dept not in allowed_depts:
                continue
        if allowed_levels is not None:
            level = code_to_level_bucket(code)
            if level not in allowed_levels:
                continue

        rows = get_course_rows(evals_df, code)
        if rows.empty:
            continue
        agg = aggregate_for_instructor(rows, None)  # 综合所有教师
        eff = get_effective_tags(code, agg, overrides_df)

        wl = eff["workload"]
        te = eff["teaching"]
        if wl is None or te is None:
            continue
        if wl[1] not in ELIGIBLE_WORKLOAD_LABELS:
            continue
        if te[1] not in ELIGIBLE_TEACHING_LABELS:
            continue

        eligible.append((code, title, eff))
    return eligible


def pick_daily_course(eligible, salt=0):
    """
    根据今天的日期（本地时间）从合格池中选一门课。
    salt > 0 时用于管理员"换一个"功能 — 不影响普通用户。
    返回 (base_code, title, effective_tags) 或 None。
    """
    if not eligible:
        return None
    today_str = date.today().isoformat()  # 例如 "2026-05-01"
    seed_str = f"{today_str}#{salt}"
    # 用 sha256 把字符串映射成稳定的整数
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(eligible)
    return eligible[idx]


# ─── 界面 ─────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="水课finder", page_icon="📚", layout="centered")

evals_df, eval_files = load_evals()
catalog_df = load_catalog()
overrides_df = load_overrides()

if evals_df.empty:
    st.error(
        "❌ 找不到任何评估数据。\n\n"
        "请先按文件结构跑评估爬虫，例如：`jhu/as.020/evals.csv`"
    )
    st.stop()

courses = get_unique_courses(evals_df)

# ─── 侧边栏 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("图例")
    st.subheader("工作量")
    for emoji, label, color in WORKLOAD_TAGS:
        st.markdown(f":{color}[{emoji} **{label}**]")
    st.subheader("授课老师")
    for emoji, label, color in TEACHING_TAGS:
        st.markdown(f":{color}[{emoji} **{label}**]")
    st.subheader("额外标记")
    st.markdown(f":{BORING_TAG[2]}[{BORING_TAG[0]} **{BORING_TAG[1]}**]")

    st.divider()
    st.caption(f"已加载 {len(courses)} 门课程")
    st.caption(f"已加载 {len(overrides_df)} 条手动备注")
    if not catalog_df.empty:
        st.caption(f"已加载 {len(catalog_df)} 条课程目录信息")
    st.divider()
    # 数据来源 — 改成下拉菜单，显示 "as.020 — Biology" 格式
    # 列表会随院系增加而变长，下拉更整洁
    source_options = []
    for fp in eval_files:
        parts = fp.split(os.sep)
        if len(parts) >= 3:
            school = parts[-3]
            dept = parts[-2]
            display = f"{school} / {get_dept_display_name(dept)}"
            source_options.append(display)
    if source_options:
        with st.expander(f"数据来源（{len(source_options)} 个院系）"):
            for s in source_options:
                st.caption(f"• {s}")
    else:
        st.caption("数据来源：无")

    # 管理员登录
    st.divider()
    st.subheader("管理员")
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    if not st.session_state["is_admin"]:
        password_input = st.text_input(
            "密码", type="password", key="admin_pw_input",
            placeholder="输入密码进入管理员模式",
        )
        if password_input:
            if password_input == ADMIN_PASSWORD:
                st.session_state["is_admin"] = True
                st.rerun()
            else:
                st.error("密码错误")
    else:
        st.success("✓ 管理员已登录")
        if st.button("退出管理员模式"):
            st.session_state["is_admin"] = False
            st.rerun()


# ─── 主界面：分 Tab ───────────────────────────────────────────────────────────

if st.session_state.get("is_admin"):
    daily_tab, user_tab, admin_tab = st.tabs(["⭐ 每日好课", "🔍 浏览", "🔧 管理员"])
else:
    daily_tab, user_tab = st.tabs(["⭐ 每日好课", "🔍 浏览"])
    admin_tab = None

# ─── 每日好课 Tab ─────────────────────────────────────────────────────────────

with daily_tab:
    st.title("⭐ 每日好课")
    st.caption(f"今日推荐 · {date.today().strftime('%Y年%m月%d日')}")

    # 加载每日过滤设置
    allowed_depts, allowed_levels, filter_exists = load_daily_filter()
    if filter_exists:
        # 文件存在：用其中的设置；空集合 = 全禁
        eligible = get_eligible_courses(
            courses, evals_df, overrides_df,
            allowed_depts=allowed_depts,
            allowed_levels=allowed_levels,
        )
    else:
        # 默认：无过滤（当前行为）
        eligible = get_eligible_courses(courses, evals_df, overrides_df)

    # 管理员可以"换一个"，用 salt 重新选；普通用户不受影响
    if st.session_state.get("is_admin"):
        if "daily_salt" not in st.session_state:
            st.session_state["daily_salt"] = 0
        col_left, col_right = st.columns([3, 1])
        with col_right:
            if st.button("🎲 换一个", use_container_width=True):
                st.session_state["daily_salt"] += 1
        salt = st.session_state["daily_salt"]
        if salt > 0:
            with col_left:
                st.caption("⚙️ 管理员预览（仅你看到此课程，普通用户看到的是当日固定推荐）")
    else:
        salt = 0

    pick = pick_daily_course(eligible, salt=salt)

    if pick is None:
        st.info(
            "暂时没有合格的课程可推荐。\n\n"
            "条件：工作量为 **水课** 或更水，且老师评级为 **还行** 或更好。"
        )
    else:
        base_code, course_title, eff = pick

        # 大字号 hero 卡片
        st.markdown("")
        with st.container(border=True):
            st.markdown(f"## 📘 {course_title}")
            st.markdown(f"### `{base_code}`")

            rows = get_course_rows(evals_df, base_code)
            department = rows.iloc[0]["department"] if not rows.empty else ""
            if department:
                st.markdown(f"**院系：** {department}")

            # 教师列表
            all_instructors = sorted(rows["instructor"].dropna().unique().tolist())
            if all_instructors:
                st.markdown(f"**授课教师：** {' · '.join(all_instructors)}")

            st.divider()

            # 标签展示（突出显示）
            for key in ["workload", "teaching", "boring"]:
                tag = eff[key]
                if tag:
                    emoji, label, color = tag
                    st.markdown(f"## {emoji} :{color}[{label}]")

            # 备注（如有）
            override_match = overrides_df[overrides_df["course_code"] == base_code]
            if not override_match.empty:
                note = str(override_match.iloc[0].get("note", "") or "")
                if note:
                    st.divider()
                    st.info(f"ℹ️ {note}")

        st.caption(f"从 {len(eligible)} 门合格课程中挑选 · 明日 0 点更换")


# ─── 用户视图 ─────────────────────────────────────────────────────────────────

with user_tab:
    st.title("📚 水课finder")
    st.caption("搜索课程，查看综合评级。")

    search_query = st.text_input(
        "按课程代码或名称搜索",
        placeholder="例如：genetics、AS.020.303、biology",
    )

    if search_query:
        q = search_query.lower()
        matches = [
            (code, title) for code, title in courses
            if q in code.lower() or q in title.lower()
        ]
    else:
        matches = courses

    if not matches:
        st.warning("无匹配结果，请尝试其他关键词。")
    else:
        options = [f"{code} — {title}" for code, title in matches]
        selected = st.selectbox(f"找到 {len(matches)} 个匹配", options)

        if selected:
            base_code = selected.split(" — ")[0]
            rows = get_course_rows(evals_df, base_code)

            if rows.empty:
                st.error("数据中找不到该课程。")
            else:
                st.divider()

                course_title = rows.iloc[0]["course_title"]
                department = rows.iloc[0]["department"]
                st.subheader(f"{base_code} — {course_title}")
                st.markdown(f"**院系：** {department}")

                # 教师下拉（默认按字母顺序选第一个）
                all_instructors = sorted(rows["instructor"].dropna().unique().tolist())
                instructor_options = ["全部教师（综合）"] + all_instructors
                default_idx = 1 if all_instructors else 0

                selected_instructor = st.selectbox(
                    "选择教师", instructor_options, index=default_idx,
                )

                instructor_filter = (None if selected_instructor == "全部教师（综合）"
                                     else selected_instructor)
                agg = aggregate_for_instructor(rows, instructor_filter)

                # 推荐/避免横幅
                override_match = overrides_df[overrides_df["course_code"] == base_code]
                if not override_match.empty:
                    rec = str(override_match.iloc[0].get("recommendation", "")).lower()
                    note = str(override_match.iloc[0].get("note", "") or "")
                    if rec == "avoid":
                        st.error(f"🚫 **手动标记 — 别选：** {note}")
                    elif rec == "take":
                        st.success(f"✅ **手动标记 — 推荐：** {note}")
                    elif note:
                        st.info(f"ℹ️ **备注：** {note}")

                # 标签
                st.markdown("### 评级")
                effective = get_effective_tags(base_code, agg, overrides_df)
                if effective["is_overridden"]:
                    st.caption("⚙️ 此课程的标签已被管理员调整")

                shown = 0
                for key in ["workload", "teaching", "boring"]:
                    tag = effective[key]
                    if tag:
                        emoji, label, color = tag
                        st.markdown(f"#### {emoji} :{color}[{label}]")
                        shown += 1

                if shown == 0:
                    st.info("此教师暂无足够数据生成评级。")


# ─── 管理员视图 ───────────────────────────────────────────────────────────────

if admin_tab is not None:
    with admin_tab:
        st.title("🔧 管理员面板")
        st.caption("查看所有课程的当前评级，并手动覆盖。")

        admin_search = st.text_input(
            "按课程代码或名称搜索（管理员）",
            placeholder="例如：genetics、AS.020.303",
            key="admin_search",
        )

        if admin_search:
            q = admin_search.lower()
            admin_matches = [
                (code, title) for code, title in courses
                if q in code.lower() or q in title.lower()
            ]
        else:
            admin_matches = courses

        # 课程总览表（管理员一目了然看到现有标签 + 覆盖状态）
        st.subheader(f"课程总览（{len(admin_matches)} 门）")

        overview_rows = []
        for code, title in admin_matches:
            rows = get_course_rows(evals_df, code)
            agg = aggregate_for_instructor(rows, None)  # 全部教师
            eff = get_effective_tags(code, agg, overrides_df)
            overview_rows.append({
                "课程代码": code,
                "课程名": title,
                "工作量": eff["workload"][1] if eff["workload"] else "—",
                "老师": eff["teaching"][1] if eff["teaching"] else "—",
                "简单到无聊": "✓" if eff["boring"] else "",
                "已覆盖": "⚙️" if eff["is_overridden"] else "",
            })

        st.dataframe(
            pd.DataFrame(overview_rows),
            hide_index=True, use_container_width=True, height=300,
        )

        st.divider()
        st.subheader("编辑标签覆盖")

        if not admin_matches:
            st.warning("没有匹配的课程。")
        else:
            edit_options = [f"{c} — {t}" for c, t in admin_matches]
            edit_selected = st.selectbox(
                "选择要编辑的课程", edit_options, key="admin_edit_select"
            )
            edit_code = edit_selected.split(" — ")[0]

            # 当前数据
            edit_rows = get_course_rows(evals_df, edit_code)
            edit_agg = aggregate_for_instructor(edit_rows, None)
            current_eff = get_effective_tags(edit_code, edit_agg, overrides_df)

            # 当前覆盖值
            current_override = overrides_df[overrides_df["course_code"] == edit_code]
            if not current_override.empty:
                cur_wl_label = str(current_override.iloc[0].get("workload_tag", "") or "")
                cur_te_label = str(current_override.iloc[0].get("teaching_tag", "") or "")
                cur_br_flag  = str(current_override.iloc[0].get("boring_tag", "") or "").lower()
            else:
                cur_wl_label, cur_te_label, cur_br_flag = "", "", ""

            # 显示当前自动计算 vs 实际显示
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**自动计算**")
                wl_auto = workload_tag_from_score(edit_agg["workload"])
                te_auto = teaching_tag_from_score(edit_agg["teaching"])
                br_auto = boring_tag_from_scores(edit_agg["workload"], edit_agg["intellectual"])
                st.caption(f"工作量: {wl_auto[1] if wl_auto else '—'}")
                st.caption(f"老师: {te_auto[1] if te_auto else '—'}")
                st.caption(f"简单到无聊: {'✓' if br_auto else '✗'}")
            with col_b:
                st.markdown("**当前显示**")
                st.caption(f"工作量: {current_eff['workload'][1] if current_eff['workload'] else '—'}")
                st.caption(f"老师: {current_eff['teaching'][1] if current_eff['teaching'] else '—'}")
                st.caption(f"简单到无聊: {'✓' if current_eff['boring'] else '✗'}")

            st.markdown("**设置覆盖标签**（选择"+ ADMIN_NONE +"则使用自动计算）")

            wl_options = [ADMIN_NONE] + [t[1] for t in WORKLOAD_TAGS]
            te_options = [ADMIN_NONE] + [t[1] for t in TEACHING_TAGS]
            br_options = [ADMIN_NONE, "强制显示", "强制隐藏"]

            wl_default = wl_options.index(cur_wl_label) if cur_wl_label in wl_options else 0
            te_default = te_options.index(cur_te_label) if cur_te_label in te_options else 0
            if cur_br_flag in ("true", "1", "yes"):
                br_default = 1
            elif cur_br_flag in ("false", "0", "no"):
                br_default = 2
            else:
                br_default = 0

            new_wl = st.selectbox("工作量覆盖", wl_options, index=wl_default, key="adm_wl")
            new_te = st.selectbox("老师覆盖", te_options, index=te_default, key="adm_te")
            new_br = st.selectbox("简单到无聊覆盖", br_options, index=br_default, key="adm_br")

            # 备注（可选）
            cur_note = ""
            if not current_override.empty:
                cur_note = str(current_override.iloc[0].get("note", "") or "")
            new_note = st.text_input("备注（可选，会显示在用户视图中）",
                                     value=cur_note, key="adm_note")

            save_col, clear_col = st.columns(2)
            with save_col:
                if st.button("💾 保存覆盖", type="primary", use_container_width=True):
                    fields = {
                        "workload_tag": "" if new_wl == ADMIN_NONE else new_wl,
                        "teaching_tag": "" if new_te == ADMIN_NONE else new_te,
                        "note": new_note,
                    }
                    if new_br == "强制显示":
                        fields["boring_tag"] = "true"
                    elif new_br == "强制隐藏":
                        fields["boring_tag"] = "false"
                    else:
                        fields["boring_tag"] = ""
                    upsert_override(edit_code, **fields)
                    st.success(f"已保存 {edit_code} 的覆盖")
                    st.rerun()

            with clear_col:
                if st.button("🗑 清除标签覆盖（保留备注）",
                             use_container_width=True):
                    delete_override_tags(edit_code)
                    st.success(f"已清除 {edit_code} 的标签覆盖")
                    st.rerun()

            st.divider()
            st.subheader("当前所有覆盖")
            if overrides_df.empty:
                st.caption("（无）")
            else:
                # 只显示有内容的列
                show_df = overrides_df.copy()
                # 把空字符串显示成 "—"
                for col in show_df.columns:
                    show_df[col] = show_df[col].fillna("").astype(str).replace("", "—")
                st.dataframe(show_df, hide_index=True, use_container_width=True)

        # ─── 每日好课过滤设置 ─────────────────────────────────────────────────
        st.divider()
        st.subheader("⭐ 每日好课筛选范围")
        st.caption("控制「每日好课」可以从哪些院系和课程级别中抽取课程。"
                   "默认全选 = 当前行为（不过滤）。")

        # 收集数据中实际出现的所有 dept codes
        all_depts_in_data = set()
        for code, _ in courses:
            d = code_to_dept_code(code)
            if d:
                all_depts_in_data.add(d)
        all_depts_sorted = sorted(all_depts_in_data)

        # 加载已存的过滤设置（如有）
        saved_depts, saved_levels, has_filter = load_daily_filter()
        if not has_filter:
            # 默认全选
            cur_depts = set(all_depts_sorted)
            cur_levels = set(LEVEL_BUCKETS)
        else:
            # 文件存在：用文件里的设置；如果数据里有新 dept 而文件没记录，默认包含
            saved_depts = saved_depts or set()
            saved_levels = saved_levels or set()
            cur_depts = saved_depts | (all_depts_in_data - _read_known_depts(DAILY_FILTER_FILE))
            cur_levels = saved_levels | (set(LEVEL_BUCKETS) - _read_known_levels(DAILY_FILTER_FILE))

        with st.form("daily_filter_form"):
            st.markdown("**院系（多选）**")
            # 给 multiselect 一个易读的格式
            dept_format = lambda d: get_dept_display_name(d)
            selected_depts = st.multiselect(
                "选择允许出现在「每日好课」的院系",
                options=all_depts_sorted,
                default=[d for d in all_depts_sorted if d in cur_depts],
                format_func=dept_format,
                key="filter_depts",
            )

            st.markdown("**课程级别（多选）**")
            st.caption("课号百位分组：100s = 100-199, 200s = 200-299, etc.")
            selected_levels = st.multiselect(
                "选择允许的课程级别",
                options=LEVEL_BUCKETS,
                default=[l for l in LEVEL_BUCKETS if l in cur_levels],
                key="filter_levels",
            )

            col_save, col_reset = st.columns(2)
            with col_save:
                save_clicked = st.form_submit_button(
                    "💾 保存筛选设置", type="primary", use_container_width=True,
                )
            with col_reset:
                reset_clicked = st.form_submit_button(
                    "🔄 重置为全选（默认）", use_container_width=True,
                )

        if save_clicked:
            save_daily_filter(
                set(selected_depts), set(selected_levels),
                all_depts_sorted, LEVEL_BUCKETS,
            )
            st.success(
                f"已保存：{len(selected_depts)}/{len(all_depts_sorted)} 院系，"
                f"{len(selected_levels)}/{len(LEVEL_BUCKETS)} 级别"
            )
            st.rerun()

        if reset_clicked:
            if os.path.exists(DAILY_FILTER_FILE):
                os.remove(DAILY_FILTER_FILE)
            st.success("已重置为默认（全选，不过滤）")
            st.rerun()

        # 预览：当前筛选下能选的合格课程数
        preview_eligible = get_eligible_courses(
            courses, evals_df, overrides_df,
            allowed_depts=set(selected_depts) if selected_depts != all_depts_sorted else None,
            allowed_levels=set(selected_levels) if selected_levels != LEVEL_BUCKETS else None,
        )
        st.caption(f"📊 当前筛选下「每日好课」可选池："
                   f"**{len(preview_eligible)} 门课程**")
