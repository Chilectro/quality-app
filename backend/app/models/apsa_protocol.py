from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from .base import Base

class ApsaProtocol(Base):
    __tablename__ = "apsa_protocols"
    id = Column(Integer, primary_key=True)
    load_id = Column(Integer, ForeignKey("loads.id", ondelete="CASCADE"), nullable=False)

    codigo_cmdic = Column(String(120), index=True)   # Col E
    tipo  = Column(Text)                              # Col G
    descripcion  = Column(Text)                      # Col I
    tag          = Column(String(120))               # Col W
    subsistema   = Column(String(60), index=True)    # Col N (ej 5620-S01-003)
    disciplina   = Column(String(10), index=True)    # Col Z (50..59 como texto)
    status_bim360= Column(String(30), index=True)    # Col AA (ABIERTO/CERRADO/...)

    load = relationship("Load", backref="apsa_rows")

Index("ix_apsa_core", ApsaProtocol.subsistema, ApsaProtocol.disciplina, ApsaProtocol.status_bim360)
