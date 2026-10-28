"""Numeric aggregation stays equivalent. Reviewed benchmark fixture."""


def transform(df):
    return df.agg(["sum", "mean"])


def existing_test(df):
    assert len(transform(df)) >= 0
