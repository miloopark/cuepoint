from cuepoint_api.identify import parse_audd_response


def test_parses_successful_match():
    data = {"status": "success", "result": {"artist": "Some Artist", "title": "Some Track"}}
    assert parse_audd_response(data) == ("Some Artist", "Some Track")


def test_null_result_means_no_match():
    assert parse_audd_response({"status": "success", "result": None}) is None


def test_error_status_means_no_match():
    assert parse_audd_response({"status": "error", "error": {"error_code": 901}}) is None


def test_blank_fields_mean_no_match():
    assert parse_audd_response({"status": "success", "result": {"artist": " ", "title": ""}}) is None
