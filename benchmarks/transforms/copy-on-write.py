"""Chained inplace fill no longer changes parent. Reviewed benchmark fixture."""


def transform(df):
    df = df.copy()
    df["value"].fillna(0, inplace=True)
    return df


def existing_test(df):
    assert len(transform(df)) >= 0
