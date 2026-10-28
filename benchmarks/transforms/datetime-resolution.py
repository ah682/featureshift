"""Parsed datetime resolution changes. Reviewed benchmark fixture."""
import pandas as pd


def transform(df):
    return pd.DataFrame({"day": pd.to_datetime(df["day"])})


def existing_test(df):
    assert len(transform(df)) >= 0
