"""The schema files in sql/ must cover every column the app actually reads and writes.

sql/create_bioassay_results.sql and sql/create_clinical_case_data.sql are reconstructions:
both tables were created by hand in the Supabase dashboard before the files existed, so
the files were derived from the app's own reads and writes. That makes them easy to drift
out of date — add a field to an insert payload and the migration silently stops matching,
and a fresh database gets a table the app cannot write to.

So the check is mechanical: parse the insert payloads out of data_manager with `ast`, parse
the DDL with PostgreSQL's own parser via pglast, and require the columns to line up. No
database connection needed, and nothing here asserts anything about the *live* tables —
those may legitimately differ, which is why each file ends with a query to diff them.
"""
import ast
import pathlib

import pglast
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SQL = REPO / "sql"

# Columns the database fills in, so an insert payload never mentions them.
_DB_MANAGED = {"id", "created_at", "updated_at"}

TABLES = {
    "bioassay_results": {
        "ddl": "create_bioassay_results.sql",
        "writer": "submit_bioassay_result",
        # Read by consumers but not written by the insert: ordering/aggregation columns.
        "read_only": {"created_at"},
    },
    "clinical_case_data": {
        "ddl": "create_clinical_case_data.sql",
        "writer": "submit_clinical_case_record",
        "read_only": {"created_at"},
    },
}


def _ddl_columns(filename: str, table: str) -> set[str]:
    """Column names from the `create table` for `table`, plus any `add column` statements.

    Uses pglast (the real PostgreSQL grammar) rather than a regex, so a file that does not
    parse fails here instead of at 2am in the SQL Editor.
    """
    sql = (SQL / filename).read_text(encoding="utf-8")
    columns: set[str] = set()

    for raw in pglast.parse_sql(sql):
        stmt = raw.stmt
        if isinstance(stmt, pglast.ast.CreateStmt):
            if stmt.relation.relname != table:
                continue
            for element in stmt.tableElts or ():
                if isinstance(element, pglast.ast.ColumnDef) and element.colname:
                    columns.add(element.colname)
        elif isinstance(stmt, pglast.ast.AlterTableStmt):
            if stmt.relation.relname != table:
                continue
            for cmd in stmt.cmds or ():
                definition = getattr(cmd, "def_", None)
                if isinstance(definition, pglast.ast.ColumnDef) and definition.colname:
                    columns.add(definition.colname)
    return columns


def _written_columns(function_name: str) -> set[str]:
    """The keys of the dict literal assigned to `record` inside a data_manager function.

    Both writers build `record = {...}` and hand it straight to .insert(), so the literal's
    keys are exactly the columns the app writes.
    """
    source = (REPO / "utils" / "data_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.Assign):
                continue
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if "record" in targets and isinstance(stmt.value, ast.Dict):
                return {
                    key.value for key in stmt.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
        raise AssertionError(f"no `record = {{...}}` literal found in {function_name}")
    raise AssertionError(f"{function_name} not found in utils/data_manager.py")


class TestEverySqlFileParses:
    @pytest.mark.parametrize("path", sorted(SQL.glob("*.sql")), ids=lambda p: p.name)
    def test_postgres_accepts_the_grammar(self, path):
        # pglast wraps the real PostgreSQL parser, so this catches DDL that would only fail
        # once pasted into the SQL Editor — including the RLS/policy statements.
        pglast.parse_sql(path.read_text(encoding="utf-8"))


class TestSchemaCoversWhatTheAppWrites:
    @pytest.mark.parametrize("table", sorted(TABLES))
    def test_no_column_is_written_that_the_schema_lacks(self, table):
        spec = TABLES[table]
        written = _written_columns(spec["writer"])
        declared = _ddl_columns(spec["ddl"], table)

        missing = written - declared
        assert not missing, (
            f"{spec['writer']} writes {sorted(missing)}, which {spec['ddl']} does not "
            "declare — a fresh database would reject every save."
        )

    @pytest.mark.parametrize("table", sorted(TABLES))
    def test_no_column_is_declared_that_nothing_uses(self, table):
        """A column in the migration that nothing writes or reads is either dead weight or
        a sign the writer was changed without the schema."""
        spec = TABLES[table]
        declared = _ddl_columns(spec["ddl"], table)
        accounted = _written_columns(spec["writer"]) | spec["read_only"] | _DB_MANAGED

        assert not declared - accounted, (
            f"{spec['ddl']} declares {sorted(declared - accounted)}, which nothing in the "
            "app writes or reads."
        )

    @pytest.mark.parametrize("table", sorted(TABLES))
    def test_a_key_column_the_delete_helper_recognises_is_declared(self, table):
        """_delete_all_rows discovers the key at runtime from _KEY_CANDIDATES. A fresh
        database built from these files must present one, or its rows are undeletable."""
        from utils.data_manager import _KEY_CANDIDATES

        declared = _ddl_columns(TABLES[table]["ddl"], table)
        assert declared & set(_KEY_CANDIDATES), (
            f"{TABLES[table]['ddl']} declares no column from _KEY_CANDIDATES "
            f"({_KEY_CANDIDATES}), so delete_all_* could never clear this table."
        )

    @pytest.mark.parametrize("table", sorted(TABLES))
    def test_created_at_is_declared(self, table):
        """Both entry pages sort by created_at; without it the page raises on first load."""
        assert "created_at" in _ddl_columns(TABLES[table]["ddl"], table)


class TestReconciliationCoversTheWholeTable:
    """Section 2 of each file re-adds every column via `add column if not exists`, so a
    table that drifted becomes readable. A column present only in the `create table` is
    the gap that leaves an older database broken."""

    @pytest.mark.parametrize("table", sorted(TABLES))
    def test_every_created_column_is_also_reconciled(self, table):
        sql = (SQL / TABLES[table]["ddl"]).read_text(encoding="utf-8")

        created: set[str] = set()
        altered: set[str] = set()
        for raw in pglast.parse_sql(sql):
            stmt = raw.stmt
            if isinstance(stmt, pglast.ast.CreateStmt) and stmt.relation.relname == table:
                for element in stmt.tableElts or ():
                    if isinstance(element, pglast.ast.ColumnDef) and element.colname:
                        created.add(element.colname)
            elif isinstance(stmt, pglast.ast.AlterTableStmt) and stmt.relation.relname == table:
                for cmd in stmt.cmds or ():
                    definition = getattr(cmd, "def_", None)
                    if isinstance(definition, pglast.ast.ColumnDef) and definition.colname:
                        altered.add(definition.colname)

        # The primary key is exempt: you cannot bolt one onto an existing table this way.
        gap = created - altered - {"id"}
        assert not gap, (
            f"{TABLES[table]['ddl']} creates {sorted(gap)} but never re-adds them in the "
            "reconciliation section, so a drifted database stays broken for those columns."
        )
