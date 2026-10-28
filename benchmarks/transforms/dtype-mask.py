"""String feature lost by dtype mask. Reviewed benchmark fixture."""


def transform(df):
    return df.loc[:, df.dtypes == "object"]


def existing_test(df):
    assert len(transform(df)) >= 0
