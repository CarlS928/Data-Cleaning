# Data Model Relationships

Each relationship is many-to-one, written as fact table column → dimension table column.

## fact_fees
- fact_fees.client_id → dim_client.client_id
- fact_fees.advisor_id → dim_advisor.advisor_id
- fact_fees.fee_date → dim_date.date

## fact_portfolio_snapshot
- fact_portfolio_snapshot.client_id → dim_client.client_id
- fact_portfolio_snapshot.advisor_id → dim_advisor.advisor_id
- fact_portfolio_snapshot.benchmark_id → dim_benchmark.benchmark_id
- fact_portfolio_snapshot.snapshot_date → dim_date.date

## fact_transactions
- fact_transactions.client_id → dim_client.client_id
- fact_transactions.advisor_id → dim_advisor.advisor_id
- fact_transactions.security_id → dim_security.security_id
- fact_transactions.txn_date → dim_date.date

## Dimension to dimension (snowflake links)
- dim_client.advisor_id → dim_advisor.advisor_id
- dim_security.benchmark_id → dim_benchmark.benchmark_id

## Notes for cleaning
- **Dates:** The fact tables store real dates, not `date_id`, so they join to `dim_date.date`. Convert both sides to the same date type before joining.
- **Decimal IDs:** `benchmark_id` in the snapshot table and `security_id` in the transactions table have values like `1.0` and `45.0`. Change them to whole numbers so they match the dimension keys.
- **Blank security IDs:** Some transactions have no `security_id`. These look like cash movements such as Deposit, so they won't link to `dim_security`. That's expected.
- **Duplicate advisor path:** `advisor_id` is in every fact table and also in `dim_client`. In Power BI, use only one active path to `dim_advisor`, either through the fact table or through the client, to avoid ambiguous relationships.
