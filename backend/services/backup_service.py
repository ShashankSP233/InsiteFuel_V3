from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json
import os
import subprocess
import tempfile
from urllib.parse import urlparse

from backend.config import settings


BACKUP_DIR = Path("storage/backups")
ATTACHMENTS_DIR = Path("storage/attachments")


class BackupService:

    @staticmethod
    def create_backup(
        created_by_user_id: int | None = None,
    ) -> Path:
        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d_%H%M%S")

        backup_name = (
            f"insitefuel_backup_{timestamp}.zip"
        )

        backup_path = BACKUP_DIR / backup_name

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            database_file = (
                temp_path / "database.sql"
            )

            BackupService._dump_database(
                database_file
            )

            metadata = {
                "application": "InsiteFuel V3",
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "database_backup": "database.sql",
                "attachments_included": (
                    ATTACHMENTS_DIR.exists()
                ),
            }

            metadata_file = (
                temp_path / "metadata.json"
            )

            metadata_file.write_text(
                json.dumps(
                    metadata,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with ZipFile(
                backup_path,
                "w",
                compression=ZIP_DEFLATED,
            ) as archive:

                archive.write(
                    database_file,
                    arcname="database.sql",
                )

                archive.write(
                    metadata_file,
                    arcname="metadata.json",
                )

                if ATTACHMENTS_DIR.exists():
                    for file_path in ATTACHMENTS_DIR.rglob("*"):
                        if file_path.is_file():
                            archive.write(
                                file_path,
                                arcname=(
                                    Path("attachments")
                                    / file_path.relative_to(
                                        ATTACHMENTS_DIR
                                    )
                                ),
                            )

        return backup_path

    @staticmethod
    def _dump_database(
        output_file: Path,
    ) -> None:

        parsed = urlparse(
            settings.database_url
        )

        if parsed.scheme not in {
            "postgresql",
            "postgresql+psycopg",
        }:
            raise RuntimeError(
                "Backup requires a PostgreSQL database URL."
            )

        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        username = parsed.username
        database = parsed.path.lstrip("/")

        if not username or not database:
            raise RuntimeError(
                "Database URL is missing PostgreSQL "
                "username or database name."
            )

        command = [
            "pg_dump",
            "--host",
            host,
            "--port",
            port,
            "--username",
            username,
            "--format",
            "plain",
            "--file",
            str(output_file),
            database,
        ]

        password = parsed.password

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,   
                    **(
                        {"PGPASSWORD": password}
                        if password
                        else {}
                    ),
                },
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "pg_dump was not found on the system."
            ) from exc

        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pg_dump failed: {exc.stderr.strip()}"
            ) from exc

    @staticmethod
    def list_backups() -> list[dict]:
        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        backups = []

        for path in sorted(
            BACKUP_DIR.glob("*.zip"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            stat = path.stat()

            backups.append(
                {
                    "filename": path.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        tz=timezone.utc,
                    ),
                }
            )

        return backups

    @staticmethod
    def get_backup(
        filename: str,
    ) -> Path | None:

        path = (
            BACKUP_DIR / filename
        ).resolve()

        backup_root = (
            BACKUP_DIR.resolve()
        )

        if (
            backup_root not in path.parents
            or path.suffix.lower() != ".zip"
        ):
            return None

        if not path.exists() or not path.is_file():
            return None

        return path
