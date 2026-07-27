from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type_oracle: str | None = None
    type_db2: str | None = None
    not_null: bool = False
    comment: str = ""  # from COMMENT ON COLUMN, verbatim


@dataclass
class Table:
    name: str
    module: str
    comment: str = ""  # from COMMENT ON TABLE, verbatim
    columns: list[Column] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    fks: list[tuple[str, str, str]] = field(default_factory=list)  # (col, ref_table, ref_col)
    indexes: list[tuple[str, list[str], bool]] = field(
        default_factory=list
    )  # (name, cols, unique)
    sequences: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    dialects: set[str] = field(default_factory=set)  # {"oracle","db2"}
    # Repo-relative path(s) this object was actually read from (set by the
    # runner, which knows the real file -- see hivedbparse.run). Empty by
    # default so `emit` can fall back to its module-synthesized path.
    source_files: list[str] = field(default_factory=list)


@dataclass
class PlsqlObject:
    name: str
    module: str
    kind: str  # package|procedure|function|view|trigger
    signature: str = ""
    body_oracle: str = ""  # full source, verbatim
    body_db2: str = ""
    comment: str = ""
    dialects: set[str] = field(default_factory=set)
    source_files: list[str] = field(default_factory=list)
