from sqlalchemy import Column,Integer,String,TIMESTAMP,ForeignKey, Boolean, Date
from sqlalchemy.sql import func
from database import Base

class Contestant(Base):
    __tablename__ = "contestants"
    id = Column(Integer,primary_key=True,index=True)
    name= Column(String,nullable=False)
    surname= Column(String,nullable=False)
    email= Column(String,nullable=False,unique=True)
    phone= Column(String,nullable=False)
    school= Column(String,nullable=False)
    class_and_profile = Column(String,nullable=False)
    city = Column(String,nullable=False)
    birthdate = Column(Date,nullable=False)

    supervisor_name = Column(String,nullable=False)
    supervisor_surname = Column(String,nullable=False)
    supervisor_info = Column(String,nullable=False)

    previous_accomplishments = Column(String)
    about = Column(String,nullable=False)
    interests = Column(String,nullable=False)
    contributions = Column(String,nullable=False)
    story = Column(String,nullable=False)

    topic = Column(String,nullable=False)
    whytopic = Column(String,nullable=False)
    persuation = Column(String,nullable=False)
    experience = Column(String,nullable=False)
    ways_of_grabing_interest = Column(String,nullable=False)

    video_file_path = Column(String)
    rules_accepted = Column(Boolean,nullable=False)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
class Viewer(Base):
    __tablename__ = "viewers"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String,nullable=False)
    surname = Column(String,nullable=False)
    school = Column(String)
    class_and_profile = Column(String)
    email = Column(String,nullable=False,unique=True)
    phone = Column(String,nullable=False)
    rules_accepted = Column(Boolean,nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Volunteer(Base):
    __tablename__ = "volunteers"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String,nullable=False)
    surname = Column(String,nullable=False)
    school = Column(String, nullable=False)
    class_and_profile = Column(String, nullable=False)
    email = Column(String,nullable=False,unique=True)
    phone = Column(String,nullable=False)
    rules_accepted = Column(Boolean,nullable=False)
    birthdate = Column(Date,nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class AdminUser(Base):
    __tablename__="admin_users"
    id=Column(Integer,primary_key=True,index=True)
    username=Column(String,unique=True,nullable=False,index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)