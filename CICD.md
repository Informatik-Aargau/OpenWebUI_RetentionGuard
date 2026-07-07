# CI/CD Dokumentation

## 1. Überblick

Unsere Projekte nutzen **GitLab CI/CD** zur automatisierten Build- und Deployment-Pipeline. Applikationen werden als **Docker-Container** gebaut, in die **GitLab Container Registry** gepusht und als **Kubernetes-Ressourcen** (z.B. CronJob oder Deployment) auf der **Aargau Cloud Platform (ACP)** deployed. Jedes Projekt hat zwei Umgebungen: **Stage** und **Prod**.

---

## 2. Branch- und Umgebungsstrategie

| Branch  | Umgebung | Deployment     | Schutz                          |
|---------|----------|----------------|---------------------------------|
| `stage` | STAGE    | **Automatisch** bei jedem Push | Protected – nur Maintainers dürfen pushen/mergen |
| `prod`  | PROD     | **Manuell** (Approval in GitLab UI nötig) | Protected – niemand darf direkt pushen, nur Merge von `stage` |

Der `stage`-Branch ist der **Default-Branch**. Produktions-Deployments erfolgen ausschliesslich über einen Merge von `stage` nach `prod`, gefolgt von einer manuellen Freigabe in der GitLab-Oberfläche.

---

## 3. Pipeline-Stages

Die Pipeline ist in `.gitlab-ci.yml` definiert und besteht typischerweise aus **zwei Stages**:

### 3.1 `build` – Docker Image bauen

- **Image**: `docker:latest` mit Docker-in-Docker (`docker:dind`)
- **Trigger**: Pushes auf `stage` oder `prod`
- Baut das Docker-Image mit dem Tag `$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA` (kurzer Commit-Hash als Tag)
- Pusht das Image in die **GitLab Container Registry**
- Das Dockerfile basiert typischerweise auf `python:3-slim-bookworm`, installiert die kantonalen CA-Zertifikate, konfiguriert den Proxy, installiert Dependencies via `uv sync` und läuft als **non-root User** (UID 1000)

### 3.2 `deploy` – Deployment auf Kubernetes

Zwei separate Jobs, je nach Branch:

- **`deploy-stage`**: Automatisch bei Push auf `stage`
- **`deploy-prod`**: Manuell (`when: manual`) bei Push auf `prod`

Beide Jobs nutzen das interne Image `#[.....]/base-images/alpine-k8s` (mit vorinstalliertem `kubectl`) und führen folgende Schritte aus:

1. **Kubeconfig einrichten** – aus der GitLab CI/CD File-Variable `KUBECONFIG`
2. **Registry-Secret erstellen** – `docker-registry` Secret für Image-Pulling aus der GitLab Registry
3. **Env-Secret erstellen** – die `.env`-Datei wird als Base64-encodiertes Kubernetes Secret deployed (Variable `B64_DOTENV`)
4. **K8s-Ressourcen deployen** – via `envsubst` werden Variablen in den YAML-Manifesten unter `k8s/` substituiert und angewendet

---

## 4. Kubernetes-Architektur (Aargau Cloud Platform)

### 4.1 Ressourcen-Typen

Je nach Projekt wird eine passende Kubernetes-Ressource deployed:

- **CronJob** – für periodische Batch-Aufgaben (z.B. tägliche Datenbereinigung)
- **Deployment + Service** – für dauerlaufende Dienste

Typische CronJob-Konfiguration:

| Parameter                    | Stage                  | Prod                   |
|------------------------------|------------------------|------------------------|
| **Timezone**                 | `Europe/Zurich`        | `Europe/Zurich`        |
| **Concurrency Policy**       | `Forbid` (kein paralleler Lauf) | `Forbid`     |
| **History**                  | 3 erfolgreiche / 1 fehlgeschlagene Jobs | dito |

### 4.2 Namespaces

Jedes Projekt läuft unter den AargauGPT Namespaces:

- `#[.....]-stage`
- `#[.....]-prod`

### 4.3 Security Context

Pods laufen mit strikten Sicherheitseinstellungen:

- `runAsNonRoot: true`, UID/GID 1000
- `allowPrivilegeEscalation: false`
- `seccompProfile: RuntimeDefault`
- Alle Linux Capabilities gedropt (`drop: ALL`)

### 4.4 Secrets Management

- **`.env`-Datei**: Wird als Kubernetes Secret gespeichert und als File in den Container gemountet (`/app/.env`). Inhalt stammt aus der GitLab-Variable `B64_DOTENV`.
- **Image-Pull-Secret**: Separates `docker-registry`-Secret für den Zugriff auf die GitLab Container Registry.
- **Kubeconfig**: Als geschützte/maskierte File-Variable in GitLab CI/CD gespeichert.

---

## 5. Secret- und Konfigurationsmanagement

### GitLab CI/CD Variables

| Variable         | Typ   | Scope       | Beschreibung                                      |
|------------------|-------|-------------|---------------------------------------------------|
| `B64_DOTENV`     | Env   | Stage/Prod  | Base64-encodierter Inhalt der `.env`-Datei         |
| `KUBECONFIG`     | File  | Stage/Prod  | Kubeconfig für den jeweiligen K8s-Cluster          |
| `K8S_PULL_IMAGE` | Env   | Alle        | Token für Image-Pull aus der GitLab Registry       |
| `CI_REGISTRY_*`  | Auto  | Alle        | Automatisch von GitLab bereitgestellt              |

### Hilfsskripte unter `env/`

Jedes Projekt enthält im Ordner `env/` Skripte zur Verwaltung der GitLab CI/CD-Variablen:

- `.envB64.py` – Encodiert eine `.env`-Datei (pro Umgebung: `.env_stage`, `.env_prod`) zu Base64 und pusht sie via GitLab API als CI/CD-Variable
- `.kubeconfig.py` – Lädt die Kubeconfig-Dateien für beide Umgebungen hoch
- `update_gitlab_variables.py` – Orchestriert das Hochladen aller Variablen (`.env` + Kubeconfig) für beide Umgebungen in einem Schritt

Verwendung:

```powershell
$env:GITLAB_TOKEN = "your-token"
$env:GITLAB_PROJECT_ID = "namespace/project-name"

# Einzeln
uv run .\env\.envB64.py -e stage
uv run .\env\.envB64.py -e prod

# Oder alles auf einmal
uv run .\env\update_gitlab_variables.py
```

---

## 6. Deployment-Flow (Zusammenfassung)

```
Push auf "stage"
    │
    ├─► build-image
    │     └─► Docker build & push → GitLab Container Registry
    │
    └─► deploy-stage (automatisch)
          ├─► Registry-Secret anlegen
          ├─► .env-Secret aus B64_DOTENV anlegen
          └─► K8s-Ressourcen deployen

Merge "stage" → "prod"
    │
    ├─► build-image
    │     └─► Docker build & push → GitLab Container Registry
    │
    └─► deploy-prod (manuelles Approval nötig)
          ├─► Registry-Secret anlegen
          ├─► .env-Secret aus B64_DOTENV anlegen
          └─► K8s-Ressourcen deployen
```

---

## 7. Infrastruktur-spezifische Details (Kanton Aargau)

- **Proxy**: Alle HTTP(S)-Requests im Container gehen über `#[.....]`
- **CA-Zertifikate**: Kantonale Root- und Sub-CA-Zertifikate (`#[.....]`, `#[.....]`) werden im Docker-Build installiert
- **GitLab-Instanz**: Selbst-gehostet unter `#[.....]`
- **Container Registry**: Interne Registry unter `#[.....]`
- **Runner-Tags**: `task/fast`, `os/linux`, `kind/docker`, `net/ads` – die Runner laufen im internen ADS-Netzwerk
- **Locale/Timezone**: `de_CH.UTF-8` / `Europe/Zurich`
- **Retry**: Jeder Job wird bei Fehler bis zu **2x automatisch wiederholt** (global konfiguriert)
- **Timeout**: 10 Minuten pro Job

---

## 8. Monitoring & Troubleshooting

- **Pipeline-Logs**: GitLab UI unter CI/CD → Pipelines
- **K8s-Ressourcen prüfen**: `kubectl get <ressource> -n <namespace> -l app=<app-name>`
- **Pod-Logs**: `kubectl logs -n <namespace> -l app=<app-name>`
- **Manueller CronJob-Trigger**: `kubectl create job --from=cronjob/<cronjob-name> manual-test -n <namespace>`
