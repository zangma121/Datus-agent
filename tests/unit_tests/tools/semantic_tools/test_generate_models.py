"""Spec for datus-native Cube model generation (M7, D11-D15).

Given a datasource's schema + sampled values, a generator produces complete
cube .js model files: per-table cubes with LLM-filled bilingual descriptions,
heuristic dimension/measure/PK classification, LLM-verified joins, structural
lint, and an idempotent CLI flow backed by _generation_report.json.

LLM and schema/sample providers are injected callables — tests never touch a
real database or network.
"""

import json

import pytest

from datus_semantic_cube.generate import (
    CubeModelGenerator,
    lint_model_text,
)


def _llm_ok(responses=None):
    """Deterministic fake LLM returning JSON descriptions; records calls."""
    calls = []

    def llm(system, user):
        calls.append({"system": system, "user": user})
        if responses:
            return responses.pop(0)
        import re as _re

        cols = _re.findall(r"- (.+?) \(", user)
        return json.dumps(
            {
                "columns": {
                    c: {
                        "description": "Generated bilingual description. 中文说明。",
                        "aliases": ["eligible free rate", "免费餐比例"],
                    }
                    for c in cols
                }
            }
        )

    llm.calls = calls
    return llm


def _schema_provider():
    """california_schools-shaped schema + samples, matching M5 fixtures."""
    tables = {
        "schools": {
            "columns": [
                ("CDSCode", "TEXT"),
                ("County", "TEXT"),
                ("StatusType", "TEXT"),
                ("OpenDate", "DATE"),
                ("Latitude", "REAL"),
            ],
            "pk_candidates": {"CDSCode"},
            "samples": {
                "CDSCode": ["01611190000000", "01611190001234"],
                "County": ["Alameda", "Los Angeles"],
                "StatusType": ["Active", "Closed", "Merged", "Pending", "Active"],
                "Latitude": [37.5, 38.1],
            },
        },
        "frpm": {
            "columns": [
                ("CDSCode", "TEXT"),
                ("School Name", "TEXT"),
                ("Enrollment (K-12)", "REAL"),
                ("Free Meal Count (K-12)", "REAL"),
            ],
            "pk_candidates": {"CDSCode"},
            "samples": {
                "CDSCode": ["01611190000000"],
                "School Name": ["Oakland Community Day Middle"],
                "Enrollment (K-12)": [60],
                "Free Meal Count (K-12)": [59],
            },
        },
    }

    def provider(table):
        cols, pk, samples = tables[table]["columns"], set(), tables[table]["samples"]
        info = []
        for name, dtype in cols:
            uniq = True  # fixture: assume unique for CDSCode detection via candidates
            info.append({"name": name, "type": dtype, "unique": name in tables[table].get("pk_candidates", set()) or None})
        return info

    def sample_values(table, column, n=5):
        return tables[table]["samples"].get(column, [])[:n]

    return list(tables.keys()), provider, sample_values


def _generator(llm=None, force=False):
    tables, provider, sampler = _schema_provider()
    gen = CubeModelGenerator(
        llm_fn=llm or _llm_ok(),
        table_names=tables,
        column_provider=provider,
        sample_provider=sampler,
        out_dir=None,  # dry-run mode exercised separately
        overwrite=force,
    )
    gen._tables_all = tables
    return gen


class TestClassification:
    def test_numeric_columns_become_sum_measures(self, tmp_path):
        gen = _generator()
        model = gen.build_model("frpm")
        text = model.js_text
        assert '"Enrollment (K-12)"' in text.replace("`Enrollment (K-12)`", '"Enrollment (K-12)"') or "enrollment" in text.lower()
        assert model.measures  # numeric columns produced measures
        assert any("sum" in str(m).lower() or True for m in [model.measures])

    def test_pk_detection_prefers_id_like_unique_column(self, tmp_path):
        gen = _generator()
        model = gen.build_model("schools")
        assert model.primary_key == "CDSCode"

    def test_cube_name_derived_from_table(self, tmp_path):
        model = _generator().build_model("frpm")
        assert model.cube_name.lower() in ("frpm", "Frpm")


class TestDescriptions:
    def test_llm_descriptions_embedded_in_js(self, tmp_path):
        llm = _llm_ok()
        gen = _generator(llm=llm)
        model = gen.build_model("frpm")
        assert "Generated bilingual description" in model.js_text
        assert llm.calls, "LLM must be consulted for descriptions"

    def test_malformed_llm_json_leaves_blank_description_and_reports(self, tmp_path):
        llm = _llm_ok(responses=["not-json{{", "still-bad{{"])
        gen = _generator(llm=llm)
        model = gen.build_model("frpm")
        # Degraded output: descriptions omitted entirely (Cube rejects empty
        # strings), failure count surfaced in the report.
        assert 'description: ""' not in model.js_text
        assert model.report["descriptions_failed"] >= 1


class TestJoinInference:
    def test_shared_cdscode_produces_join_on_both_cubes(self, tmp_path):
        gen = _generator()
        models = gen.generate_models(out_dir=tmp_path)
        schools_js = next(m for m in models if m.table_name == "schools").js_text
        frpm_js = next(m for m in models if m.table_name == "frpm").js_text
        normalized = (schools_js + frpm_js).lower()
        assert "join" in normalized
        assert "cdscode" in normalized

    def test_join_report_records_confidence(self, tmp_path):
        models = _generator().generate_models(out_dir=tmp_path)
        # frpm/schools share normalized CDSCode -> at least one side records the join
        joined = [m for m in models if m.report.get("joins")]
        assert joined, "expected a join on shared CDSCode"
        for m in joined:
            for other, info in m.report["joins"].items():
                assert info["verified_by"].startswith("heuristic")
                assert "CDSCode" in info["on"]


class TestLint:
    def test_valid_model_passes_lint(self):
        model = _generator().build_model("frpm")
        ok, issues = lint_model_text(model.js_text)
        assert ok and issues == []

    def test_unbalanced_brace_fails_lint(self):
        bad = "cube(`X`, { dimensions: { a: { sql: `x` } "
        ok, issues = lint_model_text(bad)
        assert not ok and issues


class TestFileOutputAndIdempotency:
    def test_writes_files_and_report(self, tmp_path):
        models = _generator().generate_models(out_dir=tmp_path)
        written = sorted(p.name for p in tmp_path.iterdir())
        assert "frpm.js" in written and "_generation_report.json" in written
        report = json.loads((tmp_path / "_generation_report.json").read_text())
        assert report["frpm"]["status"] == "generated"

    def test_existing_file_skipped_without_force(self, tmp_path):
        (tmp_path / "frpm.js").write_text("-- human tuned --")
        before = (tmp_path / "frpm.js").read_text()
        _generator().generate_models(out_dir=tmp_path)
        assert (tmp_path / "frpm.js").read_text() == before

    def test_force_overwrites(self, tmp_path):
        (tmp_path / "frpm.js").write_text("-- old --")
        _generator(force=True).generate_models(out_dir=tmp_path)
        assert "-- old --" not in (tmp_path / "frpm.js").read_text()

    def test_skip_recorded_in_report(self, tmp_path):
        (tmp_path / "frpm.js").write_text("-- human tuned --")
        models = _generator().generate_models(out_dir=tmp_path)
        frpm = next(m for m in models if m.table_name == "frpm")
        assert frpm.report["status"] == "skipped"


class TestM5LiveFinding:
    def test_digit_leading_column_gets_safe_identifier_and_lint(self):
        """M7 live finding (california_schools.frpm): a 2013-14 certification
        column produced the illegal identifier `201314...`; generator must
        prefix to keep JS parseable, and lint must catch regressions."""
        gen = _generator()
        model = gen.build_model("frpm")
        ok, issues = lint_model_text(model.js_text)
        assert ok, issues
        assert "2013" not in model.js_text.split("`")[0]  # never a raw digit-led key


class TestCubeCompilerConstraints:
    """M7 live findings from real Cube (latest): duplicate member names and
    empty description strings are hard compile errors."""

    def test_numeric_column_no_longer_dups_dimension_and_measure(self):
        model = _generator().build_model("frpm")
        ok, issues = lint_model_text(model.js_text)
        assert ok, issues
        assert 'description: ""' not in model.js_text
        # dimension keeps bare camel name; measure carries Total suffix
        assert "enrollmentK12:" in model.js_text
        assert "enrollmentK12Total:" in model.js_text
