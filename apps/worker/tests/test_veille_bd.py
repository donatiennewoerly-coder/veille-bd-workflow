import asyncio
from datetime import date, timedelta
from typing import Any

import pytest
from mistralai.workflows.testing import create_test_worker
from worker.workflows import veille_bd
from worker.workflows.veille_bd import (
    CSV_COLUMNS,
    VeilleBDMensuelle,
    VeilleItem,
    csv_to_rows,
    extract_json_array,
    filter_new_items,
    month_bounds,
    previous_month,
    rows_to_csv,
)


def make_item(oeuvre: str, source_url: str, titre_bd: str = "BD") -> VeilleItem:
    return VeilleItem(
        oeuvre=oeuvre,
        auteur_oeuvre="Auteur",
        titre_bd=titre_bd,
        adaptateurs="Dessinateur",
        editeur="Éditeur",
        date_evenement="2025-05-10",
        statut="paru",
        langue_pays="FR",
        resume="Résumé",
        source_url=source_url,
    )


def test_previous_month() -> None:
    assert previous_month(date(2025, 3, 1)) == (2025, 2)
    assert previous_month(date(2025, 1, 15)) == (2024, 12)


def test_month_bounds() -> None:
    assert month_bounds(2025, 2) == ("2025-02-01", "2025-02-28")
    assert month_bounds(2024, 2) == ("2024-02-01", "2024-02-29")


def test_csv_roundtrip_escapes_commas_and_quotes() -> None:
    rows = [list(CSV_COLUMNS), ["a,b", 'He said "hi"', "line\nbreak"]]
    parsed = csv_to_rows(rows_to_csv(rows))
    assert parsed == rows


def test_extract_json_array_tolerates_surrounding_text() -> None:
    text = 'Voici le résultat : [{"oeuvre": "Vipère au poing", "source_url": "https://x.fr"}] Merci.'
    parsed = extract_json_array(text)
    assert parsed[0]["oeuvre"] == "Vipère au poing"


def test_extract_json_array_raises_without_array() -> None:
    with pytest.raises(ValueError):
        extract_json_array("aucun tableau ici")


def test_filter_new_items_dedupes_against_existing_rows() -> None:
    existing = [
        list(CSV_COLUMNS),
        [
            "p",
            "Vipère au poing",
            "Hervé Bazin",
            "BD1",
            "",
            "",
            "",
            "",
            "",
            "",
            "https://x.fr",
            "2025-05-01",
        ],
    ]
    items = [
        make_item("Vipère au poing", "https://x.fr", "BD1"),
        make_item("Bel-Ami", "https://y.fr", "BD2"),
        make_item("Bel-Ami", "https://y.fr", "BD2"),
    ]
    new = filter_new_items(existing, items)
    assert len(new) == 1
    assert new[0].oeuvre == "Bel-Ami"


@pytest.mark.asyncio
async def test_workflow_dry_run_uses_previous_month(
    monkeypatch: Any, temporal_env: Any
) -> None:
    research_calls: list[tuple[str, str]] = []

    @veille_bd.workflows.activity(name="veille-bd-recherche")
    async def stub_research(period_start: str, period_end: str) -> list[VeilleItem]:
        research_calls.append((period_start, period_end))
        return [make_item("Bel-Ami", "https://y.fr", "BD2")]

    async def stub_sync(
        items: list[VeilleItem], period_start: str, period_end: str, added_at: str
    ) -> dict:
        raise AssertionError("dry_run ne doit pas écrire dans la Google Sheet")

    monkeypatch.setattr(veille_bd, "run_veille_research", stub_research)
    monkeypatch.setattr(veille_bd, "sync_sheet", stub_sync)

    async with create_test_worker(
        temporal_env,
        workflows=[VeilleBDMensuelle],
        activities=[stub_research],
    ):
        handle = await temporal_env.client.start_workflow(
            "veille-bd-mensuelle",
            {"dry_run": True},
            id="test-veille-bd-dry-run",
            task_queue="test-task-queue",
            execution_timeout=timedelta(seconds=10),
        )
        result = await asyncio.wait_for(handle.result(), timeout=15)

    today = date.today()
    year, month = previous_month(today)
    start, end = month_bounds(year, month)
    assert research_calls == [(start, end)]
    assert result["dry_run"] is True
    assert result["new_items_count"] == 1
    assert result["items"][0]["oeuvre"] == "Bel-Ami"
    assert result["sheet_url"] is None
