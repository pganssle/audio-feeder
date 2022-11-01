"""Types common between database_handler and sql_database_handler.

This exists for compatibility while the old database_handler code still exists.
"""
import typing

from . import object_handler as oh

ID = typing.NewType("ID", int)
Table = typing.Mapping[ID, oh.BaseObject]
