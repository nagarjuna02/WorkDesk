import os
from turtle import width
import requests
import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil import parser
from pytz import timezone
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# --- Configuration & Styling ---
load_dotenv()

st.set_page_config(page_title="Work Dashboard", layout="wide")

# CSS for a clean, professional look
st.markdown("""
    <style>
    /* 1. Hide default Streamlit clutter */
    header {visibility: hidden;}
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    .block-container { padding-top: 1.5rem; padding-bottom: 0rem; }

    /* 2. Sidebar Width Lock */
    [data-testid="stSidebar"] {
        min-width: 200px !important;
        max-width: 200px !important;
        width: 200px !important;
    }
    [data-testid="stSidebarCollapsedControl"] { left: 200px !important; }

    /* 3. Ghost Refresh Button Styling */
    div[data-testid="column"] { align-self: center; }
    div[data-testid="stButton"] > button {
        border: none;
        background-color: transparent;
        font-size: 22px;
        padding: 0px;
        margin-top: 10px;
    }
    div[data-testid="stButton"] > button:hover {
        background-color: transparent;
        color: #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Logic Layer ---
class JiraExporter:
    def __init__(self):
        self.url = f"{os.getenv('JIRA_URL').rstrip('/')}/rest/api/3/search/jql"
        self.base_url = os.getenv('JIRA_URL').rstrip('/')
        self.email = os.getenv('JIRA_EMAIL')
        self.token = os.getenv('JIRA_API_TOKEN')
        self.auth = HTTPBasicAuth(self.email, self.token)
    
    def format_to_est(self, date_str):
        if not date_str: return "N/A"
        try:
            utc_dt = parser.parse(date_str)
            est_dt = utc_dt.astimezone(timezone('US/Eastern'))
            return est_dt.strftime('%Y-%m-%d %I:%M %p')
        except:
            return "N/A"

    @st.cache_data(ttl=600) # Cache for 10 minutes to save API calls
    def fetch_and_process(_self, jql_query):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        payload = {
            "jql": jql_query,
            "maxResults": 50,
            "fields": ["summary", "status", "assignee", "reporter", "created", "updated"]
        }
        
        try:
            response = requests.post(_self.url, json=payload, headers=headers, auth=_self.auth)
            response.raise_for_status()
            issues = response.json().get("issues", [])
            
            data = []
            for issue in issues:
                f = issue.get("fields", {})
                key = issue.get("key")
                # Create the direct link to the ticket
                ticket_url = f"{_self.base_url}/browse/{key}"
                data.append({
                    "Key": ticket_url,  # Store the URL here
                    "Key Label": key,   # Keep the label for display    
                    "Summary": f.get("summary"),
                    "Assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
                    "Reporter": (f.get("reporter") or {}).get("displayName", "Unknown"),
                    "Status": (f.get("status") or {}).get("name"),
                    "Created (EST)": _self.format_to_est(f.get("created")),
                    "Updated (EST)": _self.format_to_est(f.get("updated"))
                })
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Jira API Error: {e}")
            return pd.DataFrame()

def style_status(val):
    color_map = {
        "In Progress": "background-color: #d4edda; color: #155724;",
        "Waiting for approval": "background-color: #f8d7da; color: #721c24;",
        "Awaiting User": "background-color: #f8d7da; color: #721c24;",
        "Open": "background-color: #fff3cd; color: #856404;",
        "Assigned": "background-color: #fff3cd; color: #856404;"
    }
    return color_map.get(val, "")

def style_stale_issues(val):
    if not val or val == "N/A":
        return ""
    try:
        # Parse the formatted string back to a datetime object
        updated_dt = datetime.strptime(val, '%Y-%m-%d %I:%M %p')
        # Make it timezone aware for EST
        est_tz = timezone('US/Eastern')
        updated_dt = est_tz.localize(updated_dt)
        
        # Check if difference is > 48 hours
        now = datetime.now(est_tz)
        if (now - updated_dt).total_seconds() > 172800:  # 48 hours in seconds
            return "color: #000; font-weight: bold;" # Red and Bold
    except Exception:
        pass
    return ""
# --- Main App ---
st.markdown("## Jira Tickets")
exporter = JiraExporter()

# # Top Header Area
# head_col1, head_col2 = st.columns([0.2, 0.8])
# with head_col1:
#     st.markdown("## Jira Tickets")
# with head_col2:
#     if st.button("🔄", help="Force Refresh Data"):
#         st.cache_data.clear()
#         st.rerun()

# JQL Configuration
QUERIES = {
    "Reported": "reporter = currentUser() AND resolution = Unresolved AND assignee != currentUser() ORDER BY created DESC",
    "Assigned": "assignee = currentUser() AND resolution = Unresolved ORDER BY created DESC"
}

tab1, tab2 = st.tabs(["📤 Reported by Me", "📥 Assigned to Me"])

with tab1:
    df_rep = exporter.fetch_and_process(QUERIES["Reported"])
    if not df_rep.empty:
        # Sort and filter
        df_display = df_rep.drop(columns=['Reporter']).sort_values("Status")
        styled_df = (df_display.style
                     .map(style_status, subset=["Status"])
                     .map(style_stale_issues, subset=["Updated (EST)"]))
        st.dataframe(styled_df, width="stretch", hide_index=True,
                    column_config={
                        "Key": st.column_config.LinkColumn(
                            "Key",
                            help="Click to open ticket in Jira",
                            validate="^https://.*",
                            display_text=r"([^/]+)$" # This regex extracts the Key from the end of the URL
                        ),
                    } 
                   )
    else:
        st.info("No reported issues found.")

with tab2:
    df_asn = exporter.fetch_and_process(QUERIES["Assigned"])
    if not df_asn.empty:
        df_display = df_asn.drop(columns=['Assignee']).sort_values("Status")
        styled_df = (df_display.style
                     .map(style_status, subset=["Status"])
                     .map(style_stale_issues, subset=["Updated (EST)"]))
        st.dataframe(styled_df, width="stretch", hide_index=True,
                     column_config={
                            "Key": st.column_config.LinkColumn(
                                "Key",
                                help="Click to open ticket in Jira",
                                validate="^https://.*",
                                display_text=r"([^/]+)$" # This regex extracts the Key from the end of the URL
                            ),
                        }
                    )
    else:
        st.info("No assigned issues found.")

# Sidebar
with st.sidebar:
    st.subheader("Work Dashboard")
    st.caption(f"Last Refresh: {datetime.now(timezone('US/Eastern')).strftime('%I:%M %p EST')}")