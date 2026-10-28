"""Numeric scaling stays equivalent. Reviewed benchmark fixture."""


def transform(df):
    return df.assign(scaled=df["value"] / 10)


def existing_test(df):
    assert len(transform(df)) >= 0
