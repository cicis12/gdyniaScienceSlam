(This readme is work in progress and will be expanded in the future)
# Gdynia Science Slam Website
## Dependencies
This project uses PostgreSQL, remember to install it locally for development and to include it on the production server


## Tutorials:
## Development
### Running a Python virtual envirement
In the project folder run:   


If running for the first time: `python -m venv venv`   

`source venv/bin/activate`

Install the project dependencies before starting the app or running migrations:
```bash
python -m pip install -r requirements.txt
```

### Running an uvicorn server (Development)
```bash
    uvicorn main:app --reload
```
### Adding a new static page:

#### 1. Frontend
Add an html page to the base project directory `<name>.html`

#### 2. Backend
In `main.py`
```py
#serve pages (@app.get)

(...)

@app.get("/<name>", response_class=FileResponse)
def <name>():
    return BASE_DIR/ "<name>.html"
```
    
### Adding new form:

#### 1. Add a frontend form page
Add an html page for the form (see `registration.html`) to the base project directory   

**Attention:** Pay attention to `action="/<action>"` in `<form>`. It has to exactly match the post listener in `main.py`.   

**Attention:** Also pay attention to `name="<name>"` in the individual `<input>` fields, as they also need to match the fields in `main.py`.   

#### 2. Serve the page
In `main.py`
Under `#serve pages (@app.get)` add:
```py 
#serve pages (@app.get)

(...)

@app.get("/<pagename>", response_class=FileResponse)
def <pagename>():
    return BASE_DIR/ "<pagename>.html"
```
#### 3. Add a model to `models.py`
In `models.py` add a class
```py
class <Name>(Base):
    __tablename__ = "<name>"
    <field> = Column(Type,nullable=T/F,primary_key=T/F,index=T/F)
```
For example:
```py
class Viewer(Base):
__tablename__ = "viewers"
id = Column(Integer,primary_key=True,index=True)
name = Column(String,nullable=False)
surname = Column(String,nullable=False)
school = Column(String)
email = Column(String,nullable=False)
phone = Column(String,nullable=False)
consent_file_path = Column(String, nullable=False)
created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
```
#### 4. Add table to DB
In `/alembic/env.py` to
```py
from models import [...]
```
add the name of your class.   
Add a migration
```bash
alembic revision --autogenerate -m "<Desciption of changes"
```
Then apply changes by
```bash
alembic upgrade head
```

#### 5. Import the created class to `main.py`
In `main.py` to line starting with `from models import ...` add the name of your class, i.e.
```py
from models import Viewer
```
#### 6. Add POST listening
Add listening to the form.   
Make sure `<nameOfField>` is the same as the name of inputs in your .html file
```py
@app.post("/<action>")
async def handle_exampleform(
    #if required
    <nameOfField>: <type> = Form(...),
    #if not
    <nameOfField>: <type> | None = Form(None),

    db: Session = Depends(get_db),
):
    new_example = Example(
        #Either
        <nameOfField>=<nameOfField>.strip(),
        #Or just (if not required or if not string or if you dont want .strip())
        <nameOfField>=<nameOfField>,
    )
    try:
        db.add(new_example)
        db.commit()
        db.refresh(new_example)
    except IntegrityError:
        db.rollback()
        return JSONResponse(status_code=400, content={"success": False, "message": "<Something that was supposed to be unique is already in the DB>"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "<success>"}
    )
```
##### 5.1 Handling videos
If handling videos add:
```py
@app.post("/<action>")
async def handle_exampleform(
    #If required
    exampleVideo: UploadFile = File(...),
    #If not
    exampleVideo: UploadFile | None = File(None), 
    db: Session = Depends(get_db),
):
    video_file_path = None
    if video and video.filename:
        if video.size > 0:
            video_file_path = await save_video(video)
    #If video is required you may add an else with JSON error handling
    #[...]
```

### Adding a new admin page
If adding an admin page pls render via jinja2

### Changing the DB (Development)
#### 1. Apply any nessesary modifications to `models.py`
#### 2. Update the DB with alembic
In venv run:
```bash
ENV_FILE="admin_DBcreds.env" alembic revision --autogenerate -m "<descriptionOfChanges>"
```
If adding required fields, now:  
In the newly created alembic migration file find a line:
```py
 op.add_column('<table>', sa.Column('<collumn name>', ...
 ```
 Add to the end
 ```py
 [...], server_default="<server default>")
```
```bash
ENV_FILE="admin_DBcreds.env" alembic upgrade head
```
## Production
### Docker Compose deployment (recommended)

Docker packages the application and its Python dependencies, PostgreSQL, Redis,
and a Caddy HTTPS proxy. Database and uploaded files live in persistent named
volumes. Only the proxy publishes ports. The app runs as a non-root user, uses a
separate database role with data-access grants, and shares rate limits through
Redis. Docker does not supply a server, configure your DNS, or replace backups.

Run these steps yourself on the target Linux server, in its host terminal:

1. Install Docker Engine and the Compose plugin for your distribution using
   <https://docs.docker.com/engine/install/>. Install Python 3 for the interactive
   configuration helper. Start/enable Docker where required:
   ```bash
   sudo systemctl enable --now docker
   docker version
   docker compose version
   ```
   Your terminal must have Docker daemon access. If you run deployment as root,
   use that same user for later commands because configuration is private.
2. Copy the complete application to the server. Commit or transfer all required
   new files first; a clone does not include uncommitted/untracked changes.
   Do not copy your development virtual environment or development credentials.
3. For public hosting, point the domain's A record to the server IPv4 address and
   allow inbound TCP 80/443 in the host and provider firewalls. The default proxy
   binding is IPv4; configure IPv6 binding before advertising an AAAA record.
   Ensure those ports are available; the script does not stop other web servers.
4. From the project directory, run:
   ```bash
   ./deploy.sh
   ```
   It asks for the domain, certificate contact email, worker count, first
   superadmin username/password, and optional MailerSend settings. Database
   passwords and the two token secrets are generated automatically. Verify the
   sender/domain with MailerSend yourself before providing its API key. Skipping
   mail setup leaves email sending unavailable.
5. The script builds the image, starts PostgreSQL/Redis, waits for readiness,
   creates database roles, applies Alembic migrations/grants, creates the first
   superadmin, then starts the app and Caddy. Open `https://your-domain/admin`.
   Use the admin configuration import to move public content if needed.

The script pauses for Docker installation/access and first public DNS/firewall
setup because those actions depend on your host and external accounts. Public
certificates are obtained/renewed by Caddy after DNS and networking are ready.
On Fedora with Docker SELinux isolation enabled, the script labels the private
secret directory `container_file_t`; the proxy config bind mount uses `:Z`.
It never disables SELinux or changes unrelated PostgreSQL installations.

Deployment files:

- `Dockerfile`: application image; tests, environment files, and uploads are excluded.
- `compose.yaml`: app, PostgreSQL 17, Redis, Caddy, volumes, and one-off bootstrap.
- `deployment/Caddyfile`: HTTPS proxy and a 160 MB request limit for ZIP imports.
- `deploy.sh`: human-readable deployment and maintenance commands.
- `scripts/deploy_support.py`: configuration, DB setup, account creation, and backup support.

Configuration is stored in ignored `.deploy/`, separate from the existing native
`*.env` files. Its directory and `secrets/` are mode 0700. Secret files are 0444
so the authorized non-root containers can read file-backed Compose secrets; the
protected parent directories prevent other host users from reading them. Keep
those directories private. Docker administrators can access container secrets.
The temporary plaintext bootstrap-admin password is removed after successful
initialization; existing account passwords and token/database secrets are
preserved on reruns. Keep `.deploy/` with your private backups.

You can collect settings without starting services, or validate an existing setup:
```bash
./deploy.sh --configure-only
./deploy.sh --check
```

For the default `.deploy/` configuration, setup creates a project-root `.env`
symlink to `.deploy/site.env`, allowing plain `docker compose ps` and
`docker compose logs` to load the settings automatically. The Compose file fixes
the default project name to `gdynia-science-slam`, matching the deploy script.
Existing `.env` files are preserved. If one already exists, or you use a custom
configuration/project, use `./deploy.sh status` or the explicit command:
```bash
docker compose --project-name gdynia-science-slam --env-file .deploy/site.env ps
```
For an installation created before this fix, update the source then run
`./deploy.sh --configure-only` once. This adds environment discovery without
regenerating credentials, changing the database, or restarting containers.

Subsequent maintenance:
```bash
./deploy.sh          # Build current source, migrate, and recreate app/proxy
./deploy.sh status
./deploy.sh logs
./deploy.sh stop     # Preserve all data volumes
./deploy.sh start    # Start an already initialized stack
./deploy.sh backup
```
Update/copy the source yourself before redeploying; the script does not pull Git
or discard local changes. Back up before deploying schema changes. Major database
version upgrades are separate work; do not change the PostgreSQL image major tag
against an existing volume. Refresh compatible service images deliberately with:
```bash
docker compose --project-name gdynia-science-slam --env-file .deploy/site.env pull db redis proxy
```
Then rerun `./deploy.sh`. The deployment script recreates app/proxy containers so
updated file-backed secrets are actually mounted, even when code is unchanged.
To enable skipped email sending later, edit `.deploy/secrets/MAIL.env`: temporarily
use mode 0600 while editing, then restore 0444 and rerun `./deploy.sh`. For domain,
contact email, or worker changes, update both `config.json` and its corresponding
quoted values in `site.env`; `--check` verifies they agree. Database passwords are
not rotated by editing secret files; preserve them or coordinate a DB-side password
change deliberately.

For local testing, choose `localhost`. The proxy binds to 127.0.0.1 and uses a
local CA. Export its public root certificate after the first startup:
```bash
docker compose --project-name gdynia-science-slam --env-file .deploy/site.env cp proxy:/data/caddy/pki/authorities/local/root.crt .deploy/caddy-root.crt
```
Trust that certificate in your own browser/OS using its certificate-management
instructions. A container cannot automatically add trust to your host browser.
Do not bypass TLS certificate checks for public deployments.

`./deploy.sh backup` briefly stops the app to keep the database and uploads
consistent, then restarts it. Each private `backups/<timestamp>/` folder includes
`database.dump`, `uploads.tar.gz`, `configuration.tar.gz`, and `caddy-data.tar.gz`.
Redis counters are not part of the durable application backup. Copy backups off
this machine and keep them private. An admin content ZIP excludes accounts,
submissions, voters, and votes, so it is not a full backup.

To restore a backup, use a **fresh replacement stack**, with the matching source:

1. Restore `configuration.tar.gz` into `.deploy/` and retain private directory
   permissions. Build the app image and start only PostgreSQL/Redis:
   ```bash
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env build app
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env up -d --wait db redis
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env run --rm --no-deps -T bootstrap python scripts/deploy_support.py bootstrap --roles-only
   ```
2. Restore the DB **only into that empty replacement database**:
   ```bash
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env exec -T db pg_restore -U postgres --role=gss_migrator --no-owner --no-acl --exit-on-error -d gdynia_science_slam < /path/to/backup/database.dump
   ```
3. Restore uploaded files into the two app volumes:
   ```bash
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env run --rm --no-deps -T --entrypoint python app -c 'import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall("/app",filter="data")' < /path/to/backup/uploads.tar.gz
   ```
4. Restore certificate data if you want to retain the local CA or existing TLS state:
   ```bash
   docker compose --project-name gdynia-science-slam --env-file .deploy/site.env run --rm --no-deps -T --entrypoint sh proxy -c 'tar -xzf - -C /data' < /path/to/backup/caddy-data.tar.gz
   ```
5. Update DNS for the new server and run `./deploy.sh` to check migrations/grants
   and start the site. Existing restored superadmin passwords are preserved.
   Caddy can obtain new public certificates. For local HTTPS, restore/trust the
   original CA or trust the new CA before using the browser.

For a fresh DB reused with a configuration whose bootstrap password was cleared,
provide a new bootstrap password before deploying:
```bash
python3 scripts/deploy_support.py configure --bootstrap-password
```
This only supplies a password for an account that does not exist; it does not
reset existing account passwords. `GSS_DEPLOY_DIR`, `GSS_COMPOSE_PROJECT`, and
`GSS_APP_IMAGE` support explicit alternative configurations; keep the same project
name when updating so the same data volumes are reused. Run the script on the
server with its local Docker daemon; remote Docker contexts require transferring
bind-mounted configuration to that daemon's host separately.

Never use `docker compose down --volumes` on a deployment you want to keep.

### Native deployment (manual alternative)
### Initial deployment:
#### 0. Enter venv and install dependencies
Install PostgreSQL on the host device (outside Flatpak or another app sandbox).

Debian/Ubuntu:
```bash
sudo apt update
sudo apt install postgresql postgresql-client
sudo systemctl enable --now postgresql
```

Fedora:
```bash
sudo dnf install postgresql-server postgresql
# Run only for a new installation with no initialized database cluster:
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

Check that the server is available before continuing:
```bash
pg_isready -h 127.0.0.1 -p 5432
```
After pulling the repository,enter the pulled folder   
Install venv by
```bash
python -m venv venv
```
And run it:
```bash
source venv/bin/activate
```

Install python dependencies by running
```bash
pip install -r requirements.txt
```

#### 1. Change postgre identification settings
Access the psql superuser console by
`sudo -u postgres psql`
or
`psql -U postgres`

type
```sql
SHOW hba_file;
```
Enter the given file and search for
```
local   all     all                     ident
host    all     all     127.0.0.1/32    ident
```
or
```
local   all     all                     peer
host    all     all     127.0.0.1/32    peer
```

Keep the local `postgres` administrative connection on `peer` so that
`sudo -u postgres psql` continues to work. Configure the app's TCP connections
on `127.0.0.1/32` and `::1/128` to use `scram-sha-256`. Do not change unrelated
access rules. Set `password_encryption` to `scram-sha-256` before creating the
roles below (for example, `SET password_encryption = 'scram-sha-256';` in that
psql session). Save the configuration and reload the service:
```bash
sudo systemctl reload postgresql
```

Restart Postgre by
```bash
sudo systemctl restart postgresql
```
or if it fails
```bash
sudo service postgresql restart
```
#### 2. Create a user in psql and add credentials to .env
Access the psql superuser console by
`sudo -u postgres psql`
or
`psql -U postgres`

Create an admin user:  
Use separate migration and application roles. The migration role does not need
to match your Linux username when connecting with a password over TCP.

```sql
CREATE USER <adminUsername> WITH PASSWORD '<adminPassword>';
```
Create an app user:
```sql
CREATE USER <appUsername> WITH PASSWORD '<appPassword>';
```
Create two .env files: `DBcreds.env` and `admin_DBcreds.env`   
In `DBcreds.env` hold:
```env   
DB_NAME=<DBname>
DB_USER=<appUsername>   
DB_PASSWORD=<appPassword>   
DB_HOST=127.0.0.1
DB_PORT=5432
```
And in `admin_DBcreds.env` hold:
```env   
DB_NAME=<DBname>
DB_USER=<adminUsername>   
DB_PASSWORD=<adminPassword>   
DB_HOST=127.0.0.1
DB_PORT=5432
```


#### 3. Create the database
Via the psql terminal do:
```sql
CREATE DATABASE <DBname> OWNER <adminUsername>;
```
Exit by typing
```sql
\q
```
Protect both credential files and verify the migration connection first:
```bash
chmod 600 DBcreds.env admin_DBcreds.env
psql -h 127.0.0.1 -U <adminUsername> -d <DBname> -W -c "SELECT current_user;"
```
Run commands from the repository root with the virtual environment active.
Do not recreate an existing database or overwrite credentials without checking
its contents. If roles already exist, inspect them before changing passwords.

#### 4. Run migrations (add tables to db)
Do:
```bash
ENV_FILE="admin_DBcreds.env" alembic upgrade head
```

#### 5. Add permissions to the app user
Enter the postgres console for the DB u created:
```bash
psql <DBname>
```
Add permissions for the app user:
```sql
GRANT CONNECT ON DATABASE <DBname> TO <appUsername>;
GRANT USAGE ON SCHEMA public TO <appUsername>;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO <appUsername>;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public
TO <appUsername>;

ALTER DEFAULT PRIVILEGES
FOR ROLE <adminUsername>
IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES
TO <appUsername>;

ALTER DEFAULT PRIVILEGES
FOR ROLE <adminUsername>
IN SCHEMA public
GRANT USAGE, SELECT
ON SEQUENCES
TO <appUsername>;
``` 
Exit the psql console by
`\q`
#### 6. Connect your mail API
For mail support add a file `MAIL.env`
in which put:
```env
MAIL_API_KEY=<mailApiKey>
EMAIL_FROM=<emailAdressToEmailFrom>
```
The Api key you need to get from a provider, like mailersend, mailgun or sendgrid
Note: email sending in `mail.py` is set up for `mailersend`, if switching providers, modify the file accordingly.
#### 7. Further actions
Please follow steps `Add a secret key`  
and `Creating an admin user for the admin dashboard`  

### Add a secret key and a voter secret key
Create files named `SECRET_KEY.env` and `VOTER_SECRET_KEY.env`
in `SECRET_KEY.env`:
```env
    SECRET_KEY=<random-long-string>
```
in `VOTER_SECRET_KEY.env`
```env
    VOTER_SECRET_KEY=<random-long-string>
```
You can generate one safely by
```bash
openssl rand -hex 32
```
### Creating an admin user for the admin dashboard
Run
```bash
    python create_admin.py
```
Enter the username and password. For the first native-deployment account, enable
superadmin access after creating it:
```bash
python make_superadmin.py
```
Enter the same username and review the prompt. This utility toggles privileges;
do not blindly rerun it for an account that is already a superadmin. Docker
bootstrap creates its initial account with superadmin access directly.

### Rate-limit storage
Local development uses in-process memory storage by default, so Redis is not required.
For production or multiple application workers, configure Redis with
`RATE_LIMIT_STORAGE_URI=redis://localhost:6379/0` and enable the Redis service:
```bash
apt install redis-server
systemctl start redis-server
systemctl enable redis-server
```
### Updating database (Production)
Pull the most recent changes from git
```bash
git fetch
git pull
```
Update the database (run a migration) by:
```bash
ENV_FILE="admin_DBcreds.env" alembic upgrade head
```

### Automated local database setup
On a host with PostgreSQL already running and sudo access, use the existing
`DBcreds.env` and `admin_DBcreds.env` settings:
```bash
venv/bin/python scripts/setup_local_database.py
```
Run this in your device's terminal so sudo can prompt for authentication.
The script creates missing roles and the database, preserves existing role
passwords and data, applies migrations, grants application access, and verifies
the seeded tables. Existing credentials must already match any existing roles.
It restricts the credential files to their owner. Install dependencies first.

### Verify database setup
After migrations and grants, check the migration revision and application access:
```bash
ENV_FILE=admin_DBcreds.env venv/bin/alembic current
venv/bin/alembic heads
psql -h 127.0.0.1 -U <appUsername> -d <DBname> -W -c "SELECT count(*) FROM team_members;"
```
The current revision should match the head. After future migrations, reapply
existing-table grants if needed; default privileges must be assigned for the
migration role that actually creates tables. For an application smoke check,
configure the mail and token secrets described above, then run
`venv/bin/uvicorn main:app --reload`.


### Admin accounts, sessions, and form uploads

Install the updated dependencies and apply the new migration before starting this
version. The migration adds `admin_users.is_sysadmin` and `admin_sessions`; existing
accounts and submissions are preserved. Existing admin cookies become invalid,
so administrators must log in again.

```bash
venv/bin/python -m pip install -r requirements.txt
ENV_FILE=admin_DBcreds.env venv/bin/alembic upgrade head
venv/bin/python make_sysadmin.py
```

Apply the usual application-role grants to new tables after a manual migration.
`deploy.sh` handles migrations and grants during its normal bootstrap step.
`make_sysadmin.py` prompts for an existing username and toggles system administrator
access, just like `make_superadmin.py` toggles superadmin access. To use it inside
an existing Docker deployment, run `docker compose --env-file .deploy/site.env exec app python make_sysadmin.py`.

System administrators inherit superadmin access and can use **Zarządzaj
administratorami** at `/admin/admins` to create/delete accounts, enable/disable
accounts, change superadmin status, and reset passwords. Sysadmin status itself is
managed by the script. The page prevents self-deletion/self-disabling and removal
of the last active sysadmin. Account changes revoke existing sessions. Password
changes made through other scripts also invalidate sessions automatically. Logout
revokes the current session. Session cookies contain random tokens; only token
digests and credential fingerprints are stored in the database. Sessions expire
after four hours.

Admin-authored HTML is sanitized when rendered, including existing/imported copy
and previews. Text formatting, links, images, basic SVG shapes and Tailwind classes
are supported. Scripts, event handlers, unsafe link schemes, embedded documents,
and inline CSS are removed from rendered content. Stored source remains editable.

Public forms support private video, PDF, and image attachments. Add a **Plik**
field in the form builder and choose one or more accepted categories: videos, images,
documents, or archives. Each field accepts one file. The selected categories are
enforced by both the file picker and server and saved with each form version.
Uploads are limited to 100 MiB per file, three files per
submission, and 110 MiB for the entire multipart request. Videos include MP4, MOV, WebM and MKV; images include PNG, JPG/JPEG, WebP and GIF;
documents include PDF, Office/OpenDocument files, TXT, CSV and RTF; archives include
ZIP, RAR, 7z, TAR and GZ. Basic signature checks apply. Archives are never extracted
and are served as downloads. Existing fields default to videos, images and documents.
Files are stored under `uploads/forms/`, outside `/static`, and are served only to
active logged-in admins. Videos support authenticated byte-range playback and
all attachments can be downloaded. Playback depends on the browser's support for
the video's codec; the download link remains available. Include the private
uploads volume/directory in backups alongside the database. Site configuration
ZIP exports do not contain private submissions or their attachments.

Form requests are limited before parsing to **10 per minute and 100 per hour per
IP**. Configure `FORM_SUBMISSION_RATE_LIMIT` with a `limits` expression such as
`10/minute;100/hour` to account for shared networks at an event. The existing
`RATE_LIMIT_STORAGE_URI` selects shared Redis storage in Docker; local development
uses memory. `FORM_UPLOAD_STORAGE_LIMIT_MB` defaults to `10240` (10 GiB total saved
form attachments). Exceeding the storage budget rejects new uploads without
deleting existing files. JSON-only submissions are limited to 256 KiB, individual
text answers to 10,000 characters, and outdated form versions are rejected with a
request to refresh. The admin viewer loads 50 submissions per page.

In **Odpowiedzi formularzy**, select a form and choose **Eksportuj odpowiedzi (ZIP)**
to download every submission, across all pages and form versions. The archive contains
`answers.txt`, `answers.csv` (UTF-8 with BOM, semicolon separated), and an
`attachments/<submission-id>/` folder. CSV uses one row per question with submission,
date, version, field, question, answer, and attachment path columns. Questions follow
the version originally submitted. Missing attachments are marked in the answers;
the remaining records still export. Regular admins with access to submissions can
also export them. ZIP generation uses temporary disk storage, cleaned after download.


### Partner invitation page

`/become-a-partner` is edited by superadmins at `/admin/become-a-partner`
(linked from system settings). Add, edit, hide, delete, and order up to 50 sections:
a six-item grid matching About, paragraph with an optional side image, three SVG icon columns, large heading,
a group of up to 20 contact people with circular photos and an optional Team link, FAQ, and a contact
form. New sections start hidden. SVG code is validated and descriptive HTML is
sanitized. Paragraph images can be uploaded, replaced, or removed, with configurable
alt text; text and image stack on mobile. FAQ questions can be added and removed individually.

Enable the homepage feature to show a separate full section after Partners, using
the same text-and-photo layout as About and Previous Editions. It has configurable
text, link and photo (falling back to the homepage About photo). The invitation page
must be visible. This section is independent of the Partners section visibility. Public
page visibility is controlled in system settings and also blocks contact submissions.
Use **Podgląd zmian** for a desktop/tablet/mobile preview of the unsaved draft,
including selected photos. Preview loads as a regular, script-free page inside
the admin dialog, with loading and error feedback. Preview never stores content
or sends mail. All edits,
additions and deletions are saved together with **Zapisz całą stronę**. Failed saves
preserve the draft and roll back newly uploaded photos. Existing single-person
sections are automatically read as a group containing that person.

Content uses the existing `system_settings` table; no new migration is needed.
Full configuration exports include this page, paragraph images, and contact photos. Older bundles
without its optional content preserve the existing page on import.

Set the contact recipient in this editor. The recipient remains server-side.
Mail uses the existing MailerSend configuration: `MAIL_API_KEY` and `EMAIL_FROM`
in native `MAIL.env`, or `.deploy/secrets/MAIL.env` for Docker. Verify the sender
or domain in MailerSend. After changing server mail settings, restart the app
(or rerun `./deploy.sh` for Docker). No new provider or environment variable is
required if mail is already configured.

Messages are sent as plain text from `EMAIL_FROM`, with the visitor's address as
`Reply-To`, and a `[Współpraca]` subject prefix. Empty recipient or missing mail
configuration returns an unavailable message; provider rejection/timeout returns
an error and preserves form input. Success means MailerSend accepted the message,
not guaranteed inbox delivery. Messages are not stored in the database and no
automatic reply is sent. Sending requires JavaScript. Contact requests are limited
to 32 KiB and share the configured `FORM_SUBMISSION_RATE_LIMIT` values with a
separate per-IP counter; Docker uses Redis across workers.

### Link UUID interaction analytics

Superadmins can create shareable links and view reports at `/admin/analytics`
(**Statystyki interakcji** in system settings). Each link has a random UUID, for
example `/become-a-partner?ref=<uuid>`. It is carried to other public HTML pages
through internal links, including standalone forms and voting. UUIDs identify
links, not verified people: forwarding a link combines recipients' activity.
A fresh visit UUID is generated for each page load. No localStorage, sessionStorage,
fingerprinting, external analytics service, or analytics IP storage is used. Signed
session cookies remember tracking consent and partner-page access separately.
Existing server/proxy access logs are separate and may still contain IPs and URLs.

**Collection is off by default.** Enable it explicitly in the analytics admin page.
Entering a public page through an active `?ref=<uuid>` link opens a configurable
tracking-consent popup. Edit its title, sanitized HTML content, and Yes/No labels
at `/admin/analytics`. No analytics script is started and no interaction data is
accepted by the server until consent is granted. The submitted choice includes
the exact popup revision: changing its content or labels invalidates prior consent,
and an older open popup cannot approve wording the visitor has not seen.

**No** (including Escape) removes the UUID from the current URL and internal links,
deletes any tracking-consent cookie, and leaves only a signed `gss_partner_access`
flag containing no UUID. **Yes** also creates `gss_tracking_consent`, containing the
link UUID and consent revision. Both are HttpOnly, SameSite=Lax session cookies,
Secure on HTTPS, with a signed validity limit of 24 hours. The access flag cannot
be forged by setting a plain browser boolean. A rejected visitor is not associated
with a link in the database. Reopening the original invitation after declining
asks again; the access-only flag deliberately does not remember which UUID was
rejected. Cookie handling must be enabled to remember the choice across navigation.

DNT/GPC requests, logged-in admin sessions, and embedded/admin previews remain
excluded. The footer **Wyłącz statystyki tej wizyty** action stops the tracker and
revokes the consent cookie on the server while keeping partner-page access.
Opening with `analytics=off` also prevents collection. The configurable consent
text should match your privacy information; see the [EDPB URL-tracking guidance](https://www.edpb.europa.eu/documents/guideline/guidelines-22023-on-technical-scope-of-art-53-of-eprivacy-directive_en).

In `/admin/become-a-partner`, enable **Udostępniaj stronę tylko odbiorcom aktywnego
linku UUID** and use the main Save button to restrict the page. Ordinary visitors
then get a 404, and its navigation links and homepage feature are hidden. An active
invitation URL or the signed access flag grants access, even after tracking is
refused. The contact endpoint follows the same access restriction. The normal
public page-visibility setting still takes precedence. Superadmins can inspect
the page and use previews without an invitation. Disabling a UUID prevents new
invitations/analytics for that link; already-issued identity-free access flags remain
valid until their session/24-hour expiry. Disable public page visibility to block
all visitors immediately. This is link-based access, not a personal login system.

Reports show estimated visible time, clicks, and FAQ openings per section and
page. Time counts only while the tab is visible and focused and at least half of
the smaller of a section or the available viewport is visible. Tracking pauses
after 60 seconds without pointer, keyboard, touch, or scroll activity. The `Cała
strona` row supplies total page time; **do not sum section times** because visible
sections and parallel tabs overlap. This measures visibility, not reading, gaze,
or verified human engagement. Click counts do not include entered values or
link destinations. Form contents, email addresses, and voting choices are not
read by the tracker. JavaScript blockers, offline navigation, abrupt browser
termination, inactivity, and interrupted network requests can undercount.

The browser sends cumulative counters every 10 seconds, with a final beacon when
the page is hidden or left. Duplicate and out-of-order requests use maxima instead
of adding time again. Each section's total is capped at 24 hours per page load and
at the server-observed visit age plus 15 seconds. At most 100 section counters are
accepted per visit. Client counters remain untrusted approximate analytics.
`/api/interactions` accepts up to 32 KiB; `ANALYTICS_RATE_LIMIT` defaults to
`240/minute;20000/hour` per IP, using the existing Redis/memory limiter storage.
IP addresses used for the rate limiter are not written to analytics tables.

Visits and their counters expire after 90 days; expired data is deleted when
analytics are received or a report/dashboard is opened (not by a background job).
Admins can disable a link, clear its statistics, or delete the link and all its
visits. There is a limit of 500 links. Analytics, link labels/UUIDs, and the enabled
switch and consent-popup settings are excluded from site configuration ZIP
exports/imports; DB backups do include them. The partner UUID-only option travels
with the partner-page content. Popup/access behavior uses the existing settings
table and needs no additional migration beyond the analytics tables.

This feature adds three tables. Apply the migration before opening the analytics
admin page on another installation:

```bash
ENV_FILE=admin_DBcreds.env venv/bin/alembic upgrade head
```

For native deployment, grant the app role `SELECT, INSERT, UPDATE, DELETE` on
`interaction_links`, `interaction_visits`, and `interaction_sections` if its default
grants do not already cover new tables. Docker's normal `./deploy.sh` runs migrations
and grants automatically. No external API key is needed. Test with a private
browser window because logged-in administrators are excluded.

Tracking script checks can also be run with Node.js:

```bash
node tests/interaction_analytics_test.cjs
node tests/referral_consent_test.cjs
```
