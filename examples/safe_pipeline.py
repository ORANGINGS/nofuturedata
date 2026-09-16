"""Causal trailing example used by the README."""


def make_feature(df):
    return df["close"].shift(1).rolling(20).mean()

