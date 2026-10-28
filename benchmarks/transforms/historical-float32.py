"""Historical float32 string formatting. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.Series([0.1], dtype="float32", name="feature").astype("string").to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
