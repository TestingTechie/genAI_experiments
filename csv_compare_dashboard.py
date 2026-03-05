import pandas as pd
import streamlit as st


st.set_page_config(page_title="CSV Comparison Dashboard", layout="wide")
st.title("CSV Comparison Dashboard for Data Testing")


def load_csv(path_or_buffer):
    return pd.read_csv(path_or_buffer)


def get_file_summary(df: pd.DataFrame, file_name: str):
    return {
        "file": file_name,
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_null_values": int(df.isnull().sum().sum()),
    }


def compare_structure(source_df: pd.DataFrame, target_df: pd.DataFrame):
    source_cols = set(source_df.columns)
    target_cols = set(target_df.columns)

    common_cols = sorted(source_cols & target_cols)
    source_only_cols = sorted(source_cols - target_cols)
    target_only_cols = sorted(target_cols - source_cols)

    null_summary = pd.DataFrame(
        {
            "source_nulls": source_df.isnull().sum(),
            "target_nulls": target_df.isnull().sum(),
        }
    ).fillna(0).astype(int)
    null_summary.index.name = "column"

    return common_cols, source_only_cols, target_only_cols, null_summary


def compare_rows(source_df: pd.DataFrame, target_df: pd.DataFrame, key_col: str):
    source_keys = source_df[key_col]
    target_keys = target_df[key_col]

    only_source = source_df[~source_keys.isin(target_keys)].copy()
    only_target = target_df[~target_keys.isin(source_keys)].copy()

    source_match = source_df[source_keys.isin(target_keys)].copy()
    target_match = target_df[target_keys.isin(source_keys)].copy()

    source_match = source_match.set_index(key_col)
    target_match = target_match.set_index(key_col)

    common_keys = source_match.index.intersection(target_match.index)
    source_match = source_match.loc[common_keys].sort_index()
    target_match = target_match.loc[common_keys].sort_index()

    compare_cols = sorted(set(source_match.columns).intersection(set(target_match.columns)))

    mismatch_rows = []

    for key in common_keys:
        s_row = source_match.loc[key]
        t_row = target_match.loc[key]

        # Handle duplicate keys by comparing row-by-row for each key occurrence.
        if isinstance(s_row, pd.DataFrame) or isinstance(t_row, pd.DataFrame):
            s_rows = s_row if isinstance(s_row, pd.DataFrame) else s_row.to_frame().T
            t_rows = t_row if isinstance(t_row, pd.DataFrame) else t_row.to_frame().T

            pair_count = min(len(s_rows), len(t_rows))
            for i in range(pair_count):
                s_series = s_rows.iloc[i]
                t_series = t_rows.iloc[i]
                for col in compare_cols:
                    s_val = s_series[col]
                    t_val = t_series[col]
                    equal = (pd.isna(s_val) and pd.isna(t_val)) or (s_val == t_val)
                    if not equal:
                        mismatch_rows.append(
                            {
                                key_col: key,
                                "row_instance": i,
                                "column": col,
                                "source_value": s_val,
                                "target_value": t_val,
                            }
                        )
        else:
            for col in compare_cols:
                s_val = s_row[col]
                t_val = t_row[col]
                equal = (pd.isna(s_val) and pd.isna(t_val)) or (s_val == t_val)
                if not equal:
                    mismatch_rows.append(
                        {
                            key_col: key,
                            "row_instance": 0,
                            "column": col,
                            "source_value": s_val,
                            "target_value": t_val,
                        }
                    )

    mismatch_df = pd.DataFrame(mismatch_rows)

    summary = {
        "matching_key_count": int(len(common_keys)),
        "rows_only_in_source": int(len(only_source)),
        "rows_only_in_target": int(len(only_target)),
        "mismatch_count": int(len(mismatch_df)),
    }

    return only_source, only_target, mismatch_df, summary


st.sidebar.header("Input Files")
default_paths_enabled = st.sidebar.checkbox("Use local files source.csv and target.csv", value=True)

source_input = "source.csv"
target_input = "target.csv"

if not default_paths_enabled:
    source_input = st.sidebar.file_uploader("Upload source CSV", type=["csv"], key="src")
    target_input = st.sidebar.file_uploader("Upload target CSV", type=["csv"], key="tgt")

if source_input is None or target_input is None:
    st.info("Provide both source and target files to start comparison.")
    st.stop()

try:
    source_df = load_csv(source_input)
    target_df = load_csv(target_input)
except Exception as exc:
    st.error(f"Failed to read CSV files: {exc}")
    st.stop()

if source_df.empty and target_df.empty:
    st.warning("Both files are empty.")
    st.stop()

common_cols, source_only_cols, target_only_cols, null_summary = compare_structure(source_df, target_df)

st.header("1) File Summary")
left, right = st.columns(2)
with left:
    st.subheader("Source")
    st.json(get_file_summary(source_df, "source"))
with right:
    st.subheader("Target")
    st.json(get_file_summary(target_df, "target"))

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

st.header("2) Row Comparison")
possible_keys = [col for col in common_cols if source_df[col].is_unique and target_df[col].is_unique]

default_key = possible_keys[0] if possible_keys else (common_cols[0] if common_cols else None)

if default_key is None:
    st.error("No common columns found. Cannot perform row-level comparison.")
    st.stop()

key_col = st.selectbox("Select key column", options=common_cols, index=common_cols.index(default_key))

only_source, only_target, mismatch_df, row_summary = compare_rows(source_df, target_df, key_col)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Matching Keys", row_summary["matching_key_count"])
m2.metric("Rows only in Source", row_summary["rows_only_in_source"])
m3.metric("Rows only in Target", row_summary["rows_only_in_target"])
m4.metric("Mismatched Values", row_summary["mismatch_count"])

st.header("3) Mismatch Analysis")

if mismatch_df.empty:
    st.success("No mismatched values found for matching keys.")
else:
    mismatch_by_column = (
        mismatch_df.groupby("column", dropna=False)
        .size()
        .reset_index(name="mismatch_count")
        .sort_values("mismatch_count", ascending=False)
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
        data=filtered.to_csv(index=False),
        file_name="mismatch_report.csv",
        mime="text/csv",
    )
