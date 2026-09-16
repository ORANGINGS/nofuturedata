"""Intentionally unsafe example used by the README."""


def make_feature(df):
    # The feature at t receives the value from t+1.
    return df["close"].shift(-1)

