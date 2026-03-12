from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta
import pandas as pd
import logging
import os

# -------------------------------
# CONFIG
# -------------------------------
DATA_DIR = "/opt/airflow/data"
RAW_DATA = os.path.join(DATA_DIR, "titanic.csv")
PROCESSED_DATA = os.path.join(DATA_DIR, "processed.csv")   # after missing handled
FEATURED_DATA = os.path.join(DATA_DIR, "featured.csv")     # after feature engineering
ENCODED_DATA = os.path.join(DATA_DIR, "encoded.csv")       # final training-ready data

MLFLOW_TRACKING_URI = "http://mlflow:5000"
EXPERIMENT_NAME = "Titanic_Experiment"

# -------------------------------
# TASK 10 — HYPERPARAMETER SETS
# Each DAG run picks the next unused
# config automatically via MLflow run count
# Run 1: n_estimators=100, max_depth=4,  min_samples_split=2
# Run 2: n_estimators=150, max_depth=6,  min_samples_split=5
# Run 3: n_estimators=200, max_depth=8,  min_samples_split=10
# -------------------------------
HYPERPARAMETER_SETS = [
    {"n_estimators": 100, "max_depth": 4,  "min_samples_split": 2},
    {"n_estimators": 150, "max_depth": 6,  "min_samples_split": 5},
    {"n_estimators": 200, "max_depth": 8,  "min_samples_split": 10},
]

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(seconds=5),
}

dag = DAG(
    dag_id="mlops_airflow_mlflow_pipeline",
    default_args=default_args,
    start_date=datetime.now() - timedelta(days=1),
    schedule=None,
    catchup=False,
    tags=["mlops", "titanic", "mlflow"],
    description=(
        "End-to-end ML pipeline: ingest → validate → "
        "[parallel: missing+feature] → encode → train → "
        "evaluate → branch → register/reject"
    ),
)


# ================================================
# HELPER — pick hyperparams based on run count
# ================================================
def get_hyperparams(tracking_uri: str, experiment_name: str) -> dict:
    """
    Checks how many MLflow runs exist for this experiment
    and picks the next hyperparameter set cyclically.
    This means:
      - 1st DAG run  → HYPERPARAMETER_SETS[0]
      - 2nd DAG run  → HYPERPARAMETER_SETS[1]
      - 3rd DAG run  → HYPERPARAMETER_SETS[2]
      - 4th DAG run  → HYPERPARAMETER_SETS[0] (cycles)
    """
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    try:
        experiment = client.get_experiment_by_name(experiment_name)
        if experiment is None:
            run_count = 0
        else:
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                max_results=1000,
            )
            run_count = len(runs)
    except Exception:
        run_count = 0

    index = run_count % len(HYPERPARAMETER_SETS)
    chosen = HYPERPARAMETER_SETS[index]
    logging.info(
        f"Run count so far: {run_count} → "
        f"Using hyperparameter set [{index}]: {chosen}"
    )
    return chosen


# ================================================
# TASK 2 — Data Ingestion
# ================================================
def data_ingestion(**context):
    if not os.path.exists(RAW_DATA):
        raise FileNotFoundError(f"Titanic CSV not found at {RAW_DATA}")

    df = pd.read_csv(RAW_DATA)

    logging.info("=" * 50)
    logging.info("DATA INGESTION")
    logging.info(f"Dataset Shape     : {df.shape}")
    logging.info(f"Columns           : {df.columns.tolist()}")
    logging.info(f"Missing Values    :\n{df.isnull().sum()}")
    logging.info("=" * 50)

    context["ti"].xcom_push(key="dataset_path", value=RAW_DATA)
    context["ti"].xcom_push(key="dataset_rows", value=int(df.shape[0]))
    context["ti"].xcom_push(key="dataset_cols", value=int(df.shape[1]))


# ================================================
# TASK 3 — Data Validation
# ================================================
def data_validation(**context):
    path = context["ti"].xcom_pull(key="dataset_path", task_ids="data_ingestion")
    df = pd.read_csv(path)

    df["Embarked"] = df["Embarked"].replace(r"^\s*$", pd.NA, regex=True)

    age_missing_pct = df["Age"].isnull().mean()
    emb_missing_pct = df["Embarked"].isnull().mean()

    logging.info(f"Age missing      : {age_missing_pct:.2%}")
    logging.info(f"Embarked missing : {emb_missing_pct:.2%}")

    if age_missing_pct > 0.30:
        raise ValueError(
            f"Age missing {age_missing_pct:.2%} exceeds 30% — retrying..."
        )
    if emb_missing_pct > 0.30:
        raise ValueError(
            f"Embarked missing {emb_missing_pct:.2%} exceeds 30% — retrying..."
        )

    logging.info("Validation passed ✅")


# ================================================
# TASK 4a — Handle Missing Values
# Reads RAW → saves PROCESSED
# ================================================
def handle_missing(**context):
    # Always read from RAW so parallel execution is safe
    df = pd.read_csv(RAW_DATA)

    before_nulls = df.isnull().sum().sum()

    df["Age"]      = df["Age"].fillna(df["Age"].median())
    df["Embarked"] = df["Embarked"].fillna(df["Embarked"].mode()[0])
    df["Fare"]     = df["Fare"].fillna(df["Fare"].median())

    after_nulls = df[["Age", "Embarked", "Fare"]].isnull().sum().sum()

    df.to_csv(PROCESSED_DATA, index=False)

    logging.info(f"Nulls before : {before_nulls}")
    logging.info(f"Nulls after  : {after_nulls}")
    logging.info(f"Saved clean data → {PROCESSED_DATA}")
    logging.info(f"Shape: {df.shape}")

    # Push confirmation for encoding task
    context["ti"].xcom_push(key="processed_path", value=PROCESSED_DATA)


# ================================================
# TASK 4b — Feature Engineering
# Reads RAW → saves FEATURED
# (Runs in parallel with handle_missing — both
#  read RAW independently so no race condition)
# ================================================
def feature_engineering(**context):
    # Read RAW independently (parallel-safe)
    df = pd.read_csv(RAW_DATA)

    # FamilySize & IsAlone
    df["FamilySize"] = df["SibSp"] + df["Parch"] + 1
    df["IsAlone"]    = (df["FamilySize"] == 1).astype(int)

    # Title extraction from Name
    df["Title"] = df["Name"].str.extract(r" ([A-Za-z]+)\.", expand=False)
    df["Title"] = df["Title"].replace(
        ["Lady", "Countess", "Capt", "Col", "Don", "Dr",
         "Major", "Rev", "Sir", "Jonkheer", "Dona"], "Rare"
    )
    df["Title"] = df["Title"].replace(
        {"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"}
    )

    # Save only the engineered columns + PassengerId as merge key
    feature_cols = ["PassengerId", "FamilySize", "IsAlone", "Title"]
    df[feature_cols].to_csv(FEATURED_DATA, index=False)

    logging.info(f"Engineered features: FamilySize, IsAlone, Title")
    logging.info(f"Saved featured data → {FEATURED_DATA}")
    logging.info(f"Sample:\n{df[feature_cols].head()}")

    context["ti"].xcom_push(key="featured_path", value=FEATURED_DATA)


# ================================================
# TASK 5 — Encoding
# Reads PROCESSED + FEATURED → saves ENCODED
# This is the ONLY place that merges both outputs
# ================================================
def encoding(**context):
    processed_path = context["ti"].xcom_pull(
        key="processed_path", task_ids="handle_missing"
    )
    featured_path = context["ti"].xcom_pull(
        key="featured_path", task_ids="feature_engineering"
    )

    logging.info(f"Reading processed data from : {processed_path}")
    logging.info(f"Reading featured data from  : {featured_path}")

    # Load both CSVs
    df_proc = pd.read_csv(processed_path)   # has clean Age/Embarked/Fare
    df_feat = pd.read_csv(featured_path)    # has FamilySize, IsAlone, Title

    # Merge on PassengerId — guarantees row alignment even if order differs
    df = pd.merge(df_proc, df_feat, on="PassengerId", how="left")

    logging.info(f"Shape after merge: {df.shape}")
    logging.info(f"Columns: {df.columns.tolist()}")

    # Verify critical columns exist before encoding
    for col in ["Sex", "Embarked", "Title"]:
        if col not in df.columns:
            raise ValueError(f"Expected column '{col}' missing after merge!")

    # One-hot encode
    df = pd.get_dummies(df, columns=["Sex", "Embarked", "Title"])

    # Drop irrelevant columns
    drop_cols = ["PassengerId", "Name", "Ticket", "Cabin"]
    df.drop(columns=drop_cols, inplace=True, errors="ignore")

    # Convert bool columns to int (sklearn compatibility)
    bool_cols = df.select_dtypes(include="bool").columns
    df[bool_cols] = df[bool_cols].astype(int)

    # Verify target column exists
    if "Survived" not in df.columns:
        raise ValueError("Target column 'Survived' missing from encoded data!")

    df.to_csv(ENCODED_DATA, index=False)

    logging.info(f"Encoding complete. Final shape: {df.shape}")
    logging.info(f"Final columns: {df.columns.tolist()}")
    logging.info(f"Saved encoded data → {ENCODED_DATA}")

    context["ti"].xcom_push(key="encoded_path", value=ENCODED_DATA)
    context["ti"].xcom_push(key="final_shape",  value=str(df.shape))


# ================================================
# TASK 6 + 7 — Train Model + Log Metrics
# Reads ENCODED (the final merged+cleaned CSV)
# ================================================
def train_model(**context):
    import mlflow
    import mlflow.sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score
    )

    # Pull the exact path XCom'd from encoding task
    encoded_path = context["ti"].xcom_pull(
        key="encoded_path", task_ids="encoding"
    )
    logging.info(f"Training on data from: {encoded_path}")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    os.environ["MLFLOW_TRACKING_URI"] = MLFLOW_TRACKING_URI

    mlflow.set_experiment(EXPERIMENT_NAME)

    # ── TASK 10: auto-select hyperparams ──
    params = get_hyperparams(MLFLOW_TRACKING_URI, EXPERIMENT_NAME)
    n_estimators      = params["n_estimators"]
    max_depth         = params["max_depth"]
    min_samples_split = params["min_samples_split"]

    logging.info(
        f"Hyperparameters → n_estimators={n_estimators}, "
        f"max_depth={max_depth}, min_samples_split={min_samples_split}"
    )

    df = pd.read_csv(encoded_path)
    X  = df.drop("Survived", axis=1)
    y  = df["Survived"]

    dataset_size = len(df)
    n_features   = X.shape[1]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    run_name = (
        f"RF_est{n_estimators}_depth{max_depth}_split{min_samples_split}"
    )

    with mlflow.start_run(run_name=run_name) as run:

        # ── Task 6: log params & dataset info ──
        mlflow.log_param("model_type",         "RandomForestClassifier")
        mlflow.log_param("n_estimators",        n_estimators)
        mlflow.log_param("max_depth",           max_depth)
        mlflow.log_param("min_samples_split",   min_samples_split)
        mlflow.log_param("test_size",           0.2)
        mlflow.log_param("random_state",        42)
        mlflow.log_metric("dataset_size",       dataset_size)
        mlflow.log_metric("n_features",         n_features)
        mlflow.log_metric("train_size",         len(X_train))
        mlflow.log_metric("test_size_rows",     len(X_test))

        # ── Train ──
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            random_state=42,
        )
        model.fit(X_train, y_train)
        preds = model.predict(X_test)

        # ── Task 7: compute & log all metrics ──
        acc       = accuracy_score(y_test, preds)
        precision = precision_score(y_test, preds, zero_division=0)
        recall    = recall_score(y_test, preds, zero_division=0)
        f1        = f1_score(y_test, preds, zero_division=0)

        mlflow.log_metric("accuracy",  acc)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall",    recall)
        mlflow.log_metric("f1_score",  f1)

        # ── Log model artifact ──
        mlflow.sklearn.log_model(
            model,
            name="model",
        )

        run_id = run.info.run_id
        logging.info(f"MLflow run_id  : {run_id}")
        logging.info(f"Run name       : {run_name}")
        logging.info(
            f"Metrics — accuracy: {acc:.4f}, precision: {precision:.4f}, "
            f"recall: {recall:.4f}, f1: {f1:.4f}"
        )

    # Push all metrics + run_id for downstream tasks
    context["ti"].xcom_push(key="accuracy",   value=float(acc))
    context["ti"].xcom_push(key="precision",  value=float(precision))
    context["ti"].xcom_push(key="recall",     value=float(recall))
    context["ti"].xcom_push(key="f1_score",   value=float(f1))
    context["ti"].xcom_push(key="run_id",     value=run_id)
    context["ti"].xcom_push(key="run_name",   value=run_name)
    context["ti"].xcom_push(key="n_estimators",      value=n_estimators)
    context["ti"].xcom_push(key="max_depth",         value=max_depth)
    context["ti"].xcom_push(key="min_samples_split", value=min_samples_split)


# ================================================
# TASK 7 — Evaluation Summary
# ================================================
def evaluate_model(**context):
    ti        = context["ti"]
    acc       = ti.xcom_pull(key="accuracy",          task_ids="train_model")
    precision = ti.xcom_pull(key="precision",         task_ids="train_model")
    recall    = ti.xcom_pull(key="recall",            task_ids="train_model")
    f1        = ti.xcom_pull(key="f1_score",          task_ids="train_model")
    run_id    = ti.xcom_pull(key="run_id",            task_ids="train_model")
    run_name  = ti.xcom_pull(key="run_name",          task_ids="train_model")
    n_est     = ti.xcom_pull(key="n_estimators",      task_ids="train_model")
    depth     = ti.xcom_pull(key="max_depth",         task_ids="train_model")
    split     = ti.xcom_pull(key="min_samples_split", task_ids="train_model")

    logging.info("=" * 60)
    logging.info("MODEL EVALUATION SUMMARY")
    logging.info(f"  Run Name          : {run_name}")
    logging.info(f"  MLflow Run ID     : {run_id}")
    logging.info(f"  n_estimators      : {n_est}")
    logging.info(f"  max_depth         : {depth}")
    logging.info(f"  min_samples_split : {split}")
    logging.info(f"  Accuracy          : {acc:.4f}")
    logging.info(f"  Precision         : {precision:.4f}")
    logging.info(f"  Recall            : {recall:.4f}")
    logging.info(f"  F1-Score          : {f1:.4f}")
    logging.info(f"  Threshold         : 0.80")
    logging.info(f"  Decision          : {'APPROVE ✅' if acc >= 0.80 else 'REJECT ❌'}")
    logging.info("=" * 60)


# ================================================
# TASK 8 — Branch Decision
# ================================================
def branch_decision(**context):
    acc = context["ti"].xcom_pull(key="accuracy", task_ids="train_model")
    logging.info(f"Branch — accuracy={acc:.4f}, threshold=0.80")
    return "register_model" if acc >= 0.80 else "reject_model"


# ================================================
# TASK 9a — Register Model in MLflow Registry
# ================================================
def register_model(**context):
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    ti       = context["ti"]
    run_id   = ti.xcom_pull(key="run_id",       task_ids="train_model")
    acc      = ti.xcom_pull(key="accuracy",     task_ids="train_model")
    f1       = ti.xcom_pull(key="f1_score",     task_ids="train_model")
    run_name = ti.xcom_pull(key="run_name",     task_ids="train_model")

    model_uri = f"runs:/{run_id}/model"
    result    = mlflow.register_model(
        model_uri=model_uri,
        name="TitanicSurvivalModel"
    )

    # Tag the registered version
    client.set_registered_model_tag(
        "TitanicSurvivalModel", "task", "binary_classification"
    )
    client.set_model_version_tag(
        "TitanicSurvivalModel", result.version, "accuracy",     f"{acc:.4f}"
    )
    client.set_model_version_tag(
        "TitanicSurvivalModel", result.version, "f1_score",     f"{f1:.4f}"
    )
    client.set_model_version_tag(
        "TitanicSurvivalModel", result.version, "run_name",     run_name
    )
    client.set_model_version_tag(
        "TitanicSurvivalModel", result.version, "approved_by",  "airflow_pipeline"
    )

    # Also tag the source run
    client.set_tag(run_id, "status",           "registered")
    client.set_tag(run_id, "model_version",    str(result.version))
    client.set_tag(run_id, "registry_name",    "TitanicSurvivalModel")

    logging.info(f"✅ Registered: TitanicSurvivalModel v{result.version}")
    logging.info(f"   Run ID   : {run_id}")
    logging.info(f"   Accuracy : {acc:.4f} | F1: {f1:.4f}")


# ================================================
# TASK 9b — Reject Model + log reason to MLflow
# ================================================
def reject_model(**context):
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    ti       = context["ti"]
    run_id   = ti.xcom_pull(key="run_id",       task_ids="train_model")
    acc      = ti.xcom_pull(key="accuracy",     task_ids="train_model")
    f1       = ti.xcom_pull(key="f1_score",     task_ids="train_model")
    n_est    = ti.xcom_pull(key="n_estimators", task_ids="train_model")
    depth    = ti.xcom_pull(key="max_depth",    task_ids="train_model")

    rejection_reason = (
        f"Accuracy {acc:.4f} below threshold 0.80. "
        f"F1={f1:.4f}. "
        f"Tried n_estimators={n_est}, max_depth={depth}. "
        f"Suggestions: increase estimators, tune depth, or engineer more features."
    )

    client.set_tag(run_id, "status",           "rejected")
    client.set_tag(run_id, "rejection_reason", rejection_reason)

    logging.info(f"❌ Model REJECTED")
    logging.info(f"   Reason: {rejection_reason}")


# ================================================
# OPERATORS
# ================================================

ingestion = PythonOperator(
    task_id="data_ingestion",
    python_callable=data_ingestion,
    dag=dag,
)

validation = PythonOperator(
    task_id="data_validation",
    python_callable=data_validation,
    dag=dag,
)

# PARALLEL TASKS (Task 4)
missing = PythonOperator(
    task_id="handle_missing",
    python_callable=handle_missing,
    dag=dag,
)

feature = PythonOperator(
    task_id="feature_engineering",
    python_callable=feature_engineering,
    dag=dag,
)

encode = PythonOperator(
    task_id="encoding",
    python_callable=encoding,
    dag=dag,
)

train = PythonOperator(
    task_id="train_model",
    python_callable=train_model,
    dag=dag,
)

evaluate = PythonOperator(
    task_id="evaluate_model",
    python_callable=evaluate_model,
    dag=dag,
)

branch = BranchPythonOperator(
    task_id="branch_decision",
    python_callable=branch_decision,
    dag=dag,
)

register = PythonOperator(
    task_id="register_model",
    python_callable=register_model,
    dag=dag,
)

reject = PythonOperator(
    task_id="reject_model",
    python_callable=reject_model,
    dag=dag,
)

end = EmptyOperator(
    task_id="end",
    trigger_rule="none_failed_min_one_success",
    dag=dag,
)

# ================================================
# DEPENDENCIES
#
#        data_ingestion
#              │
#        data_validation
#           ┌──┴──┐
#    handle_missing  feature_engineering   ← PARALLEL
#           └──┬──┘
#           encoding           ← merges PROCESSED + FEATURED via PassengerId
#              │
#          train_model         ← reads ENCODED (fully cleaned + engineered)
#              │
#        evaluate_model
#              │
#        branch_decision
#          ┌───┴───┐
#   register_model  reject_model
#          └───┬───┘
#             end
# ================================================

ingestion  >> validation
validation >> [missing, feature]   # fan-out → parallel
[missing, feature] >> encode       # fan-in  → both must complete
encode     >> train >> evaluate >> branch
branch     >> [register, reject]   >> end