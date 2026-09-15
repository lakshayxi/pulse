# Data policy

Pulse contains no real customer data and no personally identifiable information. All records are deterministic, behaviourally plausible synthetic observations generated from fake IDs with seed `1729`. Git excludes generated full datasets to keep the repository small; use `make data PROFILE=full` or `pulse-simulate --profile full` to recreate them. Hidden simulation mechanisms remain separate from observed outputs so downstream analyses cannot inspect them.

Each generated customer has a 120-day observation horizon, which supports evaluation of the D90 window (days 90-96 after signup). Transactions include both `settled` and `failed` attempts; financial activity metrics use settled meaningful transaction types only. Development mode has 20,000 customers, while CI uses 2,000 and full mode uses 100,000.
