"""Deployment support. Host configuration uses only Python's standard library.
Database bootstrap runs inside the app image, where project dependencies exist.
"""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SECRET_FILES = ('postgres_password', 'DBcreds.env', 'admin_DBcreds.env', 'SECRET_KEY.env',
                'VOTER_SECRET_KEY.env', 'MAIL.env', 'bootstrap_admin.json')


def valid_domain(value):
    value = value.lower()
    if value == 'localhost':
        return True
    try:
        ipaddress.ip_address(value)
        return False  # Public deployments use a DNS name; local testing uses localhost.
    except ValueError:
        pass
    return len(value) <= 253 and '.' in value and all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
        for label in value.split('.')) and not value.endswith(('.local', '.internal', '.localhost'))


def valid_email(value):
    return re.fullmatch(r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', value) is not None


def prompt(label, validate, default=None):
    while True:
        value = input(label + (f' [{default}]' if default is not None else '') + ': ').strip()
        value = value or default or ''
        if validate(value):
            return value
        print('Please enter a valid value.')


def admin_password():
    while True:
        value = getpass.getpass('First superadmin password (12+ characters, at most 72 UTF-8 bytes): ')
        if len(value) < 12 or len(value.encode()) > 72:
            print('Password length is outside the supported range.')
        elif value != getpass.getpass('Repeat password: '):
            print('Passwords did not match.')
        else:
            return value


def write_file(path, value, mode=0o444):
    # Use a new inode so interrupted writes cannot truncate existing credentials.
    temporary = path.with_name(path.name + '.new-' + secrets.token_hex(4))
    try:
        temporary.write_text(value, encoding='utf-8')
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def env_text(values):
    return ''.join(f'{key}={json.dumps(str(value))}\n' for key, value in values.items())


def configure(directory, bootstrap_password=False):
    if (directory / 'config.json').exists():
        check(directory)
        if bootstrap_password:
            path = directory / 'secrets/bootstrap_admin.json'
            account = json.loads(path.read_text())
            account['password'] = admin_password()
            write_file(path, json.dumps(account) + '\n')
            print('Bootstrap password saved. Existing account passwords will not be changed.')
        else:
            print('Reusing existing deployment configuration and secrets.')
        return
    if directory.exists() and any(directory.iterdir()):
        raise RuntimeError('Incomplete deployment directory. Restore its backup or choose a new GSS_DEPLOY_DIR; existing files were preserved.')
    if not sys.stdin.isatty():
        raise RuntimeError('Initial configuration requires an interactive host terminal.')

    print('Use a public DNS name, or localhost for local HTTPS testing.')
    domain = prompt('Website domain', valid_domain, 'localhost').lower()
    contact = prompt('Certificate contact email', valid_email)
    workers = int(prompt('Application workers', lambda value: value.isdigit() and 1 <= int(value) <= 8, '2'))
    username = prompt('First superadmin username', lambda value: re.fullmatch(r'[a-zA-Z0-9_.@\-]{3,80}', value) is not None, 'admin')
    password = admin_password()
    mail_now = prompt('Configure MailerSend now? (yes/no)', lambda value: value in {'yes', 'no'}, 'no') == 'yes'
    api_key, sender = '', ''
    if mail_now:
        print('Create the API key and verify the sender domain in your MailerSend account first.')
        while not re.fullmatch(r'[a-zA-Z0-9._+=/\-]+', api_key):
            api_key = getpass.getpass('MailerSend API key: ').strip()
        sender = prompt('Verified sender email', valid_email)
    else:
        print('Email sending will remain unavailable until MAIL.env is configured.')

    config = dict(domain=domain, contact=contact, workers=workers, admin_username=username)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.deploy-stage-', dir=directory.parent))
    try:
        staging.chmod(0o700)
        secret_dir = staging / 'secrets'
        secret_dir.mkdir(mode=0o700)
        for filename, content in {
            'postgres_password': secrets.token_hex(32) + '\n',
            'DBcreds.env': env_text(dict(DB_USER='gss_app', DB_PASSWORD=secrets.token_hex(32), DB_NAME='gdynia_science_slam', DB_HOST='db', DB_PORT='5432')),
            'admin_DBcreds.env': env_text(dict(DB_USER='gss_migrator', DB_PASSWORD=secrets.token_hex(32), DB_NAME='gdynia_science_slam', DB_HOST='db', DB_PORT='5432')),
            'SECRET_KEY.env': env_text(dict(SECRET_KEY=secrets.token_hex(32))),
            'VOTER_SECRET_KEY.env': env_text(dict(VOTER_SECRET_KEY=secrets.token_hex(32))),
            'MAIL.env': env_text(dict(MAIL_API_KEY=api_key, EMAIL_FROM=sender)),
            'bootstrap_admin.json': json.dumps(dict(username=username, password=password)) + '\n',
        }.items():
            write_file(secret_dir / filename, content)
        write_file(staging / 'config.json', json.dumps(config, indent=2) + '\n', 0o600)
        write_file(staging / 'site.env', env_text(dict(SITE_DOMAIN=domain, ACME_EMAIL=contact,
                   APP_WORKERS=workers, BIND_ADDRESS='127.0.0.1' if domain == 'localhost' else '0.0.0.0')), 0o600)
        if directory.exists():
            directory.rmdir()  # Only an empty directory is accepted above.
        staging.rename(directory)
    finally:
        if staging.exists():
            import shutil
            shutil.rmtree(staging)
    print('Configuration saved. Secrets are kept outside the application image.')


def check(directory):
    config = json.loads((directory / 'config.json').read_text())
    if not valid_domain(config['domain']) or not valid_email(config['contact']) or type(config['workers']) is not int or not 1 <= config['workers'] <= 8:
        raise RuntimeError('Invalid deployment domain, email, or worker count.')
    for filename in SECRET_FILES:
        path = directory / 'secrets' / filename
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Deployment secret files are missing or unsafe; restore the configuration backup.')
    if not (directory / 'site.env').is_file():
        raise RuntimeError('site.env is missing.')
    try:
        actual = {}
        for line in (directory / 'site.env').read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                key, value = line.split('=', 1)
                actual[key] = json.loads(value)
        expected = {'SITE_DOMAIN': config['domain'], 'ACME_EMAIL': config['contact'],
                    'APP_WORKERS': str(config['workers']),
                    'BIND_ADDRESS': '127.0.0.1' if config['domain'] == 'localhost' else '0.0.0.0'}
        if actual != expected:
            raise ValueError('mismatch')
    except (ValueError, TypeError):
        raise RuntimeError('config.json and site.env must contain matching deployment settings.') from None
    if directory.stat().st_mode & 0o077 or (directory / 'secrets').stat().st_mode & 0o077:
        raise RuntimeError('Set deployment directory and secrets directory permissions to 0700.')
    # File-backed Compose secrets must be readable by the app's non-root UID.
    # Their host parent directories remain 0700; check does not mutate configuration.
    for filename in SECRET_FILES:
        if not (directory / 'secrets' / filename).stat().st_mode & 0o004:
            raise RuntimeError('Secret files must be 0444 inside the protected 0700 directories; see README.md.')
    return config


def connect_with_retry(psycopg, **kwargs):
    for attempt in range(30):
        try:
            return psycopg.connect(connect_timeout=3, **kwargs)
        except psycopg.OperationalError:
            if attempt == 29:
                raise RuntimeError('Database connection failed. Check the saved credentials and DB volume; no passwords were changed.') from None
            time.sleep(2)


def bootstrap(roles_only=False):
    import psycopg
    from psycopg import sql
    from dotenv import dotenv_values

    migration_file = Path('/run/secrets/migration_database')
    app_file = Path('/run/secrets/app_database')
    migration = dotenv_values(migration_file)
    app = dotenv_values(app_file)
    if migration['DB_NAME'] != app['DB_NAME'] or migration['DB_USER'] == app['DB_USER']:
        raise RuntimeError('Migration and app credentials must target the same DB with separate users.')
    root_password = Path('/run/secrets/postgres_password').read_text().strip()
    with connect_with_retry(psycopg, host='db', user='postgres', password=root_password, dbname='postgres', autocommit=True) as root:
        # Serialize bootstrap jobs for this application, including their migrations.
        root.execute("SELECT pg_advisory_lock(724096311)")
        for config in (migration, app):
            name = config['DB_USER']
            role = root.execute('SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=%s', (name,)).fetchone()
            if role is None:
                root.execute(sql.SQL("SET password_encryption='scram-sha-256'"))
                root.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Identifier(name), sql.Literal(config['DB_PASSWORD'])))
            elif any(role):
                raise RuntimeError('An application DB role has elevated privileges; review it manually.')
        owner = root.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s', (app['DB_NAME'],)).fetchone()
        if owner is None:
            root.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(app['DB_NAME']), sql.Identifier(migration['DB_USER'])))
        elif owner[0] != migration['DB_USER']:
            raise RuntimeError('Existing database has a different owner; review it manually before deploying.')

        if roles_only:
            print('Database roles and empty database prepared for restoration.', flush=True)
            return

        print('Applying Alembic migrations...', flush=True)
        environment = os.environ.copy()
        for key in ('DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_HOST', 'DB_PORT'):
            environment.pop(key, None)
        environment['ENV_FILE'] = str(migration_file)
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=environment, capture_output=True, text=True)
        if result.returncode:
            details = result.stderr
            for sensitive in (root_password, app['DB_PASSWORD'], migration['DB_PASSWORD']):
                details = details.replace(sensitive, '[redacted]')
            print(details[-4000:], file=sys.stderr)
            raise RuntimeError('Alembic migration failed; inspect the redacted error above.')
        with psycopg.connect(host='db', user=migration['DB_USER'], password=migration['DB_PASSWORD'], dbname=app['DB_NAME']) as db:
            user = sql.Identifier(app['DB_USER'])
            db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(app['DB_NAME']), user))
            db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(user))
            db.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}').format(user))
            db.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(user))
            db.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}').format(user))
            db.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}').format(user))

        os.environ['ENV_FILE'] = str(app_file)
        for key in ('DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_HOST', 'DB_PORT'):
            os.environ.pop(key, None)
        sys.path.insert(0, str(ROOT))
        from database import SessionLocal
        from models import AdminUser
        from security import hash_password
        account = json.loads(Path('/run/secrets/bootstrap_admin').read_text())
        with SessionLocal() as db:
            existing = db.query(AdminUser).filter_by(username=account['username']).first()
            if existing:
                if not existing.is_superadmin or not existing.is_active:
                    raise RuntimeError('Bootstrap username belongs to an inactive or ordinary admin; review the account manually.')
                print('Existing superadmin preserved.', flush=True)
            else:
                password = account['password']
                if len(password) < 12 or len(password.encode()) > 72:
                    raise RuntimeError('A new DB needs a bootstrap password. Run configure --bootstrap-password on the host.')
                db.add(AdminUser(username=account['username'], password_hash=hash_password(password), is_superadmin=True, is_active=True))
                db.commit()
                print('First superadmin created.', flush=True)
            db.execute(sqlalchemy_text('SELECT 1'))
    print('Database roles, migrations, grants, and app access verified.', flush=True)


def sqlalchemy_text(statement):
    from sqlalchemy import text
    return text(statement)


def archive_uploads():
    # Binary output is consumed by deploy.sh backup; never print status messages here.
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
        for path in (ROOT / 'uploads', ROOT / 'static/uploads'):
            archive.add(path, arcname=str(path.relative_to(ROOT)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'check', 'domain', 'bootstrap', 'clear-bootstrap-password', 'archive-uploads'))
    parser.add_argument('--directory', type=Path, default=ROOT / '.deploy')
    parser.add_argument('--bootstrap-password', action='store_true')
    parser.add_argument('--roles-only', action='store_true', help='Prepare an empty DB for manual backup restoration; skip migrations and account creation')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.command == 'configure':
        configure(directory, args.bootstrap_password)
    elif args.command == 'check':
        check(directory)
        print('Saved deployment settings are valid.')
    elif args.command == 'domain':
        print(check(directory)['domain'])
    elif args.command == 'clear-bootstrap-password':
        path = directory / 'secrets/bootstrap_admin.json'
        account = json.loads(path.read_text())
        account['password'] = ''
        write_file(path, json.dumps(account) + '\n')
    elif args.command == 'bootstrap':
        bootstrap(args.roles_only)
    else:
        archive_uploads()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # DB/library exceptions can contain URLs or secrets; only our own messages are shown.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print('Deployment stopped: ' + message, file=sys.stderr)
        sys.exit(1)
