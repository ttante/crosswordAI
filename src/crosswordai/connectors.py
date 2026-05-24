"""Source connector interfaces and external metadata connectors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    source_type: str
    title: str
    url_or_path: str
    provider: str
    trust_score: float
    license_or_rights_status: str
    content: str
    raw_metadata: dict[str, object] | None = None


class HttpFetcher(Protocol):
    def fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, object]:
        ...


class UrllibJsonFetcher:
    def fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, object]:
        request = Request(url, headers=headers or {})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))


class SourceConnector:
    source_type = "abstract"

    def fetch(self, theme: str) -> ConnectorResult:
        raise NotImplementedError


class OfflineStubConnector(SourceConnector):
    def __init__(
        self,
        *,
        source_type: str,
        provider: str,
        trust_score: float,
        license_or_rights_status: str = "metadata_only",
    ) -> None:
        self.source_type = source_type
        self.provider = provider
        self.trust_score = trust_score
        self.license_or_rights_status = license_or_rights_status

    def fetch(self, theme: str) -> ConnectorResult:
        return ConnectorResult(
            source_type=self.source_type,
            title=f"{theme} ({self.provider} stub)",
            url_or_path=f"offline://{self.provider}/{theme.replace(' ', '_')}",
            provider=self.provider,
            trust_score=self.trust_score,
            license_or_rights_status=self.license_or_rights_status,
            content=f"Offline metadata stub for {theme} from {self.provider}.",
            raw_metadata={"theme": theme, "offline": True},
        )


class WikipediaConnector(SourceConnector):
    source_type = "wikipedia"

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or UrllibJsonFetcher()

    def fetch(self, theme: str) -> ConnectorResult:
        url = "https://en.wikipedia.org/w/api.php?" + urlencode(
            {
                "action": "query",
                "format": "json",
                "prop": "extracts|info",
                "exintro": "1",
                "explaintext": "1",
                "redirects": "1",
                "inprop": "url",
                "titles": theme,
            }
        )
        payload = self.fetcher.fetch_json(url, headers=_headers())
        pages = _nested_dict(payload, "query", "pages")
        page = next(iter(pages.values())) if pages else {}
        title = str(page.get("title", theme))
        extract = str(page.get("extract", ""))
        page_url = str(page.get("fullurl", url))
        return ConnectorResult(
            source_type=self.source_type,
            title=title,
            url_or_path=page_url,
            provider="wikipedia",
            trust_score=0.75,
            license_or_rights_status="cc-by-sa-summary",
            content=extract or f"Wikipedia page metadata for {title}.",
            raw_metadata=payload,
        )


class WikidataConnector(SourceConnector):
    source_type = "wikidata"

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or UrllibJsonFetcher()

    def fetch(self, theme: str) -> ConnectorResult:
        url = "https://www.wikidata.org/w/api.php?" + urlencode(
            {
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "search": theme,
                "limit": "5",
            }
        )
        payload = self.fetcher.fetch_json(url, headers=_headers())
        search = payload.get("search", [])
        first = search[0] if isinstance(search, list) and search else {}
        label = str(first.get("label", theme)) if isinstance(first, dict) else theme
        description = str(first.get("description", "")) if isinstance(first, dict) else ""
        entity_id = str(first.get("id", "")) if isinstance(first, dict) else ""
        content = f"{label}. {description}".strip()
        if entity_id:
            content = f"{content} Wikidata entity: {entity_id}."
        return ConnectorResult(
            source_type=self.source_type,
            title=label,
            url_or_path=f"https://www.wikidata.org/wiki/{entity_id}" if entity_id else url,
            provider="wikidata",
            trust_score=0.85,
            license_or_rights_status="cc0-metadata",
            content=content or f"Wikidata metadata for {theme}.",
            raw_metadata=payload,
        )


class MusicBrainzConnector(SourceConnector):
    source_type = "musicbrainz"

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or UrllibJsonFetcher()

    def fetch(self, theme: str) -> ConnectorResult:
        url = "https://musicbrainz.org/ws/2/artist/?" + urlencode(
            {
                "query": theme,
                "fmt": "json",
                "limit": "5",
            }
        )
        payload = self.fetcher.fetch_json(url, headers=_headers())
        artists = payload.get("artists", [])
        first = artists[0] if isinstance(artists, list) and artists else {}
        name = str(first.get("name", theme)) if isinstance(first, dict) else theme
        artist_id = str(first.get("id", "")) if isinstance(first, dict) else ""
        disambiguation = str(first.get("disambiguation", "")) if isinstance(first, dict) else ""
        tags = first.get("tags", []) if isinstance(first, dict) else []
        tag_names = ", ".join(str(tag.get("name")) for tag in tags if isinstance(tag, dict) and tag.get("name"))
        content_parts = [name, disambiguation, f"MusicBrainz artist: {artist_id}" if artist_id else "", f"Tags: {tag_names}" if tag_names else ""]
        return ConnectorResult(
            source_type=self.source_type,
            title=name,
            url_or_path=f"https://musicbrainz.org/artist/{artist_id}" if artist_id else url,
            provider="musicbrainz",
            trust_score=0.85,
            license_or_rights_status="open-metadata",
            content=". ".join(part for part in content_parts if part),
            raw_metadata=payload,
        )


class OpenLibraryConnector(SourceConnector):
    source_type = "openlibrary"

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or UrllibJsonFetcher()

    def fetch(self, theme: str) -> ConnectorResult:
        url = "https://openlibrary.org/search.json?" + urlencode({"q": theme, "limit": "5"})
        payload = self.fetcher.fetch_json(url, headers=_headers())
        docs = payload.get("docs", [])
        first = docs[0] if isinstance(docs, list) and docs else {}
        title = str(first.get("title", theme)) if isinstance(first, dict) else theme
        authors = ", ".join(str(author) for author in first.get("author_name", [])[:3]) if isinstance(first, dict) else ""
        key = str(first.get("key", "")) if isinstance(first, dict) else ""
        content = f"{title}. Authors: {authors}. OpenLibrary key: {key}."
        return ConnectorResult(
            source_type=self.source_type,
            title=title,
            url_or_path=f"https://openlibrary.org{key}" if key else url,
            provider="openlibrary",
            trust_score=0.8,
            license_or_rights_status="open-metadata",
            content=content,
            raw_metadata=payload,
        )


def default_connectors(*, offline: bool = False) -> dict[str, SourceConnector]:
    if offline:
        return offline_connectors()
    return {
        "wikipedia": WikipediaConnector(),
        "wikidata": WikidataConnector(),
        "musicbrainz": MusicBrainzConnector(),
        "openlibrary": OpenLibraryConnector(),
    }


def offline_connectors() -> dict[str, SourceConnector]:
    return {
        "wikipedia": OfflineStubConnector(source_type="wikipedia", provider="wikipedia", trust_score=0.75),
        "wikidata": OfflineStubConnector(source_type="wikidata", provider="wikidata", trust_score=0.85),
        "musicbrainz": OfflineStubConnector(source_type="musicbrainz", provider="musicbrainz", trust_score=0.85),
        "openlibrary": OfflineStubConnector(source_type="openlibrary", provider="openlibrary", trust_score=0.8),
    }


def _headers() -> dict[str, str]:
    return {"User-Agent": "crosswordai/0.1.0 (local research tool)"}


def _nested_dict(payload: dict[str, object], *keys: str) -> dict[str, object]:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}
