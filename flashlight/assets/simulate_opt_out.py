from pathlib import Path

import dagster as dg
from dagster import io_manager, AssetOut, String, Field, Int, AssetExecutionContext
from sqlalchemy.testing.suite.test_reflection import metadata

from flashlight.resources import domain_partitions


# @dg.multi_asset(
#     required_resource_keys={"browser_manager", "llm"},
#     partitions_def=domain_partitions,
#     outs={
#         "opt_out_url": AssetOut(
#             dagster_type=str,
#             group_Name="opt_out",
#             io_manager_key="io_manager",
#             description="Opt Out URL",
#             metadata={"ext": ".pkl"}
#         ),
#         "opt_out_trace": AssetOut(
#             dagster_type=Path,
#             group_name="traces",
#             io_manager_key="io_manager",
#             description="Playwright trace archive for opt-out navigation",
#             metadata={"ext": ".zip"},
#         ),
#     },
#     config_schema={
#         "url": Field(String, is_required=False, description="Starting website URL"),
#         "load_timeout_ms": Field(
#             Int, default_value=60_000, description="Page load timeout in milliseconds"
#         ),
#         "operation_delay_ms": Field(
#             Int, default_value=2_000, description="Page operation delay in milliseconds"
#         ),
#         "scroll_delay_ms": Field(
#             Int,
#             default_value=1000,
#             description="Page scroll delay " "in milliseconds for infinite scroll",
#         ),
#     },
# )
# async def opt_out(context: AssetExecutionContext):
