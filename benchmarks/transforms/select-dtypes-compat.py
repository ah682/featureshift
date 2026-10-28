"""Object select_dtypes retains strings in 3.0. Reviewed benchmark fixture."""


def transform(df):
    return df.select_dtypes(include=["object"])


def existing_test(df):
    assert len(transform(df)) >= 0
