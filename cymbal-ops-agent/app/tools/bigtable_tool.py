"""Cloud Bigtable MCP Microservice Toolset for Cymbal Operations Agent.

Integrates with the GCP Database Toolbox MCP microservice deployed on Cloud Run
to query live cashier metrics and audit status flags from Cloud Bigtable.
"""

import os
import subprocess
from typing import Optional
import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StreamableHTTPConnectionParams

BIGTABLE_MCP_URL = os.getenv(
    "BIGTABLE_MCP_URL",
    "https://mcp-toolbox-bigtable-kkde7j4k3a-uc.a.run.app"
).rstrip("/")

SERVICE_ACCOUNT = os.getenv(
    "BIGTABLE_MCP_SERVICE_ACCOUNT",
    "cymbal-sa-data@vic-data-elevate.iam.gserviceaccount.com"
)


def get_oidc_token(audience: Optional[str] = None) -> str:
    """Generate GCP OIDC ID Token for the Cloud Run MCP microservice audience.

    Attempts standard authentication paths:
    1. Pure Python IAM service account impersonation (local development).
    2. Direct compute engine / Cloud Run metadata service fetch (production).
    3. gcloud CLI subprocess impersonation fallback.
    4. gcloud CLI direct print-identity-token fallback.

    Args:
        audience: The target audience URL (Cloud Run service URL).

    Returns:
        OIDC ID token string.
    """
    target_audience = audience or BIGTABLE_MCP_URL

    # 1. Pure Python service account impersonation
    try:
        source_creds, _ = google.auth.default()
        target_creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=SERVICE_ACCOUNT,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=3600,
        )
        id_creds = impersonated_credentials.IDTokenCredentials(
            target_credentials=target_creds,
            target_audience=target_audience,
            include_email=True,
        )
        id_creds.refresh(Request())
        if id_creds.token:
            return id_creds.token
    except Exception:
        pass

    # 2. Direct fetch (when deployed in Cloud Run with attached SA)
    try:
        token = id_token.fetch_id_token(Request(), target_audience)
        if token:
            return token
    except Exception:
        pass

    # 3. gcloud CLI impersonation
    try:
        token = subprocess.check_output(
            [
                "gcloud",
                "auth",
                "print-identity-token",
                f"--impersonate-service-account={SERVICE_ACCOUNT}",
                f"--audiences={target_audience}",
            ],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip().split("\n")[-1]
        if token:
            return token
    except Exception:
        pass

    # 4. gcloud CLI direct identity token
    try:
        token = subprocess.check_output(
            [
                "gcloud",
                "auth",
                "print-identity-token",
                f"--audiences={target_audience}",
            ],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip().split("\n")[-1]
        if token:
            return token
    except Exception:
        pass

    return ""


def create_bigtable_mcp_toolset(
    url: Optional[str] = None,
) -> McpToolset:
    """Create an McpToolset instance connected to Cloud Bigtable microservice.

    Args:
        url: Cloud Run service URL.

    Returns:
        Configured ADK McpToolset instance.
    """
    target_url = (url or BIGTABLE_MCP_URL).rstrip("/")
    token = get_oidc_token(target_url)

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    connection_params = StreamableHTTPConnectionParams(
        url=f"{target_url}/mcp",
        headers=headers,
    )
    return McpToolset(connection_params=connection_params)


# Module-level toolset instance ready for agent binding
bigtable_mcp_toolset = create_bigtable_mcp_toolset()

__all__ = [
    "bigtable_mcp_toolset",
    "create_bigtable_mcp_toolset",
    "get_oidc_token",
    "BIGTABLE_MCP_URL",
]
