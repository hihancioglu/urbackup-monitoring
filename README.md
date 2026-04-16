# UrBackup Monitoring

Advanced monitoring and analytics layer for UrBackup.

## Features

- Backup health monitoring
- Live job tracking
- Log analysis (error detection)
- Storage usage tracking
- Incremental backup analytics

## Configuration

The app needs UrBackup credentials as environment variables:

- `URB_URL` (or `URBACKUP_URL`)
- `URB_USER` (or `URBACKUP_USER`)
- `URB_PASS` (or `URBACKUP_PASS`)

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

## Example output

```json
{
  "client": "PC-523",
  "status": "OK",
  "last_backup_hours": 5,
  "size_gb": 9.3
}
```
