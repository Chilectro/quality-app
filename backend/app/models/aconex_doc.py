from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey, Index
from sqlalchemy.orm import relationship
from .base import Base

class AconexDoc(Base):
    __tablename__ = "aconex_docs"
    id = Column(Integer, primary_key=True)
    load_id = Column(Integer, ForeignKey("loads.id", ondelete="CASCADE"), nullable=False)

    document_no     = Column(String(120), index=True)   # Col A
    title           = Column(Text)
    discipline      = Column(String(60), index=True)
    function        = Column(String(120), index=True)   # Col H
    subsystem_text  = Column(String(255))               # Col L (texto largo)
    subsystem_code  = Column(String(60), index=True)    # derivado (ej 5620-S01-003)
    system_no       = Column(String(60))
    file_name       = Column(String(255))
    equipment_tag_no= Column(String(120))
    date_received   = Column(String(30))  # si prefieres, cambia a Date
    revision        = Column(String(30))
    transmitted     = Column(String(60))

    load = relationship("Load", backref="aconex_rows")

Index("ix_aconex_core", AconexDoc.subsystem_code, AconexDoc.function, AconexDoc.discipline)