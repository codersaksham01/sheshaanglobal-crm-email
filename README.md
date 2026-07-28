# Smart Export CRM V7.2 — Outlook Desktop App

This build runs on **http://127.0.0.1:5050** so an older Titan build on port 5000 cannot hide the update.

## Start on Windows

1. Extract the ZIP completely.
2. Double-click `RUN_OUTLOOK_DESKTOP.bat`.
3. Confirm `http://127.0.0.1:5050/version` says **Outlook Desktop Active**.

## Keep existing CRM data

Copy `export_import_crm.sqlite` from the old CRM directory into this directory before starting. This preserves buyers, templates, campaigns, and activity history.

## Email behavior

- Buyer and campaign email buttons use a `mailto:` draft.
- Windows opens the installed app registered for the MAILTO protocol.
- Recipient, subject, and message body are pre-filled.
- Outlook Web is not used anywhere.
- Legacy `/titan-compose` and `/outlook-compose` links remain compatible.
- The CRM never sends email automatically. Review the draft and click Send in Outlook.

## Important Windows setting

Microsoft Outlook must be the default app for MAILTO links. If a browser or another mail app opens, double-click `SET_OUTLOOK_AS_DEFAULT.bat`, then set Outlook as the default for the **MAILTO** protocol.
