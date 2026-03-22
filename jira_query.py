import os
import requests
import pandas as pd
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime
from dateutil import parser
from pytz import timezone

class JiraExporter:
    def __init__(self):
        load_dotenv()
        self.url = f"{os.getenv('JIRA_URL').rstrip('/')}/rest/api/3/search/jql"
        self.email = os.getenv('JIRA_EMAIL')
        self.token = os.getenv('JIRA_API_TOKEN')
        self.auth = HTTPBasicAuth(self.email, self.token)
        self.base_path = r"C:\Users\nagarjuna.bandi\OneDrive - STG Logistics, Inc\Python Projects\Work Desk\files\jira_tickets"
        
        # Ensure directory exists
        os.makedirs(self.base_path, exist_ok=True)
    
    def format_to_est(self,date_str):
        if not date_str or date_str == "N/A":
            return "N/A"
        try:
            # Parse the Jira ISO timestamp
            utc_dt = parser.parse(date_str)
            # Convert to Eastern Time
            est_tz = timezone('US/Eastern')
            est_dt = utc_dt.astimezone(est_tz)
            # Format as Date and Time
            return est_dt.strftime('%Y-%m-%d %I:%M %p EST')
        except Exception:
            return "N/A"

    def fetch_issues(self, jql_query, max_results=500):
        """Fetches issues from Jira and returns a raw list of dicts."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        payload = {
            "jql": jql_query,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "reporter", "created", "updated"]
        }

        try:
            response = requests.post(self.url, json=payload, headers=headers, auth=self.auth)
            response.raise_for_status()
            return response.json().get("issues", [])
        except Exception as e:
            print(f"API Error: {e}")
            return []

    def process_to_dataframe(self, issues):
        """Converts raw Jira JSON into a clean Pandas DataFrame."""
        extracted_data = []
        for issue in issues:
            fields = issue.get("fields", {})
            # Extract dates
            created_raw = fields.get("created", "")
            updated_raw = fields.get("updated", "")
            created_date = created_raw[:10] if created_raw else ""
            updated_date = updated_raw[:10] if updated_raw else ""
            extracted_data.append({
                "Issue Key": issue.get("key"),
                "Summary": fields.get("summary"),
                "Assignee Name": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
                "Reporter Name": (fields.get("reporter") or {}).get("displayName", "Unknown"),
                "Status": (fields.get("status") or {}).get("name"),
                "Created (EST)": self.format_to_est(fields.get("created")),
                "Updated (EST)": self.format_to_est(fields.get("updated"))
            })
        return pd.DataFrame(extracted_data)

    def save_to_csv(self, df, filename):
        """Saves the DataFrame to the specified path."""
        if df.empty:
            print(f"No data found for {filename}. Skipping save.")
            return

        full_path = os.path.join(self.base_path, f"{filename}.csv")
        df.to_csv(full_path, index=False, encoding='utf-8-sig') # utf-8-sig helps Excel open it correctly
        print(f"Saved {len(df)} issues to: {full_path}")

    def run_export(self, jql, filename):
        """Orchestrator method to run the full flow."""
        raw_issues = self.fetch_issues(jql)
        df = self.process_to_dataframe(raw_issues)
        self.save_to_csv(df, filename)
    
  

# --- Execution ---

if __name__ == "__main__":
    exporter = JiraExporter()

    queries = {
        "reported_by_me": (
            "reporter = currentUser() "
            "AND resolution = Unresolved "
            "AND assignee != currentUser()"
            "ORDER BY created DESC"
 
        ),
        "assigned_to_me": (
            "assignee = currentUser() "
            "AND resolution = Unresolved "
            "ORDER BY created DESC"
        )
    }

    for file_name, jql in queries.items():
        exporter.run_export(jql, file_name)

    print("\nDone!")