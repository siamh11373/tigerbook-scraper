from tigerbook_scraper.html_probe import compare_html


def test_html_shell_does_not_pass_as_complete():
    result = compare_html('<div id="app"></div><script src="app.js"></script>', {"Name": "Person"})
    assert result["missing_field_labels"] == ["Name"]
    assert not result["full_record_verified"]


def test_json_unicode_repeated_records_and_html_entities():
    html = '<p>A &amp; B</p><script type="application/json">{"city":"\\u6771\\u4eac"}</script>'
    result = compare_html(html, {"Name": "A & B", "Jobs": [{"city": "東京"}, {"city": "Paris"}]})
    assert result["fields_with_all_string_values_present"] == 1
    assert result["missing_field_labels"] == ["Jobs"]
    assert result["standalone_json_blocks"] == 1


def test_all_values_present_is_only_a_candidate():
    result = compare_html("<p>Synthetic</p>", {"Name": "Synthetic"})
    assert result["conclusion"] == "needs_structural_validation"
    assert not result["full_record_verified"]
