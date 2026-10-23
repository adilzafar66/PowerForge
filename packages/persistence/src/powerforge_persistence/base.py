"""Single declarative Base shared by all persistence mappings."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
