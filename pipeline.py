import json
import numpy as np
import os
import pandas as pd
import argparse

import sys
sys.path.append("C:/Users/cnava/Repos/PolaPy")

from polapy.competitiveness import navarrete_etal as competitiveness
from polapy.polarization import navarrete_etal as polarization

RATE_THRESHOLD = 0.03
VOTES_POLLING = 0
# Values accepted are {"rate": "rank"}
_labels = open("acronyms.json", encoding="utf-8")
_labels = json.load(_labels)

# SELET DATASET TO USE
parser = argparse.ArgumentParser()
# year, country, location_level, election_round, method
parser.add_argument("-y", "--year", default=2022, type=int, required=True)
parser.add_argument("-c", "--country", default="France",
                    type=str, required=True)
parser.add_argument("-l", "--level", default="department_id",
                    type=str, required=True)
parser.add_argument("-r", "--round", default="first_round",
                    type=str, required=False)
parser.add_argument("-m", "--method", default="nv",
                    type=str, required=False)

parser.add_argument("-n", "--ncandidates", default=2,
                    type=int, required=False)

parser.add_argument("-f", "--filter", default=1,
                    type=int, required=False)

args = parser.parse_args()

year = args.year
country = args.country
location_level = args.level
election_round = args.round
method = args.method
n_candidates = args.ncandidates
flag_candidates = args.filter

"""
Read CSV files generated by each pipeline to generate data to use in regressions
and descriptive analysis througout the manuscript.

Data origin, features and data cleaning procedure is explained in the supplementary material.
"""


def map_antagonism(
    year,
    country,
    location_level,
    election_round
):

    df = pd.read_csv(
        f"data_output/{country}/{year}_{election_round}.csv.gz",
        compression="gzip"
    )
    df.columns = [x.lower() for x in df.columns]
    df = df[~df["candidate"].isin(["OTHER"])]
    if flag_candidates == 1 and "flag_candidates" in list(df):
        df = df[df["flag_candidates"] == 1].copy()

    df_location = pd.read_csv(
        f"data_output/{country}/{year}_{election_round}_location.csv.gz", compression="gzip")

    data = pd.merge(df_location[[location_level, "polling_id"]].drop_duplicates(
    ), df.copy(), on="polling_id", how="right").copy()

    nv_output = []
    for idx, dt in data.groupby(location_level):
        geography = idx
        print(geography)

        dd = dt.groupby("candidate").agg({"value": "sum"})
        dd["share"] = dd.apply(lambda x: x/x.sum())
        values = list(dd.sort_values("share", ascending=False).head(
            n_candidates).index.unique())

        dt = dt[dt["candidate"].isin(values)].copy()

        ee = dt.groupby("polling_id").agg({"value": "sum"})
        values_polling = list(
            ee[ee["value"] > VOTES_POLLING].index.unique())
        dt = dt[dt["polling_id"].isin(values_polling)].copy()

        # Re-calculates voting percentage of candidates after removing outliers
        tt = dt.groupby(["polling_id", "candidate"]).agg({"value": "sum"})
        tt["share"] = tt.groupby(
            level=[0], group_keys=False).apply(lambda x: x/x.sum())
        tt = tt.reset_index()

        dt = tt[["polling_id", "candidate", "share", "value"]]

        dt = pd.merge(
            dt, df_location[["polling_id", location_level]]).drop_duplicates()
        dt = dt.reset_index(drop=True).dropna(subset=[location_level])

        v, df_between = competitiveness(dt, votes="value", unit="polling_id")
        df_between["type"] = "EC"

        v, df_within = polarization(dt, votes="value", unit="polling_id")
        df_within["type"] = "EP"

        df_polarization = pd.concat([df_between, df_within])

        df_polarization[location_level] = geography

        nv_output.append(df_polarization)

    df_dv = pd.concat(nv_output, ignore_index=True)

    path = f"data_curated/{country}/antagonism_{year}_{location_level}_{election_round}.csv.gz"
    df_dv.to_csv(path, compression="gzip", index=False)


map_antagonism(
    year,
    country,
    location_level,
    election_round
)