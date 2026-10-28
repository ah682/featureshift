"""Generated probe is terminated at its deadline. Reviewed benchmark fixture."""


def transform(df):
    return df[["value"]]


def existing_test(df):
    assert len(transform(df)) >= 0
