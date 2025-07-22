import pandas as pd
import numpy as np
import os
from .get_data import obtain_mimic_dataset
from .generate_dataset import generate_mortality_dataset, generate_discharge_dataset, generate_test_dataset
from .discharge_model import train_discharge_model, get_discharge_predictions
from .mortality_model import train_mortality_model, get_mortality_predictions

MANDATORY_COLUMNS = [
    "stay_id",
    "hr",
    "rate_epinephrine",
    "rate_norepinephrine",
    "rate_dopamine",
    "rate_dobutamine",
    "meanbp_min",
    "pao2fio2ratio_novent",
    "pao2fio2ratio_vent",
    "gcs_min",
    "bilirubin_max",
    "creatinine_max",
    "platelet_min",
    "admission_age",
    "icu_expire_flag",
    "admission_type_Medical",
    "admission_type_ScheduledSurgical",
    "admission_type_UnscheduledSurgical",
    "charlson_comorbidity_index",
]


def check_dataset(dataset_filename):
    df = pd.read_csv(dataset_filename, index_col=0)
    for c in MANDATORY_COLUMNS:
        assert c in df.columns, f"Column {c} is mandatory."
        assert isinstance(df[c].dtype, type(np.dtype("float64"))) or isinstance(df[c].dtype, type(np.dtype("int"))), (
            f"Column {c} is not Float or Int: {df[c].dtype}"
        )


def run_full_pipeline(base_path, service_account_file):
    # base_path = '../data'
    obtain_mimic_dataset(base_path, download_data=True, service_account_file=service_account_file)
    check_dataset(os.path.join(base_path, "mimic_iv_nan_corrected.csv"))
    print(">> Genrating datasets")
    generate_mortality_dataset(base_path)
    generate_discharge_dataset(base_path)
    print(">> Training mortality model")
    train_mortality_model(base_path)
    print(">> Training discharge model")
    train_discharge_model(base_path)
    print(">> DONE!")


def run_test_pipeline(dataset_filename, base_path, mortality_model_filename, disch_model_filename):
    check_dataset(dataset_filename)
    dataset = generate_test_dataset(base_path, dataset_filename)

    mortality_outcome = get_mortality_predictions(base_path, dataset, mortality_model_filename)
    discharge_outcome = get_discharge_predictions(base_path, dataset, disch_model_filename)
    return {"mortality_outcome": mortality_outcome, "discharge_outcome": discharge_outcome}


# Example run:
# run_test_pipeline('/tmp/dataset.csv', './',
#                   'lstm_mortality_model.m', 'lstm_disch_model.m)


if __name__ == "__main__":
    run_full_pipeline("/tmp/data", "mimic-iii-332416-b6aa0849fbac.json")
