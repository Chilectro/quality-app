from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from .base import Base
import enum

class SourceEnum(str, enum.Enum):
    APSA = "APSA"
    ACONEX = "ACONEX"

class Load(Base):
    __tablename__ = "loads"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(Enum(SourceEnum), nullable=False)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(128), nullable=True)
    loaded_at = Column(DateTime, server_default=func.now(), nullable=False)