"""A training feature selector that assumes inferred strings have object dtype."""


def transform(df):
    return df.loc[:, df.dtypes == "object"]


def existing_test(df):
    # The supplied test checks rows but misses loss of feature columns.
    assert len(transform(df)) == len(df)

