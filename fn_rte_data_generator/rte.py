import logging

from collections import defaultdict
from datetime import timedelta

import pytz



TARGET_RTE_PERCENTAGE = 0.90
ESTIMATED_AUX_ENERGY_CONSUMPTION = 0.058
MAX_IN_PAST_SEARCH_DAYS = 3


# local logger
_logger = logging.getLogger(__name__)


def collect_charging_dataframe(cognite_client, start, end):
    time_series = [
        "njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNQS10_EB001_UH002_XQ05.Value",
        "njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNQS10_EB001_UH002_XQ06.Value",
        "njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNQS10_EB001_UH003_XQ05.Value",
        "njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNQS10_EB001_UH003_XQ06.Value",
    ]
    all_timeseries_df = cognite_client.time_series.data.retrieve_dataframe(
        start=start, end=end, external_id=time_series
    )

    # sum all df values from each timeserie to one aggregated/summed value in dataframe and return the dataframe (timestamp, summed value)
    return all_timeseries_df.sum(axis=1).to_frame()


def calculate_rte_actual(cognite_client, rte_blocks, aux_energy_consumption=ESTIMATED_AUX_ENERGY_CONSUMPTION):
    mwh_charged = 0
    mwh_delivered = 0

    hours = calculate_rte_time(rte_blocks)

    if hours == 0:
        return -1  # no blocks found, -1 as indicator that there is no data

    for block in rte_blocks:
        start = pytz.utc.localize(block["start"])
        end = pytz.utc.localize(block["end"])
        if block["type"] == "charging":
            charging_df = collect_charging_dataframe(cognite_client, start, end)
            mwh_charged += charging_df.sum().values[0]
        elif block["type"] == "discharging":
            discharge_df = cognite_client.time_series.data.retrieve_dataframe(
                # start=start + timedelta(hours=1), end=end + timedelta(hours=1),
                start=start,
                end=end,
                external_id="njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNDA01_BU001_XQ01.Value",
            )
            mwh_delivered += discharge_df.sum().values[0]

    return mwh_delivered / (mwh_charged + (aux_energy_consumption * hours)) * 100


def clean_block(block_type):
    return {"type": block_type, "start": None, "first_drop": None, "end": None, "simultaneous": False}


def calculate_rte_blocks(initial_start, initial_end, cognite_client, handle_start=True):
    """
    Calculates RTE time blocks for the given time range.
    """
    discharging_df = cognite_client.time_series.data.retrieve_dataframe(
        start=initial_start,
        end=initial_end,
        external_id="njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNDA01_BU001_XQ01.Value",
    )

    charging_df = collect_charging_dataframe(cognite_client, initial_start, initial_end)

    timeseries = {"NDA01_BU001_XQ01": discharging_df, "HeaterTotalPower": charging_df}

    # generate dictionary with values merged by timestamp - to mitigate problems with not existing matching data points
    timestamp_values = defaultdict(lambda: dict(**{key: None for key in timeseries.keys()}))
    for time_serie, cognite_df in timeseries.items():
        cognite_df.reset_index()
        for timestamp, value_serie in cognite_df.iterrows():
            timestamp_values[timestamp][time_serie] = value_serie.values[0]

    rte_blocks = []
    rte_block_charging = clean_block("charging")
    rte_block_discharging = clean_block("discharging")

    unclosed_rte_block_charging = None

    # RTE blocks finishes at moment when discharge power is less than 10 MWH for 30 minutes,
    # except if it is simultaneously discharging and then finishing with charging
    # in this case rte block finishes immediately after discharging stops (x<10) and
    # charging after this moment is new rte block
    minimal_stopping_duration = timedelta(minutes=30)
    # threshold for MWH to consider block as started/ended
    mwh_threshold = 10

    first_charging_drop_dt = None
    first_discharging_drop_dt = None
    timestamp_dt = None
    for timestamp, values in timestamp_values.items():
        # convert pandas timestamp to datetime
        timestamp_dt = timestamp.to_pydatetime()

        # missing value has to stay NONE if data is missing to not close blocks by mistake and to reduce calculation
        charging_value = values.get("HeaterTotalPower")
        discharging_value = values.get("NDA01_BU001_XQ01")

        # marking blocks that are running in simultaneously charging and discharging
        simultaneous_charging = bool(
            charging_value is not None
            and discharging_value is not None
            and charging_value > mwh_threshold
            and discharging_value > mwh_threshold
        )
        if simultaneous_charging:
            rte_block_charging["simultaneous"] = True
            rte_block_discharging["simultaneous"] = True

        # Check is it start of the block if not started already
        # charging
        if charging_value is not None and charging_value > mwh_threshold:
            if rte_block_charging["start"] is None:
                rte_block_charging["start"] = timestamp_dt
                first_charging_drop_dt = None
            # reset the first drop timestamp if we started again before setting charging end
            elif not rte_block_charging["end"] and first_charging_drop_dt:
                first_charging_drop_dt = None

        # discharging
        if discharging_value is not None and discharging_value > mwh_threshold:
            if rte_block_discharging["start"] is None:
                rte_block_discharging["start"] = timestamp_dt
                first_discharging_drop_dt = None
            elif not rte_block_discharging["end"] and first_discharging_drop_dt:
                # reset the first drop timestamp if we started again before setting discharging end
                first_discharging_drop_dt = None

        # Check is it end of the block if started already
        # charging
        if charging_value is not None and charging_value < mwh_threshold and rte_block_charging["start"]:
            if not first_charging_drop_dt:
                first_charging_drop_dt = timestamp_dt  # marking moment of turning off the block
            else:
                if timestamp_dt - first_charging_drop_dt >= minimal_stopping_duration:
                    rte_block_charging["end"] = first_charging_drop_dt
                    rte_block_charging["first_drop"] = first_charging_drop_dt
                    rte_blocks.append(rte_block_charging)
                    rte_block_charging = clean_block("charging")

        # discharging
        if discharging_value is not None and discharging_value < mwh_threshold and rte_block_discharging["start"]:
            if not first_discharging_drop_dt:
                first_discharging_drop_dt = timestamp_dt  # marking moment of turning off the block
                # Special case for simultaneous charging and discharging
                # if charging continues after discharging stops then we need to close discharging block wihout
                # additional 30 min and start new charging block
                # todo: implement: if trip happens and it is not longer then 30 min dont create clean cut with new
                #  charging block - just close discharging block - to find out about 30 min  trip we would eed to look
                #  into the future
                if rte_block_discharging["simultaneous"] and first_charging_drop_dt is None:
                    # charging
                    rte_block_charging["end"] = first_discharging_drop_dt
                    rte_blocks.append(rte_block_charging)
                    rte_block_charging = clean_block("charging")
                    rte_block_charging["start"] = first_discharging_drop_dt
                    # discharging
                    rte_block_discharging["end"] = first_discharging_drop_dt
                    rte_blocks.append(rte_block_discharging)
                    rte_block_discharging = clean_block("discharging")

            else:
                if (
                    rte_block_discharging["end"] is None
                    and timestamp_dt - first_discharging_drop_dt > minimal_stopping_duration
                ):
                    rte_block_discharging["end"] = first_discharging_drop_dt + timedelta(minutes=30)
                    rte_block_discharging["first_drop"] = first_discharging_drop_dt
                    rte_blocks.append(rte_block_discharging)
                    rte_block_discharging = clean_block("discharging")

    # last blocks handling
    # the unfinished blocks are not needed for today if they did not close before time ends.
    # they will be ignored for today and they will be calculated in next day when discharge of this block will finish
    if rte_block_charging["start"]:
        rte_block_charging["end"] = timestamp_dt
        rte_block_charging["first_drop"] = first_charging_drop_dt
        unclosed_rte_block_charging = rte_block_charging
    elif rte_blocks and rte_blocks[-1]["type"] == "charging":
        unclosed_rte_block_charging = None
        # information needed if we are looking yesterday fo find rte block starting point for today
    if rte_block_discharging["start"]:
        rte_block_discharging["end"] = timestamp_dt
        rte_block_discharging["first_drop"] = first_discharging_drop_dt
        rte_blocks.append(rte_block_discharging)

    # handling for first blocks
    # check if first block is a discharging block - if yes then we need to find starting charging block in past days
    if handle_start and rte_blocks and rte_blocks[0]["type"] == "discharging":
        # TODO: check for charging continuation from previous days hours - not just for charging block
        for block in rte_blocks.copy():
            if block["type"] == "charging":
                break
            previous_day_unclosed_charging_block = None
            days_before = 1
            while previous_day_unclosed_charging_block is None and days_before <= MAX_IN_PAST_SEARCH_DAYS:
                # TODO: previous block might be simultaneously charging and discharging so this one calculated
                #  differently! We need to define how to do it - should be added to RTE day before or
                #  here with special calculation?
                _, previous_day_unclosed_charging_block = calculate_rte_blocks(
                    initial_start - timedelta(days=days_before),
                    initial_end - timedelta(days=days_before),
                    cognite_client,
                    handle_start=False,  # now we only search for unclosed charging block - stop recursion
                )
                if previous_day_unclosed_charging_block:
                    # if there is unclosed charging block from previous day then we need to add it to the list
                    rte_blocks.insert(0, previous_day_unclosed_charging_block)
                days_before += 1

            if not previous_day_unclosed_charging_block:
                # todo: THIS should not be added to RTE calculations as 100 or infinit value - because
                #  probably it is malformed data
                #  - we should log this information and make investigation task or something to confirm what happened
                # if there is no unclosed charging block from previous day then we need to remove discharging block
                # because we have no information about starting charging block
                _logger.error(
                    f"No unclosed charging block found for discharging block"
                    f" {initial_start - timedelta(days=days_before)}"
                )
                popped = rte_blocks.pop(0)

    return rte_blocks, unclosed_rte_block_charging


def divide_rte_blocks(rte_blocks):
    """
    Divides RTE blocks into linear and simultaneous blocks.
    """
    linear_blocks = []
    simultaneous_blocks = []
    for block in rte_blocks:
        if block["simultaneous"]:
            simultaneous_blocks.append(block)
        else:
            linear_blocks.append(block)
    return linear_blocks, simultaneous_blocks


def calculate_rte_time(rte_time_blocks):
    """
    Calculates operational time for RTE blocks. It returns the total time in hours.
    Operational time is since start of first block to end of last block reducing time in between non overlapping blocks
    """
    if rte_time_blocks is None or len(rte_time_blocks) == 0:
        return 0
    # Sort intervals by start time
    rte_time_blocks.sort(key=lambda x: x["start"])

    interval_start = None
    interval_end = None
    total_time = 0
    for block in rte_time_blocks:
        start = block["start"]
        end = block["end"]

        if interval_start is None:
            interval_start = start
            interval_end = end
        elif start <= interval_end:
            interval_end = max(interval_end, end)
        else:
            total_time += (interval_end - interval_start).total_seconds()
            interval_start = start
            interval_end = end
    # add last interval
    total_time += (interval_end - interval_start).total_seconds()

    return total_time / 3600
