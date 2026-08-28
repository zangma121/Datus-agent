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
        """Cube adds its own aggregate for typed measures — the member sql
        must stay a bare expression (M5 nested-aggregate lesson)."""
        js = transpile_model(frpm_yaml["data_source"])
        assert "sum(CAST" not in js
        assert "SUM(CAST" not in js
        assert "enrollment_k12" in js

    def test_ratio_expr_dual_emitted(self, frpm_yaml):
        js = transpile_model(frpm_yaml["data_source"])
        # aggregate member keeps the OSI name
        assert "freeMealRate: {" in js
        # row-level sibling gets PerRow suffix (per-school ranking member)
        assert "freeMealRatePerRow" in js


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


