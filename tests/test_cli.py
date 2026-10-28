"""CLI configuration must retain the local-only server boundary."""

from unittest.mock import Mock

import pytest
import uvicorn

from featureshift import api, cli


@pytest.mark.parametrize("setting,value", [
    ("FEATURESHIFT_HOST", "0.0.0.0"),
    ("FEATURESHIFT_HOST", "example.org"),
    ("FEATURESHIFT_PORT", "not-a-port"),
])
def test_invalid_server_environment_is_rejected_before_startup(
    monkeypatch: pytest.MonkeyPatch, setting: str, value: str,
) -> None:
    monkeypatch.setenv(setting, value)
    engine = Mock()
    server = Mock()
    monkeypatch.setattr(cli, "Engine", engine)
    monkeypatch.setattr(api, "create_app", Mock())
    monkeypatch.setattr(uvicorn, "run", server)

    with pytest.raises(SystemExit) as error:
        cli.main(["serve"])

    assert error.value.code == 2
    engine.assert_not_called()
    server.assert_not_called()


def test_case_listing_does_not_parse_unused_server_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FEATURESHIFT_PORT", "not-a-port")
    assert cli.main(["cases"]) == 0
    assert "selector" in capsys.readouterr().out
