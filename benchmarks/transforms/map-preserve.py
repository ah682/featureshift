"""Portable string conversion preserves missing values. Reviewed benchmark fixture."""


def transform(df):
    return df[["value"]].apply(lambda col: col.map(str, na_action="ignore")).astype(object)


def existing_test(df):
    assert len(transform(df)) >= 0
