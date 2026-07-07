# OpenWebUI RetentionGuard

> **⚠️ Öffentliche Version / Public Version**
>
> Dies ist die öffentliche Version dieses Repositories. Sämtliche Verweise auf Secrets, interne Hostnamen, Proxy-Adressen, Zertifikatspfade und sonstige Infrastruktur des Kantons Aargau wurden durch `#[.....]` ersetzt.
>
> This is the public version of this repository. All references to secrets, internal hostnames, proxy addresses, certificate paths, and other infrastructure of the Canton of Aargau have been replaced with `#[.....]`.

---

## Überblick / Overview

**RetentionGuard** ist ein automatisierter, auditierbarer Bereinigungsdienst für [Open WebUI](https://github.com/open-webui/open-webui). Er gleicht Benutzerdaten zwischen der OpenWebUI-PostgreSQL-Datenbank und einem MDM-System (Master Data Management) ab und löscht inaktive Benutzer, verwaiste Chats und verwaiste Dateien nach konfigurierbaren Retention-Regeln.

**RetentionGuard** is an automated, auditable cleanup service for [Open WebUI](https://github.com/open-webui/open-webui). It reconciles user data between the OpenWebUI PostgreSQL database and an MDM (Master Data Management) system, then deletes inactive users, orphaned chats, and orphaned files according to configurable retention rules.

---

## Features

- **Benutzerbereinigung / User Cleanup**: Löscht Benutzer, die im MDM inaktiv sind (Austritt), kein MDM-Konto haben oder als "pending" zu lange inaktiv waren.
- **Chat-Bereinigung / Chat Cleanup**: Entfernt alte, nicht archivierte und nicht angepinnte Chats, die keinem Ordner zugeordnet sind.
- **Datei-Bereinigung / File Cleanup**: Löscht verwaiste Dateien, die von keinem Chat, keiner Knowledge Base und keinem Channel referenziert werden.
- **Dry-Run-Modus**: Standardmässig aktiviert – simuliert Löschungen ohne tatsächliche Änderungen.
- **Sicherheitsschwellwerte / Safety Thresholds**: Erzwingt automatisch den Dry-Run-Modus, wenn die Anzahl der Löschungen einen konfigurierbaren Schwellwert übersteigt.
- **Audit-Logging**: Speichert alle Batch-Ausführungen und gelöschte Benutzer in einer separaten Analytics-Datenbank.
- **CSV-Export**: Optionale Ausgabe von Benutzerberichten als CSV-Dateien.

---

## Architektur / Architecture

```
┌─────────────────┐     ┌────────────────┐     ┌──────────────────┐
│  OpenWebUI API  │◄────│ RetentionGuard │────►│  MDM API         │
│  (REST)         │     │  (Python)      │     │  (REST)          │
└─────────────────┘     └───────┬────────┘     └──────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
          ┌─────────────┐ ┌─────────┐ ┌──────────────┐
          │ OpenWebUI DB│ │Analytics│ │ CSV Outputs  │
          │ (PostgreSQL)│ │   DB    │ │ (optional)   │
          └─────────────┘ └─────────┘ └──────────────┘
```

---

## Projektstruktur / Project Structure

| Datei / File | Beschreibung / Description |
|---|---|
| `main.py` | Einstiegspunkt – orchestriert den gesamten Retention-Workflow |
| `openwebui_handler.py` | Kommunikation mit der OpenWebUI REST API (Benutzer abrufen/löschen) |
| `mdm_handler.py` | Abfrage des MDM-Systems zur Ermittlung des Benutzerstatus |
| `chat_handler.py` | Erkennung und Löschung alter, nicht archivierter Chats |
| `file_handler.py` | Erkennung und Löschung verwaister Dateien |
| `postgres_handler.py` | Direkte PostgreSQL-Abfragen (Benutzer-Emails) |
| `db_handler.py` | Schreibt Audit-Daten in die Analytics-Datenbank |
| `create_db.py` | Erstellt die benötigten Tabellen in der Analytics-Datenbank |
| `logging_utils.py` | Logging-Konfiguration |
| `analyse.py` | Hilfsskript zur CSV-Analyse |
| `Dockerfile` | Container-Build-Definition |
| `pyproject.toml` | Python-Projektdefinition und Abhängigkeiten |
| `k8s/` | Kubernetes-Manifeste (CronJob, Secret) |
| `env/` | Hilfsskripte für CI/CD-Variablen-Management |
| `CICD.md` | CI/CD-Dokumentation |
| `GITLAB_SETUP.md` | GitLab-Setup-Anleitung |

---

## Löschlogik / Deletion Logic

Ein Benutzer wird zur Löschung markiert, wenn **mindestens eine** der folgenden Bedingungen zutrifft:

1. **Kein aktives MDM-Konto**: `count < 1` UND `austrittsdatum` liegt vor dem Schwellwert (`DELETE_AFTER_DAYS_INACTIVE` Tage).
2. **Kein MDM-Konto vorhanden**: `count < 1` UND kein `austrittsdatum` vorhanden UND letzte Aktivität älter als `DELETE_AFTER_DAYS_INACTIVE` Tage.
3. **Pending-Benutzer inaktiv**: Rolle = `pending` UND letzte Aktivität älter als `DELETE_AFTER_DAYS_INACTIVE` Tage.

Chats werden gelöscht, wenn sie:
- Nicht archiviert, nicht angepinnt und keinem Ordner zugeordnet sind
- Älter als `DELETE_CHATS_OLDER_THAN_DAYS` Tage sind

Dateien werden gelöscht, wenn sie:
- Von keinem Chat, keiner Knowledge Base und keinem Channel referenziert werden
- Älter als `DELETE_FILES_OLDER_THAN_DAYS` Tage sind

---

## Konfiguration / Configuration

Die Konfiguration erfolgt über Umgebungsvariablen (`.env`-Datei):

### Datenbank-Verbindungen / Database Connections

| Variable | Beschreibung |
|---|---|
| `SOURCE_DB_NAME` | OpenWebUI-Datenbankname |
| `CONF_DB_NAME` | PostgreSQL-Datenbankname (Benutzer-Emails) |
| `CONF_DB_USER` | DB-Benutzer (Quelle) |
| `CONF_DB_USER_PASSWORD` | DB-Passwort (Quelle) |
| `CONF_DB_HOST` | DB-Host (Quelle) |
| `CONF_DB_PORT` | DB-Port (Quelle) |
| `TARGET_DB_HOST` | Analytics-DB-Host |
| `TARGET_DB_PORT` | Analytics-DB-Port |
| `TARGET_DB_NAME` | Analytics-DB-Name |
| `TARGET_DB_USER` | Analytics-DB-Benutzer |
| `TARGET_DB_PASSWORD` | Analytics-DB-Passwort |

### API-Verbindungen / API Connections

| Variable | Beschreibung |
|---|---|
| `OPENAI_API_USER` | OpenWebUI API URL (z.B. `https://host/api/v1/users`) |
| `OPENAI_API_KEY` | OpenWebUI API Bearer Token |
| `MDM_API_USER` | MDM API URL (Hauptendpunkt) |
| `MDM_API_USER_EGOV` | MDM API URL (eGov-Endpunkt) |
| `MDM_API_USER_CLIENT_ID` | MDM API Client ID |
| `MDM_API_USER_CLIENT_SECRET` | MDM API Client Secret |

### Löschparameter / Deletion Parameters

| Variable | Default | Beschreibung |
|---|---|---|
| `DELETE_DRY_RUN` | `1` | `1` = Simulation, `0` = tatsächliche Löschung |
| `DELETE_AFTER_DAYS_INACTIVE` | `62` | Tage nach Austritt bis zur Löschung |
| `DELETE_CHATS_OLDER_THAN_DAYS` | `92` | Alter in Tagen für Chat-Löschung |
| `DELETE_FILES_OLDER_THAN_DAYS` | `92` | Alter in Tagen für Datei-Löschung |
| `DRY_RUN_IF_MORE_THAN_N_DELETIONS` | `1` | Safety-Feature aktivieren (`1`/`0`) |
| `DRY_RUN_IF_MORE_THAN_N_USER_DELETIONS` | `30` | Schwellwert für Benutzer-Löschungen |
| `DRY_RUN_IF_MORE_THAN_N_CHAT_DELETIONS` | `100` | Schwellwert für Chat-Löschungen |
| `DRY_RUN_IF_MORE_THAN_N_FILE_DELETIONS` | `100` | Schwellwert für Datei-Löschungen |
| `MDM_BULK_REQUEST_CHUNK_SIZE` | `100` | Chunk-Grösse für MDM-API-Anfragen |

### Sonstiges / Miscellaneous

| Variable | Default | Beschreibung |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log-Level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `CREATE_OUTPUT_CSVS` | `0` | `1` = CSV-Dateien erstellen |

---

## Voraussetzungen / Prerequisites

- Python ≥ 3.13.2
- [uv](https://docs.astral.sh/uv/) (Package Manager)
- PostgreSQL-Zugang zur OpenWebUI-Datenbank
- OpenWebUI API-Zugang (Admin-Token)
- MDM API-Zugang

---

## Lokale Ausführung / Local Execution

```bash
# Dependencies installieren
uv sync

# .env-Datei erstellen und konfigurieren
cp .env.example .env  # Vorlage anpassen

# Ausführen (Dry-Run standardmässig aktiviert)
uv run main.py
```

---

## Deployment

Das Projekt ist für den Betrieb als **Kubernetes CronJob** konzipiert. Details zur CI/CD-Pipeline und zum Deployment finden sich in:

- [CICD.md](./CICD.md) – CI/CD-Pipeline-Dokumentation
- [GITLAB_SETUP.md](./GITLAB_SETUP.md) – GitLab-Repository-Setup

---

## Datenbank-Schema / Database Schema

RetentionGuard erstellt zwei Tabellen in der Analytics-Datenbank:

### `retentionguard_batch_execution`
Tracking jeder Batch-Ausführung (Start, Ende, Dauer, Löschzähler, Exit-Code).

### `retentionguard_deleted`
Protokoll aller gelöschten Benutzer mit Metadaten (Batch-ID, User-ID, Löschgrund, Name, E-Mail, Rolle, Timestamps, Settings).

---

## Lizenz / Licence

[MIT](./LICENCE)
