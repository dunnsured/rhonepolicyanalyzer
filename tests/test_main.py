"""Tests for FastAPI application endpoints."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, _analyses, _analysis_status, _report_r2_paths, _report_paths
from app.models.responses import AnalysisStatusResponse
from app.models.scoring import PolicyAnalysis, PolicyMetadata, ReportSections


@pytest.fixture(autouse=True)
def clear_stores():
    """Clear in-memory stores before each test."""
    _analyses.clear()
    _analysis_status.clear()
    _report_r2_paths.clear()
    _report_paths.clear()
    yield
    _analyses.clear()
    _analysis_status.clear()
    _report_r2_paths.clear()
    _report_paths.clear()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert "knowledge_base_loaded" in data


class TestAnalyzeEndpoint:
    """Tests for POST /api/v1/analyze."""

    def test_analyze_returns_202(self, client):
        """Test that analyze endpoint returns 202 Accepted."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test_policy.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"client_name": "Test Corp", "industry": "Technology"},
        )
        assert response.status_code == 202
        data = response.json()
        assert "analysis_id" in data
        assert data["status"] == "pending"

    def test_analyze_rejects_non_pdf(self, client):
        """Test that non-PDF files are rejected."""
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
            data={"client_name": "Test Corp"},
        )
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_analyze_rejects_oversized_file(self, client):
        """Test that oversized files are rejected."""
        # Create a file larger than the default 50MB limit
        with patch("app.main.get_settings") as mock_settings:
            settings = MagicMock()
            settings.max_upload_bytes = 100  # 100 bytes limit for testing
            settings.max_upload_size_mb = 0
            settings.temp_dir = Path("/tmp/rhone-analyzer-test")
            settings.knowledge_dir = Path(__file__).parent.parent / "app" / "knowledge"
            settings.r2_account_id = ""
            settings.r2_access_key_id = ""
            settings.r2_secret_access_key = ""
            mock_settings.return_value = settings

            response = client.post(
                "/api/v1/analyze",
                files={"file": ("big.pdf", io.BytesIO(b"x" * 200), "application/pdf")},
                data={"client_name": "Test Corp"},
            )
            assert response.status_code == 413

    def test_analyze_creates_status_entry(self, client):
        """Test that submitting an analysis creates a status entry."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test_policy.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"client_name": "Test Corp"},
        )
        analysis_id = response.json()["analysis_id"]
        assert analysis_id in _analysis_status


class TestStatusEndpoint:
    """Tests for GET /api/v1/analyze/{id}/status."""

    def test_status_not_found(self, client):
        """Test 404 for unknown analysis ID."""
        response = client.get("/api/v1/analyze/nonexistent/status")
        assert response.status_code == 404

    def test_status_pending(self, client):
        """Test status returns pending state."""
        _analysis_status["test123"] = AnalysisStatusResponse(
            analysis_id="test123",
            status="pending",
            progress=0,
        )
        response = client.get("/api/v1/analyze/test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["progress"] == 0

    def test_status_in_progress(self, client):
        """Test status returns in-progress state."""
        _analysis_status["test456"] = AnalysisStatusResponse(
            analysis_id="test456",
            status="scoring",
            progress=50,
        )
        response = client.get("/api/v1/analyze/test456/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scoring"
        assert data["progress"] == 50

    def test_status_completed(self, client, sample_analysis):
        """Test status returns completed state with summary."""
        _analysis_status["test123"] = AnalysisStatusResponse(
            analysis_id="test123",
            status="completed",
            progress=100,
        )
        _analyses["test123"] = sample_analysis
        _report_paths["test123"] = Path("/tmp/fake_report.pdf")

        response = client.get("/api/v1/analyze/test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert "overall_score" in data
        assert "report_url" in data

    def test_status_failed(self, client):
        """Test status returns failed state with error."""
        _analysis_status["test789"] = AnalysisStatusResponse(
            analysis_id="test789",
            status="failed",
            progress=0,
            error="Claude API rate limited after 3 retries",
        )
        response = client.get("/api/v1/analyze/test789/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Claude API rate limited after 3 retries"


class TestGetAnalysisEndpoint:
    """Tests for GET /api/v1/analyze/{id}."""

    def test_get_analysis_not_found(self, client):
        """Test 404 for unknown analysis ID."""
        response = client.get("/api/v1/analyze/nonexistent")
        assert response.status_code == 404

    def test_get_analysis_in_progress(self, client):
        """Test 202 for analysis still in progress."""
        _analysis_status["inprogress"] = AnalysisStatusResponse(
            analysis_id="inprogress",
            status="scoring",
            progress=50,
        )
        response = client.get("/api/v1/analyze/inprogress")
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "scoring"

    def test_get_analysis_completed(self, client, sample_analysis):
        """Test full results returned for completed analysis."""
        _analyses["test123"] = sample_analysis
        response = client.get("/api/v1/analyze/test123")
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_id"] == "test123"
        assert data["status"] == "completed"
        assert data["overall_score"] == 6.8
        assert len(data["coverage_scores"]) > 0


class TestReportEndpoint:
    """Tests for GET /api/v1/analyze/{id}/report."""

    def test_report_not_found(self, client):
        """Test 404 for unknown analysis ID."""
        response = client.get("/api/v1/analyze/nonexistent/report", follow_redirects=False)
        assert response.status_code == 404

    def test_report_in_progress(self, client):
        """Test 202 when analysis is still running."""
        _analysis_status["running"] = AnalysisStatusResponse(
            analysis_id="running",
            status="scoring",
            progress=50,
        )
        response = client.get("/api/v1/analyze/running/report", follow_redirects=False)
        assert response.status_code == 202

    def test_report_local_file(self, client, tmp_path):
        """Test local file serving when R2 is not configured."""
        # Create a fake report file
        report_file = tmp_path / "test_report.pdf"
        report_file.write_bytes(b"%PDF-1.4 fake report content")
        _report_paths["test123"] = report_file

        response = client.get("/api/v1/analyze/test123/report", follow_redirects=False)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    @patch("app.main._r2_configured", return_value=True)
    @patch("app.main._get_r2_client")
    def test_report_r2_redirect(self, mock_r2_client, mock_r2_configured, client):
        """Test R2 redirect when R2 is configured."""
        mock_client = MagicMock()
        mock_client.get_signed_url.return_value = "https://r2.example.com/signed-url"
        mock_r2_client.return_value = mock_client
        _report_r2_paths["test123"] = "reports/test123/report.pdf"

        response = client.get("/api/v1/analyze/test123/report", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://r2.example.com/signed-url"
