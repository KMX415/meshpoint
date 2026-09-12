# Dashboard access

The Viewer fixes and public summaries below are **v0.8.0 development** features.
They are unreleased and remain subject to RC testing. The default remains a
dashboard requiring login.

## Choose an access level

| Access | What it can see | What it can change |
| --- | --- | --- |
| Administrator | Full dashboard, Settings, enabled Terminal and optional app pages | Device configuration, messaging and management actions |
| Viewer login | Dashboard, Stats, Messages, Radio and permitted configuration pages | No shared device or message state; own login password can still be changed |
| Public visitor | Only administrator-selected aggregate summaries | Nothing |

Viewer is for trusted observers: it can read existing conversations and node
information. It is not the same as the limited public view. Configuration
editors are disabled, compose/delete and Send Now actions are hidden, and
opening a conversation does not mark it read for everyone. The server also
rejects shared-state writes, independently of the visible controls.

## Device-side permissions

Web Terminal is disabled by default in this development build, including upgrades
without an explicit opt-in. Merge `web_terminal_enabled: true` into the existing
`dashboard` mapping in `config/local.yaml` on the device and restart Meshpoint.
Use an unquoted YAML boolean. This grants administrators a full shell under the
service account. There is no dashboard API to toggle it. While disabled, Terminal
is omitted from the sidebar and its HTTP and WebSocket endpoints reject access.
Set `false` and restart to revoke access and end existing sessions.

Terminal colors follow the selected dashboard theme without reconnecting or
clearing the session. Confirmation dialogs return keyboard focus to their opener;
Tab cycles the action buttons, Enter activates the focused action, and Escape
cancels.

[Source installation](PLUGINS.md#install-and-enable) has a separate device-side
opt-in. These controls do not restrict backup restore or sandbox trusted plugins.
Review configuration and optional code in any archive before restoring it.

## Enable a Viewer login

1. Sign in as administrator and open **Settings > Auth**.
2. In **Viewer role**, enter and confirm a Viewer password, then enable it.
3. In a separate browser session, sign in as `viewer` and verify the pages.

Settings and Terminal remain administrator-only. Use **Disable viewer** to
remove Viewer login. **Sign out everywhere** invalidates outstanding sessions;
use it when existing sessions must end immediately.

## Enable selected public summaries

1. Open **Settings > Auth > Public view** as administrator.
2. Select the pages to share and check **Enable public viewing**.
3. Choose **Save public view**. At least one page is required while enabled.
4. Open the normal dashboard address in a signed-out/private browser window.

| Page | Published fields |
| --- | --- |
| Dashboard | Known node count and count active in the last 24 hours |
| Stats | Stored packet count, packets in the last hour, hourly average packets/minute, recent RSSI and SNR averages |
| Radio | Configured region, frequency, bandwidth and spreading factor |

Anyone who can reach the device's dashboard address can read those summaries.
No port forwarding or cloud publishing is performed by this setting. Messages,
node identities/locations, credentials, keys, other configuration and optional
app pages are not part of the public feed. The public Radio page describes the
configured receive parameters, not every optional receiver or an RF health test.

Signed-in users keep their normal dashboard. Public visitors have an **Admin
sign in** link. Public viewing does not issue a session or unlock the dashboard
WebSocket. First-run administrator setup is still required before public access.

## Disable or change public access

Uncheck pages and save to remove them. Uncheck **Enable public viewing** and
save to require login again. These settings apply without a service restart.
New requests to a removed page are rejected immediately, including cached API
results. An already open public page refreshes every 15 seconds while visible;
data previously received by a visitor cannot be recalled. Unavailable data is
shown as unavailable rather than a fabricated zero.

Settings persist under `web_auth.public_view_enabled` and
`web_auth.public_view_pages`; use the form to validate the allowed page names.
The default enabled value is false. Backups restore the saved access policy,
so review public access after restoring a device.

## Troubleshooting

- No public form: check the installed branch/build; these additions are unreleased.
- Still seeing the full dashboard: use a browser without an existing login.
- Redirected to login: public viewing is off or no supported pages are selected.
- Counts temporarily unavailable: wait for startup or inspect the service logs.
- Viewer sees a disabled editor: this is expected; sign in as administrator to edit.
- Optional app missing as Viewer/public: optional app pages currently require admin.

See [common errors](COMMON-ERRORS.md) for password recovery and expired sessions.
