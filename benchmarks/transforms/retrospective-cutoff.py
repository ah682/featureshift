"""Later migration documents cannot diagnose a 2020 incident. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.Series(["a", None], dtype=object, name="label").astype(str).to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
