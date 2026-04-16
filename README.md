# UrBackup Monitoring

Advanced monitoring and analytics layer for UrBackup.

## Features

- Backup health monitoring
- Live job tracking
- Last activity (`with_lastacts=1`) collection
- Background lastacts collector (works even when dashboard page is closed)
- Backup log detail collection by `logid`
- Historical backup-log backfill + sync state tracking (no duplicate inserts)
- SQLite persistence for clients and backup logs
- Log analysis (error/warning detection)
- Storage usage tracking

## Configuration

The app needs UrBackup credentials as environment variables:

- `URB_URL` (or `URBACKUP_URL`)
- `URB_USER` (or `URBACKUP_USER`)
- `URB_PASS` (or `URBACKUP_PASS`)
- `URB_DB_PATH` (or `URBACKUP_DB_PATH`, optional, default: `/data/urbackup_monitoring.db` when `/data` exists, otherwise `data/urbackup_monitoring.db`)
- `URB_SYNC_INTERVAL_SECONDS` (optional, default: `60`)
- `URB_SYNC_MODE` (optional, for `python main.py`; `oneshot` or `daemon`)
- `URB_HISTORY_MAX_PAGES` (optional, default: `200`; history backfill page limit per run)

### Docker Compose

1. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your real UrBackup URL and credentials.
3. Start the service:

   ```bash
   docker compose up -d --build
   ```

## Sync backup logs into SQLite

Run one-shot synchronization:

```bash
python main.py
```

Run daemon synchronization loop:

```bash
URB_SYNC_MODE=daemon URB_SYNC_INTERVAL_SECONDS=60 python main.py
```

This flow:

1. Calls `progress` with `with_lastacts=1`
2. Reads `last_processed_log_id` state from SQLite
3. Backfills older logs from `logs` list API until synced boundary
4. Calls `logs` endpoint for detailed lines
5. Stores client latest state + backup log details in SQLite
6. Updates `last_processed_log_id`

## Database tables

- `clients`: latest known client status/health
- `backup_logs`: one row per backup log (`log_id` primary key) with raw JSON + parsed flags
- `sync_state`: checkpoint key/value store (`last_processed_log_id` used by sync)

## Example output

```json
{
  "lastacts_total": 12,
  "historical_total": 38,
  "new_logs_synced": 4,
  "last_processed_log_id": 7642
}
```
