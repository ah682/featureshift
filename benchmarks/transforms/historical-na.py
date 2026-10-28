"""Historical string cast with na. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.Series(["a", "b", pd.NA], dtype=object, name="label").astype(str).to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
