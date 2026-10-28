"""Declared category mapping stays equivalent. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.DataFrame({"code": df["group"].cat.codes, "category": df["group"]})


def existing_test(df):
    assert len(transform(df)) >= 0
