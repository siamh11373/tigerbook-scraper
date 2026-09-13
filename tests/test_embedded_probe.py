import json

from tigerbook_scraper.embedded_probe import inspect_embedded, inspect_script


def test_json_blocks_and_assignments():
    result = inspect_embedded(
        '<script type="application/json">{"field":"private"}</script>'
        '<script>window.__STATE__ = {"records":[{"name":"Zoë"}]};</script>'
    )
    assert result["objects"] == [{"field": "private"}, {"records": [{"name": "Zoë"}]}]
    assert result["summary"]["decoded_candidate_count"] == 2
    assert "private" not in json.dumps(result["summary"])
    assert result["summary"]["full_record_verified"] is False


def test_escaped_json_parse_unicode():
    result = inspect_embedded(
        "<script>window.state = "
        r"""JSON.parse('{"name":"Zo\\u00eb","emoji":"\\ud83d\\ude00"}');</script>"""
    )
    assert result["objects"] == [{"name": "Zoë", "emoji": "😀"}]


def test_javascript_unicode_string_escapes():
    result = inspect_embedded(r"""<script>JSON.parse('\u007b"name":"Zo\u00eb"\u007d')</script>""")
    assert result["objects"] == [{"name": "Zoë"}]


def test_malicious_expressions_are_never_executed(tmp_path):
    target = tmp_path / "should-not-exist"
    result = inspect_embedded(
        f"""<script>JSON.parse(__import__('pathlib').Path('{target}').touch());"""
        """window.state = {"a":1} + malicious(); JSON.parse('{"b":2}' + evil());</script>"""
    )
    assert result["objects"] == []
    assert not target.exists()


def test_malformed_and_unsupported_input():
    result = inspect_embedded(
        r"""<script>const a = {bad:true}; JSON.parse('\q'); JSON.parse('oops');</script>"""
    )
    assert result["objects"] == []


def test_hints_never_return_script_or_claim_interfaces():
    result = inspect_script('fetch("/private/person"); batchGet(ids); includeRelated; cursor;')
    assert result["keyword_counts"] == {"batch": 1, "related": 1, "pagination": 1, "graphql": 0}
    assert result["interfaces_confirmed"] is False
    assert "private" not in json.dumps(result)
