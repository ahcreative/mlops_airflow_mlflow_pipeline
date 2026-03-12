# 🚢 Titanic Survival Predictor

### _An End-to-End MLOps Pipeline powered by Apache Airflow & MLflow_

```
  ___  ___ _    ___  ___  ___
 |  \/  || |  / _ \| _ \/ __|
 | |\/| || |_| (_) |  _/\__ \
 |_|  |_||____\___/|_|  |___/

  Orchestrate → Track → Register → Deploy
```

> _"Not all who board shall survive — but our model will know who does."_
> A production-grade ML pipeline that predicts Titanic survival using the
> full power of modern MLOps tooling.

---

## 📖 Table of Contents

- [🏗️ Architecture Overview](#️-architecture-overview)
- [✨ Features](#-features)
- [🗂️ Project Structure](#️-project-structure)
- [⚙️ Prerequisites](#️-prerequisites)
- [🚀 Quick Start](#-quick-start)
- [🔄 Pipeline Walkthrough](#-pipeline-walkthrough)
- [📊 DAG Structure](#-dag-structure)
- [🧪 Experiment Tracking](#-experiment-tracking)
- [🏆 Model Registry](#-model-registry)
- [🔁 Retry & Failure Behavior](#-retry--failure-behavior)
- [📈 Experiment Comparison](#-experiment-comparison)
- [🛠️ Configuration](#️-configuration)
- [📋 Requirements](#-requirements)
- [🤝 Contributing](#-contributing)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                      (airflow-mlflow)                           │
│                                                                 │
│  ┌──────────────────────────┐    ┌─────────────────────────┐   │
│  │     Apache Airflow       │    │        MLflow           │   │
│  │                          │    │                         │   │
│  │  ┌─────────────────┐     │    │  ┌─────────────────┐   │   │
│  │  │   DAG Scheduler │     │    │  │  Tracking Server│   │   │
│  │  │   API Server    │────────────▶│  Experiment UI  │   │   │
│  │  │   Celery Worker │     │    │  │  Model Registry │   │   │
│  │  │   DAG Processor │     │    │  │  Artifact Store │   │   │
│  │  └─────────────────┘     │    │  └─────────────────┘   │   │
│  │                          │    │                         │   │
│  │  Port: 8080              │    │  Port: 5000             │   │
│  └──────────────────────────┘    └─────────────────────────┘   │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  PostgreSQL  │    │    Redis     │    │   Shared Volume  │  │
│  │  (Metadata)  │    │   (Broker)   │    │  ./mlflow/mlruns │  │
│  │  Port: 5432  │    │  Port: 6379  │    │  (Artifacts)     │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**How they interact:**

- **Airflow** orchestrates the entire ML workflow via a DAG with 10 tasks
- **Celery Worker** executes tasks and writes artifacts to the shared volume
- **MLflow** tracks experiments, logs metrics/params, and manages the model registry
- **PostgreSQL** stores Airflow metadata and task states
- **Redis** acts as the message broker between scheduler and workers

---

## ✨ Features

| Feature                            | Description                                                      |
| ---------------------------------- | ---------------------------------------------------------------- |
| 🔀 **Parallel Processing**         | `handle_missing` and `feature_engineering` run simultaneously    |
| 🌿 **Branching Logic**             | Auto-registers high-accuracy models, rejects low-performing ones |
| 🔁 **Auto Retry**                  | Tasks retry up to 2 times with 5-second delay on failure         |
| 🧪 **Experiment Tracking**         | All runs logged to MLflow with params, metrics & artifacts       |
| 📦 **Model Registry**              | Approved models versioned and tagged in MLflow Model Registry    |
| 🎛️ **Auto Hyperparameter Cycling** | Each DAG run auto-selects the next hyperparameter set            |
| 🔐 **XCom Communication**          | Tasks pass data securely via Airflow's XCom system               |
| 🐳 **Fully Dockerized**            | One command to spin up the entire stack                          |

---

## 🗂️ Project Structure

```
mlops_airflow_mlflow_pipeline/
│
├── 📁 dags/
│   └── mlops_airflow_mlflow_pipeline.py    # Main DAG definition
│
├── 📁 data/
│   └── titanic.csv                         # Titanic dataset
│
├── 📁 mlflow/
│   └── mlruns/                             # MLflow artifact storage
│
├── 📁 logs/                                # Airflow task logs
├── 📁 plugins/                             # Airflow plugins (empty)
├── 📁 config/                              # Airflow config
│
├── 🐳 docker-compose.yaml                  # Full stack definition
├── 📋 requirements.txt                     # Python dependencies
├── 🔑 .env                                 # Environment variables
└── 📖 README.md                            # You are here
```

---

## ⚙️ Prerequisites

Before you begin, make sure you have the following installed:

| Tool           | Version | Download                                                      |
| -------------- | ------- | ------------------------------------------------------------- |
| Docker Desktop | Latest  | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Docker Compose | v2.x    | Included with Docker Desktop                                  |
| Git            | Any     | [git-scm.com](https://git-scm.com/)                           |

> **💡 Resource Requirements:**
>
> - RAM: Minimum **4GB** allocated to Docker
> - CPU: Minimum **2 cores**
> - Disk: At least **10GB** free space

---

## 🚀 Quick Start

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/mlops_airflow_mlflow_pipeline.git
cd mlops_airflow_mlflow_pipeline
```

### 2️⃣ Create the Docker Network

```bash
docker network create airflow-mlflow
```

### 3️⃣ Create Required Directories

```bash
# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path "mlflow\mlruns", "data", "logs", "dags", "plugins", "config"

# Linux / Mac
mkdir -p mlflow/mlruns data logs dags plugins config
```

### 4️⃣ Add the Dataset

Download the Titanic dataset from [Kaggle](https://www.kaggle.com/datasets/yasserh/titanic-dataset/data) and place it at:

```
data/titanic.csv
```

### 5️⃣ Configure Environment

Create a `.env` file in the root directory:

```env
AIRFLOW_UID=50000
AIRFLOW_IMAGE_NAME=apache/airflow:3.1.8
AIRFLOW_PROJ_DIR=.
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow
AIRFLOW__API_AUTH__JWT_SECRET=airflow_jwt_secret
AIRFLOW__API_AUTH__JWT_ISSUER=airflow
```

### 6️⃣ Launch the Stack

```bash
docker-compose up -d
```

> ⏳ First launch takes **5-10 minutes** — packages are being installed inside containers.

### 7️⃣ Verify All Services Are Running

```bash
docker-compose ps
```

You should see all containers as `healthy` or `running`.

### 8️⃣ Access the UIs

| Service       | URL                   | Credentials           |
| ------------- | --------------------- | --------------------- |
| 🌊 Airflow UI | http://localhost:8080 | `airflow` / `airflow` |
| 🧪 MLflow UI  | http://localhost:5000 | No auth required      |

---

## 🔄 Pipeline Walkthrough

The DAG consists of **10 tasks** that execute in a specific order:

```
data_ingestion
      │
data_validation  ◄── retries up to 2x if missing > 30%
      │
   ┌──┴──┐
   │     │  ← PARALLEL EXECUTION
handle  feature
missing  engineering
   │     │
   └──┬──┘
   encoding  ◄── merges both outputs via PassengerId
      │
 train_model  ◄── logs to MLflow, auto-selects hyperparams
      │
evaluate_model
      │
branch_decision  ◄── accuracy ≥ 0.80?
   ┌──┴──┐
   │     │
register reject
_model  _model
   │     │
   └──┬──┘
     end
```

### Task Descriptions

| #   | Task                  | Description                                                              |
| --- | --------------------- | ------------------------------------------------------------------------ |
| 1   | `data_ingestion`      | Loads Titanic CSV, logs shape & missing values, pushes path via XCom     |
| 2   | `data_validation`     | Checks missing % in Age/Embarked, raises exception if > 30%              |
| 3   | `handle_missing`      | Fills Age (median), Embarked (mode), Fare (median)                       |
| 4   | `feature_engineering` | Creates FamilySize, IsAlone, Title features                              |
| 5   | `encoding`            | Merges processed + featured data, one-hot encodes, drops irrelevant cols |
| 6   | `train_model`         | Trains RandomForest, logs all params/metrics/artifacts to MLflow         |
| 7   | `evaluate_model`      | Prints full evaluation summary from XCom values                          |
| 8   | `branch_decision`     | Routes to register or reject based on accuracy threshold                 |
| 9   | `register_model`      | Registers model in MLflow Registry with tags                             |
| 10  | `reject_model`        | Tags the MLflow run with rejection reason                                |

---

## 📊 DAG Structure

### Running the DAG

1. Open **Airflow UI** → `http://localhost:8080`
2. Find `mlops_airflow_mlflow_pipeline` in the DAG list
3. Click the **▶ Trigger** button (top right)
4. Watch tasks turn **green** as they complete

### Triggering 3 Runs for Task 10

The pipeline **automatically cycles** through hyperparameter sets:

| Run | n_estimators | max_depth | min_samples_split |
| --- | ------------ | --------- | ----------------- |
| 1st | 100          | 4         | 2                 |
| 2nd | 150          | 6         | 5                 |
| 3rd | 200          | 8         | 10                |

Simply trigger the DAG **3 times** — no code changes needed!

---

## 🧪 Experiment Tracking

All runs are tracked in MLflow under the experiment `Titanic_Experiment`.

### Logged Parameters

```
model_type, n_estimators, max_depth,
min_samples_split, test_size, random_state
```

### Logged Metrics

```
accuracy, precision, recall, f1_score,
dataset_size, n_features, train_size, test_size_rows
```

### Viewing Results

1. Open **MLflow UI** → `http://localhost:5000`
2. Click `Titanic_Experiment`
3. See all runs with their metrics
4. Select multiple runs → click **Compare** to see side-by-side comparison

---

## 🏆 Model Registry

Models with accuracy **≥ 0.80** are automatically registered as `TitanicSurvivalModel`.

Each registered version is tagged with:

- `accuracy` — model accuracy score
- `f1_score` — F1 score
- `run_name` — hyperparameter set used
- `approved_by` — `airflow_pipeline`

### Viewing the Registry

1. Open **MLflow UI** → `http://localhost:5000`
2. Click **Models** in the top navigation
3. Click `TitanicSurvivalModel` to see all versions

---

## 🔁 Retry & Failure Behavior

The pipeline is configured with:

```python
default_args = {
    "retries": 2,
    "retry_delay": timedelta(seconds=5),
}
```

### Demonstrating Retry (Task 3)

To force a retry for demonstration purposes, temporarily lower the validation threshold in `data_validation`:

```python
# Change this temporarily
if age_missing_pct > 0.10:  # Forces failure on Titanic dataset (~20% missing)
    raise ValueError("Age missing exceeds threshold — retrying...")
```

Trigger the DAG — `data_validation` will fail twice then succeed (or exhaust retries).
**Revert back to `0.30` after capturing the screenshot.**

---

## 📈 Experiment Comparison

After 3 runs, compare in MLflow:

1. Go to `Titanic_Experiment`
2. Select all 3 runs using checkboxes
3. Click **Compare**

Expected results (approximate):

| Run                      | n_estimators | max_depth | Accuracy | F1 Score |
| ------------------------ | ------------ | --------- | -------- | -------- |
| RF_est100_depth4_split2  | 100          | 4         | ~0.82    | ~0.783   |
| RF_est150_depth6_split5  | 150          | 6         | ~0.82    | ~0.783   |
| RF_est200_depth8_split10 | 200          | 8         | ~0.82    | ~0.78    |

**Best Model:** `RF_est200_depth8_split10` — deeper trees with more estimators capture complex survival patterns better, particularly interactions between Pclass, Sex, and Age.

---

## 🛠️ Configuration

### Changing Hyperparameter Sets

Edit the `HYPERPARAMETER_SETS` list in the DAG file:

```python
HYPERPARAMETER_SETS = [
    {"n_estimators": 100, "max_depth": 4,  "min_samples_split": 2},
    {"n_estimators": 150, "max_depth": 6,  "min_samples_split": 5},
    {"n_estimators": 200, "max_depth": 8,  "min_samples_split": 10},
]
```

### Changing the Accuracy Threshold

```python
# In branch_decision function
return "register_model" if acc >= 0.80 else "reject_model"
#                               ^^^^ change this
```

### Stopping the Stack

```bash
# Stop without removing data
docker-compose down

# Stop AND remove all volumes (fresh start)
docker-compose down -v
```

---

## 📋 Requirements

```txt
pandas
numpy
scikit-learn
mlflow
```

---

## 🐛 Troubleshooting

| Problem                     | Solution                                                        |
| --------------------------- | --------------------------------------------------------------- |
| `docker-compose up` fails   | Run `docker network create airflow-mlflow` first                |
| Airflow login fails         | Wait for `airflow-init` to complete fully                       |
| MLflow 403 error            | Ensure `--allowed-hosts "*"` is in the mlflow command           |
| Permission denied `/mlflow` | Check `./mlflow/mlruns:/mlflow/mlruns` is in worker volumes     |
| Worker stuck installing     | Wait 5-10 mins, check logs with `docker logs airflow-worker-1`  |
| DAG not appearing           | Check DAG file has no syntax errors, wait 30 seconds for parser |

---

**Built with ❤️ using Apache Airflow, MLflow, and Docker**

_If this helped you, please ⭐ the repository!_
