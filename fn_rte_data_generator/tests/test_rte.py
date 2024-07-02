import dataclasses

from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Tuple
from unittest import mock

import pandas as pd

from dateutil.parser import parser

from fn_rte_data_generator.rte import calculate_rte_actual, calculate_rte_blocks, calculate_rte_time, divide_rte_blocks


def test_calculate_rte_time():
    # not overlapping
    rte_time_blocks = [
        {
            "type": "charging",
            "start": parser().parse("2023-12-13 18:20:00"),
            "end": parser().parse("2023-12-13 18:30:00"),
            "first_drop": parser().parse("2023-12-13 18:25:00"),
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 18:30:00"),
            "end": parser().parse("2023-12-13 18:50:00"),
            "first_drop": parser().parse("2023-12-13 18:35:00"),
        },
    ]
    assert calculate_rte_time(rte_time_blocks) == 0.5

    # overlapping
    rte_time_blocks = [
        {
            "type": "charging",
            "start": parser().parse("2023-12-13 18:00:00"),
            "end": parser().parse("2023-12-13 18:30:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 18:10:00"),
            "end": parser().parse("2023-12-13 19:00:00"),
            "first_drop": None,
        },
    ]
    assert calculate_rte_time(rte_time_blocks) == 1.0

    # overlapping with not overlapping additional block
    rte_time_blocks = [
        {
            "type": "charging",
            "start": parser().parse("2023-12-13 18:00:00"),
            "end": parser().parse("2023-12-13 18:30:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 18:10:00"),
            "end": parser().parse("2023-12-13 19:00:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 19:10:00"),
            "end": parser().parse("2023-12-13 19:40:00"),
            "first_drop": None,
        },
    ]
    assert calculate_rte_time(rte_time_blocks) == 1.5

    # one fully overlapping with overlapping additional blocks
    rte_time_blocks = [
        {
            "type": "charging",
            "start": parser().parse("2023-12-13 18:00:00"),
            "end": parser().parse("2023-12-13 19:30:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 18:10:00"),
            "end": parser().parse("2023-12-13 19:20:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 19:40:00"),
            "end": parser().parse("2023-12-13 20:10:00"),
            "first_drop": None,
        },
        {
            "type": "discharging",
            "start": parser().parse("2023-12-13 20:00:00"),
            "end": parser().parse("2023-12-13 20:10:00"),
            "first_drop": None,
        },
    ]
    assert calculate_rte_time(rte_time_blocks) == 2


@dataclasses.dataclass
class Block:
    start: pd.Timestamp
    time_in_minutes: int
    points_count: int
    total_mwh: int
    type: str
    gap: Optional[int] = None


def generate_dataframes(fake_blocks) -> Tuple[List[pd.DataFrame], pd.DataFrame]:
    data_per_timestamps = defaultdict(lambda: dict(**{"charging": 0, "discharging": 0}))
    for fake_block in fake_blocks:
        gap = round(fake_block.time_in_minutes / fake_block.points_count) if not fake_block.gap else fake_block.gap
        timestamps = [
            pd.Timestamp(dt)
            for dt in pd.date_range(
                start=fake_block.start, periods=fake_block.points_count, freq=f"{gap}min"  # set up equal gaps
            )
        ]
        average_value = fake_block.total_mwh / fake_block.points_count  # average value per point
        fake_data_points = [average_value for _ in range(fake_block.points_count)]  # create fake data points

        for timestamp, value in zip(timestamps, fake_data_points):
            data_per_timestamps[timestamp][fake_block.type] = value

    # Hardcoded MWH delivered data
    mwh_charged = []
    mwh_delivered = []
    for values in data_per_timestamps.values():
        mwh_charged.append(values["charging"])
        mwh_delivered.append(values["discharging"])

    # Create the DataFrame
    df_charged = pd.DataFrame({"Timestamp": data_per_timestamps.keys(), "MWH_Charged": mwh_charged})
    df_delivered = pd.DataFrame({"Timestamp": data_per_timestamps.keys(), "MWH_Delivered": mwh_delivered})

    df_charged.set_index("Timestamp", inplace=True)

    df_delivered.set_index("Timestamp", inplace=True)

    return df_charged, df_delivered


def create_dataframes_mock(delivered_dfs):
    mocked = mock.MagicMock()

    def returns_logic(start, end, external_id):
        if (
            external_id
            == "njv:opcda://localhost/ABB.AC800MC_OpcDaServer.3:s=Applications.App_1.gvNDA01_BU001_XQ01.Value"
        ):
            return delivered_dfs.pop(0)

    mocked.time_series.data.retrieve_dataframe.side_effect = returns_logic
    return mocked


@mock.patch("src.jobs.rte.collect_charging_dataframe")
def test_calculate_rte_blocks__one_day_fallback(mock_collect_charging_dataframe):
    # remember that 60min block will be split like list with 0 index value:
    # 00:20, 00:20 + 15min, 00:20 + 30min, 00:20 + 45min
    # it is important for overlapping blocks etc
    fake_blocks = [
        Block(pd.Timestamp("2023-12-13 00:20:00"), 60, 4, 400, "discharging"),
        Block(pd.Timestamp("2023-12-13 01:20:00"), 60, 4, 0, "paused"),
        Block(pd.Timestamp("2023-12-13 02:20:00"), 60, 4, 1200, "charging"),
        Block(pd.Timestamp("2023-12-13 03:20:00"), 60, 4, 1200, "discharging"),
        Block(pd.Timestamp("2023-12-13 4:20:00"), 45, 3, 0, "paused"),
        Block(pd.Timestamp("2023-12-13 5:05:00"), 60, 4, 400, "charging"),
    ]

    day_before_blocks = [
        Block(pd.Timestamp("2023-12-12 08:20:00"), 60, 4, 1200, "charging"),
        Block(pd.Timestamp("2023-12-12 09:20:00"), 60, 4, 1200, "discharging"),
        Block(pd.Timestamp("2023-12-12 10:20:00"), 45, 3, 0, "paused"),
        Block(pd.Timestamp("2023-12-12 23:00:00"), 60, 5, 400, "charging", 15),
    ]

    df_charged, df_delivered = generate_dataframes(fake_blocks)
    df_charged_day_before, df_delivered_day_before = generate_dataframes(day_before_blocks)
    final_charged_1, final_delivered_1 = generate_dataframes([day_before_blocks[-1], fake_blocks[0]])
    final_charged_2, final_delivered_2 = generate_dataframes(fake_blocks[2:4])

    charged_blocks = [df_charged, df_charged_day_before]
    mock_collect_charging_dataframe.side_effect = lambda client, start, end: charged_blocks.pop(0)
    dataframes_mock = create_dataframes_mock([df_delivered, df_delivered_day_before])

    # Call the function
    blocks, _ = calculate_rte_blocks(
        initial_start=datetime(9999, 12, 13),  # not important - mocked response to cognite
        initial_end=datetime(9999, 12, 14),  # not important - mocked response to cognite
        # magic mock has tu fake usage of cognite_client by function cognite_client.time_series.data.retrieve_dataframe
        cognite_client=dataframes_mock,
    )
    total_hours = calculate_rte_time(blocks)
    assert total_hours == 5.0
    assert all([not block["simultaneous"] for block in blocks])

    final_blocks = [final_charged_1, final_charged_2]
    mock_collect_charging_dataframe.side_effect = lambda client, start, end: final_blocks.pop(0)
    assert (
        round(
            calculate_rte_actual(
                cognite_client=create_dataframes_mock([final_delivered_1, final_delivered_2]), rte_blocks=blocks
            ),
            2,
        )
        == 99.98
    )  # due to AUX consumption not 100%


@mock.patch("src.jobs.rte.collect_charging_dataframe")
def test_calculate_rte_blocks__small_gaps_on_discharge(mock_collect_charging_dataframe):
    # remember that 60min block will be split like list with 0 index value:
    # 00:20, 00:20 + 15min, 00:20 + 30min, 00:20 + 45min
    # it is important for overlapping blocks etc
    fake_blocks = [
        Block(pd.Timestamp("2023-12-13 01:20:00"), 60, 4, 0, "paused"),
        # first rte block
        Block(pd.Timestamp("2023-12-13 02:20:00"), 60, 4, 1200, "charging"),
        Block(pd.Timestamp("2023-12-13 03:20:00"), 60, 4, 600, "discharging", 20),
        Block(pd.Timestamp("2023-12-13 4:20:00"), 15, 3, 0, "paused"),
        Block(pd.Timestamp("2023-12-13 04:30:00"), 5, 6, 300, "discharging"),  # 6 to have 0 and 5th point
        Block(pd.Timestamp("2023-12-13 4:35:00"), 30, 3, 0, "paused", 10),  # to test boundary conditions
        Block(pd.Timestamp("2023-12-13 05:05:00"), 25, 5, 300, "discharging", 5),
        # end
        Block(pd.Timestamp("2023-12-13 5:20:00"), 60, 12, 0, "paused", 5),
        # ignored
        Block(pd.Timestamp("2023-12-13 7:15:00"), 60, 4, 400, "charging"),
    ]
    final_dfs = [*fake_blocks[:-2]]

    df_charged, df_delivered = generate_dataframes(fake_blocks)
    final_df_charged, final_df_delivered = generate_dataframes(final_dfs)

    mock_collect_charging_dataframe.return_value = df_charged
    dataframes_mock = create_dataframes_mock([df_delivered])

    # Call the function
    blocks, _ = calculate_rte_blocks(
        initial_start=datetime(9999, 12, 13),  # not important - mocked response to cognite
        initial_end=datetime(9999, 12, 14),  # not important - mocked response to cognite
        # magic mock has tu fake usage of cognite_client by function cognite_client.time_series.data.retrieve_dataframe
        cognite_client=dataframes_mock,
    )
    total_hours = round(calculate_rte_time(blocks), 2)
    assert all([not block["simultaneous"] for block in blocks])
    assert total_hours == 3.67
    final_blocks = [final_df_charged]
    mock_collect_charging_dataframe.side_effect = lambda client, start, end: final_blocks.pop(0)
    assert (
        round(calculate_rte_actual(cognite_client=create_dataframes_mock([final_df_delivered]), rte_blocks=blocks), 2)
        == 99.98
    )  # due to AUX consumption not 100%


@mock.patch("src.jobs.rte.collect_charging_dataframe")
def test_calculate_rte_blocks__simultaneous_with_cut(mock_collect_charging_dataframe):
    # remember that 60min block will be split like list with 0 index value:
    # 00:20, 00:20 + 15min, 00:20 + 30min, 00:20 + 45min
    # it is important for overlapping blocks etc
    fake_blocks = [
        Block(pd.Timestamp("2023-12-13 01:20:00"), 60, 4, 0, "paused"),
        # first rte block
        Block(pd.Timestamp("2023-12-13 02:20:00"), 120, 7, 2800, "charging", 20),  # this will be split in two
        Block(pd.Timestamp("2023-12-13 02:20:00"), 60, 4, 1400, "discharging", 20),
        # cut for simultaneous and  start for linear
        Block(pd.Timestamp("2023-12-13 4:20:00"), 15, 3, 0, "paused"),
        Block(pd.Timestamp("2023-12-13 04:30:00"), 60, 4, 1400, "discharging", 20),
        # end
    ]
    final_dfs = [
        Block(pd.Timestamp("2023-12-13 02:20:00"), 60, 4, 1400, "charging", 20),  # this will be split in two
        Block(pd.Timestamp("2023-12-13 02:20:00"), 60, 4, 1400, "discharging", 20),
        Block(pd.Timestamp("2023-12-13 03:20:00"), 60, 4, 1400, "charging", 20),
        Block(pd.Timestamp("2023-12-13 4:20:00"), 15, 3, 0, "paused"),
        Block(pd.Timestamp("2023-12-13 04:30:00"), 60, 4, 1400, "discharging", 20),
    ]

    df_charged, df_delivered = generate_dataframes(fake_blocks)

    dataframes_mock = create_dataframes_mock([df_delivered])
    mock_collect_charging_dataframe.return_value = df_charged
    # Call the function
    blocks, _ = calculate_rte_blocks(
        initial_start=datetime(9999, 12, 13),  # not important - mocked response to cognite
        initial_end=datetime(9999, 12, 14),  # not important - mocked response to cognite
        # magic mock has tu fake usage of cognite_client by function cognite_client.time_series.data.retrieve_dataframe
        cognite_client=dataframes_mock,
    )
    linear_blocks, simultaneous_blocks = divide_rte_blocks(blocks)
    assert len(linear_blocks) == 2 and len(simultaneous_blocks) == 2
    assert simultaneous_blocks[0]["simultaneous"] and not linear_blocks[0]["simultaneous"]
    linear_total_hours = round(calculate_rte_time(linear_blocks), 2)
    simultaneous_total_hours = round(calculate_rte_time(simultaneous_blocks), 2)
    assert linear_total_hours == 1.75 and simultaneous_total_hours == 1.33
    final_charged_1, final_delivered_1 = generate_dataframes(final_dfs[:2])
    final_charged_2, final_delivered_2 = generate_dataframes(final_dfs[2:])

    final_blocks = [final_charged_1, final_charged_2]
    mock_collect_charging_dataframe.side_effect = lambda client, start, end: final_blocks.pop(0)
    assert (
        round(
            calculate_rte_actual(
                cognite_client=create_dataframes_mock([final_delivered_1, final_delivered_2]), rte_blocks=blocks
            ),
            2,
        )
        == 99.99
    )  # due to AUX consumption not 100%
