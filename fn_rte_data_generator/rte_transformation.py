import datetime as dt
import logging

from rte import calculate_rte_actual, calculate_rte_blocks, divide_rte_blocks


# local logger
_logger = logging.getLogger(__name__)


def process_rte_kpis(today_date, cognite_client):
    """Calculates RTE KPIS for the day before yesterday and inserts it to CDF."""
    today = dt.datetime.combine(today_date, dt.time())  # starts and ends at 0:00
    initial_start = today - dt.timedelta(days=2)
    initial_end = today - dt.timedelta(days=1)

    discharge_df = cognite_client.time_series.data.retrieve_dataframe(
        start=initial_start,
        end=initial_end,
        external_id="njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNDA01_BU001_XQ01.Value",
    )

    # confirm are there RTE blocks for given day
    mwh_delivered = discharge_df.sum().values[0]
    if mwh_delivered == 0:
        _logger.warning(
            f"No data for mwh_discharged - no RTE block closed on given day {initial_start} - {initial_end}"
        )
        return

    # find RTE blocks for given time range
    rte_blocks, _ = calculate_rte_blocks(initial_start, initial_end, cognite_client=cognite_client)
    if not rte_blocks:
        _logger.warning(f"No RTE blocks found for {initial_start} - {initial_end}")
        return
    # divide simultaneous charging and discharging blocks from linear ones
    linear_blocks, simultaneous_blocks = divide_rte_blocks(rte_blocks)

    # Calculate RTE KPIs
    linear_rte_actual = calculate_rte_actual(cognite_client, linear_blocks)
    simultaneous_rte_actual = calculate_rte_actual(cognite_client, simultaneous_blocks)

    # insert RTEs into CDF
    if linear_blocks:
        cognite_client.time_series.data.insert(
            [(initial_start, round(linear_rte_actual, 2))], external_id="HEATCUBE_RTE_ACTUAL"
        )
    if simultaneous_blocks:
        cognite_client.time_series.data.insert(
            [(initial_start, round(simultaneous_rte_actual, 2))], external_id="HEATCUBE_RTE_ACTUAL_SIMULTANEOUS"
        )
