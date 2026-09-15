"""Provider HTTP boundaries normalize genuine response shapes into Paper."""

import httpx

from litwatch import providers


def test_openalex_normalizes_work_metadata() -> None:
    provider_type = getattr(providers, "OpenAlexProvider", None)
    assert provider_type is not None

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == "underwater acoustic TDOA"
        return httpx.Response(
            200,
            json={
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W123",
                        "title": "Underwater Acoustic TDOA",
                        "doi": "https://doi.org/10.1000/ACOUSTIC",
                        "publication_year": 2026,
                        "authorships": [
                            {"author": {"display_name": "Ada Researcher"}, "author_position": "first"}
                        ],
                        "abstract_inverted_index": {"Underwater": [0], "acoustic": [1], "TDOA": [2]},
                        "primary_location": {"landing_page_url": "https://example.org/work"},
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = provider_type(client=client).search("underwater acoustic TDOA", 5)

    assert len(records) == 1
    assert records[0].title == "Underwater Acoustic TDOA"
    assert records[0].authors == ["Ada Researcher"]
    assert records[0].abstract == "Underwater acoustic TDOA"
    assert records[0].doi == "10.1000/acoustic"
    assert records[0].year == 2026
    assert records[0].provider_id == "W123"
    assert records[0].providers == ["openalex"]
    assert records[0].url == "https://example.org/work"


def test_arxiv_normalizes_atom_entry() -> None:
    provider_type = getattr(providers, "ArxivProvider", None)
    assert provider_type is not None

    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>https://arxiv.org/abs/2401.12345v2</id>
        <title>  Underwater Acoustic\n TDOA Localization  </title>
        <summary> A robust\n localization method. </summary>
        <published>2026-07-01T00:00:00Z</published>
        <author><name>Lin Researcher</name></author>
        <arxiv:doi>10.2000/ACOUSTIC</arxiv:doi>
      </entry>
    </feed>"""

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["max_results"] == "5"
        assert "all:underwater" in request.url.params["search_query"]
        return httpx.Response(200, text=feed)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = provider_type(client=client).search("underwater acoustic TDOA", 5)

    assert len(records) == 1
    assert records[0].title == "Underwater Acoustic TDOA Localization"
    assert records[0].abstract == "A robust localization method."
    assert records[0].authors == ["Lin Researcher"]
    assert records[0].arxiv_id == "2401.12345"
    assert records[0].doi == "10.2000/acoustic"
    assert records[0].year == 2026
    assert records[0].source == "arxiv"
    assert records[0].provider_id == "2401.12345"


def test_crossref_normalizes_work_metadata_and_strips_abstract_markup() -> None:
    provider_type = getattr(providers, "CrossrefProvider", None)
    assert provider_type is not None

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query.bibliographic"] == "underwater acoustic TDOA"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "message": {
                    "items": [
                        {
                            "DOI": "10.3000/ACOUSTIC",
                            "title": ["Underwater Acoustic TDOA"],
                            "abstract": "<jats:p>Robust &amp; accurate.</jats:p>",
                            "author": [{"given": "Marie", "family": "Researcher"}],
                            "issued": {"date-parts": [[2025, 3, 1]]},
                            "URL": "https://doi.org/10.3000/ACOUSTIC",
                        }
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = provider_type(client=client).search("underwater acoustic TDOA", 5)

    assert len(records) == 1
    assert records[0].title == "Underwater Acoustic TDOA"
    assert records[0].abstract == "Robust & accurate."
    assert records[0].authors == ["Marie Researcher"]
    assert records[0].doi == "10.3000/acoustic"
    assert records[0].year == 2025
    assert records[0].source == "crossref"
    assert records[0].provider_id == "10.3000/acoustic"
