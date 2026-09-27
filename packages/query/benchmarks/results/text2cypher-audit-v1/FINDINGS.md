# Superseded raw-text audit

This initial pass discovered that the 2025 training corpus stores most clause
separators as literal escaped newlines. Exact raw-string overlap was therefore
misleading, and lexical feature counts on that representation are not suitable
for coverage comparisons. Keep this report as the diagnostic record; use the
explicitly normalized [v2 audit](../text2cypher-audit-v2/REPORT.json) for workload
selection. Neither pass executed queries or read test splits.
