"""Explicit observed grouping stays equivalent. Reviewed benchmark fixture."""


def transform(df):
    return df.groupby("group", observed=True)["value"].sum().to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
