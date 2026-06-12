# Work Desk

*Office Workspace Management App*

## Overview

Work Desk is a Streamlit-based internal dashboard for working with Jira tickets.
It provides a focused UI for:

- signing in with Microsoft Entra ID
- resolving the signed-in user through Microsoft Graph
- viewing tickets reported by the current Jira user
- viewing tickets assigned to the current Jira user
- filtering by created date range
- searching across all visible table data
- using the signed-in Microsoft email as the Jira ticket owner filter

The app is designed for quick day-to-day ticket review with a dense table layout, tabbed views, and Microsoft-backed user context.

## Features

- `Jira` page with:
  - `Reported by Me`, `Assigned to Me`, and `Unassigned Queue` tabs with active ticket counts
  - default view of unresolved tickets plus tickets resolved in the last 14 days
  - optional created-date filter that overrides the default resolved-window behavior
  - free-text search across the displayed table fields
  - manual refresh control
  - status-based sorting, then created date ascending
- `Admin` page with:
  - signed-in Microsoft profile details
  - read-only Jira filter email sourced from Microsoft Graph
- paginated Jira API loading to fetch more than the first page of issues
- clickable Jira ticket links directly from the table

## Project Structure

```text
app.py          Streamlit application
style.css       App styling
requirements.txt Python dependencies
.env            Default Jira connection settings
```

## Requirements

- Python 3.11+ recommended
- Jira Cloud access
- A valid Jira API token for the account being used
- Microsoft Entra app registration with a web redirect URI for the Streamlit app
- Microsoft Graph delegated `User.Read` permission granted for sign-in profile lookup

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create a `.env` file with default Jira settings:

```env
JIRA_URL=https://your-domain.atlassian.net/
JIRA_EMAIL=your.email@example.com
JIRA_API_TOKEN=your_jira_api_token
ENTRA_CLIENT_ID=your_entra_client_id
ENTRA_TENANT_ID=your_entra_tenant_id
ENTRA_CLIENT_SECRET=your_entra_client_secret
ENTRA_REDIRECT_URI=http://localhost:8501
```

Do not commit real credentials or tokens.

The `ENTRA_REDIRECT_URI` value must exactly match a web redirect URI configured
on the Entra app registration. For local Streamlit development, use
`http://localhost:8501` unless you run Streamlit on another port.

## Run

```powershell
streamlit run app.py
```

Then open the local Streamlit URL in your browser.

## How It Works

- The app loads Jira and Entra settings from `.env`.
- Users must sign in with Microsoft before the Jira dashboard renders.
- During the OAuth callback, the app exchanges the authorization code with MSAL,
  calls Microsoft Graph `/me`, stores only the non-secret display profile in the
  Streamlit session, and discards the access token.
- The Jira ticket owner filter always uses the email from the signed-in Microsoft account.
- The `Jira` page uses those active settings to query Jira using JQL.
- Ticket tables are styled and sorted for faster review.

## Notes

- If the created-date filter is enabled, the selected date range is used directly.
- If the created-date filter is disabled, the app shows unresolved tickets plus tickets resolved within the last 14 days.
- The `Reported by Me` tab excludes tickets that are both reported by and assigned to the current user.
- The `Unassigned Queue` tab shows unassigned tickets in the Reporting queue.

## Future Expansion

The sidebar navigation is structured so additional internal tools or pages can be added later without changing the overall app layout.
