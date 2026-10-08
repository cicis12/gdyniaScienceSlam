"""Run from a host terminal: venv/bin/python scripts/setup_local_database.py."""
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def configuration(filename):
    path = ROOT / filename
    config = dotenv_values(path)
    if not all(config.get(key) for key in ('DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_HOST')):
        raise RuntimeError(f'{filename} is missing required database settings')
    if config['DB_HOST'] not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('This script only configures a local database')
    path.chmod(0o600)
    return config


def administrator(statement):
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-At', '-d', 'postgres'],
        input=statement.as_string() if isinstance(statement, sql.Composable) else statement,
        text=True, capture_output=True,
    )
    if result.returncode:
        # PostgreSQL errors can include statements containing passwords.
        raise RuntimeError('PostgreSQL administrative command failed; check sudo and server access')
    return result.stdout.strip()


def connect(config):
    return psycopg.connect(user=config['DB_USER'], password=config['DB_PASSWORD'],
        dbname=config['DB_NAME'], host=config['DB_HOST'],
        port=config.get('DB_PORT', '5432'), connect_timeout=5)


def main():
    admin = configuration('admin_DBcreds.env')
    app = configuration('DBcreds.env')
    if admin['DB_NAME'] != app['DB_NAME'] or admin.get('DB_PORT', '5432') != app.get('DB_PORT', '5432'):
        raise RuntimeError('Both credential files must target the same database and port')
    if admin['DB_USER'] == app['DB_USER']:
        raise RuntimeError('Use separate migration and application roles')
    subprocess.run(['sudo', '-v'], check=True)
    # Existing roles and their passwords are preserved.
    for config in (admin, app):
        exists = administrator(sql.SQL('SELECT 1 FROM pg_roles WHERE rolname = {};').format(sql.Literal(config['DB_USER'])))
        if not exists:
            administrator(sql.SQL("SET password_encryption = 'scram-sha-256'; CREATE ROLE {} LOGIN PASSWORD {};").format(
                sql.Identifier(config['DB_USER']), sql.Literal(config['DB_PASSWORD'])))
    exists = administrator(sql.SQL('SELECT 1 FROM pg_database WHERE datname = {};').format(sql.Literal(admin['DB_NAME'])))
    if not exists:
        administrator(sql.SQL('CREATE DATABASE {} OWNER {};').format(sql.Identifier(admin['DB_NAME']), sql.Identifier(admin['DB_USER'])))
    with connect(admin) as conn:
        conn.execute('SELECT 1')
    environment = os.environ.copy()
    # Ensure inherited DB_* variables cannot override the migration configuration.
    for key in ('DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_HOST', 'DB_PORT'):
        environment.pop(key, None)
    environment['ENV_FILE'] = str(ROOT / 'admin_DBcreds.env')
    # Capture errors because SQLAlchemy tracebacks may contain connection details.
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=environment, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Migration failed; no application grants were applied')
    with connect(admin) as conn:
        statements = [
            sql.SQL('GRANT CONNECT ON DATABASE {} TO {};').format(sql.Identifier(admin['DB_NAME']), sql.Identifier(app['DB_USER'])),
            sql.SQL('GRANT USAGE ON SCHEMA public TO {};').format(sql.Identifier(app['DB_USER'])),
            sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {};').format(sql.Identifier(app['DB_USER'])),
            sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {};').format(sql.Identifier(app['DB_USER'])),
            sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {};').format(sql.Identifier(admin['DB_USER']), sql.Identifier(app['DB_USER'])),
            sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {};').format(sql.Identifier(admin['DB_USER']), sql.Identifier(app['DB_USER'])),
        ]
        for statement in statements:
            conn.execute(statement)
    with connect(app) as conn:
        revision = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        team = conn.execute('SELECT count(*) FROM team_members').fetchone()[0]
        gallery = conn.execute('SELECT count(*) FROM gallery_photos').fetchone()[0]
    print(f'Database setup verified. Revision: {revision}; team members: {team}; gallery photos: {gallery}.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Setup stopped ({type(error).__name__}).', file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        else:
            print('Check local authentication and existing role credentials. Secrets were not printed.', file=sys.stderr)
        sys.exit(1)
