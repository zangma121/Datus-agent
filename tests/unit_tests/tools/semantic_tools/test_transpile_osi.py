"""Spec for the OSI YAML -> Cube JS transpiler (M8).

One model source for all three engines: OSI YAML (consumed natively by dosi
and metricflow) transpiles deterministically into Cube JS so the cube engine
needs no separately authored models.

Mapping decisions (T-D1~T-D3):
- measures: sql=expr verbatim, type = agg mapped (SUM->sum, AVG->average,
  COUNT_DISTINCT->count_distinct); exprs containing arithmetic operators are
  DUAL-EMITTED: aggregate measure (leaf columns wrapped in their OSI agg) plus
  a row-level ``<name>PerRow`` dimension (M5 lesson: highest/lowest questions
  rank per row).
- identifiers[type=PRIMARY] -> primaryKey dimension; the same identifier name
  appearing in 2+ cubes auto-generates belongsTo joins (later cube -> earlier).
- TIME dimensions degrade to plain dimensions (BIRD fake primary time maps
  through untouched).
- description passes through; description is omitted entirely when empty
  (Cube rejects "").
"""

import json
import re

import pytest
import yaml

from datus_semantic_cube.transpile import transpile_dir, transpile_model

FRPM_YAML = """
data_source:
  name: frpm
  description: "FRPM eligibility statistics."
  sql_query: |
    SELECT
      CDSCode,
      "Enrollment (K-12)"       AS enrollment_k12,
      "Free Meal Count (K-12)"  AS free_meal_count_k12
    FROM frpm
  identifiers:
    - name: school
      type: PRIMARY
      expr: CDSCode
  measures:
    - name: enrollment_k12
      agg: SUM
      expr: enrollment_k12
      create_metric: true
    - name: free_meal_count_k12
      agg: SUM
      expr: free_meal_count_k12
      create_metric: true
    - name: school_count
      agg: COUNT_DISTINCT
      expr: CDSCode
      create_metric: true
    - name: free_meal_rate
      agg: SUM
      expr: free_meal_count_k12 / enrollment_k12
      create_metric: true
  dimensions:
    - name: school_name
      expr: "School Name"
      description: "School name."
    - name: report_date
      type: TIME
      expr: "DATE('2013-07-01')"
      type_params:
        is_primary: true
        time_granularity: DAY
  mutability:
    type: FULL_MUTATION
"""


@pytest.fixture
def frpm_yaml():
    return yaml.safe_load(FRPM_YAML)


class TestMeasureMapping:
    def test_agg_maps_to_cube_types(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        assert "type: `sum`" in js
        assert "type: `count_distinct`" in js

    def test_pure_column_expr_no_manual_aggregate(self, frpm_yaml):
        """Cube adds its own aggregate for typed measures — a PURE measure's
        member sql must stay a bare expression (M5 nested-aggregate lesson).
        Numeric aggs get a CAST (strictly-typed backends reject SUM over
        text columns; same shape as the M7 live models)."""
        js = transpile_model(frpm_yaml["data_source"])
        m = re.search(r"enrollmentK12: \{ sql: `([^`]+)`", js)
        assert m, js
        assert m.group(1) == 'CAST("enrollment_k12" AS DOUBLE PRECISION)'

    def test_mixed_case_column_refs_are_quoted(self, frpm_yaml):
        """Unquoted CDSCode folds to lowercase in Postgres and stops
        resolving — bare column refs carry embedded double quotes."""
        js = transpile_model(frpm_yaml["data_source"])
        assert 'sql: `"CDSCode"`' in js
        m = re.search(r"schoolCount: \{ sql: `([^`]+)`", js)
        assert m, js
        assert m.group(1) == '"CDSCode"'

    def test_spaced_dimension_expr_is_quoted(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        assert 'sql: `"School Name"`' in js

    def test_preaggregated_expr_stays_calculated(self, frpm_yaml):
        """An expr already containing an aggregate must not be emitted under
        a type Cube would aggregate again (double-aggregation lesson)."""
        ds = frpm_yaml["data_source"]
        ds["measures"].append({"name": "manual_sum", "agg": "SUM", "expr": "SUM(enrollment_k12)"})
        js = transpile_model(ds)
        assert re.search(r"manualSum: \{ sql: `SUM\(enrollment_k12\)`, type: `number`", js)

    def test_ratio_expr_dual_emitted(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        # aggregate member keeps the OSI name
        assert "freeMealRate: {" in js
        # row-level sibling gets PerRow suffix (per-school ranking member)
        assert "freeMealRatePerRow" in js


class TestDualEmitAggregateLeg:
    """T-D1: the aggregate leg wraps leaf columns in their OSI agg — a ratio
    measure aggregates as ratio-of-sums, not sum-of-ratios (M5-verified
    hand-written shape)."""

    def test_aggregate_leg_is_ratio_of_sums(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        m = re.search(r"freeMealRate: \{ sql: `([^`]+)`", js)
        assert m, js
        sql = m.group(1)
        assert 'SUM(CAST("free_meal_count_k12" AS DOUBLE PRECISION))' in sql
        assert 'SUM(CAST("enrollment_k12" AS DOUBLE PRECISION))' in sql

    def test_aggregate_leg_protects_division_by_zero(self, frpm_yaml):
        """Postgres raises on x/0 — denominators get the NULLIF guard the
        hand-written model carries."""
        js = transpile_model(frpm_yaml["data_source"])
        m = re.search(r"freeMealRate: \{ sql: `([^`]+)`", js)
        assert m, js
        assert 'NULLIF(SUM(CAST("enrollment_k12" AS DOUBLE PRECISION)), 0)' in m.group(1)

    def test_aggregate_leg_type_is_calculated_number(self, frpm_yaml):
        """type: number (calculated) — the OSI agg lives in the wrapped leaves,
        so a count-typed derived measure cannot become a nonsense count."""
        js = transpile_model(frpm_yaml["data_source"])
        assert re.search(r"freeMealRate: \{ sql: `[^`]+`, type: `number`", js)

    def test_perrow_keeps_verbatim_expr(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        m = re.search(r"freeMealRatePerRow: \{ sql: `([^`]+)`", js)
        assert m, js
        assert "SUM(" not in m.group(1)


class TestDimensionsAndIdentifiers:
    def test_primary_identifier_is_pk_dimension(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        assert "primaryKey: true" in js
        assert "CDSCode" in js

    def test_time_dim_degrades_to_plain(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        assert "is_primary_time" not in js
        assert "reportDate" in js

    def test_description_passthrough(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        assert "School name." in js


class TestJoins:
    def test_shared_identifier_generates_belongsto(self, frpm_yaml, tmp_path):
        other_yaml = """
data_source:
  name: schools
  identifiers:
    - name: school
      type: PRIMARY
      expr: CDSCode
  dimensions:
    - name: county
      expr: County
"""
        out = tmp_path / "osi"
        out.mkdir()
        (out / "frpm.yml").write_text(FRPM_YAML)
        (out / "schools.yml").write_text(other_yaml)

        models = transpile_dir(str(out), out_dir=str(tmp_path / "out"))
        by_table = {m["table_name"]: m for m in models}
        assert "join" in by_table["schools"]["js_text"].lower()
        assert "Frpm" in by_table["schools"]["js_text"]


class TestLintAndReport:
    def test_output_passes_lint(self, frpm_yaml):
        from datus_semantic_cube.generate import lint_model_text

        js = transpile_model(frpm_yaml["data_source"])
        ok, issues = lint_model_text(js)
        assert ok, issues

    def test_transpile_dir_writes_report(self, frpm_yaml, tmp_path):
        out = tmp_path / "osi"
        out.mkdir()
        (out / "frpm.yml").write_text(FRPM_YAML)
        models = transpile_dir(str(out), out_dir=str(tmp_path / "out"))
        report = json.loads((tmp_path / "out" / "_generation_report.json").read_text())
        assert report["frpm"]["status"] == "generated"
        assert models

    def test_ignored_sections_reported(self, tmp_path):
        """T-D3: sections the transpiler drops (mutability here, doc-level
        keys generally) are named in the report, never silently lost."""
        out = tmp_path / "osi"
        out.mkdir()
        (out / "frpm.yml").write_text(FRPM_YAML + "\nviews:\n  - name: v\n")
        models = transpile_dir(str(out), out_dir=str(tmp_path / "out"))
        ignored = models[0]["report"]["ignored"]
        assert "mutability" in ignored
        assert "views" in ignored


class TestAliasesAndAggCoverage:
    def test_alias_passthrough_in_description(self, frpm_yaml):
        ds = frpm_yaml["data_source"]
        ds["measures"][2]["aliases"] = ["eligible free rate", "free meal rate"]
        js = transpile_model(ds)
        assert "Aliases: eligible free rate, free meal rate" in js

    def test_avg_maps_to_average(self, frpm_yaml):
        ds = frpm_yaml["data_source"]
        ds["measures"].append({"name": "avg_enrollment", "agg": "AVG", "expr": "enrollment_k12"})
        js = transpile_model(ds)
        assert "type: `average`" in js


class TestMemberCollisions:
    def test_member_name_collision_stays_lint_clean(self, frpm_yaml):
        """Any member-name clash (e.g. a dimension occupying the PerRow slot)
        resolves with a deterministic unique name instead of emitting
        duplicate JS keys."""
        from datus_semantic_cube.generate import lint_model_text

        ds = frpm_yaml["data_source"]
        ds["dimensions"].append({"name": "free_meal_rate_per_row", "expr": "1"})
        js = transpile_model(ds)
        ok, issues = lint_model_text(js)
        assert ok, issues
        assert "freeMealRatePerRow" in js


