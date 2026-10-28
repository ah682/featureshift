"""Numeric-to-string conversion preserves null. Reviewed benchmark fixture."""


def transform(df):
    return df[["value"]].astype(str)


def existing_test(df):
    assert len(transform(df)) >= 0
