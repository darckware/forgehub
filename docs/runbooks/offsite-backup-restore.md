# Restore the VPS from the offsite Google Drive backup

The encrypted restic repository is `gdrive:vps-backup/restic`. Recovery needs access to the Google account that owns that Drive folder and the restic password kept outside the VPS. The password is in Marcelo's password manager under `restic-backup-vps`. Do not put it in a command line, shell history, ticket, or repository.

The daily snapshot covers `/root` and `/etc`. It includes consistent SQL dumps in `/root/backup/offsite-staging/postgres/`, online SQLite copies in `/root/backup/offsite-staging/sqlite/`, and a host inventory in `/root/backup/offsite-staging/system/`. Live Postgres data directories and regenerable caches are excluded. See the exclude list at `/root/.hermes/profiles/athos/scripts/backup_offsite_root.excludes` after restoring the files.

## Confirm that a usable snapshot exists

On a replacement host, install `restic`, `rclone`, and `sqlite3`. Configure an OAuth Google Drive remote named `gdrive` with scope `drive.file` and authorize the account that owns `vps-backup`. Use a dedicated OAuth client; the shared rclone client is being retired. Keep `rclone.conf` readable only by root.

Enter the restic password interactively in a root shell, then inspect the repository:

```bash
export RESTIC_REPOSITORY=rclone:gdrive:vps-backup/restic
read -rsp 'Restic password: ' RESTIC_PASSWORD; echo
export RESTIC_PASSWORD
restic snapshots
restic check
```

Choose a snapshot ID from `restic snapshots`. A listed snapshot is not by itself proof of a complete recovery: check its `paths` include `/root` and `/etc`, inspect the staged database dumps after restore, and verify the applications. If the latest snapshot is missing or fails `restic check`, select the last checked snapshot and record the gap.

## Restore one file or directory

Restore into a separate directory first. For example:

```bash
mkdir -p /root/restore
restic restore latest --target /root/restore --include /root/project/forgehub/.env
ls -l /root/restore/root/project/forgehub/.env
```

Replace `latest` with a snapshot ID to recover an earlier version. Compare content and permissions before copying anything into service paths. Delete the temporary copy after use. Never restore directly over a running application.

## Rebuild a replacement VPS

1. Provision the OS and secure network access. Save a copy of the new host's `/etc` before replacing individual files. Restore the chosen snapshot into an empty staging directory:

   ```bash
   mkdir -p /root/restore-full
   restic restore SNAPSHOT_ID --target /root/restore-full
   ```

2. Inspect `/root/restore-full/root/backup/offsite-staging/system/` for package, Docker, network, cron, and systemd inventories. Install Docker and the required packages. Restore selected `/etc` configuration and systemd units after reviewing host-specific addresses, interfaces, certificates, and service accounts. Do not replace the whole new `/etc` tree blindly.
3. Copy the restored `/root` data, preserving ownership and permissions. Restore project files, `.env` files, Hermes profiles, bridge configuration, and application secrets before starting services. Recreate the Docker `foundation_network` and other networks recorded in the inventory. Bring up each project's Postgres service with an **empty** data directory. Do not copy live `*/postgres` data directories from a snapshot into a running database.
4. Import the SQL dumps from `offsite-staging/postgres/<container>/`. Restore `_globals.sql` first, then each `<database>.sql` into an empty database using `psql` in that project's Postgres container. Confirm the database name and user from its compose configuration before importing. The dumps are plain SQL, generated with `pg_dumpall --globals-only` and `pg_dump --no-owner`. Check the exit status and row counts, especially for `forgevault-postgres-1/forgevault.sql`, before starting application services.
5. Start the application containers, host bridge, and Hermes user gateway. Restore selected SQLite copies from `offsite-staging/sqlite/` only while their owning service is stopped; run `PRAGMA integrity_check` on each before use. Regenerate caches and dependencies excluded from the snapshot.
6. Validate the ForgeHub and ForgeVault APIs, authentication, Hermes Messages and crons, the Auditor checks, and a fresh backup run. Confirm the backup reports `result=ok` and its new snapshot appears in Drive. Reauthorize rclone on the replacement host if the restored token is no longer valid.

The usual Postgres dump directories are `forgehub_postgres`, `hindsight_postgres`, `forgerouter_postgres`, `forgevault-postgres-1`, `darckware-postgres`, and `coreti_postgres`. Check the actual dump directory list before declaring recovery complete. Keep the restored SQL dumps and `.env` files root-only; remove the staging directory after validation.

## Routine restore test

On the current VPS, restore a sample into a disposable directory and compare the restored Athos profile and ForgeHub `.env` with the originals. Start a temporary Postgres container with its own empty data directory, import the ForgeVault globals and database dump, and count tables and key rows. Run `sqlite3 <restored-copy> 'PRAGMA integrity_check;'` on one staged Hermes database. Remove the disposable directory and container after the checks. Record the snapshot ID, checks, and result in the backup operations log; a backup is not accepted until this test passes.
