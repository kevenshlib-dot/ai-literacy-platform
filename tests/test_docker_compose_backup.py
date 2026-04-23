import os
import subprocess
import tempfile
import textwrap
from pathlib import Path


SOURCE_SCRIPT = Path("scripts/backup_postgres.sh")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _create_temp_project() -> tuple[Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="backup-script-test-"))
    project_root = temp_dir / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)

    script_copy = scripts_dir / "backup_postgres.sh"
    script_copy.write_text(SOURCE_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    script_copy.chmod(0o755)

    return project_root, script_copy


def _create_fake_commands(project_root: Path, fail_pg_dump: bool = False) -> tuple[Path, Path]:
    fake_bin = project_root / "fake-bin"
    fake_bin.mkdir(parents=True)
    docker_log = project_root / "docker.log"

    docker_script = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        printf '%s\\n' "$*" >> "{docker_log}"
        joined="$*"

        case "$joined" in
          *"config --services"*)
            printf 'postgres\\n'
            ;;
          *"ps --status running --services"*)
            printf 'postgres\\n'
            ;;
          *'printf "%s" "$POSTGRES_DB"'*)
            printf 'ai_literacy_db'
            ;;
          *'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"'*)
            {'printf "pg_dump failed\\n" >&2\n            exit 1' if fail_pg_dump else "printf 'mock-backup-data\\n'"}
            ;;
          *)
            printf 'unexpected docker invocation: %s\\n' "$*" >&2
            exit 1
            ;;
        esac
        """
    )
    _write_executable(fake_bin / "docker", docker_script)

    gzip_script = textwrap.dedent(
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        cat
        """
    )
    _write_executable(fake_bin / "gzip", gzip_script)

    return fake_bin, docker_log


def _run_script(script_path: Path, fake_bin: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    return subprocess.run(
        [str(script_path), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_backup_script_creates_backup_file_from_compose_service() -> None:
    project_root, script_path = _create_temp_project()
    fake_bin, _docker_log = _create_fake_commands(project_root)
    (project_root / "docker-compose.yml").write_text("services:\n  postgres:\n", encoding="utf-8")

    result = _run_script(script_path, fake_bin, project_root)

    assert result.returncode == 0, result.stderr

    backup_dir = project_root / "backups" / "postgres"
    backup_files = list(backup_dir.glob("ai_literacy_db_*.sql.gz"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text(encoding="utf-8") == "mock-backup-data\n"
    assert str(backup_files[0]) in result.stdout


def test_backup_script_resolves_relative_compose_override_from_repo_root() -> None:
    project_root, script_path = _create_temp_project()
    fake_bin, docker_log = _create_fake_commands(project_root)
    (project_root / "docker-compose.yml").write_text("services:\n  postgres:\n", encoding="utf-8")
    (project_root / "docker-compose.alt.yml").write_text("services:\n  postgres:\n", encoding="utf-8")

    outside_dir = project_root.parent / "outside"
    outside_dir.mkdir()

    result = _run_script(
        script_path,
        fake_bin,
        outside_dir,
        "--compose-file",
        "docker-compose.alt.yml",
    )

    assert result.returncode == 0, result.stderr
    assert str(project_root / "docker-compose.alt.yml") in docker_log.read_text(encoding="utf-8")


def test_backup_script_removes_tmp_file_when_pg_dump_fails() -> None:
    project_root, script_path = _create_temp_project()
    fake_bin, _docker_log = _create_fake_commands(project_root, fail_pg_dump=True)
    (project_root / "docker-compose.yml").write_text("services:\n  postgres:\n", encoding="utf-8")

    result = _run_script(script_path, fake_bin, project_root)

    assert result.returncode != 0
    backup_dir = project_root / "backups" / "postgres"
    assert not list(backup_dir.glob("*.tmp"))
    assert not list(backup_dir.glob("*.sql.gz"))
