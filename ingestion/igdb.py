"""IGDB game metadata. This source has no sales figures.

Without Twitch client credentials the source is unavailable. Nothing is
invented in its place, and nothing is written to the official fact tables.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ingestion.http import USER_AGENT, get_bytes
from ingestion.records import SourceOutcome

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"


def igdb_outcome(
    retrieved_at: datetime | None = None,
    output_root=None,
) -> SourceOutcome:
    """Return metadata when credentials work, otherwise an unavailable outcome."""

    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    client_id = os.environ.get("NIH_IGDB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NIH_IGDB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return SourceOutcome(
            source_id="igdb_game_metadata",
            source_class="public_reference",
            status="unavailable",
            accepted=0,
            rejected=0,
            missing=0,
            message=(
                "IGDB was not called. Set NIH_IGDB_CLIENT_ID and "
                "NIH_IGDB_CLIENT_SECRET (Twitch application credentials). "
                "No titles or sales were substituted."
            ),
        )
    try:
        import requests

        token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if token_response.status_code >= 400:
            raise RuntimeError(f"Twitch token request returned HTTP {token_response.status_code}")
        token = token_response.json().get("access_token")
        if not token:
            raise RuntimeError("Twitch token response did not include access_token.")
        body = get_bytes(
            GAMES_URL,
            session=_authorized_session(client_id, token),
        )
    except Exception as exc:
        return SourceOutcome(
            source_id="igdb_game_metadata",
            source_class="public_reference",
            status="failed",
            accepted=0,
            rejected=0,
            missing=0,
            message=f"IGDB request failed: {exc}. No metadata was substituted.",
        )
    return _write_metadata(body, retrieved_at, output_root)


class _AuthorizedSession:
    """Small adapter so get_bytes can POST the IGDB query with auth headers."""

    def __init__(self, client_id: str, token: str) -> None:
        self.client_id = client_id
        self.token = token

    def get(self, url, headers, timeout):
        import requests

        response = requests.post(
            url,
            data="fields name,first_release_date; where name != null; limit 20;",
            headers={
                **headers,
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {self.token}",
            },
            timeout=timeout,
        )
        return response

    def close(self) -> None:
        return None


def _authorized_session(client_id: str, token: str) -> _AuthorizedSession:
    return _AuthorizedSession(client_id, token)


def _write_metadata(body: bytes, retrieved_at: datetime, output_root) -> SourceOutcome:
    import json
    from pathlib import Path

    from nih.config import project_root

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return SourceOutcome(
            source_id="igdb_game_metadata",
            source_class="public_reference",
            status="failed",
            accepted=0,
            rejected=0,
            missing=0,
            message=f"IGDB response was not JSON: {exc}",
        )
    if not isinstance(payload, list):
        return SourceOutcome(
            source_id="igdb_game_metadata",
            source_class="public_reference",
            status="failed",
            accepted=0,
            rejected=0,
            missing=0,
            message="IGDB response was not a list of games.",
        )
    root = output_root or (project_root() / "data")
    destination = Path(root) / "cleaned" / "public_reference"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "igdb_games.json"
    records = []
    for item in payload:
        if not isinstance(item, dict) or "name" not in item:
            continue
        records.append(
            {
                "source": "igdb",
                "retrieved_at": retrieved_at.isoformat(),
                "name": item.get("name"),
                "first_release_date": item.get("first_release_date"),
                "sales_units": None,
            }
        )
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return SourceOutcome(
        source_id="igdb_game_metadata",
        source_class="public_reference",
        status="loaded" if records else "failed",
        accepted=len(records),
        rejected=0,
        missing=0,
        message=(
            f"Wrote {len(records)} IGDB metadata rows to {path.name}. "
            "These rows have no sales units and are not official Nintendo disclosures."
            if records
            else "IGDB returned no game names."
        ),
    )
