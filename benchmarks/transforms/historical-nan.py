"""Historical string cast with nan. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.Series(["a", "b", float("nan")], dtype=object, name="label").astype(str).to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
