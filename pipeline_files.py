import json
import numpy as np
import os
import pandas as pd

from comchoice.aggregate import borda, divisiveness, win_rate
from comchoice.preprocessing.to_pairwise import to_pairwise
from glob import glob
from scipy.stats import kurtosis, skew


RATE_THRESHOLD = 0.02
VOTES_POLLING = 100
# Values accepted are {"rate": "rank"}
_labels = open("acronyms.json", encoding="utf-8")
_labels = json.load(_labels)

"""
Read CSV files generated by each pipeline to generate data to use in regressions
and descriptive analysis througout the manuscript.

Data origin, features and data cleaning procedure is explained in the supplementary material.
"""

regression = False


def er_polarization(rates, weights, alpha=0.25, K=1000):
    xx = np.multiply.outer(weights ** (1 + alpha), weights)
    yy = np.absolute(np.subtract.outer(rates, rates))
    # avg = np.average(rates, weights=weights)

    return K * np.sum(xx * yy)


def calculate_divisiveness(
    year,
    country,
    location_level,
    method="std"
):
    # labels = _labels[f"{country}_{year}"]
    runoff_countries = ["France", "Chile", "Brazil", "Romania"]

    df = pd.read_csv(
        f"data_output/{country}/{year}_first_round.csv.gz",
        compression="gzip"
    )
    df.columns = [x.lower() for x in df.columns]

    dd = df.groupby("candidate").agg({"value": "sum"})
    dd["rate"] = dd.apply(lambda x: x/x.sum())
    values = list(dd[dd["rate"] > RATE_THRESHOLD].index.unique())

    if country in runoff_countries:
        df_runoff = pd.read_csv(
            f"data_output/{country}/{year}_runoff.csv.gz", compression="gzip")
        df_runoff.columns = [x.lower() for x in df_runoff.columns]

        df_runoff = df_runoff[df_runoff["candidate"].isin(values)]

    df_location = pd.read_csv(
        f"data_output/{country}/{year}_first_round_location.csv.gz", compression="gzip")

    df = df[df["candidate"].isin(values)].copy()

    ee = df.groupby("polling_id").agg({"value": "sum"})
    values_polling = list(ee[ee["value"] > VOTES_POLLING].index.unique())
    df = df[df["polling_id"].isin(values_polling)].copy()

    # Re-calculates voting percentage of candidates after removing outliers
    tt = df.groupby(["polling_id", "candidate"]).agg({"value": "sum"})
    tt["rate"] = tt.groupby(level=[0]).apply(lambda x: x/x.sum())
    tt = tt.reset_index()
    tt["rank"] = tt.groupby(["polling_id"])["value"].rank(
        "min", ascending=False).astype(int)
    df = tt[["polling_id", "candidate", "rate", "rank", "value"]]

    df1 = pd.merge(df, df_location[["polling_id", location_level]])

    df1 = df1.groupby([location_level, "candidate"]).agg({"value": "sum"})
    df1["rate"] = df1.groupby(level=[0]).apply(lambda x: x/x.sum())
    df1 = df1.reset_index()

    if country in runoff_countries:
        df2 = pd.merge(df_runoff, df_location[["polling_id", location_level]])

        df2 = df2.groupby([location_level, "candidate"]).agg({"value": "sum"})
        df2["rate"] = df2.groupby(level=[0]).apply(lambda x: x/x.sum())
        df2 = df2.reset_index()

        df_rounds = pd.merge(df1, df2, on=[location_level, "candidate"])
        df_rounds["diff"] = df_rounds["rate_y"] - df_rounds["rate_x"]

    path = f"data_output/{country}/{year}_pairwise.csv.gz"

    if not os.path.isfile(path):

        df_pwc = to_pairwise(
            df,
            alternative="candidate",
            verbose=True,
            voter="polling_id"
        )
        df_pwc.to_csv(path, compression="gzip", index=False)

    else:
        df_pwc = pd.read_csv(path, compression="gzip")

    data = pd.merge(df_location[[location_level, "polling_id"]].drop_duplicates(
    ), df.copy(), on="polling_id").copy()

    if method in ["std", "std_rank"]:
        _ = "rate" if method == "std" else "rank"
        # Uses Standard deviation of a feature to measure how divisive a location is.
        df_dv = data.groupby([location_level, "candidate"])\
            .agg({_: "std"})\
            .rename(columns={_: "value"}).reset_index()

    elif method == "divisiveness":
        output = []

        data = pd.merge(df_location[[location_level, "polling_id"]].drop_duplicates(
        ), df_pwc.copy(), on="polling_id").copy()
        for i, tmp in data.groupby(location_level):
            print(i)
            dv = divisiveness(
                tmp,
                method=win_rate,
                voter="polling_id",
                method_kws=dict(voter="polling_id")
            )
            dv[location_level] = i
            output.append(dv)

        df_dv = pd.concat(output, ignore_index=True)
        df_dv = df_dv.rename(columns={"alternative": "candidate"})

    elif method in ["kurtosis", "skew"]:

        output = []
        _ = skew if method == "skew" else kurtosis

        for i, tmp in data.groupby(location_level):
            for candidate, tmp_cand in tmp.groupby("candidate"):
                output.append({
                    "candidate": candidate,
                    "value": _(tmp_cand["rate"].dropna()),
                    location_level: i
                })

        df_dv = pd.DataFrame(output)

    elif method == "er":
        output = []
        alpha = 0.25
        df_tmp = pd.merge(
            data,
            data.groupby("polling_id").agg({"value": "sum"}).rename(
                columns={"value": "N"}).reset_index(),
            on="polling_id"
        )
        for idx, _data in df_tmp.groupby(["candidate", location_level]):
            candidate, geography = idx
            _data = _data.fillna(0)
            _data["weight"] = _data["N"] / _data["N"].sum()
            weights = _data["weight"].fillna(0).values
            rates = _data["rate"].fillna(0).values

            value = er_polarization(rates, weights, alpha=alpha, K=1000)

            output.append({
                "value": value,
                "candidate": candidate,
                location_level: geography
            })

        df_dv = pd.DataFrame(output)

    path = f"data_output/{country}/{year}_divisiveness_{location_level}_{method}.csv.gz"
    df_dv.to_csv(path, compression="gzip", index=False)

    location = "polling_id"

    def get_rate(df, location=["polling_id"], level=[0]):
        df_tmp = df.groupby(location + ["candidate"]).agg({"value": "sum"})
        df_tmp["rate"] = df_tmp.groupby(level=level).apply(lambda x: x/x.sum())
        df_tmp = df_tmp.reset_index()

        return df_tmp

    if regression:
        df = pd.merge(df, df_location, on="polling_id")

        df_a = get_rate(
            df, location=[location_level, "polling_id"], level=[0, 1])
        df_a = pd.merge(df_a, df_dv.rename(columns={"value": "divisiveness"}), on=[
                        location_level, "candidate"])

        if country in runoff_countries:
            df_b = get_rate(df_runoff)

        dd = df_a.pivot_table(
            index=["polling_id"],
            columns=["candidate"],
            values=["rate", "value", "divisiveness"]
        ).reset_index()

        cols = []
        for column in dd.columns:
            a, b = column
            new_column = None
            if not b:
                new_column = a
            else:
                new_column = f"{a}_{b}"  # labels

            cols.append(new_column)

        dd.columns = cols
        if country in runoff_countries:
            dd = pd.merge(dd, df_b, on="polling_id")
        encoding = "utf-8"
        if country == "Romania":
            encoding = "iso8859_16"
        dd.to_csv(
            f"data_regressions/{country}_{year}_polling_station_{method}.csv",
            encoding=encoding,
            index=False
        )


for year, country, location_level in [
    # (2009, "Romania", "county_name"),
    # (2017, "Chile", "province"),
    # (2021, "Chile", "province"),
    # (2017, "Chile", "commune"),
    # (2021, "Chile", "commune"),
    # (2002, "France", "department_id"),
    (2007, "France", "department_id"),
    (2012, "France", "department_id"),
    (2017, "France", "department_id"),
    (2022, "France", "department_id"),
    # (2018, "Brazil", "region_id")
    # (2022, "Italy", "province_id"),
    # (2021, "Germany", "constituency"),
    # (2019, "Spain", "province_id")
]:
    # "er" "divisiveness" "std", "std_rank", "skew", "kurtosis"
    for method in ["divisiveness"]:
        print(year, country, location_level, method)
        calculate_divisiveness(year, country, location_level, method)
