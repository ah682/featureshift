"""Existing test catches the lost feature. Reviewed benchmark fixture."""


def transform(df):
    return df.loc[:, df.dtypes == "object"]


def existing_test(df):
    assert "label" in transform(df).columns
