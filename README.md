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

### Changing the DB (Development)
#### 1. Apply any nessesary modifications to `models.py`
#### 2. Update the DB with alembic
In venv run:
```bash
ENV_FILE="admin_DBcreds.env" alembic revision --autogenerate -m "<descriptionOfChanges>"
ENV_FILE="admin_DBcreds.env" alembic upgrade head
```

## Production
### Initial deployment:
#### 0. Enter venv and install dependencies
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
host    all     all     127.0.0.1/32    ident
```
or
```
host    all     all     127.0.0.1/32    peer
```

Replace `peer` or `ident` with `scram-sha-256`. Save and exit.   

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
**ATTENTION: Set the <adminUsername> to the linux username on your system!!!**

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
DB_HOST=localhost   
DB_PORT=5432
```
And in `admin_DBcreds.env` hold:
```env   
DB_NAME=<DBname>
DB_USER=<adminUsername>   
DB_PASSWORD=<adminPassword>   
DB_HOST=localhost   
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

#### 6. Further actions
Please follow steps `Add a secret key`  
and `Creating an admin user for the admin dashboard`  

### Add a secret key
Create a file named `SECRET_KEY.env`
```env
    SECRET_KEY=<random-long-string>
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
Enter the username and password.
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
