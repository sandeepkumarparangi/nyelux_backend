"""
Department model for organizational structure.
REAL implementation - no fake data.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from src.db.base_class import Base


class Department(Base):
    """
    Departments within organizations.
    Used for access control and user grouping.
    """
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)  # Department code/abbreviation
    description = Column(String(500), nullable=True)
    
    # Hierarchy
    parent_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    organization = relationship("Organization", back_populates="departments")
    parent_department = relationship("Department", remote_side=[id])
    users = relationship("User", back_populates="department")
    
    def __repr__(self):
        return f"<Department {self.name}>"
