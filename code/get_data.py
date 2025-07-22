"""Get MIMIC data and parse it."""

import logging
import os

import numpy as np
import pandas as pd
import tqdm

LOGGER = logging.getLogger(__name__)

NAN_RULES = {
    "pao2fio2ratio_novent": "zero",
    "pao2fio2ratio_vent": "zero",
    "gcs_min": "prev_value",
    "rate_norepinephrine": "zero",
    "rate_epinephrine": "zero",
    "rate_dopamine": "zero",
    "rate_dobutamine": "zero",
    "meanbp_min": "prev_value",
    "bilirubin_max": "prev_value",
    "platelet_min": "prev_value",
    "creatinine_max": "prev_value",
}


OUTLIER_CORRECTION = {
    "rate_epinephrine": (0, 10),
    "rate_norepinephrine": (0, 5),
    "rate_dopamine": (0, 50),
    "rate_dobutamine": (0, 40),
    "meanbp_min": (10, 150),
    "pao2fio2ratio_novent": (50, 600),
    "pao2fio2ratio_vent": (50, 600),
    "bilirubin_max": (0.1, 70),
    "creatinine_max": (0.2, 20),
    "platelet_min": (5, 2000),
}

# To exclude parients with LTSV:
# SELECT distinct chartevents.stay_id
# FROM `physionet-data.mimic_icu.chartevents` as chartevents
# LEFT JOIN `physionet-data.mimic_icu.icustays` as stays
# ON chartevents.stay_id = stays.stay_id
# WHERE itemid IN (223758, 229784, 228687) and value <> "Full code"


def _download_data(base_path="../data", service_account_file="key.json", overwrite=False):
    """
    Downloads and saves required MIMIC-IV datasets as CSV files from Google BigQuery.
    This function checks for the existence of specific CSV files in the given base_path.
    If a file does not exist or if `overwrite` is True, it executes the corresponding SQL query
    against the MIMIC-IV BigQuery datasets and saves the results as a CSV file.
    Parameters
    ----------
    base_path : str, optional
        Directory path where the CSV files will be saved. Default is "../data".
    service_account_file : str, optional
        Path to the Google Cloud service account JSON key file. Default is "key.json".
        (Currently not used; credentials loading is commented out.)
    overwrite : bool, optional
        If True, existing CSV files will be overwritten. Default is False.
    Files Downloaded
    ----------------
    - mimic_iv.csv: Combined SOFA and ICU stay details.
    - charlson_comorbidity.csv: Charlson comorbidity index per ICU stay.
    - patients_ltsv.csv: ICU stays with specific chart events and code status.
    - admission_type.csv: Admission type (ScheduledSurgical, UnscheduledSurgical, Medical) per ICU stay.
    - icu_expire_flag.csv: Flag indicating if patient expired in ICU.
    Notes
    -----
    - Requires access to the MIMIC-IV datasets on Google BigQuery.
    - Uses pandas `read_gbq` for querying BigQuery tables.
    - Credentials loading is currently commented out.
    """
    # credentials = service_account.Credentials.from_service_account_file(
    #     service_account_file)

    if not os.path.exists(os.path.join(base_path, "mimic_iv.csv")) or overwrite:
        query = """SELECT *
            FROM `physionet-data.mimic_derived.sofa` as sofa
            LEFT JOIN `physionet-data.mimic_derived.icustay_detail` as detail
            ON sofa.stay_id = detail.stay_id
            WHERE sofa.stay_id IN
            (SELECT DISTINCT stay_id FROM `physionet-data.mimic_icu.icustays`)"""

        df = pd.read_gbq(
            query,
            #  credentials=credentials,
            project_id="mimic-iii-332416",
            use_bqstorage_api=True,
        )
        df.to_csv(os.path.join(base_path, "mimic_iv.csv"))

    if not os.path.exists(os.path.join(base_path, "charlson_comorbidity.csv")) or overwrite:
        query = """SELECT stay_id, charlson_comorbidity_index
            FROM `physionet-data.mimic_derived.charlson` c
            INNER JOIN `physionet-data.mimic_icu.icustays` stays
            on c.subject_id = stays.subject_id and c.hadm_id = stays.hadm_id"""

        df = pd.read_gbq(
            query,
            #  credentials=credentials,
            project_id="mimic-iii-332416",
            use_bqstorage_api=True,
        )
        df.to_csv(os.path.join(base_path, "charlson_comorbidity.csv"))

    if not os.path.exists(os.path.join(base_path, "patients_ltsv.csv")) or overwrite:
        query = """SELECT distinct chartevents.stay_id
            FROM `physionet-data.mimic_icu.chartevents` as chartevents
            LEFT JOIN `physionet-data.mimic_icu.icustays` as stays
            ON chartevents.stay_id = stays.stay_id
            WHERE itemid IN (223758, 229784, 228687) and value <> 'Full code'"""

        df = pd.read_gbq(
            query,
            #  credentials=credentials,
            project_id="mimic-iii-332416",
            use_bqstorage_api=True,
        )
        df.to_csv(os.path.join(base_path, "patients_ltsv.csv"))

    if not os.path.exists(os.path.join(base_path, "admission_type.csv")) or overwrite:
        query = """ WITH surgflag as(
                    select transf.hadm_id
                        , case when lower(careunit) like '%surg%' then 1 else 0 end as surgical
                        , ROW_NUMBER() over
                        (
                        PARTITION BY transf.HADM_ID
                        ORDER BY transfertime
                        ) as serviceOrder
                    FROM `physionet-data.mimic_core.transfers` transf
                    left join `physionet-data.mimic_hosp.services` se
                        on transf.hadm_id = se.hadm_id)
                    SELECT
                        ie.subject_id, ie.hadm_id, ie.stay_id,
                        case
                            when adm.ADMISSION_TYPE = 'ELECTIVE' and sf.surgical = 1
                                then 'ScheduledSurgical'
                            when adm.ADMISSION_TYPE != 'ELECTIVE' and sf.surgical = 1
                                then 'UnscheduledSurgical'
                            else 'Medical'
                            end as admissiontype
                    FROM `physionet-data.mimic_icu.icustays` ie
                    inner join `physionet-data.mimic_core.admissions` adm
                    on ie.hadm_id = adm.hadm_id
                    inner join `physionet-data.mimic_core.patients` pat
                    on ie.subject_id = pat.subject_id
                    left join surgflag sf
                    on adm.hadm_id = sf.hadm_id and sf.serviceOrder = 1
                    """
        df = pd.read_gbq(
            query,
            #  credentials=credentials,
            project_id="mimic-iii-332416",
            use_bqstorage_api=True,
        )
        df.to_csv(os.path.join(base_path, "admission_type.csv"))

    if not os.path.exists(os.path.join(base_path, "icu_expire_flag.csv")) or overwrite:
        query = """SELECT stays.stay_id, 
                    IF(DATETIME_DIFF(
                        DATETIME(CONCAT(FORMAT_DATE('%Y-%m-%d', pat.dod), " 23:59:59")), 
                        stays.outtime, 
                        DAY)<=0, 1, 0) as icu_expire_flag
                    FROM `physionet-data.mimic_core.patients` pat
                    INNER JOIN `physionet-data.mimic_icu.icustays` stays
                    on pat.subject_id = stays.subject_id"""
        df = pd.read_gbq(
            query,
            #  credentials=credentials,
            project_id="mimic-iii-332416",
            use_bqstorage_api=True,
        )
        df.to_csv(os.path.join(base_path, "icu_expire_flag.csv"))


# To exclude parients with LTSV:
# SELECT distinct chartevents.stay_id
# FROM `physionet-data.mimic_icu.chartevents` as chartevents
# LEFT JOIN `physionet-data.mimic_icu.icustays` as stays
# ON chartevents.stay_id = stays.stay_id
# WHERE itemid IN (223758, 229784, 228687) and value <> "Full code"


def _load_data(base_path):
    """
    Loads and preprocesses patient data from multiple CSV files located in the specified base path.
    The function performs the following steps:
    - Reads the main patient data from 'mimic_iv.csv'.
    - Excludes patients listed in 'patients_ltsv.csv'.
    - Selects relevant columns for analysis.
    - Adds ICU expiration flag from 'icu_expire_flag.csv'.
    - Adds and one-hot encodes admission type from 'admission_type.csv'.
    - Adds Charlson comorbidity index from 'charlson_comorbidity.csv'.
    - Sorts the resulting DataFrame by 'stay_id' and 'hr'.
    Args:
        base_path (str): The directory path containing the required CSV files.
    Returns:
        pd.DataFrame: A preprocessed DataFrame containing patient data with additional features.
    """

    LOGGER.debug("Starting")
    data = pd.read_csv(os.path.join(base_path, "mimic_iv.csv"), index_col=0)
    LOGGER.debug("CSV read")
    exclude_patients = pd.read_csv(os.path.join(base_path, "patients_ltsv.csv"))
    LOGGER.debug("There are {:,.0f} patients".format(len(set(data["stay_id"]))))
    data = data[~data["stay_id"].isin(exclude_patients["stay_id"])].copy()
    LOGGER.debug("We will be using {:,.0f} patients".format(len(set(data["stay_id"]))))

    columns = [
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
        "hospital_expire_flag",
    ]
    data = data[columns].copy()
    LOGGER.debug("Dataframe parsed")

    icu_exp_flag = (
        pd.read_csv(os.path.join(base_path, "icu_expire_flag.csv"))
        .dropna()
        .set_index("stay_id")["icu_expire_flag"]
        .to_dict()
    )
    data.loc[:, "icu_expire_flag"] = data["stay_id"].map(icu_exp_flag)

    admission_type = (
        pd.read_csv(os.path.join(base_path, "admission_type.csv"))
        .dropna()
        .set_index("stay_id")["admissiontype"]
        .to_dict()
    )
    data.loc[:, "admission_type"] = data["stay_id"].map(admission_type)
    data = pd.get_dummies(data, columns=["admission_type"], dtype="int")

    comorbidities = (
        pd.read_csv(os.path.join(base_path, "charlson_comorbidity.csv"))
        .dropna()
        .set_index("stay_id")["charlson_comorbidity_index"]
        .to_dict()
    )

    data.loc[:, "charlson_comorbidity_index"] = data["stay_id"].map(comorbidities)
    LOGGER.debug("Comorbidities added")

    data.sort_values(["stay_id", "hr"], ascending=True, inplace=True)
    return data


def apply_nan_rules(df, rules):
    """
    Applies specified rules to fill NaN values in a DataFrame.
    Parameters
    ----------
    df : pandas.DataFrame
        The input DataFrame containing NaN values to be filled.
    rules : dict
        A dictionary mapping column names to fill strategies. Supported strategies:
            - "zero": Fill NaNs with 0.
            - "prev_value": Fill NaNs with the previous value within each 'stay_id' group (forward fill).
            - any other value: Fill NaNs with the specified value.
    Returns
    -------
    pandas.DataFrame
        The DataFrame with NaN values filled according to the provided rules.
    """

    fill_with_zeros = [k for k, v in rules.items() if v == "zero"]
    fill_prev_value = [k for k, v in rules.items() if v == "prev_value"]
    fill_with_value = [(k, v) for k, v in rules.items() if v not in ["zero", "prev_value"]]

    for c in tqdm.tqdm(fill_with_zeros):
        df.loc[:, c] = df[c].fillna(0)
    for c in tqdm.tqdm(fill_prev_value):
        g_ffill = df.groupby("stay_id")[[c]].fillna(method="ffill", inplace=False)
        df.loc[:, c] = g_ffill[c]
    for c, v in tqdm.tqdm(fill_with_value):
        df.loc[:, c] = df[c].fillna(v)
    return df


def correct_outliers(data):
    """
    Corrects outliers in the specified features of the input DataFrame by clipping their values to predefined bounds.
    Args:
        data (pandas.DataFrame): The input DataFrame containing features to correct.
    Returns:
        pandas.DataFrame: The DataFrame with outliers in specified features clipped to their respective bounds.
    Notes:
        The function relies on the global dictionary OUTLIER_CORRECTION, which should map feature names to (lower_bound, upper_bound) tuples.
    """

    for feature, bounds in OUTLIER_CORRECTION.items():
        lower_bound, upper_bound = bounds
        data[feature] = data[feature].clip(lower_bound, upper_bound)
    return data


def compute_sofa(data):
    """
    Computes the total SOFA (Sequential Organ Failure Assessment) score for each row in the given DataFrame.
    The SOFA score is calculated as the sum of the following sub-scores: respiration, central nervous system (cns),
    cardiovascular, liver, coagulation, and renal. If a sub-score is missing (NaN), it is treated as zero in the sum.
    If all sub-scores are missing for a row, the total SOFA score is set to None for that row.
    Parameters
    ----------
    data : pandas.DataFrame
        Input DataFrame containing the columns: 'respiration', 'cns', 'cardiovascular', 'liver', 'coagulation', 'renal'.
    Returns
    -------
    pandas.DataFrame
        The input DataFrame with an added 'sofa' column representing the total SOFA score for each row.
    """

    data.loc[:, "sofa"] = 0
    for sub_sofa in [
        "respiration",
        "cns",
        "cardiovascular",
        "liver",
        "coagulation",
        "renal",
    ]:
        data.loc[:, "sofa"] += data[sub_sofa].apply(lambda x: x if not np.isnan(x) else 0)

    data.loc[
        (data["respiration"].isna())
        & (data["cns"].isna())
        & (data["cardiovascular"].isna())
        & (data["liver"].isna())
        & (data["coagulation"].isna())
        & (data["renal"].isna()),
        "sofa",
    ] = None
    return data


def obtain_mimic_dataset(base_path, download_data=True, service_account_file="key.json"):
    """
    Obtains and processes the MIMIC-IV dataset.
    This function optionally downloads the MIMIC-IV dataset to the specified base path,
    loads the data, corrects outliers, applies rules for handling missing values, and
    removes unnecessary columns. The processed dataset is saved as a CSV file.
    Args:
        base_path (str): The directory path where the dataset will be stored and processed.
        download_data (bool, optional): If True, downloads the dataset. Defaults to True.
        service_account_file (str, optional): Path to the service account JSON file for authentication. Defaults to "key.json".
    Returns:
        None
    """

    if download_data:
        _download_data(base_path, service_account_file)
    data = _load_data(base_path)
    data = correct_outliers(data)
    data = apply_nan_rules(data, NAN_RULES)
    # data = _compute_sofa(data)
    if "Unnamed: 0_x" in data.columns:
        data.drop(columns=["Unnamed: 0_x"], inplace=True)
    data.to_csv(os.path.join(base_path, "mimic_iv_nan_corrected.csv"))
