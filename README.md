# UrBackup Monitoring

Advanced monitoring and analytics layer for UrBackup.

## Features

- Backup health monitoring
- Live job tracking
- Last activity (`with_lastacts=1`) collection
- Backup log detail collection by `logid`
- SQLite persistence for clients and backup logs
- Log analysis (error/warning detection)
- Storage usage tracking

## Configuration

The app needs UrBackup credentials as environment variables:

- `URB_URL` (or `URBACKUP_URL`)
- `URB_USER` (or `URBACKUP_USER`)
- `URB_PASS` (or `URBACKUP_PASS`)
- `URB_DB_PATH` (or `URBACKUP_DB_PATH`, optional, default: `data/urbackup_monitoring.db`)

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

This flow:

1. Calls `progress` with `with_lastacts=1`
2. Reads each `logid`
3. Calls `logs` endpoint for detailed lines
4. Stores client latest state + backup log details in SQLite

## Database tables

- `clients`: latest known client status/health
- `backup_logs`: one row per backup log (`log_id` primary key) with raw JSON + parsed flags

## Example output

```json
{
  "lastacts_total": 12,
  "new_logs_synced": 4
}
```
