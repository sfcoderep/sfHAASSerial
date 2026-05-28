# sfHAASSerial

HAAS CNC Serial Data Collection — historian-style, event-driven, Grafana-ready.

## What it does

- Polls all configured HAAS machines over TCP Q-code protocol
- Detects and records events: cycle start/stop (with measured cycle time), tool changes, part completions, alarm transitions
- Writes to MySQL using a **historian deadband** — only records a row when values change beyond configured thresholds (or every 5 minutes as a heartbeat write), massively reducing storage vs. naive every-10s writes
- Sends Slack / email alerts when machines go offline or alarms fire
- Exposes a Grafana dashboard for shop floor monitoring

## Setup

### 1. Database

```sql
mysql -u root -p < schema.sql
```

Create a write user:
```sql
CREATE USER 'sfwriter'@'%' IDENTIFIED BY 'yourpassword';
GRANT INSERT, UPDATE, SELECT ON sfcncpool.* TO 'sfwriter'@'%';
```

### 2. Credentials

Never put credentials in `config.yaml`. Use environment variables:

```bash
export HAAS_DB_HOST=sfmysql01.sf.local
export HAAS_DB_USER=sfwriter
export HAAS_DB_PASS=yourpassword
export HAAS_DB_NAME=sfcncpool
```

Or create a `.env` file in the project directory (gitignored):
```
HAAS_DB_HOST=sfmysql01.sf.local
HAAS_DB_USER=sfwriter
HAAS_DB_PASS=yourpassword
HAAS_DB_NAME=sfcncpool
```

### 3. Alerting (optional)

**Slack:** Set `HAAS_SLACK_WEBHOOK` env var, or set `slack_webhook:` in config.yaml.

**Email:** Fill in the `alerting:` block in `config.yaml` with your SMTP server details.

### 4. Install and run

```bash
pip install -r requirements.txt
python main.py
```

### 5. Grafana dashboard

1. In Grafana, add a MySQL datasource pointed at `sfcncpool`.
2. Go to Dashboards → Import → Upload JSON file → select `grafana_dashboard.json`.
3. Map the `DS_MYSQL` input to your datasource.
4. Done. The dashboard auto-refreshes every 10 seconds.

## Historian tuning

The `historian:` block in `config.yaml` controls write filtering:

```yaml
historian:
  force_write_interval: 300   # write at least every N seconds regardless
  deadbands:
    spindle_speed: 10          # don't write if RPM changed < 10
    x_position: 0.001          # don't write if position changed < 0.001"
```

For a machine sitting in alarm for 2 hours, instead of 720 identical rows you'll get 1 row when the alarm started and then 24 force-write rows (one per 5 minutes). That's ~97% fewer rows for static state — equivalent to OSIsoft PI's exception-based compression.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point, poll loop, thread management |
| `haas_client.py` | TCP socket / Q-code protocol |
| `parser.py` | Parse Q-code responses into structured data |
| `events.py` | Detect state transitions between polls |
| `historian.py` | Deadband write filtering |
| `storage.py` | MySQL writes (leak-safe connection pool) |
| `state.py` | Per-machine mutable state (thread-safe) |
| `alerting.py` | Slack/email notifications |
| `schema.sql` | Database schema + views |
| `config.yaml` | Machine list, poll settings, historian config |
| `grafana_dashboard.json` | Import directly into Grafana |
