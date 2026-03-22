# Work Desk

*Office Workspace Management App*

## Overview

Work Desk is a Streamlit-based internal dashboard for working with Jira tickets.
It provides a focused UI for:

- viewing tickets reported by the current Jira user
- viewing tickets assigned to the current Jira user
- filtering by created date range
- searching across all visible table data
- switching Jira credentials from the frontend through an Admin page

The app is designed for quick day-to-day ticket review with a dense table layout, tabbed views, and lightweight account switching.

## Features

- `Jira` page with:
  - `Reported by Me` and `Assigned to Me` tabs
  - default view of unresolved tickets plus tickets resolved in the last 14 days
  - optional created-date filter that overrides the default resolved-window behavior
  - free-text search across the displayed table fields
  - manual refresh control
  - status-based sorting, then created date ascending
- `Admin` page with:
  - frontend inputs for `Jira URL`, `Email`, and `API Token`
  - session-based credential override so different Jira credentials can be used without editing `.env`
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
```

Do not commit real credentials or tokens.

## Run

```powershell
streamlit run app.py
```

Then open the local Streamlit URL in your browser.

## How It Works

- The app loads default Jira settings from `.env`.
- The `Admin` page can override those settings for the current browser session.
- The `Jira` page uses those active settings to query Jira using JQL.
- Ticket tables are styled and sorted for faster review.

## Notes

- If the created-date filter is enabled, the selected date range is used directly.
- If the created-date filter is disabled, the app shows unresolved tickets plus tickets resolved within the last 14 days.
- The `Reported by Me` tab excludes tickets that are both reported by and assigned to the current user.

## Future Expansion

The sidebar navigation is structured so additional internal tools or pages can be added later without changing the overall app layout.
