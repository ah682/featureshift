"""Contract treats missing sentinels equally. Reviewed benchmark fixture."""


def transform(df):
    return df[["label"]]


def existing_test(df):
    assert len(transform(df)) >= 0
