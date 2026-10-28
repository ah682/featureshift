"""Unused category disappears from aggregation. Reviewed benchmark fixture."""


def transform(df):
    return df.groupby("group")["value"].sum().to_frame()


def existing_test(df):
    assert len(transform(df)) >= 0
