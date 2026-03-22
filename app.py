import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from dateutil import parser
from pytz import timezone
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# --- Configuration & Styling ---
load_dotenv()

st.set_page_config(page_title="Work Dashboard", layout="wide")


def load_css(file_name):
    with open(file_name, encoding="utf-8") as css_file:
        st.markdown(f"<style>{css_file.read()}</style>", unsafe_allow_html=True)


load_css("style.css")


class JiraExporter:
    def __init__(self, jira_url, email, token):
        self.url = f"{jira_url.rstrip('/')}/rest/api/3/search/jql"
        self.base_url = jira_url.rstrip("/")
        self.email = email
        self.token = token
        self.auth = HTTPBasicAuth(self.email, self.token)

    def format_to_est(self, date_str):
        if not date_str:
            return "N/A"
        try:
            utc_dt = parser.parse(date_str)
            est_dt = utc_dt.astimezone(timezone("US/Eastern"))
            return est_dt.strftime("%Y-%m-%d %I:%M %p")
        except Exception:
            return "N/A"

    @st.cache_data(ttl=600)
    def fetch_and_process(_self, jql_query):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        fields = ["summary", "status", "assignee", "reporter", "created", "updated"]
        max_results = 100

        try:
            issues = []
            next_page_token = None

            while True:
                payload = {
                    "jql": jql_query,
                    "maxResults": max_results,
                    "fields": fields,
                }
                if next_page_token:
                    payload["nextPageToken"] = next_page_token

                response = requests.post(_self.url, json=payload, headers=headers, auth=_self.auth)
                response.raise_for_status()
                response_data = response.json()
                batch = response_data.get("issues", [])
                issues.extend(batch)

                if response_data.get("isLast", True):
                    break

                next_page_token = response_data.get("nextPageToken")
                if not next_page_token:
                    break

            data = []
            for issue in issues:
                fields_data = issue.get("fields", {})
                key = issue.get("key")
                ticket_url = f"{_self.base_url}/browse/{key}"
                data.append(
                    {
                        "Key": ticket_url,
                        "Key Label": key,
                        "Summary": fields_data.get("summary"),
                        "Assignee": (fields_data.get("assignee") or {}).get("displayName", "Unassigned"),
                        "Reporter": (fields_data.get("reporter") or {}).get("displayName", "Unknown"),
                        "Status": (fields_data.get("status") or {}).get("name"),
                        "Created (EST)": _self.format_to_est(fields_data.get("created")),
                        "Updated (EST)": _self.format_to_est(fields_data.get("updated")),
                    }
                )
            return pd.DataFrame(data)
        except requests.HTTPError as e:
            error_details = e.response.text if e.response is not None else str(e)
            st.error(f"Jira API Error: {error_details}")
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Jira API Error: {e}")
            return pd.DataFrame()


def style_status(val):
    color_map = {
        "In Progress": "background-color: #d4edda; color: #155724;",
        "Waiting for approval": "background-color: #f8d7da; color: #721c24;",
        "Awaiting User": "background-color: #f8d7da; color: #721c24;",
        "Open": "background-color: #fff3cd; color: #856404;",
        "Assigned": "background-color: #fff3cd; color: #856404;",
        "Closed": "background-color: #f4f4f4; color: #383d41;",
        "Resolved": "background-color: #f4f4f4; color: #383d41;",
    }
    return color_map.get(val, "")


def style_stale_issues(val):
    if not val or val == "N/A":
        return ""
    try:
        updated_dt = datetime.strptime(val, "%Y-%m-%d %I:%M %p")
        est_tz = timezone("US/Eastern")
        updated_dt = est_tz.localize(updated_dt)
        now = datetime.now(est_tz)
        if (now - updated_dt).total_seconds() > 172800:
            return "color: #000; font-weight: bold;"
    except Exception:
        pass
    return ""


def dataframe_height_for_rows(row_count):
    header_height = 38
    row_height = 27
    padding = 6
    max_height = 760
    content_height = header_height + (max(row_count, 1) * row_height) + padding
    return min(content_height, max_height)


STATUS_SORT_ORDER = {
    "Open": 1,
    "Assigned": 2,
    "In Progress": 3,
    "Waiting for approval": 4,
    "Awaiting User": 5,
    "Resolved": 98,
    "Closed": 99,
}


def parse_display_datetime(value):
    if not value or value == "N/A":
        return datetime.max
    try:
        return datetime.strptime(value, "%Y-%m-%d %I:%M %p")
    except Exception:
        return datetime.max


def sort_ticket_dataframe(df):
    df_sorted = df.copy()
    df_sorted["Status Sort"] = df_sorted["Status"].map(STATUS_SORT_ORDER).fillna(50)
    df_sorted["Created Sort"] = df_sorted["Created (EST)"].apply(parse_display_datetime)
    df_sorted = df_sorted.sort_values(["Status Sort", "Created Sort"], ascending=[True, True])
    return df_sorted.drop(columns=["Status Sort", "Created Sort"])


def build_jql(view_name, created_start=None, created_end=None):
    if view_name == "Reported":
        owner_clause = "reporter = currentUser() AND (assignee != currentUser() OR assignee IS EMPTY)"
    else:
        owner_clause = "assignee = currentUser()"

    if created_start and created_end:
        filters = [
            owner_clause,
            f'created >= "{created_start.strftime("%Y-%m-%d")}"',
            f'created <= "{created_end.strftime("%Y-%m-%d")}"',
        ]
    else:
        filters = [owner_clause, "(resolution = Unresolved OR resolved >= -14d)"]

    return " AND ".join(filters) + " ORDER BY created DESC"


def initialize_settings():
    st.session_state.setdefault("jira_url", os.getenv("JIRA_URL", "").strip())
    st.session_state.setdefault("jira_email", os.getenv("JIRA_EMAIL", "").strip())
    st.session_state.setdefault("jira_api_token", os.getenv("JIRA_API_TOKEN", "").strip())


def current_jira_settings():
    return {
        "jira_url": st.session_state.get("jira_url", "").strip(),
        "email": st.session_state.get("jira_email", "").strip(),
        "token": st.session_state.get("jira_api_token", "").strip(),
    }


def render_admin_center():
    st.markdown("## Admin")
    with st.expander("Manage Jira connection settings for the current browser session.", expanded=False):
        with st.form("admin_center_form"):
            jira_url = st.text_input("Jira URL", value=st.session_state.get("jira_url", ""))
            jira_email = st.text_input("Email", value=st.session_state.get("jira_email", ""))
            jira_api_token = st.text_input(
                "API Token",
                value=st.session_state.get("jira_api_token", ""),
                type="password",
            )
            apply_settings = st.form_submit_button("Apply Credentials")

    if apply_settings:
        st.session_state["jira_url"] = jira_url.strip()
        st.session_state["jira_email"] = jira_email.strip()
        st.session_state["jira_api_token"] = jira_api_token.strip()
        st.cache_data.clear()
        st.success("Jira credentials updated for this session.")
        st.rerun()

def render_dataframe(df, hidden_column, search_text=""):
    if df.empty:
        return False

    df_display = sort_ticket_dataframe(df.drop(columns=[hidden_column]))
    if search_text.strip():
        search_blob = df_display.astype(str).agg(" ".join, axis=1)
        df_display = df_display[search_blob.str.contains(search_text, case=False, na=False)]

    if df_display.empty:
        return False
    styled_df = (
        df_display.style.map(style_status, subset=["Status"]).map(
            style_stale_issues, subset=["Updated (EST)"]
        )
    )
    st.dataframe(
        styled_df,
        width="stretch",
        hide_index=True,
        height=dataframe_height_for_rows(len(df_display)),
        column_config={
            "Key": st.column_config.LinkColumn(
                "Key",
                help="Click to open ticket in Jira",
                validate="^https://.*",
                display_text=r"([^/]+)$",
            ),
        },
    )
    return True


def render_jira_tickets():
    settings = current_jira_settings()

    if not all(settings.values()):
        st.warning("Set Jira URL, email, and API token in Admin before loading tickets.")
        return

    exporter = JiraExporter(settings["jira_url"], settings["email"], settings["token"])

    header_left, header_mid, header_right = st.columns([0.22, 0.28, 0.50])

    with header_left:
        st.markdown("## Jira")

    with header_mid:
        search_text = st.text_input(
            "Search tickets",
            placeholder="Search all table fields",
            label_visibility="collapsed",
        )

    with header_right:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([0.24, 0.38, 0.30, 0.10])

        with filter_col1:
            use_created_date_filter = st.checkbox("Created Date", value=False)

        with filter_col2:
            default_end_date = datetime.now().date()
            default_start_date = default_end_date - timedelta(days=13)
            selected_dates = st.date_input(
                "Created date range",
                value=(default_start_date, default_end_date),
                disabled=not use_created_date_filter,
                label_visibility="collapsed",
            )

        with filter_col3:
            st.markdown(
                f'<div class="header-refresh-text">Last Refresh: {datetime.now(timezone("US/Eastern")).strftime("%I:%M %p EST")}</div>',
                unsafe_allow_html=True,
            )

        with filter_col4:
            if st.button("🔄", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    created_start = None
    created_end = None
    if use_created_date_filter:
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            created_start, created_end = selected_dates
        elif isinstance(selected_dates, list) and len(selected_dates) == 2:
            created_start, created_end = selected_dates

        if created_start and created_end and created_start > created_end:
            created_start, created_end = created_end, created_start

    reported_query = build_jql("Reported", created_start, created_end)
    assigned_query = build_jql("Assigned", created_start, created_end)

    tab1, tab2 = st.tabs(["📤 Reported by Me", "📥 Assigned to Me"])

    with tab1:
        if not render_dataframe(exporter.fetch_and_process(reported_query), "Reporter", search_text):
            st.info("No reported issues found for the current filters.")

    with tab2:
        if not render_dataframe(exporter.fetch_and_process(assigned_query), "Assignee", search_text):
            st.info("No assigned issues found for the current filters.")


initialize_settings()

with st.sidebar:
    st.subheader("Applications")
    page = st.radio("Navigation", ["Jira", "Admin"], label_visibility="collapsed")

if page == "Admin":
    render_admin_center()
else:
    render_jira_tickets()
