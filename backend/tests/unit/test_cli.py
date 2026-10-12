"""Unit tests for the CLI (CLI-01)."""

from __future__ import annotations

from unittest.mock import patch

from app.cli import _build_parser, main


class TestParser:
    def test_config_validate(self):
        parser = _build_parser()
        args = parser.parse_args(["config", "validate"])
        assert args.command == "config"
        assert args.config_command == "validate"

    def test_db_migrate(self):
        parser = _build_parser()
        args = parser.parse_args(["db", "migrate"])
        assert args.command == "db"
        assert args.db_command == "migrate"

    def test_db_status(self):
        parser = _build_parser()
        args = parser.parse_args(["db", "status"])
        assert args.command == "db"
        assert args.db_command == "status"

    def test_server(self):
        parser = _build_parser()
        args = parser.parse_args(["server", "--host", "127.0.0.1", "--port", "9000"])
        assert args.command == "server"
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.reload is False

    def test_server_reload(self):
        parser = _build_parser()
        args = parser.parse_args(["server", "--reload"])
        assert args.reload is True

    def test_jobs_search(self):
        parser = _build_parser()
        args = parser.parse_args(["jobs", "search", "data analyst", "--location", "remote", "--limit", "10"])
        assert args.command == "jobs"
        assert args.jobs_command == "search"
        assert args.query == "data analyst"
        assert args.location == "remote"
        assert args.limit == 10

    def test_documents_list(self):
        parser = _build_parser()
        args = parser.parse_args(["documents", "list", "--token", "abc123"])
        assert args.command == "documents"
        assert args.docs_command == "list"
        assert args.token == "abc123"

    def test_health(self):
        parser = _build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"


class TestMain:
    def test_config_validate_success(self):
        with patch("app.cli._cmd_config_validate", return_value=0) as mock:
            result = main(["config", "validate"])
            assert result == 0
            mock.assert_called_once()

    def test_config_validate_failure(self):
        with patch("app.cli._cmd_config_validate", return_value=1) as mock:
            result = main(["config", "validate"])
            assert result == 1
            mock.assert_called_once()

    def test_db_migrate(self):
        with patch("app.cli._cmd_db_migrate", return_value=0) as mock:
            result = main(["db", "migrate"])
            assert result == 0
            mock.assert_called_once()

    def test_db_status(self):
        with patch("app.cli._cmd_db_status", return_value=0) as mock:
            result = main(["db", "status"])
            assert result == 0
            mock.assert_called_once()

    def test_server(self):
        with patch("app.cli._cmd_server", return_value=0) as mock:
            result = main(["server", "--host", "127.0.0.1", "--port", "9000"])
            assert result == 0
            mock.assert_called_once_with("127.0.0.1", 9000, False)

    def test_jobs_search(self):
        with patch("app.cli._cmd_jobs_search", return_value=0) as mock:
            result = main(["jobs", "search", "python", "--limit", "5"])
            assert result == 0
            mock.assert_called_once_with("python", None, 5, 1)

    def test_documents_list(self):
        with patch("app.cli._cmd_documents_list", return_value=0) as mock:
            result = main(["documents", "list", "--token", "abc"])
            assert result == 0
            mock.assert_called_once_with("abc", "http://127.0.0.1:8000")

    def test_health(self):
        with patch("app.cli._cmd_health", return_value=0) as mock:
            result = main(["health"])
            assert result == 0
            mock.assert_called_once_with("http://127.0.0.1:8000")


class TestCmdJobsSearch:
    def test_requires_query(self):
        from app.cli import _cmd_jobs_search

        with patch("app.domain.jobs.service.search_jobs", side_effect=ValueError("query required")):
            result = _cmd_jobs_search("", None, 5, 1)
            assert result == 1

    def test_requires_provider(self):
        from app.cli import _cmd_jobs_search

        with patch("app.domain.jobs.service.search_jobs", side_effect=RuntimeError("no provider")):
            result = _cmd_jobs_search("python", None, 5, 1)
            assert result == 1

    def test_success(self, capsys):
        from app.cli import _cmd_jobs_search

        mock_result = {
            "results": [{"title": "Job"}],
            "count": 1,
            "page": 1,
            "limit": 5,
            "total": 1,
            "audit": {},
        }
        with patch("app.domain.jobs.service.search_jobs", return_value=mock_result):
            result = _cmd_jobs_search("python", None, 5, 1)
            assert result == 0
            captured = capsys.readouterr()
            assert "Job" in captured.out


class TestCmdHealth:
    def test_success(self, capsys):
        from app.cli import _cmd_health

        mock_response = type(
            "Response",
            (),
            {"status_code": 200, "json": staticmethod(lambda: {"status": "ok"})},
        )()
        with patch("app.cli.httpx.get", return_value=mock_response):
            result = _cmd_health("http://test")
            assert result == 0
            captured = capsys.readouterr()
            assert "Healthy" in captured.out

    def test_failure(self):
        from app.cli import _cmd_health

        mock_response = type(
            "Response",
            (),
            {"status_code": 503, "json": staticmethod(lambda: {})},
        )()
        with patch("app.cli.httpx.get", return_value=mock_response):
            result = _cmd_health("http://test")
            assert result == 1

    def test_connection_error(self):
        import httpx

        from app.cli import _cmd_health

        with patch("app.cli.httpx.get", side_effect=httpx.ConnectError("refused")):
            result = _cmd_health("http://test")
            assert result == 1


class TestCmdDocumentsList:
    def test_success(self, capsys):
        from app.cli import _cmd_documents_list

        mock_response = type(
            "Response",
            (),
            {"status_code": 200, "json": staticmethod(lambda: {"items": []})},
        )()
        with patch("app.cli.httpx.get", return_value=mock_response):
            result = _cmd_documents_list("token", "http://test")
            assert result == 0
            captured = capsys.readouterr()
            assert "items" in captured.out

    def test_api_error(self):
        from app.cli import _cmd_documents_list

        mock_response = type(
            "Response",
            (),
            {"status_code": 401, "text": "unauthorized", "json": staticmethod(lambda: {})},
        )()
        with patch("app.cli.httpx.get", return_value=mock_response):
            result = _cmd_documents_list("token", "http://test")
            assert result == 1

    def test_connection_error(self):
        import httpx

        from app.cli import _cmd_documents_list

        with patch("app.cli.httpx.get", side_effect=httpx.ConnectError("refused")):
            result = _cmd_documents_list("token", "http://test")
            assert result == 1


class TestCmdConfigValidate:
    def test_valid(self, capsys):
        from app.cli import _cmd_config_validate

        with patch("app.core.config.validate_runtime_environment", return_value=None):
            result = _cmd_config_validate()
            assert result == 0
            captured = capsys.readouterr()
            assert "valid" in captured.out

    def test_invalid(self):
        from app.cli import _cmd_config_validate

        with patch("app.core.config.validate_runtime_environment", side_effect=RuntimeError("missing")):
            result = _cmd_config_validate()
            assert result == 1


class TestCmdDb:
    def test_migrate(self, capsys):
        from app.cli import _cmd_db_migrate

        result = _cmd_db_migrate()
        assert result == 0
        captured = capsys.readouterr()
        assert "supabase" in captured.out.lower()

    def test_status(self, capsys):
        from app.cli import _cmd_db_status

        result = _cmd_db_status()
        assert result == 0
        captured = capsys.readouterr()
        assert "supabase" in captured.out.lower()
