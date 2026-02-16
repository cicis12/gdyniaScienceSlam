(This readme is work in progress and will be expanded in the future)
# Gdynia Science Slam Website
## Dependencies
This project uses PostgreSQL, remember to install it locally for development and to include it on the production server


## Tutorials:
### Development: running a Python virtual envirement
In the project folder run
`python -m venv venv`
`source venv/bin/activate`

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
Add an html page for the form (see `form.html`) to the base project directory
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
#### 4. Import the created class to `main.py`
In `main.py` to line starting with `from models import ...` add the name of your class, i.e.
```py
from models import Viewer
```

#### 5. Add POST listening


### Production

#### 1. Create a user in psql
Access the psql superuser console by
`sudo -u postgres psql`
or
`psql -U postgres`

Create a user:
`CREATE USER <username> WITH PASSWORD '<password>';`

#### 2. Create the database
Via the terminal do:
`CREATE DATABASE <DBname>;`
Add the user as superuser for the database:
`GRANT ALL PRIVILEGES ON DATABASE <DBname> TO <user>;`
Exit the psql console by
`\q`

#### 3. Add tables to the database
Do:
`psql -U <user> -d <DBname> -f databaseScheme.sql`

#### 4. Add the credentials to DBcreds.env
Create a file named `DBcreds.env`
In it store:
```env   
DB_NAME=<DBname>
DB_USER=<user>   
DB_PASSWORD=<password>   
DB_HOST=localhost   
DB_PORT=5432
```

