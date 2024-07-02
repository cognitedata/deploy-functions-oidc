from datetime import timedelta

import pandas as pd


def fetch_and_prepare_availability_ts_dps(start: pd.Timestamp, end: pd.Timestamp, client):
    """Fetches NQQ00_XB12 timeseries datapoints and cleans the data.

    By using include_outside_points we are sure that we always get at least
    start and end data points.

      ____                   X_____
         |                   |
         |                   |
         |                   |
         X___________________|
             ^         ^
             |         |
           start      end

    In this case, without using include_outside_points we would not get any
    data point. With it, we get two data points:

      2024-04-07    0.0 (start)
      ...               (no dps in between)
      2024-04-08    1.0 (end)

    This then when calculated, indicates that the heatcube was operating for
    the whole time.
    """

    availability_ts_dps_cdf = client.time_series.data.retrieve_arrays(
        end=end,
        start=start,
        limit=None,
        include_outside_points=True,
        external_id="njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNQQ00_XB12.Value",
    )

    availability_ts_dps = pd.Series(availability_ts_dps_cdf.value, index=availability_ts_dps_cdf.timestamp)

    if len(availability_ts_dps) == 1:
        # If there is no status change after the end date, then duplicate existing but with end timestamp
        availability_ts_dps[end] = availability_ts_dps.iloc[0]
    else:
        # Set timestamps of outside data points to start and end of the time range
        availability_ts_dps.index = [start] + list(availability_ts_dps.index[1:-1]) + [end]

    set_end_datapoint_value(availability_ts_dps)
    availability_ts_dps = remove_consecutive_duplicates(availability_ts_dps)

    return availability_ts_dps


def set_end_datapoint_value(dps):
    """Set end dp value opposite to previous for delta time calculations

        _____   X   ... (it doesn't
            |   |   ...  matter what
            |   |   ...  is after
            X___|   ...  end datapoint )
           16   20
               end

    When we calculate time duration in particular state, we use the next
    datapoint indicating that the state changed. For example, when first is 0
    then we check how much time passed until the status changed to 1. This time
    is considered operating (status changed 0 -> 1).

    Thus, the last datapoint must be opposite to the previous, to properly
    calculate time elapsed. If it will be the same, e.g. 0 -> 0, then the
    calculations would be wrong. They would see it as heatcube was unavailable,
    because at the end it changed to working. Which is not what we want.

    Normally, we remove those consecutive duplicates, but it can't be done for
    the last data point, as it would change the time range, that's why this
    function is needed.
    """

    dps.iloc[-1] = 1 if dps.iloc[-2] == 0 else 0


def remove_consecutive_duplicates(dps):
    """Removes consecutive duplicated datapoints.

                (this)
               X___X____
          |    |       |
          |    |       |
          |    |       |
     ...  X____|       X___X
          16  18  19  20  22

    In the above graph, we see that at 19 there is additional consecutive
    datapoint that needs to be removed to make the time delta calculations
    possible.

    This function accomplishes this by selecting rows where the value in the
    current row is not equal to the value in the previous row, thereby
    filtering out (skipping) consecutive duplicate datapoints.
    """

    return dps.loc[dps.shift() != dps]


def calculate_uptime_kpi(start, end, client):
    """Calculates availability time and divides it over selected time range.

    Value 1 means there is an error or fault.
    Value 0 means no error, therefore it is okay and available.

    1         on     off    on    off    on     off    on     off
         ___      X_______      X______       X______       X_____  ....
           |      |      |      |     |       |     |       |
           |      |      |      |     |       |     |       |
           |      |      |      |     |       |     |       |
    0 ...  X______|      X______|     X_______|     X_______|
              ^                                        ^
              |                                        |
            start                                     end

    durations_between_each_dp is the time how long it lasted between each datapoint

        2024-04-15 11:47:37.342        ....
        2024-04-15 11:47:59.382        22.040  <- time elapse from last data point
        2024-04-15 11:48:10.314        10.932
        2024-04-15 11:49:22.588        ...

    durations_when_operating are only times when the heatcube was operating,
    i.e. times when the datapoint was 1, which means it broke at that time,
    which means it was working fine before it broke.

    This two are then summed up, divided and made as percentage value.
    """

    dps = fetch_and_prepare_availability_ts_dps(start, end, client)
    durations_between_each_dp = dps.index.to_series().diff().dt.total_seconds().fillna(0)
    durations_when_operating = durations_between_each_dp[dps == 1]
    return (durations_when_operating.sum() / durations_between_each_dp.sum()) * 100


def insert_uptime_kpi(today, cognite_client):
    """Calculates Uptime KPI for the day before yesterday and inserts it to CDF."""

    uptime = calculate_uptime_kpi(today - timedelta(days=2), today - timedelta(days=1), cognite_client)
    cognite_client.time_series.data.insert([(today - timedelta(days=2), uptime)], external_id="HEATCUBE_UPTIME")
