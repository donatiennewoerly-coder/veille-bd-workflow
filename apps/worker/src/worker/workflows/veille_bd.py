"""Veille mensuelle : adaptations d'œuvres littéraires francophones en bande dessinée.

Chaque exécution recherche sur le web les adaptations (annonces, parutions, projets)
publiées pendant la période, puis ajoute les nouvelles lignes à une Google Sheet
unique, créée au premier run. Prévu pour tourner sans utilisateur (schedule) :
l'accès Google Drive se fait par un compte de service dont la clé est rangée
dans le secret workspace ``GOOGLE_SERVICE_ACCOUNT_KEY``.
"""

import calendar
import csv
import io
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pydantic
from mistralai import workflows
from mistralai.workflows.plugins.mistralai import Agent, RemoteSession, Runner

SHEET_TITLE = "Veille adaptations littérature francophone en BD"
CSV_COLUMNS = [
    "periode",
    "oeuvre",
    "auteur_oeuvre",
    "titre_bd",
    "adaptateurs",
    "editeur",
    "date_evenement",
    "statut",
    "langue_pays",
    "resume",
    "source_url",
    "date_ajout",
]
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class VeilleInput(pydantic.BaseModel):
    period_start: str | None = pydantic.Field(
        default=None,
        description="Début de période ISO (AAAA-MM-JJ) ; défaut : début du mois précédent",
    )
    period_end: str | None = pydantic.Field(
        default=None,
        description="Fin de période ISO (AAAA-MM-JJ) ; défaut : fin du mois précédent",
    )
    dry_run: bool = pydantic.Field(
        default=False, description="Si vrai, recherche sans écrire dans la Google Sheet"
    )


class VeilleItem(pydantic.BaseModel):
    oeuvre: str = pydantic.Field(description="Œuvre littéraire source (titre)")
    auteur_oeuvre: str = pydantic.Field(
        default="", description="Auteur de l'œuvre source"
    )
    titre_bd: str = pydantic.Field(
        default="", description="Titre de la BD / adaptation"
    )
    adaptateurs: str = pydantic.Field(
        default="", description="Scénariste et dessinateur de la BD"
    )
    editeur: str = pydantic.Field(default="", description="Éditeur de la BD")
    date_evenement: str = pydantic.Field(
        default="", description="Date d'annonce ou de parution"
    )
    statut: str = pydantic.Field(default="", description="annoncé / en cours / paru")
    langue_pays: str = pydantic.Field(
        default="", description="Langue et pays concernés"
    )
    resume: str = pydantic.Field(default="", description="Résumé en 1-2 phrases")
    source_url: str = pydantic.Field(default="", description="URL de la source")


class VeilleOutput(pydantic.BaseModel):
    period_start: str
    period_end: str
    new_items_count: int
    total_rows: int
    sheet_url: str | None
    dry_run: bool
    items: list[VeilleItem]


def previous_month(today: Any) -> tuple[int, int]:
    year, month = today.year, today.month
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_bounds(year: int, month: int) -> tuple[str, str]:
    start = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start, end


def csv_escape(value: str) -> str:
    if any(ch in value for ch in (",", '"', "\n", "\r")):
        return '"' + value.replace('"', '""') + '"'
    return value


def rows_to_csv(rows: list[list[str]]) -> str:
    return "\n".join(",".join(csv_escape(cell) for cell in row) for row in rows) + "\n"


def csv_to_rows(content: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(content))
    return [list(row) for row in reader]


def item_key(row: list[str], columns: list[str]) -> tuple[str, ...]:
    def cell(name: str) -> str:
        return (
            row[columns.index(name)].strip().lower()
            if name in columns and columns.index(name) < len(row)
            else ""
        )

    return (cell("source_url"), cell("titre_bd"), cell("oeuvre"))


def filter_new_items(
    existing_rows: list[list[str]], items: list[VeilleItem]
) -> list[VeilleItem]:
    seen = {item_key(row, CSV_COLUMNS) for row in existing_rows[1:]}
    new_items: list[VeilleItem] = []
    for item in items:
        key = (
            item.source_url.strip().lower(),
            item.titre_bd.strip().lower(),
            item.oeuvre.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        new_items.append(item)
    return new_items


def extract_json_array(text: str) -> list[dict[str, Any]]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Aucun tableau JSON trouvé dans la réponse de l'agent")
    return json.loads(text[start : end + 1])


RESEARCH_INSTRUCTIONS = """Tu es un agent de veille spécialisé en bande dessinée et littérature francophone.
Ta mission : recenser les adaptations d'œuvres littéraires francophones en bande dessinée
(romans, nouvelles, poésie, théâtre, littérature jeunesse… d'auteurs francophones,
adaptés en BD en français). Inclus : annonces de projets, parutions, rééditions intégrales.
Exclus : mangas, comics non francophones, adaptations vers d'autres médias (film, série).
Utilise la recherche web. Réponds UNIQUEMENT avec un tableau JSON valide, sans texte autour.
Chaque élément : {"oeuvre", "auteur_oeuvre", "titre_bd", "adaptateurs", "editeur",
"date_evenement", "statut" (annoncé/en cours/paru), "langue_pays", "resume" (1-2 phrases),
"source_url"}. Si tu ne trouves rien, réponds []."""


@workflows.activity(
    name="veille-bd-recherche", start_to_close_timeout=timedelta(minutes=15)
)
async def run_veille_research(period_start: str, period_end: str) -> list[VeilleItem]:
    import mistralai.client.models

    agent = Agent(
        model="mistral-medium-latest",
        name="veille-bd-adaptations",
        description="Veille sur les adaptations d'œuvres littéraires francophones en BD",
        instructions=RESEARCH_INSTRUCTIONS,
        tools=[mistralai.client.models.WebSearchTool()],
    )
    prompt = (
        f"Recherche les adaptations d'œuvres littéraires francophones en bande dessinée "
        f"annoncées ou publiées entre le {period_start} et le {period_end} "
        f"(annonces d'éditeurs, catalogues, articles de presse spécialisée : ActuaBD, BD Gest', "
        f"BoDoï, Planète BD, éditeurs comme Delcourt, Dargaud, Casterman, Rue de Sèvres, "
        f"Sarbacane, Dupuis, Gallimard BD…). Réponds uniquement avec le tableau JSON."
    )
    outputs = await Runner.run(
        agent=agent, inputs=prompt, session=RemoteSession(), max_turns=25
    )
    import mistralai.client.models as client_models

    text = "\n".join(
        output.text for output in outputs if isinstance(output, client_models.TextChunk)
    )
    raw_items = extract_json_array(text)
    return [VeilleItem.model_validate(raw) for raw in raw_items]


def _service_account_credentials() -> dict[str, str]:
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Secret GOOGLE_SERVICE_ACCOUNT_KEY absent : ajoutez la clé JSON du compte de service "
            "en secret workspace et liez-la au déploiement."
        )
    return json.loads(key)


async def _access_token() -> str:
    import httpx
    import jwt

    creds = _service_account_credentials()
    issued_at = int(datetime.now(tz=UTC).timestamp())
    assertion = jwt.encode(
        {
            "iss": creds["client_email"],
            "scope": DRIVE_SCOPE,
            "aud": TOKEN_URL,
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        creds["private_key"],
        algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]


def _share_email() -> str:
    return os.environ.get("VEILLE_SHEET_SHARE_EMAIL", "").strip()


@workflows.activity(
    name="veille-bd-sheet-sync",
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy_max_attempts=1,
)
async def sync_sheet(
    items: list[VeilleItem], period_start: str, period_end: str, added_at: str
) -> dict[str, Any]:
    import httpx

    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60) as client:
        query = f"name = '{SHEET_TITLE}' and trashed = false"
        response = await client.get(
            DRIVE_FILES_URL,
            headers=headers,
            params={"q": query, "fields": "files(id,webViewLink)"},
        )
        response.raise_for_status()
        files = response.json().get("files", [])

        if files:
            file_id = files[0]["id"]
            export = await client.get(
                f"{DRIVE_FILES_URL}/{file_id}/export",
                headers=headers,
                params={"mimeType": "text/csv"},
            )
            export.raise_for_status()
            content = export.content.decode("utf-8")
            existing_rows = csv_to_rows(content)
        else:
            file_id = None
            existing_rows = [list(CSV_COLUMNS)]

        new_items = filter_new_items(existing_rows, items)
        new_rows = [
            [
                f"{period_start} → {period_end}",
                item.oeuvre,
                item.auteur_oeuvre,
                item.titre_bd,
                item.adaptateurs,
                item.editeur,
                item.date_evenement,
                item.statut,
                item.langue_pays,
                item.resume,
                item.source_url,
                added_at,
            ]
            for item in new_items
        ]
        full_csv = rows_to_csv(existing_rows + new_rows)

        if file_id is None:
            boundary = "veille-bd-" + uuid.uuid4().hex
            metadata = json.dumps(
                {
                    "name": SHEET_TITLE,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                }
            )
            body = (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{metadata}\r\n"
                f"--{boundary}\r\n"
                "Content-Type: text/csv\r\n\r\n"
                f"{full_csv}\r\n"
                f"--{boundary}--"
            )
            create = await client.post(
                DRIVE_UPLOAD_URL,
                headers={
                    **headers,
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                params={"uploadType": "multipart", "fields": "id,webViewLink"},
                content=body.encode("utf-8"),
            )
            create.raise_for_status()
            created = create.json()
            file_id = created["id"]
            sheet_url = created.get("webViewLink")
            if _share_email():
                permission = await client.post(
                    f"{DRIVE_FILES_URL}/{file_id}/permissions",
                    headers=headers,
                    json={
                        "role": "writer",
                        "type": "user",
                        "emailAddress": _share_email(),
                    },
                )
                permission.raise_for_status()
        else:
            update = await client.patch(
                f"{DRIVE_UPLOAD_URL}/{file_id}",
                headers={**headers, "Content-Type": "text/csv"},
                params={"uploadType": "media", "fields": "webViewLink"},
                content=full_csv.encode("utf-8"),
            )
            update.raise_for_status()
            sheet_url = update.json().get("webViewLink")

        return {
            "new_items_count": len(new_items),
            "total_rows": len(existing_rows) + len(new_rows),
            "sheet_url": sheet_url,
            "file_id": file_id,
        }


@workflows.workflow.define(name="veille-bd-mensuelle")
class VeilleBDMensuelle:
    @workflows.workflow.entrypoint
    async def run(self, data: VeilleInput) -> VeilleOutput:
        if data.period_start and data.period_end:
            period_start, period_end = data.period_start, data.period_end
        else:
            today = workflows.workflow.now().astimezone(UTC).date()
            year, month = previous_month(today)
            period_start, period_end = month_bounds(year, month)

        items = await run_veille_research(period_start, period_end)
        added_at = workflows.workflow.now().astimezone(UTC).date().isoformat()

        if data.dry_run:
            return VeilleOutput(
                period_start=period_start,
                period_end=period_end,
                new_items_count=len(items),
                total_rows=0,
                sheet_url=None,
                dry_run=True,
                items=items,
            )

        result = await sync_sheet(items, period_start, period_end, added_at)
        return VeilleOutput(
            period_start=period_start,
            period_end=period_end,
            new_items_count=result["new_items_count"],
            total_rows=result["total_rows"],
            sheet_url=result["sheet_url"],
            dry_run=False,
            items=items,
        )
