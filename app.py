import os
import secrets
import time
import msal
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

st.set_page_config(page_title="Work Desk", layout="wide")


def load_css(file_name):
    with open(file_name, encoding="utf-8") as css_file:
        st.markdown(f"<style>{css_file.read()}</style>", unsafe_allow_html=True)


load_css("style.css")

TEAM_QUEUE_FIELD_ID = "customfield_11152"
TEAM_QUEUE_JQL_FIELD = "cf[11152]"
REPORTING_QUEUE_NAME = "Reporting"
GRAPH_SCOPES = ["User.Read"]
GRAPH_ME_ENDPOINT = "https://graph.microsoft.com/v1.0/me"
AUTH_QUERY_PARAMS = (
    "code",
    "state",
    "session_state",
    "error",
    "error_description",
    "error_subcode",
)
AUTH_STATE_TTL_SECONDS = 600


@st.cache_resource(show_spinner=False)
def auth_state_registry():
    return {}


def get_query_param_value(param_name):
    value = st.query_params.get(param_name, "")
    if isinstance(value, list):
        return value[0].strip() if value else ""
    return str(value).strip()


def current_entra_settings():
    return {
        "client_id": os.getenv("ENTRA_CLIENT_ID", "").strip(),
        "tenant_id": os.getenv("ENTRA_TENANT_ID", "").strip(),
        "client_secret": os.getenv("ENTRA_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("ENTRA_REDIRECT_URI", "http://localhost:8501").strip(),
    }


def entra_settings_ready(settings):
    return all(
        [
            settings["client_id"],
            settings["tenant_id"],
            settings["client_secret"],
            settings["redirect_uri"],
        ]
    )


def build_msal_client(settings):
    authority = f"https://login.microsoftonline.com/{settings['tenant_id']}"
    return msal.ConfidentialClientApplication(
        client_id=settings["client_id"],
        authority=authority,
        client_credential=settings["client_secret"],
    )


def clear_auth_query_params():
    for param_name in AUTH_QUERY_PARAMS:
        if param_name in st.query_params:
            del st.query_params[param_name]


def clear_legacy_user_email_param():
    if "user-email" in st.query_params:
        del st.query_params["user-email"]


def register_auth_state(auth_state):
    registry = auth_state_registry()
    now = time.time()
    expired_states = [
        state for state, created_at in registry.items()
        if now - created_at > AUTH_STATE_TTL_SECONDS
    ]
    for state in expired_states:
        registry.pop(state, None)
    registry[auth_state] = now


def consume_auth_state(auth_state):
    registry = auth_state_registry()
    created_at = registry.pop(auth_state, None)
    if not created_at:
        return False
    return time.time() - created_at <= AUTH_STATE_TTL_SECONDS


def fetch_graph_user(access_token):
    response = requests.get(
        f"{GRAPH_ME_ENDPOINT}?$select=displayName,mail,userPrincipalName,id",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=(5, 20),
    )
    response.raise_for_status()
    profile = response.json()
    email = (profile.get("mail") or profile.get("userPrincipalName") or "").strip()
    if not email:
        raise ValueError("Microsoft Graph did not return a usable email address.")
    return {
        "display_name": profile.get("displayName") or email,
        "email": email,
        "graph_id": profile.get("id", ""),
    }


def handle_entra_callback(settings):
    error = get_query_param_value("error")
    code = get_query_param_value("code")

    if not error and not code:
        return

    if error:
        clear_auth_query_params()
        st.error("Microsoft sign-in was not completed. Please try again.")
        return

    returned_state = get_query_param_value("state")
    expected_state = st.session_state.get("entra_auth_state", "")
    state_matches_session = expected_state and returned_state == expected_state
    state_matches_registry = consume_auth_state(returned_state)
    state_is_valid = state_matches_session or state_matches_registry
    if not state_is_valid:
        clear_auth_query_params()
        st.session_state.pop("entra_auth_state", None)
        st.error("Microsoft sign-in could not be verified. Please start sign-in again.")
        return

    try:
        token_response = build_msal_client(settings).acquire_token_by_authorization_code(
            code,
            scopes=GRAPH_SCOPES,
            redirect_uri=settings["redirect_uri"],
        )
        access_token = token_response.get("access_token")
        if not access_token:
            raise RuntimeError(token_response.get("error", "token_exchange_failed"))

        user = fetch_graph_user(access_token)
        st.session_state["entra_user"] = user
        st.session_state["jira_filter_email"] = user["email"]
        st.session_state.pop("entra_auth_state", None)
        st.cache_data.clear()
        clear_auth_query_params()
        st.rerun()
    except Exception:
        clear_auth_query_params()
        st.session_state.pop("entra_auth_state", None)
        st.error("Microsoft sign-in succeeded, but the app could not load your Graph profile.")


def render_sign_in(settings):
    auth_state = secrets.token_urlsafe(32)
    st.session_state["entra_auth_state"] = auth_state
    register_auth_state(auth_state)
    auth_url = build_msal_client(settings).get_authorization_request_url(
        scopes=GRAPH_SCOPES,
        redirect_uri=settings["redirect_uri"],
        state=auth_state,
        prompt="select_account",
    )
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        card_html = f"""
        <div class="login-card">
            <div class="login-logo">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ff4b4b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <line x1="9" y1="3" x2="9" y2="21"/>
                    <line x1="15" y1="3" x2="15" y2="21"/>
                    <line x1="3" y1="9" x2="21" y2="9"/>
                    <line x1="3" y1="15" x2="21" y2="15"/>
                </svg>
            </div>
            <h1 class="login-title">Work Desk</h1>
            <p class="login-subtitle">Single Sign-On</p>
            <div class="login-divider"></div>
            <a href="{auth_url}" class="sso-button" target="_self">
                <svg class="ms-logo" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 23 23">
                    <rect x="0" y="0" width="11" height="11" fill="#f25022"/>
                    <rect x="12" y="0" width="11" height="11" fill="#7fba00"/>
                    <rect x="0" y="12" width="11" height="11" fill="#00a4ef"/>
                    <rect x="12" y="12" width="11" height="11" fill="#ffb900"/>
                </svg>
                <span>Sign in with Microsoft</span>
            </a>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)


def require_entra_user():
    settings = current_entra_settings()
    if not entra_settings_ready(settings):
        st.warning("Microsoft sign-in is not configured. Add Entra settings to the .env file.")
        st.stop()

    handle_entra_callback(settings)

    user = st.session_state.get("entra_user")
    if user:
        return user

    render_sign_in(settings)
    st.stop()


def signed_in_email():
    user = st.session_state.get("entra_user") or {}
    return (user.get("email") or "").strip()


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

    def post_with_retry(self, payload, headers, max_attempts=3):
        last_error = None
        request_headers = {**headers, "Connection": "close"}

        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    self.url,
                    json=payload,
                    headers=request_headers,
                    auth=self.auth,
                    timeout=(10, 60),
                )
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout) as error:
                last_error = error
                if attempt == max_attempts - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))

        raise last_error

    def format_custom_field_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, dict):
            for key in ("value", "name", "displayName"):
                if value.get(key):
                    return str(value[key])
            return str(value)
        if isinstance(value, list):
            formatted_values = [self.format_custom_field_value(item) for item in value]
            return ", ".join([item for item in formatted_values if item])
        return str(value)

    @st.cache_data(ttl=600, show_spinner=False)
    def fetch_and_process(_self, jql_query):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        fields = ["summary", "status", "assignee", "reporter", "created", "updated", TEAM_QUEUE_FIELD_ID]
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

                response = _self.post_with_retry(payload, headers)
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
                        "Team Queue": _self.format_custom_field_value(
                            fields_data.get(TEAM_QUEUE_FIELD_ID)
                        ),
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
        except (requests.ConnectionError, requests.Timeout) as e:
            st.error(f"Jira API Error: connection to Jira failed after retries: {e}")
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Jira API Error: {e}")
            return pd.DataFrame()


def style_status(val):
    color_map = {
        "In Progress": "background-color: #d4edda; color: #155724;",
        "Code Fix in Progress": "background-color: #d4edda; color: #155724;",
        "Waiting for approval": "background-color: #f8d7da; color: #721c24;",
        "Awaiting User": "background-color: #f8d7da; color: #721c24;",
        "On Hold": "background-color: #f8d7da; color: #721c24;",
        "Form Approval": "background-color: #f8d7da; color: #721c24;",
        "ON HOLD / DEPENDANCY": "background-color: #f8d7da; color: #721c24;",
        "Open": "background-color: #fff3cd; color: #856404;",
        "Assigned": "background-color: #fff3cd; color: #856404;",
        "Closed": "background-color: #f4f4f4; color: #383d41;",
        "Resolved": "background-color: #f4f4f4; color: #383d41;",
    }
    return color_map.get(val, "")

STATUS_SORT_ORDER = {
    "Open": 1,
    "Assigned": 2,
    "In Progress": 3,
    "Code Fix in Progress" : 4,
    "Waiting for approval": 5,
    "Awaiting User": 6,
    "Form Approval": 7,
    "On Hold": 8,
    "ON HOLD / DEPENDANCY": 9,
    "Resolved": 98,
    "Closed": 99,
}

INACTIVE_COUNT_STATUSES = {"canceled", "cancelled", "closed", "resolved"}


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
    row_height = 35 
    content_height = header_height + (max(row_count, 1) * row_height) 
    max_height = 650
    return min(content_height, max_height)





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


def active_ticket_count(df):
    if df.empty or "Status" not in df.columns:
        return 0
    normalized_status = df["Status"].fillna("").astype(str).str.strip().str.lower()
    return int((~normalized_status.isin(INACTIVE_COUNT_STATUSES)).sum())


def escape_jql_value(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_jql(view_name, filter_email, created_start=None, created_end=None):
    jira_user = escape_jql_value(filter_email)

    if view_name == "Reported":
        owner_clause = f'reporter = "{jira_user}" AND (assignee != "{jira_user}" OR assignee IS EMPTY)'
    elif view_name == "Unassigned Reporting":
        owner_clause = (
            f'assignee IS EMPTY AND {TEAM_QUEUE_JQL_FIELD} = '
            f'"{escape_jql_value(REPORTING_QUEUE_NAME)}" '
            'AND statusCategory != Done'
        )
    else:
        owner_clause = f'assignee = "{jira_user}"'

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
    login_email = signed_in_email()
    previous_filter_email = st.session_state.get("jira_filter_email", "")

    st.session_state["jira_filter_email"] = login_email
    if previous_filter_email and previous_filter_email != login_email:
        st.cache_data.clear()

    clear_legacy_user_email_param()


def current_jira_settings():
    return {
        "jira_url": os.getenv("JIRA_URL", "").strip(),
        "email": os.getenv("JIRA_EMAIL", "").strip(),
        "token": os.getenv("JIRA_API_TOKEN", "").strip(),
        "filter_email": signed_in_email(),
    }


def render_admin_center():
    st.markdown("## Admin Center")
    st.markdown("View your browser session settings.")
    st.markdown("---")

    signed_in_user = st.session_state.get("entra_user") or {}
    st.info(f"Signed in as {signed_in_user.get('display_name', signed_in_email())}")

    with st.expander("Session Configuration", expanded=False):
        st.text_input(
            "Jira User Email",
            value=signed_in_email(),
            disabled=True,
            help="This email comes from your Microsoft login and is used to filter Jira issues.",
        )

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
                display_text=r"([^/]+)$"
            ),
            "Team Queue": st.column_config.TextColumn("Queue", width="small"),
            "Summary": st.column_config.TextColumn("Summary", width="large"),
            "Assignee": st.column_config.TextColumn("Assignee"),
            "Reporter": st.column_config.TextColumn("Reporter"),
            "Status": st.column_config.TextColumn("Status"),
            "Created (EST)": st.column_config.TextColumn("Created (EST)"),
            "Updated (EST)": st.column_config.TextColumn("Updated (EST)"),
        },
    )
    return True


def render_jira_tickets():
    settings = current_jira_settings()

    if not settings["filter_email"]:
        st.warning("Set a Jira user email in Admin before loading tickets.")
        return

    if not all([settings["jira_url"], settings["email"], settings["token"]]):
        st.warning("Set Jira URL, email, and API token in the .env file before loading tickets.")
        return

    exporter = JiraExporter(settings["jira_url"], settings["email"], settings["token"])

    header_mid, spacer, header_right = st.columns([0.34, 0.05, 0.61])

    with header_mid:
        search_text = st.text_input(
            "Search tickets",
            placeholder="Search",
            label_visibility="collapsed",
        )

    with header_right:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([0.21, 0.43, 0.26, 0.10])

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

    created_start = None
    created_end = None
    if use_created_date_filter:
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            created_start, created_end = selected_dates
        elif isinstance(selected_dates, list) and len(selected_dates) == 2:
            created_start, created_end = selected_dates

        if created_start and created_end and created_start > created_end:
            created_start, created_end = created_end, created_start

    reported_query = build_jql("Reported", settings["filter_email"], created_start, created_end)
    assigned_query = build_jql("Assigned", settings["filter_email"], created_start, created_end)
    unassigned_reporting_query = build_jql(
        "Unassigned Reporting",
        settings["filter_email"],
        created_start,
        created_end,
    )

    current_tab = st.session_state.get("jira_tabs", "Reported by Me")
    last_tab = st.session_state.get("last_active_tab", "Reported by Me")
    is_tab_switch = (current_tab != last_tab)
    st.session_state["last_active_tab"] = current_tab

    if is_tab_switch:
        reported_df = exporter.fetch_and_process(reported_query)
        assigned_df = exporter.fetch_and_process(assigned_query)
        unassigned_reporting_df = exporter.fetch_and_process(unassigned_reporting_query)
    else:
        with st.spinner("Loading tickets..."):
            reported_df = exporter.fetch_and_process(reported_query)
            assigned_df = exporter.fetch_and_process(assigned_query)
            unassigned_reporting_df = exporter.fetch_and_process(unassigned_reporting_query)

    # Inject dynamic ticket counts using CSS so the st.tabs labels stay static in Python.
    # This prevents Streamlit from destroying and resetting active tab state on refresh.
    st.markdown(
        f"""
        <style>
        div[data-testid="stTabs"] button[role="tab"]:nth-child(1)::after {{
            content: " ({active_ticket_count(reported_df)})" !important;
        }}
        div[data-testid="stTabs"] button[role="tab"]:nth-child(2)::after {{
            content: " ({active_ticket_count(assigned_df)})" !important;
        }}
        div[data-testid="stTabs"] button[role="tab"]:nth-child(3)::after {{
            content: " ({active_ticket_count(unassigned_reporting_df)})" !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

    tab1, tab2, tab3 = st.tabs(
        [
            "Reported by Me",
            "Assigned to Me",
            "Unassigned Queue",
        ],
        key="jira_tabs",
        on_change="rerun",
    )

    with tab1:
        if not render_dataframe(reported_df, "Reporter", search_text):
            st.info("No reported issues found for the current filters.")

    with tab2:
        if not render_dataframe(assigned_df, "Assignee", search_text):
            st.info("No assigned issues found for the current filters.")

    with tab3:
        if not render_dataframe(
            unassigned_reporting_df,
            "Assignee",
            search_text,
        ):
            st.info("No unassigned Reporting tickets found for the current filters.")


clear_legacy_user_email_param()
require_entra_user()
initialize_settings()

with st.sidebar:
    signed_in_user = st.session_state.get("entra_user") or {}
    display_name = signed_in_user.get("display_name", "Signed in")

    # Render user profile using custom HTML to align with left panel items
    st.markdown(
        f"""
        <div class="sidebar-profile">
            <div class="profile-item name-item">
                <span class="profile-icon name-icon"></span>
                <span class="profile-text" title="{display_name}">{display_name}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")
    page = st.radio("Navigation", ["Jira", "Admin"], label_visibility="collapsed")

    if st.button("Sign out"):
        for key in (
            "entra_user",
            "entra_auth_state",
            "jira_filter_email",
            "jira_tabs",
            "last_active_tab",
        ):
            st.session_state.pop(key, None)
        st.cache_data.clear()
        clear_auth_query_params()
        st.rerun()

if page == "Admin":
    render_admin_center()
else:
    render_jira_tickets()
