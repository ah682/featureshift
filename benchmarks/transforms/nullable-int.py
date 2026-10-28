"""Explicit nullable integer remains equivalent. Reviewed benchmark fixture."""


def transform(df):
    return df[["count"]].astype("Int64")


def existing_test(df):
    assert len(transform(df)) >= 0
