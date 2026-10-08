from datetime import datetime
from sqlalchemy import Column,Integer,String,TIMESTAMP,ForeignKey, Boolean, Date, DateTime, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.dialects.postgresql import JSONB

class FormInfo(Base):
    __tablename__ = "form_info"
    id=Column(Integer,primary_key=True,index=True)
    slug=Column(String,unique=True,nullable=False,index=True)
    name=Column(String,unique=True,nullable=False,)
    enabled=Column(Boolean,nullable=False,default=False)
    cur_version_id=Column(Integer,nullable=False)

    versions = relationship("FormVersion", back_populates="form", foreign_keys="FormVersion.form_id")
    submissions = relationship("FormSubmission", back_populates="form")


class FormVersion(Base):
    __tablename__ = "form_version"
    id=Column(Integer,primary_key=True,index=True)
    form_id=Column(Integer,ForeignKey("form_info.id"), nullable=False)
    version_num=Column(Integer, nullable=False, default=1)
    display_name=Column(String,nullable=False)
    description=Column(String,nullable=True)
    definition=Column(JSONB,nullable=False)
    created_at=Column(DateTime, default=datetime.utcnow)

    form = relationship("FormInfo", back_populates="versions", foreign_keys=[form_id])

class FormSubmission(Base):
    __tablename__ = "form_submission"
    id=Column(Integer,primary_key=True,index=True)
    form_id=Column(Integer,ForeignKey("form_info.id"), nullable=False)
    form_version_id=Column(Integer,ForeignKey("form_version.id"), nullable=False)
    data = Column(JSONB, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    form = relationship("FormInfo", back_populates="submissions")

class AdminUser(Base):
    __tablename__="admin_users"
    id=Column(Integer,primary_key=True,index=True)
    username=Column(String,unique=True,nullable=False,index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)

class Voter(Base):
    __tablename__="voters"
    id=Column(Integer,primary_key=True,index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    votes = relationship("Vote", back_populates="voter")

class Vote(Base):
    __tablename__="votes"
    id = Column(Integer,primary_key=True,index=True)

    voter_id=Column(Integer,ForeignKey("voters.id"),nullable=False)
    choice = Column(Integer, nullable=False)
    voter = relationship("Voter", back_populates="votes")

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    position = Column(String(160), nullable=False)
    description = Column(Text, nullable=False)
    photo = Column(String(500), nullable=False)


class GalleryPhoto(Base):
    __tablename__ = "gallery_photos"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    caption = Column(String(300), nullable=False, default="")
    photo = Column(String(500), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
