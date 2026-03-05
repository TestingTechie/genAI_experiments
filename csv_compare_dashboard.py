from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComparisonConfig:
    key_column: str
    trim_strings: bool
    case_sensitive: bool
    treat_empty_as_null: bool


st.set_page_config(page_title="CSV Comparison Dashboard", layout="wide")
st.title("CSV Comparison Dashboard for Data Testing")
st.caption("Production-minded prototype: schema checks, deterministic diffing, and exportable reports.")


@st.cache_data(show_spinner=False)
def load_csv_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Load CSV from bytes with guarded parsing and deterministic options."""
    try:
        return pd.read_csv(io.BytesIO(file_bytes))
    except Exception as exc:  # pragma: no cover - surface parser detail to UI
        raise ValueError(f"Could not parse '{filename}': {exc}") from exc


def load_input_to_df(input_obj: Any, fallback_name: str) -> pd.DataFrame:
    if isinstance(input_obj, str):
        with open(input_obj, "rb") as fp:
            raw = fp.read()
        return load_csv_bytes(raw, fallback_name)

    if input_obj is None:
        raise ValueError(f"Missing required input: {fallback_name}")

    raw = input_obj.getvalue()
    return load_csv_bytes(raw, input_obj.name)


def normalize_dataframe(df: pd.DataFrame, config: ComparisonConfig, preserve_columns: list[str]) -> pd.DataFrame:
    """Normalize text values for more reliable comparison while preserving requested columns."""
    result = df.copy()
    result = result[preserve_columns]

    object_cols = result.select_dtypes(include=["object", "string"]).columns

    for col in object_cols:
        series = result[col].astype("string")
        if config.trim_strings:
            series = series.str.strip()
        if not config.case_sensitive:
            series = series.str.lower()
        if config.treat_empty_as_null:
            series = series.replace("", pd.NA)
        result[col] = series

    return result


def get_file_summary(df: pd.DataFrame, file_name: str) -> dict[str, int | str]:
    return {
        "file": file_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_keys": 0,
        "total_null_values": int(df.isnull().sum().sum()),
    }


def compare_structure(source_df: pd.DataFrame, target_df: pd.DataFrame):
    source_cols = set(source_df.columns)
    target_cols = set(target_df.columns)
    common_cols = sorted(source_cols & target_cols)
    source_only_cols = sorted(source_cols - target_cols)
    target_only_cols = sorted(target_cols - source_cols)

    combined_cols = sorted(source_cols | target_cols)
    null_summary = pd.DataFrame(index=combined_cols)
    null_summary["source_nulls"] = source_df.reindex(columns=combined_cols).isnull().sum().astype(int)
    null_summary["target_nulls"] = target_df.reindex(columns=combined_cols).isnull().sum().astype(int)
    null_summary.index.name = "column"

    return common_cols, source_only_cols, target_only_cols, null_summary


def compare_rows(source_df: pd.DataFrame, target_df: pd.DataFrame, config: ComparisonConfig):
    key_col = config.key_column

    source_indexed = source_df.copy()
    target_indexed = target_df.copy()

    source_indexed["_row_num_src"] = source_indexed.groupby(key_col).cumcount()
    target_indexed["_row_num_tgt"] = target_indexed.groupby(key_col).cumcount()

    source_indexed["_pair_idx"] = source_indexed["_row_num_src"]
    target_indexed["_pair_idx"] = target_indexed["_row_num_tgt"]

    shared_columns = sorted(set(source_df.columns).intersection(target_df.columns) - {key_col})

    paired = source_indexed.merge(
        target_indexed,
        how="outer",
        on=[key_col, "_pair_idx"],
        indicator=True,
        suffixes=("_source", "_target"),
    )

    only_source = paired[paired["_merge"] == "left_only"].copy()
    only_target = paired[paired["_merge"] == "right_only"].copy()
    both = paired[paired["_merge"] == "both"].copy()

    mismatch_rows: list[dict[str, Any]] = []
    for col in shared_columns:
        source_col = f"{col}_source"
        target_col = f"{col}_target"
        mismatch_mask = ~(
            (both[source_col] == both[target_col])
            | (both[source_col].isna() & both[target_col].isna())
        )

        if mismatch_mask.any():
            records = both.loc[mismatch_mask, [key_col, "_pair_idx", source_col, target_col]].copy()
            records["column"] = col
            records = records.rename(
                columns={
                    "_pair_idx": "row_instance",
                    source_col: "source_value",
                    target_col: "target_value",
                }
            )
            mismatch_rows.extend(records.to_dict(orient="records"))

    mismatch_df = pd.DataFrame(mismatch_rows)

    source_only_view = source_df[source_df[key_col].isin(only_source[key_col])].copy()
    target_only_view = target_df[target_df[key_col].isin(only_target[key_col])].copy()

    summary = {
        "matching_key_count": int(both[key_col].nunique(dropna=True)),
        "rows_only_in_source": int(len(source_only_view)),
        "rows_only_in_target": int(len(target_only_view)),
        "mismatch_count": int(len(mismatch_df)),
    }

    return source_only_view, target_only_view, mismatch_df, summary


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


st.sidebar.header("Input Files")
use_default_paths = st.sidebar.checkbox("Use local files source.csv and target.csv", value=True)

source_input: Any = "source.csv"
target_input: Any = "target.csv"

if not use_default_paths:
    source_input = st.sidebar.file_uploader("Upload source CSV", type=["csv"], key="src")
    target_input = st.sidebar.file_uploader("Upload target CSV", type=["csv"], key="tgt")

if source_input is None or target_input is None:
    st.info("Provide both source and target files to start comparison.")
    st.stop()

try:
    source_raw = load_input_to_df(source_input, "source.csv")
    target_raw = load_input_to_df(target_input, "target.csv")
except Exception as exc:
    LOGGER.exception("Loading failed")
    st.error(str(exc))
    st.stop()

if source_raw.empty and target_raw.empty:
    st.warning("Both files are empty.")
    st.stop()

common_cols, source_only_cols, target_only_cols, null_summary = compare_structure(source_raw, target_raw)

st.header("1) File Summary")
left, right = st.columns(2)
source_summary = get_file_summary(source_raw, "source")
target_summary = get_file_summary(target_raw, "target")

with left:
    st.subheader("Source")
    st.json(source_summary)
with right:
    st.subheader("Target")
    st.json(target_summary)

c1, c2, c3 = st.columns(3)
c1.metric("Common Columns", len(common_cols))
c2.metric("Source-only Columns", len(source_only_cols))
c3.metric("Target-only Columns", len(target_only_cols))

with st.expander("Column Structure Details", expanded=True):
    st.write("**Columns in both files**")
    st.write(common_cols if common_cols else "None")
    st.write("**Columns only in source**")
    st.write(source_only_cols if source_only_cols else "None")
    st.write("**Columns only in target**")
    st.write(target_only_cols if target_only_cols else "None")
    st.write("**Null counts by column**")
    st.dataframe(null_summary, use_container_width=True)

if not common_cols:
    st.error("No common columns found. Cannot perform row-level comparison.")
    st.stop()

st.header("2) Row Comparison")
possible_unique_keys = [col for col in common_cols if source_raw[col].is_unique and target_raw[col].is_unique]
default_key = possible_unique_keys[0] if possible_unique_keys else common_cols[0]

key_col = st.selectbox("Select key column", options=common_cols, index=common_cols.index(default_key))

st.sidebar.header("Comparison Rules")
trim_strings = st.sidebar.checkbox("Trim leading/trailing whitespace", value=True)
case_sensitive = st.sidebar.checkbox("Case-sensitive compare", value=False)
treat_empty_as_null = st.sidebar.checkbox("Treat empty strings as null", value=True)

compare_columns = [key_col] + [col for col in common_cols if col != key_col]
config = ComparisonConfig(
    key_column=key_col,
    trim_strings=trim_strings,
    case_sensitive=case_sensitive,
    treat_empty_as_null=treat_empty_as_null,
)

source_df = normalize_dataframe(source_raw, config, compare_columns)
target_df = normalize_dataframe(target_raw, config, compare_columns)

source_summary["duplicate_keys"] = int(source_df[key_col].duplicated().sum())
target_summary["duplicate_keys"] = int(target_df[key_col].duplicated().sum())
if source_summary["duplicate_keys"] or target_summary["duplicate_keys"]:
    st.warning(
        "Duplicate key values found. Rows are paired by key + occurrence index to keep comparisons deterministic."
    )

only_source, only_target, mismatch_df, row_summary = compare_rows(source_df, target_df, config)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Matching Keys", row_summary["matching_key_count"])
m2.metric("Rows only in Source", row_summary["rows_only_in_source"])
m3.metric("Rows only in Target", row_summary["rows_only_in_target"])
m4.metric("Mismatched Values", row_summary["mismatch_count"])

st.header("3) Mismatch Analysis")
if mismatch_df.empty:
    st.success("No mismatched values found for matching key records.")
else:
    mismatch_by_column = (
        mismatch_df.groupby("column", dropna=False).size().reset_index(name="mismatch_count").sort_values(
            "mismatch_count", ascending=False
        )
    )
    st.subheader("Mismatch counts by column")
    st.dataframe(mismatch_by_column, use_container_width=True)

st.subheader("Rows only in source")
st.dataframe(only_source, use_container_width=True)
st.subheader("Rows only in target")
st.dataframe(only_target, use_container_width=True)

st.header("4) Filterable Mismatch Table")
if mismatch_df.empty:
    st.info("No mismatches to display.")
else:
    filter_columns = ["All"] + sorted(mismatch_df["column"].dropna().unique().tolist())
    selected_col = st.selectbox("Filter mismatches by column", options=filter_columns)
    filtered = mismatch_df if selected_col == "All" else mismatch_df[mismatch_df["column"] == selected_col]
    st.dataframe(filtered, use_container_width=True)

    st.download_button(
        "Download mismatch report as CSV",
        data=to_csv_bytes(filtered),
        file_name="mismatch_report.csv",
        mime="text/csv",
    )

st.header("5) Production Readiness Checklist")
st.markdown(
    """
- Add authentication (SSO/OAuth) and role-based access controls.
- Log user actions + comparison metadata to centralized logging.
- Persist reports to object storage and store metadata in a database.
- Containerize and deploy behind HTTPS with health checks and autoscaling.
- Add CI tests for parsing, comparison logic, and UI smoke checks.
"""
)
