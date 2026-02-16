from sqlalchemy import Column,Integer,String,TIMESTAMP,ForeignKey
from sqlalchemy.sql import func
from database import Base

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
